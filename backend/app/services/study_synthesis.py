"""Cross-study synthesis — a decision memo generated across several Studies.

Inputs are the studies' *final analyses* (the qualitative ProjectAnalysis
report and, when present, the mixed-methods StudyAnalysis report), never the
raw transcripts: the per-study syntheses are the audited, quote-traceable
layer, and this memo must stay attributable to them. Every claim in the memo
names the studies that support it, so a stakeholder can walk any statement
back to a study report and from there to a verbatim quote.
"""

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.interview import ProjectAnalysis
from app.models.study import Study, StudyAnalysis
from app.models.synthesis import CrossStudySynthesis
from app.services import ai_models
from app.services._clients import get_anthropic_client
from app.services.usage_logger import log_claude_usage

logger = logging.getLogger("auto_interview.study_synthesis")

MEMO_SYSTEM_PROMPT = (
    "You are a principal researcher writing a decision memo for executives. "
    "You synthesise across completed research studies. You never invent evidence: "
    "every claim must be grounded in the study reports provided, and every claim "
    "names the studies that support it. You surface disagreement between studies "
    "as prominently as agreement — a memo that hides conflicts is worse than no memo."
)

_MEMO_RULES_BLOCK = """<rules>
1. GROUNDING — every key finding must cite at least one study by its exact name in
   supporting_studies. Never cite a study for a claim its report does not contain.
2. CONFLICTS ARE FIRST-CLASS — when studies disagree (different populations, different
   answers, contradictory themes), record it in conflicts with both study names. Do not
   average disagreement away.
3. VERDICT IS A RECOMMENDATION, NOT A SUMMARY — one paragraph that takes a position on
   the decision question, states the strongest reason, and names the biggest caveat.
4. RECOMMENDATIONS ARE FALSIFIABLE — each one states what evidence would prove it wrong
   ("would be wrong if ...").
5. GAPS — list what the combined studies still cannot answer about the decision.
   An empty gaps list is almost always wrong.
6. STRENGTH CALIBRATION — a finding is "strong" only when supported by 2+ studies or by
   one study with high confidence AND no contradicting study. Single-study findings with
   medium/low confidence are "weak" or "moderate".
7. CONFIDENCE — calibrate the memo confidence to the weakest link: number of studies,
   their individual confidence levels, sample sizes, and how much they overlap in scope.
8. NO MARKETING LANGUAGE — no "exciting insights", no "deep dive". Plain, direct prose.
9. Quotes: you may carry over short verbatim participant quotes from the study reports
   as evidence strings, attributed as (Study name — participant). Never fabricate or
   edit quotes.
</rules>"""

_MEMO_SCHEMA_BLOCK = """<output_schema>
Return ONLY a JSON object with exactly this shape (no markdown fences, no commentary):
{
  "decision": "the decision question this memo informs, restated in one sentence",
  "verdict": "one-paragraph position on the decision: recommendation + strongest reason + biggest caveat",
  "summary": "2-4 sentence executive summary of what the combined studies show",
  "key_findings": [
    {
      "finding": "one concrete cross-study finding (<= 25 words)",
      "detail": "2-3 sentences of substance behind the finding",
      "supporting_studies": ["exact study name", "..."],
      "evidence": "the single most convincing piece of evidence, quoted or paraphrased from a study report, with attribution",
      "strength": "strong | moderate | weak"
    }
  ],
  "conflicts": [
    {
      "topic": "short label (<= 8 words)",
      "detail": "which studies disagree, how, and the most plausible explanation"
    }
  ],
  "gaps": ["what the combined studies still cannot answer"],
  "recommendations": ["decision-oriented next step. Include a falsifier ('would be wrong if ...')."],
  "confidence": "low | medium | high",
  "confidence_rationale": "1-2 sentences: number of studies, their individual confidence, scope overlap"
}
</output_schema>"""


def gather_study_evidence(study: Study, db: Session) -> dict | None:
    """Collect the latest ready analyses for one study.

    Returns None when the study has no ready analysis of either kind —
    callers treat that as "not eligible for synthesis".
    """
    qual = None
    for project in study.projects:
        candidate = (
            db.query(ProjectAnalysis)
            .filter(
                ProjectAnalysis.project_id == project.id,
                ProjectAnalysis.status == "ready",
            )
            .order_by(ProjectAnalysis.version.desc())
            .first()
        )
        if candidate and (qual is None or (candidate.generated_at or datetime.min) > (qual.generated_at or datetime.min)):
            qual = candidate

    mixed = (
        db.query(StudyAnalysis)
        .filter(StudyAnalysis.study_id == study.id, StudyAnalysis.status == "ready")
        .order_by(StudyAnalysis.version.desc())
        .first()
    )

    if qual is None and mixed is None:
        return None

    return {"study": study, "project_analysis": qual, "study_analysis": mixed}


def latest_evidence_at(study: Study, db: Session) -> datetime | None:
    """Most recent ``generated_at`` across the study's ready analyses.

    Drives memo staleness: a decision memo generated before this timestamp
    no longer reflects the study's current findings.
    """
    evidence = gather_study_evidence(study, db)
    if evidence is None:
        return None
    times = [
        a.generated_at
        for a in (evidence["project_analysis"], evidence["study_analysis"])
        if a is not None and a.generated_at is not None
    ]
    return max(times) if times else None


def _study_block(evidence: dict) -> str:
    """Serialise one study's evidence into a prompt block."""
    study: Study = evidence["study"]
    parts = [f'<study name="{study.name}">']

    project = study.projects[0] if study.projects else None
    if project is not None:
        meta = []
        if project.research_objective:
            meta.append(f"objective: {project.research_objective}")
        if project.decision_to_inform:
            meta.append(f"decision it informed: {project.decision_to_inform}")
        if meta:
            parts.append("<context>" + " | ".join(meta) + "</context>")

    qual: ProjectAnalysis | None = evidence["project_analysis"]
    if qual is not None and qual.report:
        parts.append(
            f'<interview_synthesis participants="{qual.participant_count}" '
            f'version="{qual.version}" label="{qual.version_label}">\n'
            f"{qual.report}\n</interview_synthesis>"
        )

    mixed: StudyAnalysis | None = evidence["study_analysis"]
    if mixed is not None and mixed.report:
        parts.append(f"<mixed_methods_report>\n{mixed.report}\n</mixed_methods_report>")

    parts.append("</study>")
    return "\n".join(parts)


def _call_claude(prompt: str, db: Session, company_id: str) -> str:
    """Isolated for tests — monkeypatch this to avoid a real API call."""
    client = get_anthropic_client()
    response = client.messages.create(
        model=ai_models.sonnet(),
        max_tokens=4096,
        # Same rationale as per-study analysis: judgment, not creativity.
        **ai_models.sampling_kwargs(ai_models.sonnet(), 0.3),
        system=MEMO_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    log_claude_usage(db, response, "cross_synthesis", company_id=company_id)
    return response.content[0].text.strip()


def run_cross_synthesis(synthesis_id: str, db: Session) -> None:
    """Generate the decision memo. Meant to run in a background thread."""
    synthesis = (
        db.query(CrossStudySynthesis)
        .filter(CrossStudySynthesis.id == synthesis_id)
        .first()
    )
    if synthesis is None:
        return

    try:
        study_ids = json.loads(synthesis.study_ids)
        studies = (
            db.query(Study)
            .filter(Study.id.in_(study_ids), Study.company_id == synthesis.company_id)
            .all()
        )
        evidences = []
        for study in studies:
            evidence = gather_study_evidence(study, db)
            if evidence is not None:
                evidences.append(evidence)
        if len(evidences) < 2:
            raise ValueError("Fewer than two studies with a ready analysis.")

        blocks = "\n\n".join(_study_block(e) for e in evidences)
        study_names = ", ".join(e["study"].name for e in evidences)

        lang_instruction = (
            "\n\nIMPORTANT — OUTPUT LANGUAGE: Write ALL text fields in French. "
            "Verbatim participant quotes carried over as evidence stay in their "
            "original language — never translate quotes."
        ) if synthesis.language == "fr" else ""

        decision_line = (
            f"The decision to inform: {synthesis.decision_question}\n"
            if synthesis.decision_question
            else "No explicit decision question was provided — infer the most useful "
            "decision framing from the studies' own objectives and state it in the "
            "decision field.\n"
        )

        prompt = (
            f"{_MEMO_RULES_BLOCK}\n\n"
            f"{_MEMO_SCHEMA_BLOCK}\n\n"
            f"<task>\nWrite the decision memo across the {len(evidences)} studies below "
            f"({study_names}). Apply the rules without exception. supporting_studies must "
            f"use the exact study names as given.{lang_instruction}\n{decision_line}</task>\n\n"
            f"{blocks}\n\n"
            f"Return the JSON object now."
        )

        raw = _call_claude(prompt, db, synthesis.company_id)
        if raw.startswith("```"):
            lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()
        json.loads(raw)  # validate

        synthesis.report = raw
        synthesis.status = "ready"
        synthesis.generated_at = datetime.utcnow()
        logger.info("Cross-study synthesis %s ready (%d studies)", synthesis_id, len(evidences))

    except Exception as e:
        synthesis.status = "failed"
        synthesis.error = str(e)
        logger.warning("Cross-study synthesis %s failed: %s", synthesis_id, e)

    db.commit()
