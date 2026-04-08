import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.interview import InterviewTurn, Participant
from app.models.project import Project
from app.schemas.interview import (
    ParticipantResponse,
    TranscriptResponse,
    TranscriptTurnResponse,
)

router = APIRouter(prefix="/projects", tags=["export"])


# Filler words/phrases that indicate disengaged or low-quality responses
_FILLERS = {
    "yes", "no", "maybe", "ok", "okay", "sure", "fine", "idk",
    "i don't know", "i don't care", "i dunno", "not sure", "no idea",
    "don't know", "can't say", "cant say", "nothing", "nope", "yep", "yeah",
    "i guess", "i suppose", "not really", "kind of", "sort of",
}

def _compute_quality(turns) -> tuple[float | None, str | None]:
    """Return (score 0.0-1.0, label) from participant turns. Returns (None, None) if no data."""
    responses = [
        t.response_transcript
        for t in turns
        if t.response_transcript and t.response_transcript.strip()
    ]
    if not responses:
        return None, None

    total = 0.0
    for text in responses:
        words = text.lower().split()
        wc = len(words)
        normalized = text.lower().strip().rstrip(".!?")

        is_filler = (
            normalized in _FILLERS
            or (wc <= 3 and any(f in normalized for f in _FILLERS))
        )

        if is_filler or wc <= 2:
            score = 0.0
        elif wc <= 8:
            score = 0.2
        elif wc <= 20:
            score = 0.5
        elif wc <= 50:
            score = 0.8
        else:
            score = 1.0

        total += score

    avg = total / len(responses)

    if avg < 0.25:
        label = "low"
    elif avg < 0.5:
        label = "fair"
    elif avg < 0.75:
        label = "good"
    else:
        label = "strong"

    return round(avg, 2), label


@router.get("/{project_id}/participants", response_model=list[ParticipantResponse])
def list_participants(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[ParticipantResponse]:
    project = _get_project_or_404(project_id, company.id, db)

    participants = (
        db.query(Participant)
        .filter(Participant.project_id == project.id)
        .order_by(Participant.started_at.desc())
        .all()
    )

    result = []
    for p in participants:
        # Use persisted quality score if available, otherwise compute heuristic
        if p.quality_score is not None and p.quality_label is not None:
            q_score, q_label = p.quality_score, p.quality_label
        else:
            q_score, q_label = _compute_quality(p.turns)
        result.append(
            ParticipantResponse(
                id=p.id,
                display_name=p.display_name,
                status=p.status,
                started_at=p.started_at,
                completed_at=p.completed_at,
                turn_count=len(p.turns),
                age_range=p.age_range,
                profession=p.profession,
                country=p.country,
                quality_score=q_score,
                quality_label=q_label,
            )
        )
    return result


@router.get(
    "/{project_id}/participants/{participant_id}/transcript",
    response_model=TranscriptResponse,
)
def get_transcript(
    project_id: str,
    participant_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> TranscriptResponse:
    project = _get_project_or_404(project_id, company.id, db)

    participant = (
        db.query(Participant)
        .filter(
            Participant.id == participant_id,
            Participant.project_id == project.id,
        )
        .first()
    )
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found"
        )

    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    q_score, q_label = _compute_quality(turns)
    return TranscriptResponse(
        participant=ParticipantResponse(
            id=participant.id,
            display_name=participant.display_name,
            status=participant.status,
            started_at=participant.started_at,
            completed_at=participant.completed_at,
            turn_count=len(turns),
            age_range=participant.age_range,
            profession=participant.profession,
            country=participant.country,
            quality_score=q_score,
            quality_label=q_label,
        ),
        turns=[
            TranscriptTurnResponse(
                id=t.id,
                turn_index=t.turn_index,
                question_text=t.question_text,
                response_transcript=t.response_transcript,
                is_follow_up=t.is_follow_up,
                manually_edited=t.manually_edited,
                edited_at=t.edited_at,
                created_at=t.created_at,
                audio_recording_url=t.audio_recording_url,
                tts_audio_url=t.tts_audio_url,
            )
            for t in turns
        ],
    )


@router.get("/{project_id}/export")
def export_transcripts_csv(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Export all interview transcripts for a project as a CSV download."""
    project = _get_project_or_404(project_id, company.id, db)

    participants = (
        db.query(Participant)
        .filter(Participant.project_id == project.id)
        .order_by(Participant.started_at)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "participant_id",
        "display_name",
        "status",
        "started_at",
        "completed_at",
        "turn_index",
        "question_index",
        "is_follow_up",
        "question_text",
        "response_transcript",
        "created_at",
    ])

    for p in participants:
        turns = sorted(p.turns, key=lambda t: t.turn_index)
        if not turns:
            # Write a row for the participant even with no turns
            writer.writerow([
                p.id,
                p.display_name or "",
                p.status,
                _fmt_dt(p.started_at),
                _fmt_dt(p.completed_at),
                "", "", "", "", "", "",
            ])
        else:
            for t in turns:
                writer.writerow([
                    p.id,
                    p.display_name or "",
                    p.status,
                    _fmt_dt(p.started_at),
                    _fmt_dt(p.completed_at),
                    t.turn_index,
                    t.question_index if t.question_index is not None else "",
                    t.is_follow_up,
                    t.question_text,
                    t.response_transcript or "",
                    _fmt_dt(t.created_at),
                ])

    output.seek(0)
    filename = f"{project.name.replace(' ', '_')}_transcripts.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{project_id}/participants/{participant_id}/quality")
async def ai_quality_assessment(
    project_id: str,
    participant_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Use Claude to produce a structured quality assessment of an interview transcript."""
    from app.config import settings
    import anthropic
    import json as _json

    _get_project_or_404(project_id, company.id, db)

    participant = (
        db.query(Participant)
        .filter(Participant.id == participant_id, Participant.project_id == project_id)
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    responses = [t for t in turns if t.response_transcript]
    if not responses:
        raise HTTPException(status_code=400, detail="No responses to assess")

    # Build transcript text
    transcript_lines = []
    for t in turns:
        transcript_lines.append(f"Interviewer: {t.question_text}")
        if t.response_transcript:
            transcript_lines.append(f"Participant: {t.response_transcript}")
    transcript_text = "\n".join(transcript_lines)

    # Compute basic stats
    word_counts = [len((t.response_transcript or "").split()) for t in responses]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0
    short_pct = (sum(1 for wc in word_counts if wc < 10) / len(word_counts) * 100) if word_counts else 0

    from app.services.usage_logger import log_claude_usage

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt = f"""You are a qualitative research expert. Assess the quality of the following interview transcript.

TRANSCRIPT:
{transcript_text}

STATS:
- Total responses: {len(responses)}
- Average words per response: {avg_words:.1f}
- % of short responses (<10 words): {short_pct:.0f}%

Evaluate the participant's engagement and response quality. Consider:
- Are responses substantive and detailed, or superficial/evasive?
- Does the participant give genuine, honest answers or just say yes/no/I don't care?
- Is there emotional authenticity and personal experience in the responses?
- Are there any red flags: repeated one-word answers, obvious disengagement, incoherent responses?

Return ONLY a JSON object with this structure:
{{
  "quality_score": <float 0.0-1.0>,
  "quality_label": <"low"|"fair"|"good"|"strong">,
  "summary": "<2-3 sentences overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "issues": ["<issue 1>", "<issue 2>"]
}}

quality_score guide: 0.0-0.25=low, 0.25-0.5=fair, 0.5-0.75=good, 0.75-1.0=strong"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    log_claude_usage(
        db, response, "quality",
        company_id=company.id, project_id=project_id, participant_id=participant_id,
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    try:
        result = _json.loads(raw)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to parse quality assessment")

    result["avg_response_words"] = round(avg_words, 1)
    result["short_answer_pct"] = round(short_pct, 1)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_or_404(project_id: str, company_id: str, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


def _fmt_dt(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""
