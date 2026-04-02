"""Transcript editing endpoints — allows researchers to correct transcription errors."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.interview import InterviewTurn, Participant
from app.models.project import Project

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
    db.commit()
    db.refresh(turn)

    return {
        "id": turn.id,
        "turn_index": turn.turn_index,
        "response_transcript": turn.response_transcript,
        "manually_edited": turn.manually_edited,
        "edited_at": turn.edited_at.isoformat() if turn.edited_at else None,
    }


def _get_project_or_404(project_id: str, company_id: str, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
