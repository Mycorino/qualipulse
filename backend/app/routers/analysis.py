"""Analysis endpoints — generate and retrieve AI synthesis for a project."""

import threading

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.interview import Participant, ProjectAnalysis
from app.models.project import Project
from app.services.analysis import run_analysis

router = APIRouter(prefix="/projects", tags=["analysis"])


@router.post("/{project_id}/analysis", status_code=status.HTTP_202_ACCEPTED)
def trigger_analysis(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Kick off (or re-run) AI synthesis for all completed interviews."""
    project = _get_project_or_404(project_id, company.id, db)

    completed_count = (
        db.query(Participant)
        .filter(Participant.project_id == project.id, Participant.status == "completed")
        .count()
    )
    if completed_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No completed interviews to analyse yet.",
        )

    # Run in background thread so the response returns immediately
    thread = threading.Thread(
        target=run_analysis,
        args=(project_id, db),
        daemon=True,
    )
    thread.start()

    return {"status": "generating", "message": "Analysis started"}


@router.get("/{project_id}/analysis")
def get_analysis(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Return the latest analysis for a project, plus staleness info."""
    _get_project_or_404(project_id, company.id, db)

    analysis = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id)
        .first()
    )

    # Count total completed participants so frontend can show staleness
    completed_count = (
        db.query(Participant)
        .filter(Participant.project_id == project_id, Participant.status == "completed")
        .count()
    )

    if analysis is None:
        return {
            "status": "none",
            "completed_count": completed_count,
            "participant_count": 0,
            "generated_at": None,
            "report": None,
            "error": None,
        }

    import json
    return {
        "status": analysis.status,
        "completed_count": completed_count,
        "participant_count": analysis.participant_count,
        "generated_at": analysis.generated_at.isoformat() if analysis.generated_at else None,
        "report": json.loads(analysis.report) if analysis.report else None,
        "error": analysis.error,
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
