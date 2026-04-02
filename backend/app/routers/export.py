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

    return [
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
        )
        for p in participants
    ]


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
