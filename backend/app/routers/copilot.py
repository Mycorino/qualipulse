"""Research Copilot endpoints.

The copilot is the in-context AI assistant.

- ``POST /surveys/{id}/copilot`` runs one agent turn: the copilot reads
  the live survey, asks clarifying questions, and returns *proposed*
  changes for the researcher to accept or reject.
- ``GET/PUT /surveys/{id}/copilot/conversation`` persist the panel's chat
  thread so it resumes when the researcher navigates away and back.

See ``services/copilot.py``.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.survey import Survey
from app.schemas.copilot import ConversationState, CopilotRequest, CopilotResponse
from app.services.copilot import (
    SURVEY_ADAPTER,
    get_conversation,
    run_copilot_turn,
    save_conversation,
)

router = APIRouter(prefix="/surveys", tags=["copilot"])


def _survey_or_404(db: Session, survey_id: str, company: Company) -> Survey:
    survey = (
        db.query(Survey)
        .filter(Survey.id == survey_id, Survey.company_id == company.id)
        .first()
    )
    if survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found"
        )
    return survey


@router.post("/{survey_id}/copilot", response_model=CopilotResponse)
def survey_copilot(
    survey_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> CopilotResponse:
    """Run one Research Copilot turn against a survey."""
    survey = _survey_or_404(db, survey_id, company)
    result = run_copilot_turn(db, company, survey, SURVEY_ADAPTER, body.messages)
    return CopilotResponse(**result)


@router.get(
    "/{survey_id}/copilot/conversation", response_model=ConversationState
)
def get_copilot_conversation(
    survey_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    """Load the persisted copilot chat thread for a survey."""
    _survey_or_404(db, survey_id, company)
    return ConversationState(thread=get_conversation(db, "survey", survey_id))


@router.put(
    "/{survey_id}/copilot/conversation", response_model=ConversationState
)
def put_copilot_conversation(
    survey_id: str,
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    """Persist the copilot chat thread for a survey so it resumes later."""
    _survey_or_404(db, survey_id, company)
    save_conversation(db, company.id, "survey", survey_id, body.thread)
    return body
