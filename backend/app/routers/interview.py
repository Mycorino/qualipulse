import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.schemas.interview import (
    StartInterviewRequest,
    StartInterviewResponse,
    TurnResponse,
)
from app.services.interview_engine import process_interview_turn, start_interview
from app.services.storage import upload_audio

router = APIRouter(prefix="/interview", tags=["interview"])


class ScreenRequest(BaseModel):
    answers: dict[str, str]  # question_id → selected option


@router.get("/{token}/screening-questions")
def get_screening_questions(token: str, db: Session = Depends(get_db)):
    """Return screening questions for this project (no auth required)."""
    link = _get_active_link_or_404(token, db)
    return [
        {
            "id": q.id,
            "question": q.question,
            "options": q.options_list,
            "disqualifying_options": q.disqualifying_options_list,
            "sort_order": q.sort_order,
        }
        for q in sorted(link.project.screening_questions, key=lambda q: q.sort_order)
    ]


@router.post("/{token}/screen")
def screen_participant(token: str, body: ScreenRequest, db: Session = Depends(get_db)):
    """Check answers against disqualifying options. Returns qualified status."""
    link = _get_active_link_or_404(token, db)
    for q in sorted(link.project.screening_questions, key=lambda q: q.sort_order):
        answer = body.answers.get(q.id)
        if answer and answer in q.disqualifying_options_list:
            return {"qualified": False, "disqualified_on": q.question}
    return {"qualified": True}


@router.get("/{token}")
def validate_link(
    token: str,
    db: Session = Depends(get_db),
):
    """Validate an interview link and return project info. No auth required."""
    link = _get_active_link_or_404(token, db)
    project = link.project

    return {
        "project_name": project.name,
        "welcome_message": project.welcome_message,
        "language": project.language,
        "interview_duration_minutes": project.interview_duration_minutes,
        "question_count": len([q for q in project.guide_questions if not q.deprecated_at]),
    }


@router.post("/{token}/start", response_model=StartInterviewResponse)
def start_interview_session(
    token: str,
    body: StartInterviewRequest | None = None,
    db: Session = Depends(get_db),
):
    """Create a new participant and generate the first interview question."""
    link = _get_active_link_or_404(token, db)

    participant = Participant(
        link_id=link.id,
        project_id=link.project_id,
        display_name=body.display_name if body else None,
        profession=body.profession if body else None,
        age_range=body.age_range if body else None,
        country=body.country if body else None,
        status="in_progress",
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)

    result = start_interview(participant.id, db)

    return StartInterviewResponse(
        participant_id=participant.id,
        first_question=result["question_text"],
        tts_audio_url=result["tts_audio_url"],
    )


@router.post("/{token}/{participant_id}/respond", response_model=TurnResponse)
async def respond_to_question(
    token: str,
    participant_id: str,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Accept an audio response from the participant, process it, and return the next question."""
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)

    if participant.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is already completed",
        )

    # Upload audio and process the turn
    audio_data = await audio.read()
    ext = os.path.splitext(audio.filename or "recording.webm")[1] or ".webm"
    audio_key = f"recordings/{participant_id}/{uuid.uuid4().hex}{ext}"
    upload_audio(audio_data, audio_key)

    result = process_interview_turn(participant_id, audio_key, db)

    return TurnResponse(
        question_text=result["question_text"],
        tts_audio_url=result["tts_audio_url"],
        is_complete=result["is_complete"],
    )


@router.get("/{token}/{participant_id}/status")
def get_interview_status(
    token: str,
    participant_id: str,
    db: Session = Depends(get_db),
):
    """Get current interview status for a participant."""
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    last_question = turns[-1].question_text if turns else None

    return {
        "participant_id": participant.id,
        "status": participant.status,
        "turn_count": len(turns),
        "last_question": last_question,
        "started_at": participant.started_at.isoformat() if participant.started_at else None,
        "completed_at": participant.completed_at.isoformat() if participant.completed_at else None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_active_link_or_404(token: str, db: Session) -> InterviewLink:
    link = (
        db.query(InterviewLink)
        .filter(InterviewLink.token == token, InterviewLink.is_active.is_(True))
        .first()
    )
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview link not found or inactive",
        )
    return link


def _get_participant_or_404(
    participant_id: str, link: InterviewLink, db: Session
) -> Participant:
    participant = (
        db.query(Participant)
        .filter(
            Participant.id == participant_id,
            Participant.link_id == link.id,
        )
        .first()
    )
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participant not found",
        )
    return participant
