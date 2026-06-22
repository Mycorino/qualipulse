import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.dependencies import (
    get_accessible_project_or_404 as _get_project_or_404,
    get_current_company,
    require_verified_company,
    get_db,
)
from app.models.company import Company
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion
from app.schemas.project import (
    GuideQuestionAdd,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectSettingsPatch,
    QuestionPatch,
    QuestionResponse,
    ScreeningQuestionCreate,
    ScreeningQuestionResponse,
    ScreeningTranslationPatch,
)
from app.services.analytics import emit_event
from app.services.demo_seeder import (
    DEMO_PROJECT_NAME,
    DEMO_PROJECT_NAME_FR,
    seed_demo_project,
)
from app.services import billing_service
from app.services.feature_gates import require_project_limit, require_question_limit
from app.services.guide_parser import parse_guide_csv
from app.services.study_provisioning import study_for_new_project
from app.services.workspace import accessible_workspace_ids, can_edit, get_member_role

router = APIRouter(prefix="/projects", tags=["projects"])


def _enforce_project_limit(db: Session, company: Company, current_count: int) -> None:
    """Gate project creation by plan.

    Credits-based accounts are NOT limited by project count — usage is
    gated by interview credits (1 credit = 1 completed interview), so a
    researcher can spin up as many studies as they like. Only genuine
    legacy-tier accounts fall through to the per-tier ``max_projects``
    cap in ``feature_gates``.
    """
    sub = billing_service.get_current_subscription(db, company.id)
    plan = billing_service.get_plan(db, sub.plan_id) if sub else None
    if plan is not None and not plan.is_legacy:
        return  # credits-native — no project-count cap
    require_project_limit(company, current_count)


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(require_verified_company),
) -> ProjectResponse:
    current_count = (
        db.query(Project)
        .filter(Project.company_id == company.id, Project.is_demo == False)  # noqa: E712
        .count()
    )
    _enforce_project_limit(db, company, current_count)
    require_question_limit(company, len(body.questions))

    # Sprint 15: every project belongs to a Study. Use the one the caller
    # named (e.g. an interview round added from a Study Overview) or
    # auto-create one named after the project.
    try:
        study = study_for_new_project(db, company.id, body.name, body.study_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Study not found")

    project = Project(
        company_id=company.id,
        study_id=study.id,
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

    # Auto-translate participant-facing copy (study name + screening questions)
    # into the supported languages so the interview is native (background;
    # researcher can edit later).
    from app.services.screening_translation import schedule_screening_translation
    schedule_screening_translation(project.id)

    # Fire `study_created` only on the first non-demo project for this
    # company — the activation milestone, not every project.
    is_first_real = current_count == 0
    emit_event(
        "study_created",
        company=company,
        project_id=str(project.id),
        is_first=is_first_real,
        question_count=len(body.questions),
    )

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
    company: Company = Depends(require_verified_company),
) -> ProjectResponse:
    current_count = (
        db.query(Project)
        .filter(Project.company_id == company.id, Project.is_demo == False)  # noqa: E712
        .count()
    )
    _enforce_project_limit(db, company, current_count)

    content = await csv_file.read()
    questions = parse_guide_csv(content)
    require_question_limit(company, len(questions))

    # Sprint 15: CSV imports auto-create their parent Study like any other
    # project. (No study_id form field — imports always start a new Study.)
    study = study_for_new_project(db, company.id, name, None)

    project = Project(
        company_id=company.id,
        study_id=study.id,
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

    # Wave E — bulk-load plan context for all listed projects in one
    # query. The dashboard card renders "Step N of M in <plan name>"
    # when a project is the drafted step of a research plan.
    plan_contexts_by_project = _bulk_plan_contexts(
        db, [p.id for p in projects]
    )

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
                plan_context=plan_contexts_by_project.get(p.id),
            )
        )
    return results


def _bulk_plan_contexts(db: Session, project_ids: list[str]) -> dict:
    """Wave E — for each project_id that is linked to a ResearchPlanStep,
    return a dict {project_id: PlanContext(plan_id, plan_name,
    step_index, total_steps, step_method)}. One query for the steps
    that match, one for the plans + step counts. Projects with no
    plan link map to absent — caller defaults to None."""
    from app.models.research_plan import ResearchPlan, ResearchPlanStep
    from app.schemas.project import PlanContext

    if not project_ids:
        return {}
    steps = (
        db.query(ResearchPlanStep)
        .filter(ResearchPlanStep.project_id.in_(project_ids))
        .all()
    )
    if not steps:
        return {}
    plan_ids = list({s.plan_id for s in steps})
    plans = {
        p.id: p
        for p in db.query(ResearchPlan)
        .filter(ResearchPlan.id.in_(plan_ids))
        .all()
    }
    # Count steps per plan in a single grouped query (works on Postgres
    # + SQLite). For the small N here a list-comprehension over each
    # plan's `steps` relationship is fine — but we already loaded the
    # steps once, so just count from them.
    step_counts: dict[str, int] = {}
    for s in (
        db.query(ResearchPlanStep)
        .filter(ResearchPlanStep.plan_id.in_(plan_ids))
        .all()
    ):
        step_counts[s.plan_id] = step_counts.get(s.plan_id, 0) + 1

    out: dict = {}
    for s in steps:
        plan = plans.get(s.plan_id)
        if plan is None:
            continue
        out[s.project_id] = PlanContext(
            plan_id=plan.id,
            plan_name=plan.name,
            step_index=s.order_index,
            total_steps=step_counts.get(s.plan_id, 1),
            step_method=s.method,
        )
    return out


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

    # Renaming invalidates cached participant-facing name translations.
    if (project.name or "").strip() != (body.name or "").strip():
        project.name_translations = None
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

    # Canonical name/questions/options just changed → (re)generate localizations.
    from app.services.screening_translation import schedule_screening_translation
    schedule_screening_translation(project.id)

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
    if body.name is not None and body.name.strip():
        project.name = body.name.strip()
    if body.panel_collection_enabled is not None:
        project.panel_collection_enabled = body.panel_collection_enabled
    if body.warmup_enabled is not None:
        project.warmup_enabled = body.warmup_enabled
    if body.research_objective is not None:
        project.research_objective = body.research_objective
    if body.research_context is not None:
        project.research_context = body.research_context
    if body.decision_to_inform is not None:
        project.decision_to_inform = body.decision_to_inform
    if body.timeline is not None:
        project.timeline = body.timeline
    if body.success_criteria is not None:
        project.success_criteria = body.success_criteria
    if body.target_customer_description is not None:
        project.target_customer_description = body.target_customer_description
    if body.interview_duration_minutes is not None:
        project.interview_duration_minutes = body.interview_duration_minutes
    if body.target_participants is not None:
        project.target_participants = body.target_participants
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


@router.post(
    "/{project_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_guide_question(
    project_id: str,
    body: GuideQuestionAdd,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> QuestionResponse:
    """Add one interview-guide question. Section/question indices are
    derived from the section title — a new title starts a new section.
    Powers the Research Copilot's accept flow (and granular Setup edits)."""
    project = _get_project_or_404(project_id, company.id, db)

    live = [q for q in project.guide_questions if q.deprecated_at is None]
    require_question_limit(company, len(live) + 1)

    same_section = [
        q for q in project.guide_questions if q.section_title == body.section_title
    ]
    if same_section:
        section_index = same_section[0].section_index
        question_index = max(q.question_index for q in same_section) + 1
    else:
        section_index = (
            max((q.section_index for q in project.guide_questions), default=-1) + 1
        )
        question_index = 0
    sort_order = (
        max((q.sort_order for q in project.guide_questions), default=-1) + 1
    )

    question = InterviewGuideQuestion(
        project_id=project.id,
        section_index=section_index,
        section_title=body.section_title,
        question_index=question_index,
        main_question=body.main_question,
        interview_notes=body.interview_notes or "",
        desired_learning=body.desired_learning or "",
        researcher_notes=body.researcher_notes or None,
        sort_order=sort_order,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return QuestionResponse.model_validate(question)


@router.post(
    "/{project_id}/screening",
    response_model=ScreeningQuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_screening_question(
    project_id: str,
    body: ScreeningQuestionCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ScreeningQuestionResponse:
    """Add one screening question. Disqualifying options are kept to the
    subset that actually appears in `options`. Powers the Research
    Copilot's accept flow for proposed screeners (and granular edits)."""
    project = _get_project_or_404(project_id, company.id, db)

    options = [o.strip() for o in body.options if o and o.strip()]
    disqualifying = [d for d in body.disqualifying_options if d in options]
    sort_order = (
        max((sq.sort_order for sq in project.screening_questions), default=-1) + 1
    )
    sq = ScreeningQuestion(
        project_id=project.id,
        question=body.question.strip(),
        options=json.dumps(options),
        disqualifying_options=json.dumps(disqualifying),
        sort_order=sort_order,
    )
    db.add(sq)
    db.commit()
    db.refresh(sq)

    from app.services.screening_translation import schedule_screening_translation
    schedule_screening_translation(project.id)

    return ScreeningQuestionResponse(
        id=sq.id,
        question=sq.question,
        options=sq.options_list,
        disqualifying_options=sq.disqualifying_options_list,
        sort_order=sq.sort_order,
        translations=sq.translations_dict,
    )


@router.patch(
    "/{project_id}/screening/{screening_id}/translations",
    response_model=ScreeningQuestionResponse,
)
def patch_screening_translation(
    project_id: str,
    screening_id: str,
    body: ScreeningTranslationPatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ScreeningQuestionResponse:
    """Researcher edit of one language's localized screening text. Options are
    aligned by index to the canonical options; extra/short arrays are clamped."""
    project = _get_project_or_404(project_id, company.id, db)
    sq = (
        db.query(ScreeningQuestion)
        .filter(ScreeningQuestion.id == screening_id, ScreeningQuestion.project_id == project.id)
        .first()
    )
    if sq is None:
        raise HTTPException(status_code=404, detail="Screening question not found")

    lang = (body.lang or "").lower()[:2]
    if not lang:
        raise HTTPException(status_code=400, detail="lang is required")
    canonical = sq.options_list
    # Clamp option labels to the canonical count; pad missing with canonical.
    opts = [
        (body.options[i] if i < len(body.options) and body.options[i] else canonical[i])
        for i in range(len(canonical))
    ]
    d = sq.translations_dict
    d[lang] = {"question": body.question or sq.question, "options": opts}
    sq.translations = json.dumps(d, ensure_ascii=False)
    db.commit()
    db.refresh(sq)
    return ScreeningQuestionResponse(
        id=sq.id,
        question=sq.question,
        options=sq.options_list,
        disqualifying_options=sq.disqualifying_options_list,
        sort_order=sq.sort_order,
        translations=sq.translations_dict,
    )


@router.post("/{project_id}/screening/regenerate-translations", status_code=status.HTTP_202_ACCEPTED)
def regenerate_screening_translations(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    """Re-run auto-translation for all of a project's screening questions
    (background). Used by the 'Regenerate' action in the Setup tab."""
    project = _get_project_or_404(project_id, company.id, db)
    # Clear existing translations so the background job regenerates fresh.
    for sq in project.screening_questions:
        sq.translations = None
    db.commit()
    from app.services.screening_translation import schedule_screening_translation
    schedule_screening_translation(project.id)
    return {"status": "regenerating"}


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

def _plan_context_for_project(project: Project) -> "PlanContext | None":
    """Return PlanContext for one project, or None when not linked to
    any ResearchPlanStep. Used by the detail endpoint where bulk
    loading is overkill."""
    from app.models.research_plan import ResearchPlanStep
    from app.schemas.project import PlanContext

    step = (
        Session.object_session(project)
        .query(ResearchPlanStep)
        .filter(ResearchPlanStep.project_id == project.id)
        .first()
        if Session.object_session(project) is not None
        else None
    )
    if step is None:
        return None
    plan = step.plan
    if plan is None:
        return None
    total = len(plan.steps)
    return PlanContext(
        plan_id=plan.id,
        plan_name=plan.name,
        step_index=step.order_index,
        total_steps=total,
        step_method=step.method,
    )


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
            translations=sq.translations_dict,
        )
        for sq in sorted(project.screening_questions, key=lambda sq: sq.sort_order)
    ]
    return ProjectResponse(
        id=project.id,
        company_id=project.company_id,
        study_id=project.study_id,
        study_name=project.study.name if project.study else None,
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
        target_participants=getattr(project, "target_participants", None),
        is_demo=getattr(project, "is_demo", False),
        created_at=project.created_at,
        questions=questions,
        screening_questions=screening,
        plan_context=_plan_context_for_project(project),
    )
