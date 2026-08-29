import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.dependencies import (
    get_accessible_project_or_404 as _get_project_or_404,
    get_editable_project_or_404 as _get_editable_project_or_404,
    get_current_company,
    require_verified_company,
    get_db,
)
from app.models.company import Company
from app.models.project import (
    STIMULUS_KINDS,
    InterviewGuideQuestion,
    Project,
    ScreeningQuestion,
    StimulusAsset,
)
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
    StimulusCreate,
    StimulusPatch,
    StimulusResponse,
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
from app.services.storage import (
    IMAGE_EXTENSIONS,
    MAX_IMAGE_UPLOAD_MB,
    matches_image_magic,
    upload_image,
)
from app.services.study_provisioning import study_for_new_project
from app.services.workspace import accessible_workspace_ids, can_edit, get_member_role

router = APIRouter(prefix="/projects", tags=["projects"])

logger = logging.getLogger(__name__)


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

    # Participant-facing content defaults to the researcher's own language
    # (the copilot writes guide/screener content in project.language), but
    # an explicit choice from the client always wins.
    project_language = body.language or getattr(
        company, "preferred_language", None
    ) or "en"

    project = Project(
        company_id=company.id,
        study_id=study.id,
        name=body.name,
        language=project_language,
        interview_duration_minutes=body.interview_duration_minutes,
        system_prompt=body.system_prompt or Project.__table__.columns["system_prompt"].default.arg,
        research_objective=body.research_objective or None,
        decision_to_inform=body.decision_to_inform or None,
        target_customer_description=body.target_customer_description or None,
        panel_collection_enabled=body.panel_collection_enabled,
        warmup_enabled=body.warmup_enabled,
        profile_before_interview=body.profile_before_interview,
    )
    _apply_branding_fields(project, body, company, db)
    _inherit_branding_defaults(project, body, company, db)
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
        completed_participants = [pt for pt in p.participants if pt.counts_for_research]
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
    project = _get_editable_project_or_404(project_id, company.id, db)

    # Partial by field: only keys actually present in the request body are
    # written. The Setup tab saves one section at a time (objective + welcome
    # message, then screening questions), so a payload that omits
    # `welcome_message` must leave the saved welcome message alone rather than
    # nulling it. Same for the questions / screening_questions collections,
    # which are replaced wholesale but only when sent.
    sent = body.model_fields_set

    # Editing participant-facing free text invalidates its cached translations.
    if "name" in sent:
        if (project.name or "").strip() != (body.name or "").strip():
            project.name_translations = None
        project.name = body.name
    if "research_context" in sent:
        if (project.research_context or "").strip() != ((body.research_context or "").strip()):
            project.research_context_translations = None
        project.research_context = body.research_context or None

    # `language` is nullable on the schema to mean "inherit the workspace
    # language" at creation time; on update an absent/blank value means
    # "leave it as it is", never "clear it".
    if body.language:
        project.language = body.language
    if "interview_duration_minutes" in sent:
        project.interview_duration_minutes = body.interview_duration_minutes
    for field in (
        "research_objective",
        "welcome_message",
        "decision_to_inform",
        "target_customer_description",
    ):
        if field in sent:
            setattr(project, field, getattr(body, field) or None)
    for flag in ("panel_collection_enabled", "warmup_enabled", "profile_before_interview"):
        if flag in sent:
            setattr(project, flag, getattr(body, flag))
    if body.system_prompt is not None:
        project.system_prompt = body.system_prompt

    # Replace all questions and screening questions
    if "questions" in sent:
        for q in list(project.guide_questions):
            db.delete(q)
    if "screening_questions" in sent:
        for sq in list(project.screening_questions):
            db.delete(sq)
    db.flush()

    for idx, q in enumerate(body.questions if "questions" in sent else []):
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

    for idx, sq in enumerate(body.screening_questions if "screening_questions" in sent else []):
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


def _inherit_branding_defaults(project: Project, body, company: Company, db: Session) -> None:
    """Prefill a NEW study's branding from the workspace defaults.

    Field-by-field: an explicit value in the create payload always wins.
    Downgrade-safe: if the saved defaults include theming (branded mode /
    colour / font) but the workspace no longer has the ``custom_branding``
    entitlement, the theming is dropped (mode falls back to standard)
    instead of failing project creation.
    """
    defaults = company.branding_defaults_dict
    if not defaults:
        return

    if body.researcher_name is None and defaults.get("researcher_name"):
        project.researcher_name = defaults["researcher_name"]
    if body.researcher_logo_url is None and defaults.get("researcher_logo_url"):
        project.researcher_logo_url = defaults["researcher_logo_url"]
    if body.privacy_policy_url is None and defaults.get("privacy_policy_url"):
        project.privacy_policy_url = defaults["privacy_policy_url"]

    wants_theming = (
        defaults.get("branding_mode") == "branded"
        or defaults.get("brand_primary_color")
        or defaults.get("brand_font")
    )
    can_theme = True
    if wants_theming:
        from app.services.billing_service import workspace_has_feature

        can_theme = workspace_has_feature(db, company, "custom_branding")

    if body.branding_mode is None and defaults.get("branding_mode"):
        mode = defaults["branding_mode"]
        if mode == "branded" and not can_theme:
            mode = "standard"
        if mode in {"standard", "branded", "anonymous"}:
            project.branding_mode = mode
    if body.brand_primary_color is None and defaults.get("brand_primary_color") and can_theme:
        project.brand_primary_color = defaults["brand_primary_color"]
    if body.brand_font is None and defaults.get("brand_font") and can_theme:
        project.brand_font = defaults["brand_font"]


def _apply_branding_fields(project: Project, body, company: Company, db: Session) -> None:
    """Apply participant-facing identity/branding fields from a create or
    settings-patch payload.

    Identity fields (researcher_name / logo / privacy policy) and the
    ``anonymous`` mode are free. Visual theming — ``branded`` mode, a brand
    colour, or a font — requires the ``custom_branding`` entitlement
    (legacy Lab/Enterprise tiers, credits Team/Agency/Enterprise plans).
    """
    from app.services.billing_service import workspace_has_feature

    wants_theming = (
        body.branding_mode == "branded"
        or body.brand_primary_color is not None
        or body.brand_font is not None
    )
    if wants_theming and not workspace_has_feature(db, company, "custom_branding"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="custom_branding_required",
        )

    if body.researcher_name is not None:
        project.researcher_name = body.researcher_name.strip() or None
    if body.researcher_logo_url is not None:
        project.researcher_logo_url = body.researcher_logo_url.strip() or None
    if body.privacy_policy_url is not None:
        project.privacy_policy_url = body.privacy_policy_url.strip() or None
    if body.incentive_text is not None:
        project.incentive_text = body.incentive_text.strip()[:300] or None
    if body.branding_mode is not None:
        project.branding_mode = body.branding_mode
    if body.brand_primary_color is not None:
        project.brand_primary_color = body.brand_primary_color
    if body.brand_font is not None:
        project.brand_font = body.brand_font


@router.patch("/{project_id}/settings", response_model=ProjectResponse)
def patch_project_settings(
    project_id: str,
    body: ProjectSettingsPatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    """Update individual project settings (e.g. panel_collection_enabled)."""
    project = _get_editable_project_or_404(project_id, company.id, db)
    # Editing participant-facing free text invalidates its cached translations,
    # exactly as the full PUT does — otherwise a rename here keeps showing
    # participants the old translated study name forever.
    retranslate = False
    if body.name is not None and body.name.strip():
        if (project.name or "").strip() != body.name.strip():
            project.name_translations = None
            retranslate = True
        project.name = body.name.strip()
    if body.panel_collection_enabled is not None:
        project.panel_collection_enabled = body.panel_collection_enabled
    if body.warmup_enabled is not None:
        project.warmup_enabled = body.warmup_enabled
    if body.profile_before_interview is not None:
        project.profile_before_interview = body.profile_before_interview
    if body.interview_mode is not None:
        if body.interview_mode == "realtime_beta" and not getattr(
            company, "beta_features_enabled", False
        ):
            # The Setup toggle is hidden without the opt-in; enforce it here
            # too so a hand-crafted request cannot switch a study onto a
            # beta transport the workspace never agreed to.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "beta_features_disabled",
                    "message": "Enable beta features in Account settings first.",
                },
            )
        project.interview_mode = body.interview_mode
    if body.research_objective is not None:
        project.research_objective = body.research_objective
    if body.research_context is not None:
        if (project.research_context or "").strip() != body.research_context.strip():
            project.research_context_translations = None
            retranslate = True
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
    _apply_branding_fields(project, body, company, db)
    db.commit()
    db.refresh(project)

    if retranslate:
        from app.services.screening_translation import schedule_screening_translation
        schedule_screening_translation(project.id)

    return _project_to_response(project)


@router.post("/{project_id}/branding/logo", response_model=ProjectResponse)
async def upload_branding_logo(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    """Upload a branding logo image and set it as the project's researcher logo.

    Stored in R2 in production (absolute public URL) or under UPLOAD_DIR in
    local dev (served via /files). Same validation as the blog image upload.
    """
    project = _get_editable_project_or_404(project_id, company.id, db)
    ext = IMAGE_EXTENSIONS.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Allowed: PNG, JPEG, WebP, GIF.",
        )
    data = await file.read()
    if len(data) > MAX_IMAGE_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail=f"Image too large. Max size is {MAX_IMAGE_UPLOAD_MB}MB."
        )
    if not matches_image_magic(data, ext):
        raise HTTPException(status_code=415, detail="File content does not match its image type.")
    key = f"project-logos/{project.id}/{uuid.uuid4()}{ext}"
    project.researcher_logo_url = upload_image(data, key)
    db.commit()
    db.refresh(project)
    return _project_to_response(project)


@router.patch("/{project_id}/archive", status_code=status.HTTP_200_OK)
def archive_project(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    project = _get_editable_project_or_404(project_id, company.id, db)
    project.archived_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": project.id, "archived_at": project.archived_at.isoformat()}


@router.patch("/{project_id}/unarchive", status_code=status.HTTP_200_OK)
def unarchive_project(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    project = _get_editable_project_or_404(project_id, company.id, db)
    project.archived_at = None
    db.commit()
    return {"id": project.id, "archived_at": None}


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> None:
    """Permanently delete a study and all its data (GDPR erasure).

    Cascades interviews, transcripts, tags, analyses, memos, guide and
    screening questions, links, and stored audio files. Demo projects can be
    deleted too. The parent Study row survives (surveys may live under it).
    """
    from app.services.deletion import delete_project_data

    project = _get_editable_project_or_404(project_id, company.id, db)
    logger.warning(
        "PROJECT_DELETION: project_id=%s name=%r company_id=%s",
        project.id, project.name, company.id,
    )
    delete_project_data(db, project, delete_files=True)


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
    project = _get_editable_project_or_404(project_id, company.id, db)

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
    project = _get_editable_project_or_404(project_id, company.id, db)

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
    project = _get_editable_project_or_404(project_id, company.id, db)
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
    project = _get_editable_project_or_404(project_id, company.id, db)
    # Clear existing translations so the background job regenerates fresh.
    for sq in project.screening_questions:
        sq.translations = None
    db.commit()
    from app.services.screening_translation import schedule_screening_translation
    schedule_screening_translation(project.id, include_screening=True)
    return {"status": "regenerating"}


@router.post(
    "/{project_id}/screening/{screening_id}/translations/{lang}/generate",
    response_model=ScreeningQuestionResponse,
)
def generate_screening_translation(
    project_id: str,
    screening_id: str,
    lang: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ScreeningQuestionResponse:
    """Synchronously auto-translate this project's screening questions into
    `lang` via Claude (cached on the row; no-op if already present or lang is
    the source), then return this question with its fresh translation. Powers
    the Setup-tab editor's on-select autofill. Best-effort — on a model failure
    the translation is simply absent and the editor falls back to canonical
    text, which the researcher can then fill by hand."""
    project = _get_editable_project_or_404(project_id, company.id, db)
    sq = (
        db.query(ScreeningQuestion)
        .filter(ScreeningQuestion.id == screening_id, ScreeningQuestion.project_id == project.id)
        .first()
    )
    if sq is None:
        raise HTTPException(status_code=404, detail="Screening question not found")

    from app.services.screening_translation import ensure_screening_language
    ensure_screening_language(project, lang, db)
    db.refresh(sq)
    return ScreeningQuestionResponse(
        id=sq.id,
        question=sq.question,
        options=sq.options_list,
        disqualifying_options=sq.disqualifying_options_list,
        sort_order=sq.sort_order,
        translations=sq.translations_dict,
    )


@router.patch("/{project_id}/questions/{question_id}", response_model=QuestionResponse)
def patch_question(
    project_id: str,
    question_id: str,
    body: QuestionPatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> QuestionResponse:
    """Update researcher_notes and/or deprecated_at for a guide question."""
    project = _get_editable_project_or_404(project_id, company.id, db)

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
    if body.clear_stimulus:
        question.stimulus_id = None
    elif body.stimulus_id is not None:
        # Attaching someone else's asset would leak it into this study's
        # interview payload, so the ownership check is not optional.
        if _get_stimulus_or_404(body.stimulus_id, project.id, db) is not None:
            question.stimulus_id = body.stimulus_id

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
        stimulus_id=question.stimulus_id,
    )


# ---------------------------------------------------------------------------
# Stimulus assets
# ---------------------------------------------------------------------------

def _get_stimulus_or_404(
    stimulus_id: str, project_id: str, db: Session
) -> StimulusAsset:
    asset = (
        db.query(StimulusAsset)
        .filter(
            StimulusAsset.id == stimulus_id,
            StimulusAsset.project_id == project_id,
        )
        .first()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Stimulus not found")
    return asset


def _stimulus_to_response(asset: StimulusAsset) -> StimulusResponse:
    return StimulusResponse(
        id=asset.id,
        name=asset.name,
        kind=asset.kind,
        url=asset.url,
        body=asset.body,
        caption=asset.caption,
        ai_description=asset.ai_description,
        sort_order=asset.sort_order,
        question_count=sum(
            1 for q in asset.questions if q.deprecated_at is None
        ),
    )


def _next_stimulus_sort_order(project: Project) -> int:
    return max((a.sort_order for a in project.stimuli), default=-1) + 1


@router.get("/{project_id}/stimuli", response_model=list[StimulusResponse])
def list_stimuli(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[StimulusResponse]:
    """The study's stimulus library."""
    project = _get_project_or_404(project_id, company.id, db)
    return [
        _stimulus_to_response(a)
        for a in sorted(project.stimuli, key=lambda a: a.sort_order)
    ]


@router.post(
    "/{project_id}/stimuli",
    response_model=StimulusResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_stimulus(
    project_id: str,
    body: StimulusCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StimulusResponse:
    """Create a text stimulus (a written concept statement).

    Images come in through ``/stimuli/upload`` instead, which needs the
    multipart body and the magic-byte check.
    """
    project = _get_editable_project_or_404(project_id, company.id, db)
    if body.kind == "image":
        raise HTTPException(
            status_code=400,
            detail="Image stimuli are created through /stimuli/upload.",
        )
    if not (body.body or "").strip():
        raise HTTPException(
            status_code=400, detail="A text stimulus needs its concept text."
        )
    asset = StimulusAsset(
        project_id=project.id,
        name=body.name.strip() or "Concept",
        kind="text",
        body=body.body,
        caption=body.caption,
        ai_description=body.ai_description,
        sort_order=_next_stimulus_sort_order(project),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _stimulus_to_response(asset)


@router.post(
    "/{project_id}/stimuli/upload",
    response_model=StimulusResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_stimulus_image(
    project_id: str,
    file: UploadFile = File(...),
    name: str = Form(...),
    caption: str | None = Form(None),
    ai_description: str | None = Form(None),
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StimulusResponse:
    """Upload an image stimulus (pack shot, ad creative, screen mockup).

    Same storage path and validation as the branding logo: R2 in production,
    UPLOAD_DIR locally, content-type checked against the file's magic bytes.
    """
    project = _get_editable_project_or_404(project_id, company.id, db)
    ext = IMAGE_EXTENSIONS.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Allowed: PNG, JPEG, WebP, GIF.",
        )
    data = await file.read()
    if len(data) > MAX_IMAGE_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large. Max size is {MAX_IMAGE_UPLOAD_MB}MB.",
        )
    if not matches_image_magic(data, ext):
        raise HTTPException(
            status_code=415, detail="File content does not match its image type."
        )
    key = f"stimuli/{project.id}/{uuid.uuid4()}{ext}"
    asset = StimulusAsset(
        project_id=project.id,
        name=(name or "").strip() or "Stimulus",
        kind="image",
        url=upload_image(data, key),
        caption=caption,
        ai_description=ai_description,
        sort_order=_next_stimulus_sort_order(project),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _stimulus_to_response(asset)


@router.patch("/{project_id}/stimuli/{stimulus_id}", response_model=StimulusResponse)
def patch_stimulus(
    project_id: str,
    stimulus_id: str,
    body: StimulusPatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StimulusResponse:
    project = _get_editable_project_or_404(project_id, company.id, db)
    asset = _get_stimulus_or_404(stimulus_id, project.id, db)
    if body.name is not None:
        asset.name = body.name
    if body.body is not None:
        asset.body = body.body
    if body.caption is not None:
        asset.caption = body.caption
    if body.ai_description is not None:
        asset.ai_description = body.ai_description
    if body.sort_order is not None:
        asset.sort_order = body.sort_order
    db.commit()
    db.refresh(asset)
    return _stimulus_to_response(asset)


@router.delete(
    "/{project_id}/stimuli/{stimulus_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_stimulus(
    project_id: str,
    stimulus_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> None:
    """Delete a stimulus. Questions and past turns that referenced it keep
    their rows; the reference is nulled by the FK."""
    project = _get_editable_project_or_404(project_id, company.id, db)
    asset = _get_stimulus_or_404(stimulus_id, project.id, db)
    db.delete(asset)
    db.commit()


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
            stimulus_id=q.stimulus_id,
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
        profile_before_interview=getattr(project, "profile_before_interview", False),
        interview_mode=getattr(project, "interview_mode", "classic") or "classic",
        # Workspace-level beta opt-in, resolved through the owning company:
        # the Setup tab shows the beta transport toggle only when this is on.
        beta_features_enabled=bool(
            getattr(getattr(project, "company", None), "beta_features_enabled", False)
        ),
        decision_to_inform=getattr(project, "decision_to_inform", None),
        target_customer_description=getattr(project, "target_customer_description", None),
        target_participants=getattr(project, "target_participants", None),
        is_demo=getattr(project, "is_demo", False),
        branding_mode=getattr(project, "branding_mode", "standard") or "standard",
        brand_primary_color=getattr(project, "brand_primary_color", None),
        brand_font=getattr(project, "brand_font", None),
        researcher_name=project.researcher_name,
        researcher_logo_url=project.researcher_logo_url,
        privacy_policy_url=project.privacy_policy_url,
        incentive_text=getattr(project, "incentive_text", None),
        created_at=project.created_at,
        questions=questions,
        screening_questions=screening,
        stimuli=[
            _stimulus_to_response(a)
            for a in sorted(project.stimuli, key=lambda a: a.sort_order)
        ],
        plan_context=_plan_context_for_project(project),
    )
