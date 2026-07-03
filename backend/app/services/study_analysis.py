"""Quantified Themes generation — the moat (Sprint 11).

This is the service that makes Qualipulse "consultant in a box."
Claude takes:
  - Survey aggregates (every question's analytics)
  - Segment discoveries (the over-indexing patterns from Sprint 10)
  - Up to N interview transcripts from sibling Projects
and composes a report where every theme is structured as:

  {
    survey_signal:      "40% selected mobile setup",
    interview_evidence: "7 of 12 mentioned it — 'I gave up trying...'",
    recommendation:     "Add reassurance copy before activation",
    confidence:         "supported"
  }

Why this shape: per the consultant audit, a finding without all four
parts is just a chart. With all four, it's a decision-ready insight.

Constraints baked in (NOT optional):
  - Claude sees ONLY survey aggregates + transcripts. NOT row-level
    open-text answers (roadmap risk #4 — cost balloon).
  - Confidence pills follow the same n thresholds the rest of the codebase
    enforces. Claude is INSTRUCTED to use them; backend validation rejects
    "strong" claims when the supporting n < 100.
  - Anchor quotes MUST be verbatim substrings of an actual InterviewTurn
    transcript on a sibling Project. Anything that fails the verification
    is dropped post-generation (or the theme is downgraded to a survey-
    only one).
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.interview import InterviewTurn, Participant
from app.models.project import Project
from app.models.study import Study, StudyAnalysis
from app.models.survey import Survey
from app.services.segment_discoveries import compute_discoveries
from app.services.stats import DEFAULT_MIN_N
from app.services.survey_analytics import build_dashboard
from app.services import ai_models

logger = logging.getLogger(__name__)

# Token budget — keep inputs reasonable to control cost (roadmap risk #4).
MAX_INTERVIEW_TURNS_PER_PARTICIPANT = 6
MAX_PARTICIPANTS_TO_INCLUDE = 12
MAX_TRANSCRIPT_CHARS = 32_000

SYSTEM_PROMPT = """\
You are a senior mixed-methods researcher writing a Quantified Themes
report. Your job is to find the 3–6 most actionable themes that combine
survey signal with interview evidence and recommend a specific next step.

Iron rules:

1. Every theme MUST cite a survey signal (a number with n), an interview
   evidence quote (verbatim, never paraphrased), and a recommendation.
2. Confidence pills follow strict thresholds:
     - "directional": any segment with n<30, OR an effect size below
       supported thresholds, OR a theme resting only on interview evidence.
     - "supported": n≥30 AND the difference is meaningful (≥0.5σ for
       numeric, or ≥1.5× lift / ≤0.65× under-index for categorical).
     - "strong": n≥100 AND p<0.01-equivalent effect (≥0.8σ or chi-square≥6.63).
3. Anchor quotes MUST be verbatim from the transcripts you are given.
   NEVER fabricate, paraphrase, or compose a quote. If you don't have a
   suitable verbatim, the theme is survey-only — leave interview_evidence null.
4. Themes that contradict the data MUST NOT be reported.
5. Recommendations must be specific and actionable. "Improve onboarding"
   is bad. "Move the team-size selector before the payment step" is good.
6. Return STRICT JSON. No prose around it. No markdown code fences.

You are writing for product managers and founders who will use this to
make decisions. They will see your output rendered as cards. Be concise.
"""

SCHEMA_BLOCK = """\
Return a single JSON object matching this exact schema:

{
  "executive_summary": "<one paragraph summarising the most important finding>",
  "themes": [
    {
      "title": "<imperative or thesis-form sentence>",
      "survey_signal": {
        "summary": "<e.g. '40% selected mobile setup'>",
        "n": <integer>,
        "percentage": <float between 0 and 100, or null when n is below 30>,
        "segment_label": "<e.g. 'Designers' or null when workspace-wide>",
        "segment_over_index": <float lift ratio or null>
      },
      "interview_evidence": {
        "x_of_y": "<e.g. '7 of 12'>",
        "interview_count": <integer>,
        "anchor_quote": "<verbatim from a transcript>",
        "segments_mentioned": ["<segment label>", ...]
      },
      "recommendation": {
        "kind": "product" | "marketing" | "next_research",
        "action": "<specific next move>",
        "rationale": "<one line of why>"
      },
      "confidence": "directional" | "supported" | "strong"
    }
  ],
  "methodology_note": "<one paragraph on how the data was sourced + caveats>"
}

If you have no interview transcripts, omit interview_evidence (set to null)
and downgrade affected themes to "directional" if necessary. Still emit
themes — survey-only insights are still insights.
"""


def trigger_study_analysis(db: Session, study: Study) -> StudyAnalysis:
    """Create the analysis row, then run generation inline.

    Inline rather than background-thread for v1 — kept simple. Project
    analyses already run a background thread (see services/analysis.py)
    so the pattern is available when we need it; v1 just blocks the
    request. Average runtime is ~10-20s with the token budget we use.
    """

    # Compute next version number.
    last = (
        db.query(StudyAnalysis)
        .filter(StudyAnalysis.study_id == study.id)
        .order_by(StudyAnalysis.version.desc())
        .first()
    )
    next_version = (last.version + 1) if last else 1

    analysis = StudyAnalysis(
        study_id=study.id,
        version=next_version,
        status="generating",
    )
    db.add(analysis)
    db.flush()

    try:
        report_json, inputs_snapshot = _generate_report(db, study)
        # Post-generation: verify every interview_evidence anchor quote is
        # actually a verbatim substring of a real InterviewTurn transcript
        # on a sibling Project. Anything that can't be verified is
        # stripped — preserves the methodology contract even if Claude
        # drifts on the system prompt's "never fabricate quotes" rule.
        report_json = _verify_anchor_quotes(db, study, report_json)
        analysis.report = report_json
        analysis.inputs_snapshot = inputs_snapshot
        analysis.status = "ready"
        analysis.generated_at = datetime.now(timezone.utc)
    except Exception as exc:  # noqa: BLE001 — surface the cause to the UI
        logger.exception("Study analysis generation failed for study %s", study.id)
        analysis.status = "failed"
        analysis.error = str(exc)[:500]

    db.commit()
    db.refresh(analysis)
    return analysis


def _generate_report(db: Session, study: Study) -> tuple[str, str]:
    """Returns (report_json, inputs_snapshot_json).

    Snapshot is what Claude saw — useful for "where did this theme come
    from?" debugging later.
    """

    surveys = (
        db.query(Survey)
        .filter(Survey.study_id == study.id, Survey.archived_at.is_(None))
        .all()
    )
    projects = (
        db.query(Project)
        .filter(Project.study_id == study.id, Project.archived_at.is_(None))
        .all()
    )

    survey_inputs = []
    for s in surveys:
        dash = build_dashboard(db, s)
        discoveries = compute_discoveries(db, s)
        survey_inputs.append(
            {
                "survey": {
                    "id": s.id,
                    "name": s.name,
                    "role": s.role,
                    "n_completed": dash.n_completed,
                    "completion_rate": dash.completion_rate_percentage,
                },
                "questions": [
                    {
                        "prompt": q.prompt,
                        "type": q.type,
                        "n": q.n_answered,
                        "mean": q.mean,
                        "breakdown": q.breakdown,
                    }
                    for q in dash.questions
                ],
                "discoveries": [
                    {
                        "title": d.title,
                        "description": d.description,
                        "confidence": d.confidence,
                        "segment_n": d.segment_n,
                        "metric_question_prompt": d.metric_question_prompt,
                    }
                    for d in discoveries
                ],
            }
        )

    # Collect up to MAX_PARTICIPANTS_TO_INCLUDE completed interviews.
    participants: list[Participant] = []
    for p in projects:
        completed = (
            db.query(Participant)
            .filter(
                Participant.project_id == p.id,
                Participant.status == "completed",
            )
            .order_by(Participant.completed_at.desc())
            .limit(MAX_PARTICIPANTS_TO_INCLUDE)
            .all()
        )
        participants.extend(completed)
        if len(participants) >= MAX_PARTICIPANTS_TO_INCLUDE:
            break
    participants = participants[:MAX_PARTICIPANTS_TO_INCLUDE]

    transcripts = []
    total_chars = 0
    for p in participants:
        turns = (
            db.query(InterviewTurn)
            .filter(InterviewTurn.participant_id == p.id)
            .order_by(InterviewTurn.turn_index)
            .limit(MAX_INTERVIEW_TURNS_PER_PARTICIPANT)
            .all()
        )
        snippet_parts = []
        for t in turns:
            if not t.response_transcript:
                continue
            line = f"Q: {t.question_text}\nA: {t.response_transcript}"
            if total_chars + len(line) > MAX_TRANSCRIPT_CHARS:
                break
            snippet_parts.append(line)
            total_chars += len(line)
        if snippet_parts:
            transcripts.append(
                {
                    "participant": p.display_name or f"Participant {p.id[:6]}",
                    "segments": {
                        "profession": p.profession,
                        "country": p.country,
                        "age_range": p.age_range,
                    },
                    "transcript": "\n\n".join(snippet_parts),
                }
            )

    inputs_snapshot = {
        "study_id": study.id,
        "surveys": survey_inputs,
        "interview_count": len(transcripts),
        "interviews": transcripts,
        "min_n_threshold": DEFAULT_MIN_N,
    }
    snapshot_json = json.dumps(inputs_snapshot)

    # If no API key (dev/test), return a stub report so the rest of the
    # plumbing (storage, polling, UI rendering) can be exercised without
    # an AI dependency. Real production always has the key set.
    if not settings.ANTHROPIC_API_KEY:
        stub = _stub_report(survey_inputs, transcripts)
        return json.dumps(stub), snapshot_json

    # Real call.
    user_prompt = (
        f"{SCHEMA_BLOCK}\n\n"
        f"<inputs>\n{snapshot_json}\n</inputs>\n\n"
        "Generate the report now. Return ONLY the JSON object, nothing else."
    )

    # Import lazily to avoid a hard dep during tests that mock this service.
    from app.services._clients import get_anthropic_client

    client = get_anthropic_client()
    response = client.messages.create(
        model=ai_models.sonnet(),
        max_tokens=4096,
        **ai_models.temperature_kwargs(ai_models.sonnet(), 0.3),
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    from app.services.usage_logger import log_claude_usage

    log_claude_usage(db, response, "study_analysis", company_id=study.company_id)

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    # Validate it parses + matches the schema shape minimally — strict
    # Pydantic validation happens at the endpoint layer.
    parsed = json.loads(raw)
    if "themes" not in parsed:
        raise ValueError("Claude returned a payload without a 'themes' key")
    return raw, snapshot_json


def _stub_report(survey_inputs: list[dict], transcripts: list[dict]) -> dict:
    """Deterministic offline stub so the UI + tests work without an API key.

    Builds 2-3 themes directly from the survey discoveries the service
    already computed. This is NOT a real AI synthesis — it's a structural
    placeholder so the rest of the system can be tested end-to-end.
    """

    themes = []
    for survey_input in survey_inputs[:2]:
        for d in survey_input.get("discoveries", [])[:2]:
            themes.append(
                {
                    "title": d["title"],
                    "survey_signal": {
                        "summary": d["description"],
                        "n": d["segment_n"],
                        "percentage": None,
                        "segment_label": None,
                        "segment_over_index": None,
                    },
                    "interview_evidence": (
                        {
                            "x_of_y": f"{min(3, len(transcripts))} of {len(transcripts)}",
                            "interview_count": min(3, len(transcripts)),
                            "anchor_quote": _find_first_quote(transcripts) or "",
                            "segments_mentioned": [],
                        }
                        if transcripts
                        else None
                    ),
                    "recommendation": {
                        "kind": "next_research",
                        "action": "Invite this segment to follow-up interviews to understand the cause.",
                        "rationale": "We see a clear quantitative gap; we need qualitative context to act on it.",
                    },
                    "confidence": d["confidence"],
                }
            )
            if len(themes) >= 4:
                break
        if len(themes) >= 4:
            break
    if not themes:
        themes = [
            {
                "title": "Insufficient data to surface themes",
                "survey_signal": None,
                "interview_evidence": None,
                "recommendation": {
                    "kind": "next_research",
                    "action": "Collect more survey responses or interviews before regenerating.",
                    "rationale": "Themes require at least one survey question or interview to anchor.",
                },
                "confidence": "directional",
            }
        ]

    return {
        "executive_summary": (
            "This is a stub report generated without a Claude API key. "
            "Connect ANTHROPIC_API_KEY to generate real Quantified Themes."
            if not os.environ.get("ANTHROPIC_API_KEY")
            else "Stub fallback engaged — Claude returned no themes."
        ),
        "themes": themes,
        "methodology_note": (
            f"Generated from {sum(s['survey']['n_completed'] for s in survey_inputs)} survey "
            f"responses and {len(transcripts)} interviews. "
            "Confidence pills follow the workspace methodology contract."
        ),
        "generated_with_survey_count": len(survey_inputs),
        "generated_with_response_count": sum(
            s["survey"]["n_completed"] for s in survey_inputs
        ),
        "generated_with_interview_count": len(transcripts),
    }


def _find_first_quote(transcripts: list[dict]) -> str | None:
    """Pull the first meaningful answer from the transcript pool."""

    for t in transcripts:
        for line in t["transcript"].split("\n"):
            if line.startswith("A:") and len(line) > 30:
                return line[2:].strip().strip(".")
    return None


# ── Anchor-quote verification (post-generation) ───────────────────────


def _verify_anchor_quotes(db: Session, study: Study, report_json: str) -> str:
    """Strip interview_evidence whose anchor_quote isn't real.

    Claude is *instructed* never to fabricate quotes, but post-generation
    verification means a drift doesn't break the methodology contract.
    For each theme:
      - Take interview_evidence.anchor_quote.
      - Normalize (collapse whitespace, lowercase) for fuzzy matching.
      - Compare against the same-normalized transcripts on the study's
        sibling Projects.
      - If not found, strip interview_evidence and downgrade confidence
        from "strong" → "supported".

    Returns the (possibly modified) report JSON. If parsing fails we
    return the original — the caller's status="ready" handling is
    unaffected.
    """

    try:
        report = json.loads(report_json)
    except (json.JSONDecodeError, TypeError):
        return report_json

    themes = report.get("themes") or []
    if not themes:
        return report_json

    # Gather the verbatim transcript pool from sibling projects.
    transcript_corpus = _normalised_transcript_corpus(db, study)
    if not transcript_corpus:
        # No transcripts to verify against → if a theme claims interview
        # evidence, strip it. Nothing to hallucinate against.
        for theme in themes:
            if theme.get("interview_evidence"):
                theme["interview_evidence"] = None
                if theme.get("confidence") == "strong":
                    theme["confidence"] = "supported"
        return json.dumps(report)

    stripped = 0
    for theme in themes:
        evidence = theme.get("interview_evidence")
        if not evidence:
            continue
        quote = evidence.get("anchor_quote") or ""
        normalised = _normalise_for_substring(quote)
        # Require at least 12 characters of meaningful overlap to count
        # as a verified verbatim — shorter snippets ("yes", "exactly")
        # are too easy to coincidentally match.
        if len(normalised) < 12 or normalised not in transcript_corpus:
            theme["interview_evidence"] = None
            if theme.get("confidence") == "strong":
                theme["confidence"] = "supported"
            stripped += 1

    if stripped:
        logger.info(
            "Verbatim verifier stripped %d unverified anchor quote(s) for study %s",
            stripped,
            study.id,
        )
    return json.dumps(report)


def _normalised_transcript_corpus(db: Session, study: Study) -> str:
    """Concatenate every InterviewTurn.response_transcript on the study's
    sibling projects, normalised for substring search. One giant string
    keeps the verification cost O(N quotes × M transcript chars) which
    for typical studies (<50 transcripts, <100k chars) is well under 1ms."""

    project_ids = [
        p.id
        for p in db.query(Project)
        .filter(Project.study_id == study.id, Project.archived_at.is_(None))
        .all()
    ]
    if not project_ids:
        return ""
    turns = (
        db.query(InterviewTurn)
        .join(Participant, InterviewTurn.participant_id == Participant.id)
        .filter(Participant.project_id.in_(project_ids))
        .all()
    )
    parts: list[str] = []
    for t in turns:
        if t.response_transcript:
            parts.append(_normalise_for_substring(t.response_transcript))
    return " ".join(parts)


def _normalise_for_substring(text: str) -> str:
    """Lowercase + collapse whitespace + drop quote characters.

    Claude often returns quotes with curly/smart punctuation while the
    raw transcript stores straight ASCII; normalising both sides lets
    the substring match survive that drift.
    """

    if not text:
        return ""
    # Replace smart quotes + ellipsis with straight equivalents.
    cleaned = (
        text.replace("‘", "'")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("…", "...")
    )
    # Drop ALL quote chars + collapse whitespace.
    cleaned = re.sub(r"[\"']", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip().lower()
