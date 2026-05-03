import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectSettingsPatch,
    QuestionPatch,
    QuestionResponse,
    ScreeningQuestionResponse,
)
from app.services.demo_seeder import (
    DEMO_PROJECT_NAME,
    DEMO_PROJECT_NAME_FR,
    seed_demo_project,
)
from app.services.feature_gates import require_project_limit, require_question_limit
from app.services.guide_parser import parse_guide_csv
from app.services.workspace import accessible_workspace_ids, can_edit, get_member_role

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    current_count = (
        db.query(Project)
        .filter(Project.company_id == company.id, Project.is_demo == False)  # noqa: E712
        .count()
    )
    require_project_limit(company, current_count)
    require_question_limit(company, len(body.questions))
    project = Project(
        company_id=company.id,
        name=body.name,
        language=body.language,
        interview_duration_minutes=body.interview_duration_minutes,
        system_prompt=body.system_prompt or Project.__table__.columns["system_prompt"].default.arg,
        research_objective=body.research_objective or None,
        decision_to_inform=body.decision_to_inform or None,
        target_customer_description=body.target_customer_description or None,
        panel_collection_enabled=body.panel_collection_enabled,
        warmup_enabled=body.warmup_enabled,
    )
    db.add(project)
    db.flush()

    for idx, q in enumerate(body.questions):
        question = InterviewGuideQuestion(
            project_id=project.id,
            section_index=q.section_index,
            section_title=q.section_title,
            question_index=q.question_index,
            main_question=q.main_question,
            interview_notes=q.interview_notes or "",
            desired_learning=q.desired_learning or "",
            sort_order=idx,
        )
        db.add(question)

    for idx, sq in enumerate(body.screening_questions):
        db.add(ScreeningQuestion(
            project_id=project.id,
            sort_order=idx,
            question=sq.question,
            options=json.dumps(sq.options),
            disqualifying_options=json.dumps(sq.disqualifying_options),
        ))

    db.commit()
    db.refresh(project)

    return _project_to_response(project)


@router.post("/demo", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_demo_project(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    """Create (or return existing) a pre-populated demo project for this company.

    Idempotent: if the user already has a project named `DEMO_PROJECT_NAME`, it is
    returned instead of creating a duplicate. This also bypasses the project limit
    so free-tier users can still try the demo even if they're at 1/1 usage.
    """
    # The demo can exist under either the EN or FR name depending on the
    # company's language at seeding time — match on either so we stay
    # idempotent after a language switch.
    existing = (
        db.query(Project)
        .filter(
            Project.company_id == company.id,
            Project.is_demo == True,  # noqa: E712
            Project.name.in_([DEMO_PROJECT_NAME, DEMO_PROJECT_NAME_FR]),
        )
        .first()
    )
    if existing:
        return _project_to_response(existing)

    # Deliberately bypass project/question limits for the demo so a free-tier user
    # can always try it. We cap at one demo per company via the name check above.
    project = seed_demo_project(db, company.id)
    return _project_to_response(project)


@router.post("/import", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def import_project_from_csv(
    name: str = Form(...),
    language: str = Form("en"),
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    current_count = (
        db.query(Project)
        .filter(Project.company_id == company.id, Project.is_demo == False)  # noqa: E712
        .count()
    )
    require_project_limit(company, current_count)

    content = await csv_file.read()
    questions = parse_guide_csv(content)
    require_question_limit(company, len(questions))

    project = Project(
        company_id=company.id,
        name=name,
        language=language,
    )
    db.add(project)
    db.flush()

    for idx, q in enumerate(questions):
        question = InterviewGuideQuestion(
            project_id=project.id,
            section_index=q.section_index,
            section_title=q.section_title,
            question_index=q.question_index,
            main_question=q.main_question,
            interview_notes=q.interview_notes or "",
            desired_learning=q.desired_learning or "",
            sort_order=idx,
        )
        db.add(question)

    db.commit()
    db.refresh(project)

    return _project_to_response(project)


@router.get("/", response_model=list[ProjectListResponse])
def list_projects(
    archived: bool = Query(False, description="Return archived projects instead of active ones"),
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[ProjectListResponse]:
    workspace_ids = accessible_workspace_ids(db, company)
    query = db.query(Project).filter(Project.company_id.in_(workspace_ids))
    if archived:
        query = query.filter(Project.archived_at.isnot(None))
    else:
        query = query.filter(Project.archived_at.is_(None))
    projects = query.order_by(Project.created_at.desc()).all()

    from app.models.interview import ProjectAnalysis
    results = []
    for p in projects:
        completed_participants = [pt for pt in p.participants if pt.status == "completed"]
        completed = len(completed_participants)
        in_progress = sum(1 for pt in p.participants if pt.status == "in_progress")
        # Most recent completion so the dashboard can show "N days since last
        # response" without a separate project-state fetch per card. Guard
        # against participants with a completed status but no timestamp
        # (legacy / partially-seeded data).
        last_response_at = None
        completion_timestamps = [
            pt.completed_at for pt in completed_participants if pt.completed_at is not None
        ]
        if completion_timestamps:
            last_response_at = max(completion_timestamps)
        latest_analysis = (
            db.query(ProjectAnalysis)
            .filter(ProjectAnalysis.project_id == p.id)
            .order_by(ProjectAnalysis.version.desc())
            .first()
        )
        results.append(
            ProjectListResponse(
                id=p.id,
                name=p.name,
                language=p.language,
                created_at=p.created_at,
                archived_at=p.archived_at,
                question_count=len(p.guide_questions),
                completed_count=completed,
                in_progress_count=in_progress,
                analysis_status=latest_analysis.status if latest_analysis else None,
                last_response_at=last_response_at,
                is_demo=getattr(p, "is_demo", False),
            )
        )
    return results


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    project = _get_project_or_404(project_id, company.id, db)
    return _project_to_response(project)


@router.get("/{project_id}/state")
def get_project_state(
    project_id: str,
    include_ai_summary: bool = Query(True, description="Ask Claude for a one-sentence headline"),
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Return a glanceable state-of-the-study summary for the Overview tab.

    Combines deterministic counts (participants, staleness, analysis gap)
    with an optional AI-written one-sentence headline so the researcher
    knows immediately what to do next. See
    ``services.project_state.compute_project_state`` for the full contract.
    """
    project = _get_project_or_404(project_id, company.id, db)
    from app.services.project_state import compute_project_state

    return compute_project_state(
        project,
        db,
        include_ai_summary=include_ai_summary,
    )


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    body: ProjectCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    project = _get_project_or_404(project_id, company.id, db)

    project.name = body.name
    project.language = body.language
    project.interview_duration_minutes = body.interview_duration_minutes
    project.research_objective = body.research_objective or None
    project.welcome_message = body.welcome_message or None
    project.decision_to_inform = body.decision_to_inform or None
    project.target_customer_description = body.target_customer_description or None
    project.panel_collection_enabled = body.panel_collection_enabled
    project.warmup_enabled = body.warmup_enabled
    if body.system_prompt is not None:
        project.system_prompt = body.system_prompt

    # Replace all questions and screening questions
    for q in list(project.guide_questions):
        db.delete(q)
    for sq in list(project.screening_questions):
        db.delete(sq)
    db.flush()

    for idx, q in enumerate(body.questions):
        question = InterviewGuideQuestion(
            project_id=project.id,
            section_index=q.section_index,
            section_title=q.section_title,
            question_index=q.question_index,
            main_question=q.main_question,
            interview_notes=q.interview_notes or "",
            desired_learning=q.desired_learning or "",
            sort_order=idx,
        )
        db.add(question)

    for idx, sq in enumerate(body.screening_questions):
        db.add(ScreeningQuestion(
            project_id=project.id,
            sort_order=idx,
            question=sq.question,
            options=json.dumps(sq.options),
            disqualifying_options=json.dumps(sq.disqualifying_options),
        ))

    db.commit()
    db.refresh(project)
    return _project_to_response(project)


@router.patch("/{project_id}/settings", response_model=ProjectResponse)
def patch_project_settings(
    project_id: str,
    body: ProjectSettingsPatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    """Update individual project settings (e.g. panel_collection_enabled)."""
    project = _get_project_or_404(project_id, company.id, db)
    if body.panel_collection_enabled is not None:
        project.panel_collection_enabled = body.panel_collection_enabled
    if body.warmup_enabled is not None:
        project.warmup_enabled = body.warmup_enabled
    db.commit()
    db.refresh(project)
    return _project_to_response(project)


@router.patch("/{project_id}/archive", status_code=status.HTTP_200_OK)
def archive_project(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    project = _get_project_or_404(project_id, company.id, db)
    project.archived_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": project.id, "archived_at": project.archived_at.isoformat()}


@router.patch("/{project_id}/unarchive", status_code=status.HTTP_200_OK)
def unarchive_project(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    project = _get_project_or_404(project_id, company.id, db)
    project.archived_at = None
    db.commit()
    return {"id": project.id, "archived_at": None}


@router.patch("/{project_id}/questions/{question_id}", response_model=QuestionResponse)
def patch_question(
    project_id: str,
    question_id: str,
    body: QuestionPatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> QuestionResponse:
    """Update researcher_notes and/or deprecated_at for a guide question."""
    project = _get_project_or_404(project_id, company.id, db)

    question = (
        db.query(InterviewGuideQuestion)
        .filter(
            InterviewGuideQuestion.id == question_id,
            InterviewGuideQuestion.project_id == project.id,
        )
        .first()
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    if body.main_question is not None:
        question.main_question = body.main_question
    if body.question_index is not None:
        question.question_index = body.question_index
    if body.section_title is not None:
        question.section_title = body.section_title
    if body.section_index is not None:
        question.section_index = body.section_index
    if body.researcher_notes is not None:
        question.researcher_notes = body.researcher_notes
    if body.interview_notes is not None:
        question.interview_notes = body.interview_notes
    if body.desired_learning is not None:
        question.desired_learning = body.desired_learning
    # Allow setting deprecated_at to a value or clearing it (None = un-deprecate)
    if "deprecated_at" in body.model_fields_set:
        question.deprecated_at = body.deprecated_at

    db.commit()
    db.refresh(question)

    return QuestionResponse(
        id=question.id,
        section_index=question.section_index,
        section_title=question.section_title,
        question_index=question.question_index,
        main_question=question.main_question,
        interview_notes=question.interview_notes,
        desired_learning=question.desired_learning,
        researcher_notes=question.researcher_notes,
        deprecated_at=question.deprecated_at,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_or_404(project_id: str, company_id: str, db: Session) -> Project:
    """Fetch a project accessible by this company (as owner or workspace member).

    Projects are accessible if the caller's company owns them, OR if the caller
    is a member of the workspace that owns the project.
    """
    # Direct ownership fast path
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is not None:
        return project

    # Workspace membership path — resolve caller to a Company and check access
    caller = db.query(Company).filter(Company.id == company_id).first()
    if caller is not None:
        workspace_ids = accessible_workspace_ids(db, caller)
        project = (
            db.query(Project)
            .filter(
                Project.id == project_id,
                Project.company_id.in_(workspace_ids),
            )
            .first()
        )
        if project is not None:
            return project

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _project_to_response(project: Project) -> ProjectResponse:
    questions = [
        QuestionResponse(
            id=q.id,
            section_index=q.section_index,
            section_title=q.section_title,
            question_index=q.question_index,
            main_question=q.main_question,
            interview_notes=q.interview_notes,
            desired_learning=q.desired_learning,
            researcher_notes=q.researcher_notes,
            deprecated_at=q.deprecated_at,
        )
        for q in sorted(project.guide_questions, key=lambda q: (q.section_index, q.question_index))
    ]
    screening = [
        ScreeningQuestionResponse(
            id=sq.id,
            question=sq.question,
            options=sq.options_list,
            disqualifying_options=sq.disqualifying_options_list,
            sort_order=sq.sort_order,
        )
        for sq in sorted(project.screening_questions, key=lambda sq: sq.sort_order)
    ]
    return ProjectResponse(
        id=project.id,
        company_id=project.company_id,
        name=project.name,
        language=project.language,
        interview_duration_minutes=project.interview_duration_minutes,
        system_prompt=project.system_prompt,
        research_objective=project.research_objective,
        welcome_message=project.welcome_message,
        panel_collection_enabled=getattr(project, "panel_collection_enabled", True),
        warmup_enabled=getattr(project, "warmup_enabled", True),
        decision_to_inform=getattr(project, "decision_to_inform", None),
        target_customer_description=getattr(project, "target_customer_description", None),
        is_demo=getattr(project, "is_demo", False),
        created_at=project.created_at,
        questions=questions,
        screening_questions=screening,
    )
