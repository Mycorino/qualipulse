import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.limiter import limiter
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.schemas.interview import (
    StartInterviewRequest,
    StartInterviewResponse,
    TurnResponse,
    ResumeCheckResponse,
    ResumeSummaryResponse,
)
from app.services.interview_engine import process_interview_turn, start_interview
from app.services.storage import upload_audio

router = APIRouter(prefix="/interview", tags=["interview"])


class ScreenRequest(BaseModel):
    answers: dict[str, str]  # question_id → selected option


@router.get("/{token}/screening-questions")
@limiter.limit("60/minute")
def get_screening_questions(request: Request, token: str, db: Session = Depends(get_db)):
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
@limiter.limit("30/minute")
def screen_participant(request: Request, token: str, body: ScreenRequest, db: Session = Depends(get_db)):
    """Check answers against disqualifying options. Returns qualified status."""
    link = _get_active_link_or_404(token, db)
    for q in sorted(link.project.screening_questions, key=lambda q: q.sort_order):
        answer = body.answers.get(q.id)
        if answer and answer in q.disqualifying_options_list:
            return {"qualified": False, "disqualified_on": q.question}
    return {"qualified": True}


@router.get("/{token}")
@limiter.limit("60/minute")
def validate_link(
    request: Request,
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


@router.get("/{token}/resume", response_model=ResumeCheckResponse)
@limiter.limit("60/minute")
def check_resume_by_email(
    request: Request,
    token: str,
    email: str,
    db: Session = Depends(get_db),
):
    """Check if an in-progress interview exists for this email address."""
    link = _get_active_link_or_404(token, db)
    participant = (
        db.query(Participant)
        .filter(
            Participant.link_id == link.id,
            Participant.email == email,
            Participant.status == "in_progress",
        )
        .order_by(Participant.started_at.desc())
        .first()
    )
    if not participant:
        return ResumeCheckResponse(found=False)

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    last_turn = turns[-1] if turns else None
    return ResumeCheckResponse(
        found=True,
        participant_id=participant.id,
        last_question=last_turn.question_text if last_turn else None,
        turn_count=len(turns),
        question_index=last_turn.question_index or 0 if last_turn else 0,
    )


@router.get("/{token}/{participant_id}/resume-summary", response_model=ResumeSummaryResponse)
def get_resume_summary(
    token: str,
    participant_id: str,
    db: Session = Depends(get_db),
):
    """Return a summary of what has been covered so far for a resume flow."""
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)

    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    # Collect main (non-follow-up) questions that have a participant response
    covered: list[str] = []
    seen_q: set[int] = set()
    for t in turns:
        if (
            not t.is_follow_up
            and t.question_index is not None
            and t.question_index not in seen_q
            and t.response_transcript
        ):
            seen_q.add(t.question_index)
            covered.append(t.question_text)

    now = datetime.utcnow()
    started = participant.started_at.replace(tzinfo=None) if participant.started_at.tzinfo else participant.started_at
    elapsed_minutes = (now - started).total_seconds() / 60.0

    last_turn = turns[-1] if turns else None
    return ResumeSummaryResponse(
        questions_covered=covered,
        last_question=last_turn.question_text if last_turn else None,
        turn_count=len(turns),
        elapsed_minutes=round(elapsed_minutes, 1),
    )


@router.post("/{token}/start", response_model=StartInterviewResponse)
@limiter.limit("30/minute")
def start_interview_session(
    request: Request,
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
        email=body.email if body else None,
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
@limiter.limit("30/minute")
async def respond_to_question(
    request: Request,
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

    # Deduplication: if the most recent turn already has a response, return it
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    if turns:
        last_turn = turns[-1]
        if last_turn.response_transcript:
            # This turn was already processed — return the existing next question
            return TurnResponse(
                question_text=last_turn.question_text,
                tts_audio_url=last_turn.tts_audio_url or "",
                is_complete=participant.status == "completed",
                is_follow_up=last_turn.is_follow_up or False,
                question_index=last_turn.question_index or 0,
                elapsed_seconds=0,
                total_seconds=0,
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
        is_follow_up=result.get("is_follow_up", False),
        question_index=result.get("question_index", 0),
        elapsed_seconds=result.get("elapsed_seconds", 0),
        total_seconds=result.get("total_seconds", 0),
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
