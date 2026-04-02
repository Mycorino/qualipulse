"""AI-powered synthesis of all completed interview transcripts for a project."""

import json
from datetime import datetime

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.models.interview import Participant, ProjectAnalysis
from app.models.project import Project

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

    # Upsert analysis row with "generating" status
    analysis = db.query(ProjectAnalysis).filter(
        ProjectAnalysis.project_id == project_id
    ).first()
    if analysis is None:
        analysis = ProjectAnalysis(project_id=project_id)
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

    try:
        transcripts_block, participant_map = _build_transcripts_block(completed)
        objective_block = (
            f"RESEARCH OBJECTIVE:\n{project.research_objective}\n\n"
            if project.research_objective
            else ""
        )

        filter_note = ""
        if filter_by and filter_values:
            filter_note = f"NOTE: This analysis covers only participants filtered by {filter_by} = {', '.join(filter_values)}.\n\n"

        prompt = f"""{objective_block}{filter_note}TRANSCRIPTS ({len(completed)} completed interviews):

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

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

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
