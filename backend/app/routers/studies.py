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

import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.interview import (
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.project import Project
from app.models.study import Study, StudyAnalysis, StudyParticipant
from app.models.survey import Survey, SurveyQuestion, SurveyResponse
from app.schemas.study import (
    GeneratedValidationSurvey,
    ProjectMini,
    QuantifiedThemeReport,
    SoleInstrument,
    StudyAnalysisDetail,
    StudyAnalysisSummary,
    StudyDetail,
    StudyProgress,
    StudySummary,
    SurveyMini,
    ThemeValidationSnapshotSchema,
    ValidationSummarySchema,
)
from app.services.report_export import render_study_report_html, render_decision_report_html
from app.services.study_analysis import trigger_study_analysis, trigger_decision_analysis
from app.services.survey_analytics import build_dashboard
from app.services.validation_surveys import (
    compute_validation_summary,
    generate_validation_survey,
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

    latest_ready = (
        db.query(StudyAnalysis)
        .filter(StudyAnalysis.study_id == study.id, StudyAnalysis.status == "ready")
        .order_by(StudyAnalysis.generated_at.desc())
        .first()
    )
    progress = _compute_progress(
        study,
        survey_minis,
        project_minis,
        report_ready=latest_ready is not None,
    )
    recommended = _recommended_action(progress, surveys, projects)

    return StudyDetail(
        id=study.id,
        name=study.name,
        created_at=study.created_at,
        archived_at=study.archived_at,
        surveys=survey_minis,
        projects=project_minis,
        progress=progress,
        is_demo=any(p.is_demo for p in projects),
        recommended_action=recommended[2] if recommended else None,
        recommended_action_key=recommended[0] if recommended else None,
        recommended_action_params=recommended[1] if recommended else None,
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
    # Sprint 17: card-level progress signals.
    completed_responses = (
        db.query(func.count(SurveyResponse.id))
        .join(Survey, SurveyResponse.survey_id == Survey.id)
        .filter(
            Survey.study_id == study.id,
            SurveyResponse.completed_at.isnot(None),
        )
        .scalar()
        or 0
    )
    completed_interviews = (
        db.query(func.count(Participant.id))
        .join(Project, Participant.project_id == Project.id)
        .filter(
            Project.study_id == study.id,
            Participant.status == "completed",
        )
        .scalar()
        or 0
    )
    has_report = (
        db.query(StudyAnalysis.id)
        .filter(
            StudyAnalysis.study_id == study.id,
            StudyAnalysis.status == "ready",
        )
        .first()
        is not None
    )
    # Memo eligibility: a study can join a cross-study decision memo when it
    # has ANY ready analysis — qualitative (ProjectAnalysis) or mixed-methods
    # (StudyAnalysis). Mirrors gather_study_evidence in study_synthesis.py.
    has_ready_analysis = has_report or (
        db.query(ProjectAnalysis.id)
        .join(Project, ProjectAnalysis.project_id == Project.id)
        .filter(
            Project.study_id == study.id,
            ProjectAnalysis.status == "ready",
        )
        .first()
        is not None
    )
    # Same rule as StudyDetail.is_demo: a study is demo when it holds a
    # seeded showcase project.
    is_demo = (
        db.query(Project.id)
        .filter(
            Project.study_id == study.id,
            Project.archived_at.is_(None),
            Project.is_demo.is_(True),
        )
        .first()
        is not None
    )
    # Single-instrument studies expose their one instrument so the list
    # can open it directly instead of forcing the workspace hop.
    sole_instrument: SoleInstrument | None = None
    if survey_count + project_count == 1:
        if survey_count == 1:
            sole_survey = (
                db.query(Survey)
                .filter(Survey.study_id == study.id, Survey.archived_at.is_(None))
                .first()
            )
            if sole_survey:
                sole_instrument = SoleInstrument(
                    kind="survey",
                    id=sole_survey.id,
                    survey_status=sole_survey.status,
                )
        else:
            sole_project = (
                db.query(Project)
                .filter(Project.study_id == study.id, Project.archived_at.is_(None))
                .first()
            )
            if sole_project:
                sole_instrument = SoleInstrument(kind="interview", id=sole_project.id)

    return StudySummary(
        id=study.id,
        name=study.name,
        created_at=study.created_at,
        archived_at=study.archived_at,
        survey_count=survey_count,
        project_count=project_count,
        participant_count=participant_count,
        completed_response_count=completed_responses,
        completed_interview_count=completed_interviews,
        has_report=has_report,
        has_ready_analysis=has_ready_analysis,
        is_demo=is_demo,
        sole_instrument=sole_instrument,
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
    has_ready_analysis = (
        db.query(ProjectAnalysis.id)
        .filter(
            ProjectAnalysis.project_id == project.id,
            ProjectAnalysis.status == "ready",
        )
        .first()
        is not None
    )
    return ProjectMini(
        id=project.id,
        name=project.name,
        language=project.language,
        interview_link_count=link_count,
        completed_participant_count=completed,
        in_progress_participant_count=in_progress,
        has_ready_analysis=has_ready_analysis,
    )


def _compute_progress(
    study: Study,
    surveys: list[SurveyMini],
    projects: list[ProjectMini],
    *,
    report_ready: bool = False,
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
        # Sprint 11 fills this in based on the presence of a ready StudyAnalysis.
        report_ready_placeholder=report_ready,
    )


def _recommended_action(
    progress: StudyProgress,
    surveys: list[Survey],
    projects: list[Project],
) -> tuple[str, dict[str, int], str] | None:
    """Server-computed next-action prompt for the Study Overview chip.

    Order matches the progress-checklist order so the prompt always
    points at the next un-done step. Returns None when the study is
    fully complete (or empty — caller decides what to show).

    Returns (key, params, english_text). The key + params let the
    frontend render the prompt in the user's UI language; the English
    text is kept as a fallback for older clients.
    """

    if not surveys:
        return (
            "create_survey",
            {},
            "Create a screener survey to start collecting responses.",
        )

    if not progress.has_live_survey:
        return (
            "publish_survey",
            {},
            "Publish your survey to start collecting responses.",
        )

    if progress.total_completed_responses == 0:
        return (
            "share_survey_link",
            {},
            "Share your survey link to collect the first responses.",
        )

    if progress.total_completed_responses < 30:
        remaining = 30 - progress.total_completed_responses
        plural = "response" if remaining == 1 else "responses"
        # NOTE: the param is named `count` because i18next pluralization
        # on the frontend keys plural selection off `count` specifically.
        return (
            "collect_more_responses",
            {"count": remaining},
            f"Keep collecting — {remaining} more {plural} until inference-grade thresholds.",
        )

    if not projects:
        return (
            "open_dashboard_invite",
            {},
            "Open the survey dashboard to filter respondents and invite them to AI interviews.",
        )

    if progress.interviews_completed == 0:
        return (
            "invite_interviews",
            {},
            "Use the Screener Bridge to invite high-signal respondents to AI interviews.",
        )

    if progress.interviews_completed < 5:
        remaining = 5 - progress.interviews_completed
        return (
            "collect_more_interviews",
            {"count": remaining},
            f"Conduct {remaining} more interview(s) before generating the mixed-methods report.",
        )

    return (
        "generate_report",
        {},
        "Generate the mixed-methods report to synthesize quanti + quali into one view.",
    )


# ── Sprint 11: Quantified Themes report ──────────────────────────────


def _get_study_or_404(db: Session, study_id: str, company: Company) -> Study:
    study = (
        db.query(Study)
        .filter(Study.id == study_id, Study.company_id == company.id)
        .first()
    )
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study


def _analysis_to_summary(a: StudyAnalysis) -> StudyAnalysisSummary:
    return StudyAnalysisSummary(
        id=a.id,
        study_id=a.study_id,
        version=a.version,
        status=a.status,  # type: ignore[arg-type]
        error=a.error,
        created_at=a.created_at,
        generated_at=a.generated_at,
    )


def _analysis_to_detail(a: StudyAnalysis) -> StudyAnalysisDetail:
    report = None
    if a.report:
        try:
            report = QuantifiedThemeReport.model_validate(json.loads(a.report))
        except Exception:  # noqa: BLE001 — be honest about malformed payloads
            report = None
    return StudyAnalysisDetail(
        id=a.id,
        study_id=a.study_id,
        version=a.version,
        status=a.status,  # type: ignore[arg-type]
        error=a.error,
        created_at=a.created_at,
        generated_at=a.generated_at,
        report=report,
    )


@router.post(
    "/{study_id}/analyses",
    response_model=StudyAnalysisDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_analysis(
    study_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StudyAnalysisDetail:
    """Trigger generation of a new **Decision report** (the canonical study report).

    Synchronous (~10-20s). Produces the composed superset (approach B): it reuses
    the interview ProjectAnalysis for the qualitative dimension (themes / personas
    / journey / activated recs) and layers the survey signal + an integration
    (verdict / joint display / gaps) on top — stored as schema:"decision_v1" and
    served by report.html via the dual-path renderer.

    The JSON response's `report` is null for this shape (it is not a
    Quantified-Themes payload); the document is fetched from report.html. The
    legacy `trigger_study_analysis` generator + Quantified-Themes renderer remain
    for previously-stored reports.
    """

    study = _get_study_or_404(db, study_id, company)
    analysis = trigger_decision_analysis(db, study)
    return _analysis_to_detail(analysis)


@router.get(
    "/{study_id}/analyses",
    response_model=list[StudyAnalysisSummary],
)
def list_analyses(
    study_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[StudyAnalysisSummary]:
    study = _get_study_or_404(db, study_id, company)
    rows = (
        db.query(StudyAnalysis)
        .filter(StudyAnalysis.study_id == study.id)
        .order_by(StudyAnalysis.created_at.desc())
        .all()
    )
    return [_analysis_to_summary(r) for r in rows]


@router.get(
    "/{study_id}/analyses/latest",
    response_model=StudyAnalysisDetail | None,
)
def get_latest_analysis(
    study_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StudyAnalysisDetail | None:
    """Returns the most recent ready analysis, or None when none exist.

    Returning None (200 OK with null body) is intentional — the frontend
    distinguishes "no analysis yet" from "an analysis errored" by
    checking status on the listing endpoint, not this one.
    """

    study = _get_study_or_404(db, study_id, company)
    a = (
        db.query(StudyAnalysis)
        .filter(StudyAnalysis.study_id == study.id, StudyAnalysis.status == "ready")
        .order_by(StudyAnalysis.generated_at.desc())
        .first()
    )
    return _analysis_to_detail(a) if a else None


@router.get(
    "/{study_id}/analyses/{analysis_id}",
    response_model=StudyAnalysisDetail,
)
def get_analysis(
    study_id: str,
    analysis_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StudyAnalysisDetail:
    study = _get_study_or_404(db, study_id, company)
    a = (
        db.query(StudyAnalysis)
        .filter(
            StudyAnalysis.id == analysis_id,
            StudyAnalysis.study_id == study.id,
        )
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _analysis_to_detail(a)


@router.get(
    "/{study_id}/analyses/{analysis_id}/report.html",
    response_class=HTMLResponse,
)
def export_study_report(
    study_id: str,
    analysis_id: str,
    embed: bool = False,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Render a ready Quantified Themes analysis as a standalone,
    print-ready HTML research report.

    ``analysis_id`` accepts the literal ``latest`` to export the most
    recent ready analysis. Charts are drawn server-side from the same
    survey aggregates the generation pipeline used, so the document
    always matches the study's actual data. ``embed=1`` drops the floating
    print toolbar — used by the in-app Reports tab, which embeds this very
    document so the UI and the export can never diverge.
    """

    study = _get_study_or_404(db, study_id, company)
    if analysis_id == "latest":
        analysis = (
            db.query(StudyAnalysis)
            .filter(
                StudyAnalysis.study_id == study.id,
                StudyAnalysis.status == "ready",
            )
            .order_by(StudyAnalysis.generated_at.desc())
            .first()
        )
    else:
        analysis = (
            db.query(StudyAnalysis)
            .filter(
                StudyAnalysis.id == analysis_id,
                StudyAnalysis.study_id == study.id,
                StudyAnalysis.status == "ready",
            )
            .first()
        )
    if analysis is None or not analysis.report:
        raise HTTPException(status_code=404, detail="No ready analysis to export.")

    # Source surveys only — validation micro-surveys are folded into the
    # per-theme agreement rows, charting their raw questions would duplicate.
    surveys = (
        db.query(Survey)
        .filter(
            Survey.study_id == study.id,
            Survey.archived_at.is_(None),
            Survey.source_analysis_id.is_(None),
        )
        .order_by(Survey.created_at)
        .all()
    )
    dashboards = [
        build_dashboard(db, s, lang=company.preferred_language or "en")
        for s in surveys
    ]
    validation = compute_validation_summary(db, analysis)

    project_ids = [
        p.id
        for p in db.query(Project)
        .filter(Project.study_id == study.id, Project.archived_at.is_(None))
        .all()
    ]
    participants = []
    turn_counts: dict[str, int] = {}
    if project_ids:
        participants = (
            db.query(Participant)
            .filter(
                Participant.project_id.in_(project_ids),
                Participant.status == "completed",
            )
            .order_by(Participant.completed_at)
            .limit(50)
            .all()
        )
        if participants:
            rows = (
                db.query(InterviewTurn.participant_id, func.count(InterviewTurn.id))
                .filter(InterviewTurn.participant_id.in_([p.id for p in participants]))
                .group_by(InterviewTurn.participant_id)
                .all()
            )
            turn_counts = dict(rows)

    # Dual-path: a decision_v1 analysis renders the composed superset Decision
    # report (qual from the ProjectAnalysis + these survey charts + integration);
    # legacy Quantified-Themes reports render exactly as before.
    try:
        _rep = json.loads(analysis.report)
    except (TypeError, ValueError):
        _rep = {}
    if isinstance(_rep, dict) and _rep.get("schema") == "decision_v1":
        from app.services.study_analysis import _latest_ready_project_analysis
        pa = _latest_ready_project_analysis(db, study)
        html_doc = render_decision_report_html(
            study,
            pa,
            dashboards,
            _rep,
            participants,
            turn_counts,
            company_name=company.name,
            include_toolbar=not embed,
        )
    else:
        html_doc = render_study_report_html(
            study,
            analysis,
            dashboards,
            validation,
            participants,
            turn_counts,
            company_name=company.name,
            include_toolbar=not embed,
        )
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", study.name).strip("_") or "study"
    filename = f"{slug}_report_v{analysis.version}.html"
    return HTMLResponse(
        content=html_doc,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Sprint 14: Validation surveys (closing the loop) ─────────────────


def _get_analysis_or_404(
    db: Session, study: Study, analysis_id: str
) -> StudyAnalysis:
    a = (
        db.query(StudyAnalysis)
        .filter(
            StudyAnalysis.id == analysis_id,
            StudyAnalysis.study_id == study.id,
        )
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return a


@router.post(
    "/{study_id}/analyses/{analysis_id}/validation-survey",
    response_model=GeneratedValidationSurvey,
    status_code=status.HTTP_201_CREATED,
)
def create_validation_survey(
    study_id: str,
    analysis_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> GeneratedValidationSurvey:
    """Spawn a validation micro-survey from a ready analysis.

    Each theme in the analysis report becomes one Likert question. The
    survey lands in draft status — researcher edits + publishes
    manually (Decision 4: no auto-send).
    """

    study = _get_study_or_404(db, study_id, company)
    analysis = _get_analysis_or_404(db, study, analysis_id)
    if analysis.status != "ready":
        raise HTTPException(
            status_code=400,
            detail="Analysis is not ready — wait for generation to finish.",
        )

    try:
        survey = generate_validation_survey(db, analysis)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GeneratedValidationSurvey(
        survey_id=survey.id,
        study_id=survey.study_id,
        name=survey.name,
        question_count=len(survey.questions),
    )


@router.get(
    "/{study_id}/analyses/{analysis_id}/validation",
    response_model=ValidationSummarySchema | None,
)
def get_validation_summary(
    study_id: str,
    analysis_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ValidationSummarySchema | None:
    """Per-theme agreement for the validation survey spawned from this analysis.

    Returns null when no validation survey has been generated yet. When
    one exists but has no responses, returns the summary with an empty
    per_theme dict so the UI can render the awaiting-responses state.
    """

    study = _get_study_or_404(db, study_id, company)
    analysis = _get_analysis_or_404(db, study, analysis_id)
    summary = compute_validation_summary(db, analysis)
    if summary is None:
        return None
    return ValidationSummarySchema(
        survey_id=summary.survey_id,
        survey_name=summary.survey_name,
        survey_status=summary.survey_status,
        n_responses=summary.n_responses,
        n_completed=summary.n_completed,
        per_theme={
            idx: ThemeValidationSnapshotSchema(
                theme_index=snap.theme_index,
                n_answered=snap.n_answered,
                agreement_pct=snap.agreement_pct,
                ci_low=snap.ci_low,
                ci_high=snap.ci_high,
                distribution=snap.distribution,
            )
            for idx, snap in summary.per_theme.items()
        },
    )
