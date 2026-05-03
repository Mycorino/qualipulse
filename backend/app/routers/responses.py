"""Transcript editing endpoints — allows researchers to correct transcription errors."""

import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.interview import InterviewTurn, Participant
from app.models.project import Project
from app.services.translation import translate_participant

router = APIRouter(prefix="/projects", tags=["responses"])


class TurnEditRequest(BaseModel):
    response_transcript: str


@router.put(
    "/{project_id}/participants/{participant_id}/turns/{turn_id}",
    status_code=status.HTTP_200_OK,
)
def update_turn_transcript(
    project_id: str,
    participant_id: str,
    turn_id: str,
    body: TurnEditRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Update the transcript for a specific interview turn."""
    _get_project_or_404(project_id, company.id, db)

    participant = (
        db.query(Participant)
        .filter(Participant.id == participant_id, Participant.project_id == project_id)
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")

    turn = (
        db.query(InterviewTurn)
        .filter(InterviewTurn.id == turn_id, InterviewTurn.participant_id == participant_id)
        .first()
    )
    if turn is None:
        raise HTTPException(status_code=404, detail="Turn not found")

    turn.response_transcript = body.response_transcript
    turn.manually_edited = True
    turn.edited_at = datetime.utcnow()
    # Edit invalidates segment offsets; nulling out is better than wrong
    # highlighting. Audio file is untouched.
    turn.response_segments = None
    db.commit()
    db.refresh(turn)

    return {
        "id": turn.id,
        "turn_index": turn.turn_index,
        "response_transcript": turn.response_transcript,
        "manually_edited": turn.manually_edited,
        "edited_at": turn.edited_at.isoformat() if turn.edited_at else None,
    }


class TranslateRequest(BaseModel):
    target_language: str


@router.post(
    "/{project_id}/participants/{participant_id}/translate",
    status_code=status.HTTP_202_ACCEPTED,
)
def translate_transcript(
    project_id: str,
    participant_id: str,
    body: TranslateRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Translate every turn for a participant into target_language. Idempotent.

    Returns 202 immediately; translation runs in a background thread and
    cached translations appear on the next transcript GET.
    """
    _get_project_or_404(project_id, company.id, db)

    participant = (
        db.query(Participant)
        .filter(Participant.id == participant_id, Participant.project_id == project_id)
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")

    target = (body.target_language or "").lower().strip()
    if not target:
        raise HTTPException(status_code=400, detail="target_language is required")

    def _run():
        bg_db = SessionLocal()
        try:
            translate_participant(participant_id, bg_db, target)
        finally:
            bg_db.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "translating", "target_language": target}


def _get_project_or_404(project_id: str, company_id: str, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
