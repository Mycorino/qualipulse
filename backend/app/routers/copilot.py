"""Research Copilot endpoints.

The copilot is the in-context AI assistant. ``POST /surveys/{id}/copilot``
runs one agent turn against a survey: the copilot reads the live survey,
asks clarifying questions, and returns *proposed* changes for the
researcher to accept or reject. See ``services/copilot.py``.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.survey import Survey
from app.schemas.copilot import CopilotRequest, CopilotResponse
from app.services.copilot import run_copilot_turn

router = APIRouter(prefix="/surveys", tags=["copilot"])


@router.post("/{survey_id}/copilot", response_model=CopilotResponse)
def survey_copilot(
    survey_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> CopilotResponse:
    """Run one Research Copilot turn against a survey."""
    survey = (
        db.query(Survey)
        .filter(Survey.id == survey_id, Survey.company_id == company.id)
        .first()
    )
    if survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found"
        )

    result = run_copilot_turn(db, company, survey, body.messages)
    return CopilotResponse(**result)
