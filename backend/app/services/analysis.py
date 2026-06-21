"""AI-powered synthesis of all completed interview transcripts for a project."""

import json
from datetime import datetime

from app.services._clients import get_anthropic_client
from sqlalchemy.orm import Session

from app.config import settings
from app.models.company import Company
from app.models.interview import AnalysisThemeAnnotation, Participant, ProjectAnalysis
from app.models.memo import ProjectMemo
from app.models.project import Project
from app.services.business_context import full_context_block
from app.services.usage_logger import log_claude_usage
from app.services import ai_models

ANALYSIS_SYSTEM_PROMPT = """\
You are a sceptical senior qualitative researcher reviewing your own work for a hostile PM \
who has read every transcript and will catch any inflation. Your job is not to summarise \
the transcripts — it is to extract only what the evidence actually supports, name what it \
doesn't, and tell the team what to do next.

Stance:
- Treat small samples as small samples. 3-6 participants is anecdotal, not "validated".
- Every pattern claim needs at least 2 distinct participants. If only 1 person said it, \
it's a signal worth noting, not a theme.
- Name participants by identifier when reporting frequency. "Most" without naming is banned.
- Surface disconfirming evidence. If P3 contradicts the theme, say so in the same paragraph.
- Recommendations must be actionable AND falsifiable — describe what success looks like and \
what would prove the recommendation wrong.

Banned phrasing (REJECT before output):
- "users want a great experience", "drive engagement", "leverage", "seamless", "delight"
- Vague frequencies ("many users", "some participants") without naming who
- Themes built on a single quote
- Recommendations that read like motherhood statements ("improve onboarding")

Output: ONE valid JSON object. No markdown fences. No preamble. No trailing commentary."""


def _build_transcripts_block(participants: list[Participant]) -> tuple[str, dict[str, dict]]:
    """Build transcript block and a participant metadata map keyed by identifier.

    Returns: (transcript_text, participant_map)
    participant_map: {identifier → {display_name, profession, age_range, country}}
    """
    blocks = []
    participant_map: dict[str, dict] = {}

    for i, p in enumerate(participants, 1):
        identifier = f"P{i}"
        name = p.display_name or f"Participant {i}"
        attrs = []
        if getattr(p, "profession", None):
            attrs.append(f"profession: {p.profession}")
        if getattr(p, "age_range", None):
            attrs.append(f"age: {p.age_range}")
        if getattr(p, "country", None):
            attrs.append(f"country: {p.country}")
        # Surface the quality assessment so the synthesis prompt can flag
        # thin participants by name and downweight their evidence weight.
        q_label = getattr(p, "quality_label", None)
        q_score = getattr(p, "quality_score", None)
        if q_label:
            q_str = f"quality: {q_label}"
            if q_score is not None:
                q_str += f" ({q_score:.2f})"
            attrs.append(q_str)

        attr_str = f" ({', '.join(attrs)})" if attrs else ""
        header = f"--- [{identifier}] {name}{attr_str} ---"

        participant_map[identifier] = {
            "display_name": name,
            "profession": getattr(p, "profession", None),
            "age_range": getattr(p, "age_range", None),
            "country": getattr(p, "country", None),
        }

        turns = sorted(p.turns, key=lambda t: t.turn_index)
        lines = [header]
        for t in turns:
            lines.append(f"Q (turn {t.turn_index}): {t.question_text}")
            if t.response_transcript:
                lines.append(f"A: {t.response_transcript}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks), participant_map


# ───────────────────────────────────────────────────────────────────────────
# Static prompt blocks (declared once at module load so the prompt prefix
# stays byte-stable across calls — the Anthropic prompt cache rewards a
# longer stable prefix). Dynamic content (transcripts, objective, filters)
# is appended LAST in the user message.
# ───────────────────────────────────────────────────────────────────────────

_ANALYSIS_RULES_BLOCK = """\
<rules>
EVIDENCE CALIBRATION (tie confidence to N — do not exceed the ceiling):
- N=1-2 participants → confidence "low", label findings "anecdotal"
- N=3-5 → confidence "low" or "medium", label findings "directional"
- N=6-9 → confidence "medium", label findings "suggestive"
- N=10+ with thematic saturation → confidence "high"
Recommendations cannot promise certainty the evidence does not support.

THEME RULES:
- Each theme MUST cite ≥2 verbatim quotes from ≥2 DISTINCT participants. \
If only 1 participant supports it, do not call it a theme — drop it or move it \
to "tensions" as a single-voice signal.
- "frequency" is one of: "all" / "most" / "some" / "few". When using \
"most"/"some"/"few", name the supporting participants in the theme summary \
(e.g. "P1, P3, P5 describe …").
- Quote text must be a verbatim substring of a participant response. Do not \
paraphrase, do not stitch sentences together, do not fix grammar.
- Each quote MUST include the participant identifier (e.g. [P1]) from the \
transcript header. participant_identifier is the raw token like "P1" \
(no brackets); participant_display_name is the human name.

JTBD RULES:
- Strict format: "When I [situation], I want to [motivation], so I can [outcome]."
- The outcome must be the user's outcome, not the company's metric.

TENSION RULES:
- A tension is a forced choice or contradiction the participant lives with — \
not a feature gap. Frame as "X says/does this, BUT also Y" with both halves \
grounded in transcript evidence.

RECOMMENDATION RULES:
- Each recommendation must (a) point at a specific decision, (b) name the \
behaviour or theme it addresses, and (c) include a falsifier — what would \
prove it wrong (e.g. "If 3+ further interviews show users do X anyway, drop this").
- No motherhood statements. No "consider", "explore", "leverage".

DATA QUALITY:
- If a participant's transcript is thin (quality: low/fair, or many one-word \
answers), DO NOT use them as a primary source for a theme. You may still cite \
them, but flag the thinness.
- If the sample is too small or too thin to support themes, return fewer themes \
(or zero) and explain in confidence_rationale rather than padding.
</rules>"""

_ANALYSIS_SCHEMA_BLOCK = """\
<output_format>
Return ONE JSON object with this exact shape:
{
  "summary": "2-3 sentence executive summary. Lead with the most important finding. No marketing language.",
  "themes": [
    {
      "title": "concrete theme name (≤7 words)",
      "summary": "1-2 sentences. Name supporting participants by identifier (e.g. P1, P3).",
      "quotes": [
        {
          "text": "exact verbatim quote from transcript",
          "participant_identifier": "P1",
          "participant_display_name": "participant name",
          "turn_index": 3,
          "question_text": "the question that prompted this response"
        }
      ],
      "frequency": "all | most | some | few",
      "disconfirming_evidence": "Optional. If any participant contradicted or complicated this theme, name them and quote them briefly. Empty string if no contradiction was found."
    }
  ],
  "jobs_to_be_done": [
    {
      "job": "When I [situation], I want to [motivation], so I can [outcome].",
      "insight": "what this reveals about user motivation that wasn't obvious from the literal answer",
      "frequency": "all | most | some | few"
    }
  ],
  "tensions": [
    {
      "tension": "short label (≤6 words)",
      "detail": "Frame as a forced choice or contradiction grounded in transcript evidence. Name participants."
    }
  ],
  "recommendations": [
    "Specific decision-oriented recommendation. Include a falsifier ('would be wrong if …')."
  ],
  "confidence": "low | medium | high",
  "confidence_rationale": "1-2 sentences. State N, response depth, sample diversity, and any quality concerns.",
  "participant_count": <integer>
}
</output_format>

<examples>
ACCEPT (theme):
{
  "title": "Trust earned through unboxing, not advertising",
  "summary": "P1, P3, and P4 describe deciding to repurchase only after a tactile unboxing moment. P2 explicitly disagrees — she repurchased before any package arrived.",
  "frequency": "most",
  "disconfirming_evidence": "P2: 'I'd already ordered the second one before the first one even shipped.'"
}

REJECT (theme — single quote, vague frequency, no participant naming):
{
  "title": "Users want a delightful experience",
  "summary": "Many participants felt the product was great.",
  "frequency": "most",
  "quotes": [{"text": "It's nice."}]
}
Why rejected: marketing-speak title, single fuzzy quote with no attribution, no disconfirming evidence, "many" without naming.

ACCEPT (recommendation):
"Move the price-justification copy above the fold on the PDP — three of six participants (P1, P4, P6) bounced when they had to scroll to find it. Falsifier: a follow-up study where 2+ participants ignore the moved copy and still bounce."

REJECT (recommendation):
"Improve the onboarding experience to drive engagement."
Why rejected: motherhood statement, no decision, no falsifier, banned vocabulary.
</examples>"""


def _filter_participants(
    participants: list[Participant],
    filter_by: str | None,
    filter_values: list[str],
) -> list[Participant]:
    if not filter_by or not filter_values:
        return participants
    result = []
    for p in participants:
        val = getattr(p, filter_by, None)
        if val and val in filter_values:
            result.append(p)
    return result


def run_analysis(
    project_id: str,
    db: Session,
    filter_by: str | None = None,
    filter_values: list[str] | None = None,
) -> None:
    """Run full synthesis for completed interviews.

    Upserts a ProjectAnalysis row. Meant to be called in a background thread.
    """
    filter_values = filter_values or []

    project: Project | None = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return

    all_completed = [p for p in project.participants if p.status == "completed" and p.turns]
    completed = _filter_participants(all_completed, filter_by, filter_values)

    # Create a new versioned analysis row (keep last 3 per project)
    last = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id)
        .order_by(ProjectAnalysis.version.desc())
        .first()
    )
    next_version = (last.version + 1) if last else 1
    analysis = ProjectAnalysis(project_id=project_id, version=next_version)
    db.add(analysis)

    analysis.status = "generating"
    analysis.participant_count = len(completed)
    analysis.report = None
    analysis.error = None
    if filter_by and filter_values:
        analysis.filters = json.dumps({"filter_by": filter_by, "filter_values": filter_values})
    else:
        analysis.filters = None
    db.commit()

    # Prune: keep only the 5 most recent versions
    all_versions = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id)
        .order_by(ProjectAnalysis.version.desc())
        .all()
    )
    for old in all_versions[5:]:
        db.delete(old)
    db.commit()

    try:
        transcripts_block, participant_map = _build_transcripts_block(completed)
        # Load the owning company so we can prepend business context to the
        # Claude prompt. The analysis is infinitely more useful when the model
        # knows what the researcher actually sells and who they sell it to.
        company = db.query(Company).filter(Company.id == project.company_id).first()
        context_block = full_context_block(company, project)

        objective_block = (
            f"RESEARCH OBJECTIVE:\n{project.research_objective}\n\n"
            if project.research_objective
            else ""
        )

        filter_note = ""
        if filter_by and filter_values:
            filter_note = f"NOTE: This analysis covers only participants filtered by {filter_by} = {', '.join(filter_values)}.\n\n"

        lang = getattr(company, "preferred_language", None) or "en"
        lang_instruction = (
            f"\n\nIMPORTANT — OUTPUT LANGUAGE: Write ALL text fields (summary, theme titles, "
            f"theme summaries, JTBD jobs/insights, tension labels/details, recommendations, "
            f"confidence_rationale) in {'French' if lang == 'fr' else 'English'}. "
            f"Verbatim quotes must stay in the original transcript language — never translate quotes."
        ) if lang != "en" else ""

        # Static blocks first (rules + schema + examples) → cached prefix.
        # Dynamic blocks last (context, objective, filters, transcripts).
        prompt = (
            f"{_ANALYSIS_RULES_BLOCK}\n\n"
            f"{_ANALYSIS_SCHEMA_BLOCK}\n\n"
            f"<task>\nSynthesize the interviews below into a research report. "
            f"Apply the rules above without exception. Confidence MUST be calibrated to N "
            f"(N={len(completed)} here).{lang_instruction}\n</task>\n\n"
            f"{context_block}{objective_block}{filter_note}"
            f"<transcripts count=\"{len(completed)}\">\n{transcripts_block}\n</transcripts>\n\n"
            f"Return the JSON object now. participant_count must be {len(completed)}."
        )

        client = get_anthropic_client()
        response = client.messages.create(
            model=ai_models.sonnet(),
            max_tokens=4096,
            # 0.3: synthesis requires judgment but not creativity. Lower
            # temperature reduces hallucinated quotes and inflated frequency
            # claims — the dominant failure mode of analysis at small N.
            temperature=0.3,
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        log_claude_usage(db, response, "analysis", company_id=project.company_id, project_id=project_id)

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()

        # Validate JSON
        json.loads(raw)

        analysis.report = raw
        analysis.status = "ready"
        analysis.generated_at = datetime.utcnow()

    except Exception as e:
        analysis.status = "failed"
        analysis.error = str(e)

    db.commit()


def run_refined_analysis(project_id: str, new_analysis_id: str, parent_analysis_id: str, db: Session) -> None:
    """Run a researcher-guided refined synthesis, incorporating theme annotations and researcher context.

    Meant to be called in a background thread. Writes result to the new_analysis_id row.
    """
    project: Project | None = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return

    new_analysis = db.query(ProjectAnalysis).filter(ProjectAnalysis.id == new_analysis_id).first()
    if new_analysis is None:
        return

    parent_analysis = db.query(ProjectAnalysis).filter(ProjectAnalysis.id == parent_analysis_id).first()
    if parent_analysis is None:
        new_analysis.status = "failed"
        new_analysis.error = "Parent analysis not found"
        db.commit()
        return

    try:
        # Load annotations from the parent analysis
        annotations = (
            db.query(AnalysisThemeAnnotation)
            .filter(AnalysisThemeAnnotation.analysis_id == parent_analysis_id)
            .all()
        )

        confirmed = [a for a in annotations if a.status == "confirmed"]
        disputed = [a for a in annotations if a.status == "disputed"]
        needs_evidence = [a for a in annotations if a.status == "needs_evidence"]

        # Build annotation sections
        annotation_sections = []
        annotation_sections.append("RESEARCHER ANNOTATIONS FROM PREVIOUS ANALYSIS:")
        annotation_sections.append(
            "You are producing a refined synthesis. A domain expert has reviewed the previous analysis "
            "and provided the following signals. Incorporate them carefully."
        )
        annotation_sections.append("")

        if confirmed:
            annotation_sections.append("CONFIRMED THEMES (preserve and strengthen):")
            for a in confirmed:
                bullet = f"- {a.theme_title}"
                if a.researcher_note:
                    bullet += f": {a.researcher_note}"
                annotation_sections.append(bullet)
            annotation_sections.append("")

        if disputed:
            annotation_sections.append(
                "DISPUTED THEMES (re-examine — researcher believes these are mis-framed):"
            )
            for a in disputed:
                bullet = f"- {a.theme_title}"
                if a.researcher_note:
                    bullet += f": {a.researcher_note}"
                annotation_sections.append(bullet)
            annotation_sections.append(
                "Each disputed theme includes a researcher note explaining why. Reframe if you agree "
                "with their evidence, but if transcript data strongly supports the original framing, "
                'keep it and add a "researcher_note" field to that theme object explaining the disagreement.'
            )
            annotation_sections.append("")

        if needs_evidence:
            annotation_sections.append(
                "THEMES NEEDING MORE EVIDENCE (only include if 2+ distinct participant quotes support them):"
            )
            for a in needs_evidence:
                bullet = f"- {a.theme_title}"
                if a.researcher_note:
                    bullet += f": {a.researcher_note}"
                annotation_sections.append(bullet)
            annotation_sections.append("")

        researcher_context = parent_analysis.researcher_context or ""
        if researcher_context.strip():
            annotation_sections.append("RESEARCHER CONTEXT (implicit knowledge not visible in transcripts):")
            annotation_sections.append(researcher_context.strip())
            annotation_sections.append("")

        # Project memos — if the researcher has been taking notes while
        # reading transcripts, surface them so the refined run can weave
        # that knowledge into themes instead of ignoring it. We pull the
        # most recent 15 memos to stay under the token budget; older notes
        # are usually stale or already reflected in annotations.
        memos = (
            db.query(ProjectMemo)
            .filter(ProjectMemo.project_id == project_id)
            .order_by(ProjectMemo.updated_at.desc())
            .limit(15)
            .all()
        )
        if memos:
            annotation_sections.append(
                "RESEARCHER MEMOS (notes the researcher wrote while reading "
                "transcripts — treat as soft evidence, not hard facts):"
            )
            for memo in memos:
                # Normalise memo type → short label so Claude sees what kind
                # of note this is (general / theme-linked / tension-linked /
                # jtbd-linked).
                label_map = {
                    "general": "Note",
                    "theme_note": "Theme note",
                    "tension_note": "Tension note",
                    "jtbd_note": "JTBD note",
                }
                label = label_map.get(memo.type, "Note")
                linked = f" ({memo.linked_key})" if memo.linked_key else ""
                content = (memo.content or "").strip().replace("\n", " ")
                if content:
                    annotation_sections.append(f"- {label}{linked}: {content}")
            annotation_sections.append("")

        annotations_block = "\n".join(annotation_sections)

        # Load completed participants
        all_completed = [p for p in project.participants if p.status == "completed" and p.turns]

        # Business + study context — same grounding as the v1 run.
        company = db.query(Company).filter(Company.id == project.company_id).first()
        context_block = full_context_block(company, project)

        objective_block = (
            f"RESEARCH OBJECTIVE:\n{project.research_objective}\n\n"
            if project.research_objective
            else ""
        )

        transcripts_block, _ = _build_transcripts_block(all_completed)

        lang = getattr(company, "preferred_language", None) or "en"
        lang_instruction = (
            f"\n\nIMPORTANT — OUTPUT LANGUAGE: Write ALL text fields (summary, theme titles, "
            f"theme summaries, JTBD jobs/insights, tension labels/details, recommendations, "
            f"confidence_rationale) in {'French' if lang == 'fr' else 'English'}. "
            f"Verbatim quotes must stay in the original transcript language — never translate quotes."
        ) if lang != "en" else ""

        prompt = (
            f"{_ANALYSIS_RULES_BLOCK}\n\n"
            f"{_ANALYSIS_SCHEMA_BLOCK}\n\n"
            f"<task>\nThis is a REFINED synthesis (v2). A v1 was produced and the researcher "
            f"reviewed it. Their annotations and notes are below — treat them as expert "
            f"signals from someone who has read every transcript. Re-synthesize from the "
            f"transcripts, applying the annotations:\n"
            f"- CONFIRMED themes: keep, strengthen evidence, do not weaken.\n"
            f"- DISPUTED themes: re-examine. If you reframe, add a `researcher_note` field "
            f"to that theme object (1-2 sentences explaining what changed). If transcript "
            f"evidence still overwhelmingly supports the original framing, keep it AND add "
            f"`researcher_note` explaining the disagreement with the researcher.\n"
            f"- NEEDS-EVIDENCE themes: include ONLY if ≥2 quotes from ≥2 distinct participants "
            f"now support them. Otherwise drop.\n"
            f"In the `summary` field, add one sentence noting this is a researcher-refined synthesis.\n"
            f"All other rules (calibration to N={len(all_completed)}, ≥2 distinct participants per theme, "
            f"named participants in frequency, disconfirming evidence, falsifiable recommendations) "
            f"still apply without exception.{lang_instruction}\n</task>\n\n"
            f"{context_block}{objective_block}{annotations_block}\n"
            f"<transcripts count=\"{len(all_completed)}\">\n{transcripts_block}\n</transcripts>\n\n"
            f"Return the JSON object now. participant_count must be {len(all_completed)}."
        )

        client = get_anthropic_client()
        response = client.messages.create(
            model=ai_models.sonnet(),
            max_tokens=4096,
            # 0.3: synthesis requires judgment but not creativity. Lower
            # temperature reduces hallucinated quotes and inflated frequency
            # claims — the dominant failure mode of analysis at small N.
            temperature=0.3,
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        log_claude_usage(db, response, "analysis", company_id=project.company_id, project_id=project_id)

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()

        json.loads(raw)

        new_analysis.report = raw
        new_analysis.status = "ready"
        new_analysis.participant_count = len(all_completed)
        new_analysis.generated_at = datetime.utcnow()

    except Exception as e:
        new_analysis.status = "failed"
        new_analysis.error = str(e)

    db.commit()
