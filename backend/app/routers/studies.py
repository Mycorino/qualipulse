"""Studies router — the research-workspace surface (Sprint 9.5).

The Study Overview page is the home for a research effort. Surveys and
Projects are *instruments inside* a Study. This module powers:

  - GET /studies        : list studies in the workspace (Study List page)
  - GET /studies/{id}   : single Study with its surveys + projects +
                          progress signal (Study Overview page)

Creation stays implicit (Decision 8): the first time a researcher
creates a Survey or Project, a Study is auto-created with the same
name. There is deliberately no POST /studies endpoint.

Future sprint hooks (intentionally deferred):
  - PATCH /studies/{id}  — rename, archive (Sprint 10.5 if needed)
  - GET   /studies/{id}/segments  — computed segment discoveries (Sprint 10)
  - POST  /studies/{id}/analyses  — quantified-themes report (Sprint 11)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.interview import InterviewLink, Participant
from app.models.project import Project
from app.models.study import Study, StudyParticipant
from app.models.survey import Survey, SurveyQuestion, SurveyResponse
from app.schemas.study import (
    ProjectMini,
    StudyDetail,
    StudyProgress,
    StudySummary,
    SurveyMini,
)

router = APIRouter(prefix="/studies", tags=["studies"])


@router.get("/", response_model=list[StudySummary])
def list_studies(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[StudySummary]:
    """Workspace-scoped list of Studies + summary counts.

    Excludes archived Studies so the Study List page can be the post-
    login landing for accounts that have ≥1 active Study.
    """

    studies = (
        db.query(Study)
        .filter(Study.company_id == company.id, Study.archived_at.is_(None))
        .order_by(Study.created_at.desc())
        .all()
    )
    return [_summary_for(db, s) for s in studies]


@router.get("/{study_id}", response_model=StudyDetail)
def get_study(
    study_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StudyDetail:
    """Full Study detail powering the Overview page.

    Returns embedded surveys (with response counts) + projects (with
    interview counts) + the five-step progress signal + a server-
    computed recommended action.
    """

    study = (
        db.query(Study)
        .filter(Study.id == study_id, Study.company_id == company.id)
        .first()
    )
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    surveys = (
        db.query(Survey)
        .filter(Survey.study_id == study.id, Survey.archived_at.is_(None))
        .order_by(Survey.created_at.desc())
        .all()
    )
    projects = (
        db.query(Project)
        .filter(Project.study_id == study.id, Project.archived_at.is_(None))
        .order_by(Project.created_at.desc())
        .all()
    )

    survey_minis = [_survey_mini(db, s) for s in surveys]
    project_minis = [_project_mini(db, p) for p in projects]

    progress = _compute_progress(study, survey_minis, project_minis)
    recommended = _recommended_action(progress, surveys, projects)

    return StudyDetail(
        id=study.id,
        name=study.name,
        created_at=study.created_at,
        archived_at=study.archived_at,
        surveys=survey_minis,
        projects=project_minis,
        progress=progress,
        recommended_action=recommended,
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _summary_for(db: Session, study: Study) -> StudySummary:
    survey_count = (
        db.query(func.count(Survey.id))
        .filter(Survey.study_id == study.id, Survey.archived_at.is_(None))
        .scalar()
        or 0
    )
    project_count = (
        db.query(func.count(Project.id))
        .filter(Project.study_id == study.id, Project.archived_at.is_(None))
        .scalar()
        or 0
    )
    participant_count = (
        db.query(func.count(StudyParticipant.id))
        .filter(StudyParticipant.study_id == study.id)
        .scalar()
        or 0
    )
    return StudySummary(
        id=study.id,
        name=study.name,
        created_at=study.created_at,
        archived_at=study.archived_at,
        survey_count=survey_count,
        project_count=project_count,
        participant_count=participant_count,
    )


def _survey_mini(db: Session, survey: Survey) -> SurveyMini:
    question_count = (
        db.query(func.count(SurveyQuestion.id))
        .filter(
            SurveyQuestion.survey_id == survey.id,
            SurveyQuestion.deprecated_at.is_(None),
        )
        .scalar()
        or 0
    )
    response_count = (
        db.query(func.count(SurveyResponse.id))
        .filter(SurveyResponse.survey_id == survey.id)
        .scalar()
        or 0
    )
    completed_count = (
        db.query(func.count(SurveyResponse.id))
        .filter(
            SurveyResponse.survey_id == survey.id,
            SurveyResponse.completed_at.isnot(None),
        )
        .scalar()
        or 0
    )
    return SurveyMini(
        id=survey.id,
        name=survey.name,
        role=survey.role,
        status=survey.status,
        question_count=question_count,
        response_count=response_count,
        completed_count=completed_count,
    )


def _project_mini(db: Session, project: Project) -> ProjectMini:
    link_count = (
        db.query(func.count(InterviewLink.id))
        .filter(InterviewLink.project_id == project.id)
        .scalar()
        or 0
    )
    completed = (
        db.query(func.count(Participant.id))
        .filter(
            Participant.project_id == project.id,
            Participant.status == "completed",
        )
        .scalar()
        or 0
    )
    in_progress = (
        db.query(func.count(Participant.id))
        .filter(
            Participant.project_id == project.id,
            Participant.status == "in_progress",
        )
        .scalar()
        or 0
    )
    return ProjectMini(
        id=project.id,
        name=project.name,
        language=project.language,
        interview_link_count=link_count,
        completed_participant_count=completed,
        in_progress_participant_count=in_progress,
    )


def _compute_progress(
    study: Study,
    surveys: list[SurveyMini],
    projects: list[ProjectMini],
) -> StudyProgress:
    has_live_survey = any(s.status == "live" for s in surveys)
    total_completed = sum(s.completed_count for s in surveys)
    interviews_completed = sum(p.completed_participant_count for p in projects)
    return StudyProgress(
        has_live_survey=has_live_survey,
        total_completed_responses=total_completed,
        # Sprint 10 will replace this placeholder with a real signal
        # (≥1 over-indexing segment detected) — for now we use the same
        # n=30 threshold the methodology contract uses everywhere.
        segments_identified_placeholder=total_completed >= 30,
        interviews_completed=interviews_completed,
        # Sprint 11 lands StudyAnalysis; until then, report_ready is False.
        report_ready_placeholder=False,
    )


def _recommended_action(
    progress: StudyProgress,
    surveys: list[Survey],
    projects: list[Project],
) -> str | None:
    """Server-computed next-action prompt for the Study Overview chip.

    Order matches the progress-checklist order so the prompt always
    points at the next un-done step. Returns None when the study is
    fully complete (or empty — caller decides what to show).
    """

    if not surveys:
        return "Create a screener survey to start collecting responses."

    if not progress.has_live_survey:
        return "Publish your survey to start collecting responses."

    if progress.total_completed_responses == 0:
        return "Share your survey link to collect the first responses."

    if progress.total_completed_responses < 30:
        remaining = 30 - progress.total_completed_responses
        plural = "response" if remaining == 1 else "responses"
        return f"Keep collecting — {remaining} more {plural} until inference-grade thresholds."

    if not projects:
        return "Open the survey dashboard to filter respondents and invite them to AI interviews."

    if progress.interviews_completed == 0:
        return "Use the Screener Bridge to invite high-signal respondents to AI interviews."

    if progress.interviews_completed < 5:
        return f"Conduct {5 - progress.interviews_completed} more interview(s) before generating the mixed-methods report."

    return "Generate the mixed-methods report to synthesize quanti + quali into one view."
