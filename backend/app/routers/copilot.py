"""Research Copilot endpoints.

The copilot is the in-context AI assistant. It runs on two surfaces, each
with its own adapter (see ``services/copilot.py`` / ``copilot_interview.py``):

- ``/surveys/{id}/copilot``  — the survey builder
- ``/projects/{id}/copilot`` — the interview-guide builder

``POST .../copilot`` runs one agent turn (proposes changes). The
``.../copilot/conversation`` GET/PUT persist the panel's chat thread so
it resumes when the researcher navigates away and back.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.project import Project
from app.models.survey import Survey
from app.schemas.copilot import ConversationState, CopilotRequest, CopilotResponse
from app.services.copilot import (
    SURVEY_ADAPTER,
    get_conversation,
    get_memory,
    run_copilot_turn,
    save_conversation,
)
from app.services.copilot_interview import INTERVIEW_ADAPTER
from app.services.copilot_onboarding import ONBOARDING_ADAPTER

router = APIRouter(tags=["copilot"])


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


def _project_or_404(db: Session, project_id: str, company: Company) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company.id)
        .first()
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


# ── Survey surface ───────────────────────────────────────────────────────────


@router.post("/surveys/{survey_id}/copilot", response_model=CopilotResponse)
def survey_copilot(
    survey_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> CopilotResponse:
    """Run one Research Copilot turn against a survey."""
    survey = _survey_or_404(db, survey_id, company)
    result = run_copilot_turn(
        db, company, survey, SURVEY_ADAPTER, body.messages,
        body.active_section, body.mission,
    )
    return CopilotResponse(**result)


@router.get(
    "/surveys/{survey_id}/copilot/conversation", response_model=ConversationState
)
def get_survey_conversation(
    survey_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _survey_or_404(db, survey_id, company)
    return ConversationState(thread=get_conversation(db, "survey", survey_id))


@router.put(
    "/surveys/{survey_id}/copilot/conversation", response_model=ConversationState
)
def put_survey_conversation(
    survey_id: str,
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _survey_or_404(db, survey_id, company)
    save_conversation(db, company.id, "survey", survey_id, body.thread)
    return body


# ── Interview-guide surface ──────────────────────────────────────────────────


@router.post("/projects/{project_id}/copilot", response_model=CopilotResponse)
def project_copilot(
    project_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> CopilotResponse:
    """Run one Research Copilot turn against an interview guide."""
    project = _project_or_404(db, project_id, company)
    result = run_copilot_turn(
        db, company, project, INTERVIEW_ADAPTER, body.messages,
        body.active_section, body.mission,
    )
    return CopilotResponse(**result)


@router.get(
    "/projects/{project_id}/copilot/conversation", response_model=ConversationState
)
def get_project_conversation(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _project_or_404(db, project_id, company)
    return ConversationState(thread=get_conversation(db, "project", project_id))


@router.put(
    "/projects/{project_id}/copilot/conversation", response_model=ConversationState
)
def put_project_conversation(
    project_id: str,
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _project_or_404(db, project_id, company)
    save_conversation(db, company.id, "project", project_id, body.thread)
    return body


# ── Onboarding surface ───────────────────────────────────────────────────────


@router.post("/onboarding/copilot", response_model=CopilotResponse)
def onboarding_copilot(
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> CopilotResponse:
    """Run one onboarding-copilot turn — the new researcher's first
    conversation. The 'instrument' is the Company itself."""
    result = run_copilot_turn(
        db, company, company, ONBOARDING_ADAPTER, body.messages,
        None, body.mission,
    )
    return CopilotResponse(**result)


@router.get("/onboarding/copilot/conversation", response_model=ConversationState)
def get_onboarding_conversation(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    return ConversationState(
        thread=get_conversation(db, "company", company.id),
    )


@router.put("/onboarding/copilot/conversation", response_model=ConversationState)
def put_onboarding_conversation(
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    save_conversation(db, company.id, "company", company.id, body.thread)
    return body


@router.get("/onboarding/copilot/memory")
def get_onboarding_memory(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    """The workspace-scope memory the copilot wrote during onboarding —
    shown back to the researcher on the completion screen."""
    row = get_memory(db, "company", company.id)
    return {"memory": (row.content if row and row.content else "")}
