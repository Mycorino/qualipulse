"""AI-powered synthesis of all completed interview transcripts for a project."""

import json

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.models.interview import Participant, ProjectAnalysis
from app.models.project import Project

ANALYSIS_SYSTEM_PROMPT = """\
You are a senior qualitative researcher with deep expertise in Jobs-to-be-Done, \
behavioural psychology, and product research. You analyse interview transcripts and \
produce sharp, actionable insight reports.

Be concrete: name specific patterns, use direct quotes, flag surprises. \
Avoid generic observations. The report should help a product team make decisions.

Return ONLY valid JSON — no markdown, no preamble."""


def _build_transcripts_block(participants: list[Participant]) -> str:
    blocks = []
    for i, p in enumerate(participants, 1):
        name = p.display_name or f"Participant {i}"
        turns = sorted(p.turns, key=lambda t: t.turn_index)
        lines = [f"--- {name} ---"]
        for t in turns:
            lines.append(f"Q: {t.question_text}")
            if t.response_transcript:
                lines.append(f"A: {t.response_transcript}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def run_analysis(project_id: str, db: Session) -> None:
    """Run full synthesis for all completed interviews.

    Upserts a ProjectAnalysis row. Meant to be called in a background thread.
    """
    project: Project | None = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return

    completed = [
        p for p in project.participants if p.status == "completed" and p.turns
    ]

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
    db.commit()

    try:
        transcripts_block = _build_transcripts_block(completed)
        objective_block = (
            f"RESEARCH OBJECTIVE:\n{project.research_objective}\n\n"
            if project.research_objective
            else ""
        )

        prompt = f"""{objective_block}TRANSCRIPTS ({len(completed)} completed interviews):

{transcripts_block}

Analyse these interviews and return a JSON object with this exact structure:
{{
  "summary": "2-3 sentence executive summary of the most important finding",
  "themes": [
    {{
      "title": "short theme name",
      "summary": "1-2 sentence description",
      "quotes": ["exact quote from transcript", "another quote"],
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

        from datetime import datetime
        analysis.report = raw
        analysis.status = "ready"
        analysis.generated_at = datetime.utcnow()

    except Exception as e:
        analysis.status = "failed"
        analysis.error = str(e)

    db.commit()
