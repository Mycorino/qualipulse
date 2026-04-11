"""AI-powered synthesis of all completed interview transcripts for a project."""

import json
from datetime import datetime

import anthropic
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.company import Company
from app.models.interview import AnalysisThemeAnnotation, Participant, ProjectAnalysis
from app.models.memo import ProjectMemo
from app.models.project import Project
from app.services.business_context import full_context_block
from app.services.usage_logger import log_claude_usage

ANALYSIS_SYSTEM_PROMPT = """\
You are a senior qualitative researcher with deep expertise in Jobs-to-be-Done, \
behavioural psychology, and product research. You analyse interview transcripts and \
produce sharp, actionable insight reports.

Be concrete: name specific patterns, use direct quotes with attribution, flag surprises. \
Avoid generic observations. The report should help a product team make decisions.

Each quote MUST include the participant identifier (e.g. [P1]) as provided in the transcript headers.

Return ONLY valid JSON — no markdown, no preamble."""


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

        prompt = f"""{context_block}{objective_block}{filter_note}TRANSCRIPTS ({len(completed)} completed interviews):

{transcripts_block}

Analyse these interviews and return a JSON object with this exact structure:
{{
  "summary": "2-3 sentence executive summary of the most important finding",
  "themes": [
    {{
      "title": "short theme name",
      "summary": "1-2 sentence description",
      "quotes": [
        {{
          "text": "exact verbatim quote from transcript",
          "participant_identifier": "[P1]",
          "participant_display_name": "participant name",
          "turn_index": 3,
          "question_text": "the question that prompted this response"
        }}
      ],
      "frequency": "all / most / some / few"
    }}
  ],
  "jobs_to_be_done": [
    {{
      "job": "When I... I want to... so I can...",
      "insight": "what this reveals about user motivation",
      "frequency": "all / most / some / few"
    }}
  ],
  "tensions": [
    {{
      "tension": "short label",
      "detail": "what participants say vs. what they actually do or need"
    }}
  ],
  "recommendations": [
    "specific, actionable recommendation for the product team"
  ],
  "confidence": "low / medium / high",
  "participant_count": {len(completed)}
}}"""

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=httpx.Timeout(120.0))
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
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

        prompt = f"""{context_block}{objective_block}{annotations_block}
TRANSCRIPTS ({len(all_completed)} completed interviews):

{transcripts_block}

Analyse these interviews and return a JSON object with this exact structure:
{{
  "summary": "2-3 sentence executive summary of the most important finding",
  "themes": [
    {{
      "title": "short theme name",
      "summary": "1-2 sentence description",
      "quotes": [
        {{
          "text": "exact verbatim quote from transcript",
          "participant_identifier": "[P1]",
          "participant_display_name": "participant name",
          "turn_index": 3,
          "question_text": "the question that prompted this response"
        }}
      ],
      "frequency": "all / most / some / few"
    }}
  ],
  "jobs_to_be_done": [
    {{
      "job": "When I... I want to... so I can...",
      "insight": "what this reveals about user motivation",
      "frequency": "all / most / some / few"
    }}
  ],
  "tensions": [
    {{
      "tension": "short label",
      "detail": "what participants say vs. what they actually do or need"
    }}
  ],
  "recommendations": [
    "specific, actionable recommendation for the product team"
  ],
  "confidence": "low / medium / high",
  "participant_count": {len(all_completed)}
}}

For any theme that was disputed and you have reframed, add a "researcher_note" key to that theme object (string, 1-2 sentences explaining what changed). In the summary field, add one sentence noting this is a researcher-refined synthesis."""

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=httpx.Timeout(120.0))
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
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
