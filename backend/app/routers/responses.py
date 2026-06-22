"""Transcript editing endpoints — allows researchers to correct transcription errors."""

import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import session_scope
from app.dependencies import (
    get_accessible_project_or_404 as _get_project_or_404,
    get_current_company,
    get_db,
)
from app.models.company import Company
from app.models.interview import InterviewTurn, Participant
from app.services.transcript_cleanup import cleanup_participant
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
        with session_scope() as bg_db:
            translate_participant(participant_id, bg_db, target)

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "translating", "target_language": target}


@router.post(
    "/{project_id}/participants/{participant_id}/clean-transcript",
    status_code=status.HTTP_202_ACCEPTED,
)
def clean_transcript(
    project_id: str,
    participant_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Run the ASR sense-check pass for a participant. Idempotent.

    Normally fires automatically when an interview completes; this endpoint lets
    a researcher trigger it on demand (and backfills participants that completed
    before the feature shipped). Returns 202; corrections appear on the next
    transcript GET in `cleaned_response`.
    """
    _get_project_or_404(project_id, company.id, db)

    participant = (
        db.query(Participant)
        .filter(Participant.id == participant_id, Participant.project_id == project_id)
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")

    def _run():
        with session_scope() as bg_db:
            cleanup_participant(participant_id, bg_db)

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "cleaning"}


