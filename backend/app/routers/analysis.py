"""Analysis endpoints — generate and retrieve AI synthesis for a project."""

import json
import logging
import re
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.dependencies import (
    get_accessible_project_or_404 as _get_project_or_404,
    get_current_company,
    get_db,
)
from app.models.company import Company
from app.models.interview import AnalysisThemeAnnotation, Participant, ProjectAnalysis
from app.models.project import Project
from app.services.analysis import run_analysis, run_refined_analysis
from app.services.report_export import render_analysis_report_html

logger = logging.getLogger("auto_interview.analysis")
router = APIRouter(prefix="/projects", tags=["analysis"])

ANALYSIS_TIMEOUT_SECONDS = 300  # 5 minutes


class AnalysisTriggerRequest(BaseModel):
    filter_by: str | None = None       # e.g. "profession"
    filter_values: list[str] = []      # e.g. ["Engineer", "Designer"]


class AnnotationUpsertRequest(BaseModel):
    analysis_id: str
    theme_title: str
    status: str  # confirmed | disputed | needs_evidence
    researcher_note: str | None = None


class ResearcherContextRequest(BaseModel):
    researcher_context: str


@router.post("/{project_id}/analysis", status_code=status.HTTP_202_ACCEPTED)
def trigger_analysis(
    project_id: str,
    body: AnalysisTriggerRequest | None = None,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Kick off (or re-run) AI synthesis. Optionally filter participants by an attribute."""
    project = _get_project_or_404(project_id, company.id, db)

    # V4 paywall — AI synthesis is one of the premium product features.
    # Free workspaces can tag / memo on their 3 visible transcripts;
    # running synthesis across the study requires a paid plan or
    # credit-pack purchase (sets has_ever_paid).
    from app.services.paywall import (
        get_visibility_state,
        paywall_payload,
        FREE_PREVIEW_COUNT,
    )

    state = get_visibility_state(db, company)
    if not state.fully_unlocked:
        completed_count = (
            db.query(Participant)
            .filter(
                Participant.project_id == project.id,
                Participant.status == "completed",
            )
            .count()
        )
        locked = max(0, completed_count - FREE_PREVIEW_COUNT)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                **paywall_payload(company, locked),
                "feature": "analysis",
            },
        )

    filter_by = body.filter_by if body else None
    filter_values = body.filter_values if body else []

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

    filters_json = None
    if filter_by and filter_values:
        filters_json = json.dumps({"filter_by": filter_by, "filter_values": filter_values})

    def _run_with_timeout(project_id: str, filter_by, filter_values):
        # Create a fresh session for the background thread — the request-scoped
        # session will be closed by FastAPI after the 202 response returns.
        bg_db = SessionLocal()
        try:
            logger.info("Analysis started for project %s", project_id)
            run_analysis(project_id, bg_db, filter_by, filter_values)
            logger.info("Analysis completed for project %s", project_id)
            # Notify company that analysis is ready (email + Slack)
            try:
                from app.models.project import Project as ProjectModel
                from app.services.email import send_analysis_ready
                from app.services.slack import send_analysis_ready as slack_analysis_ready

                proj = bg_db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
                if proj and proj.company:
                    project_url = f"{settings.APP_BASE_URL}/projects/{project_id}?tab=analysis"
                    send_analysis_ready(
                        proj.company.email,
                        proj.name,
                        project_url,
                        lang=getattr(proj.company, "preferred_language", None) or "en",
                    )

                    # Slack webhook (fire-and-forget, never raises)
                    if getattr(proj.company, "slack_webhook_url", None):
                        latest = (
                            bg_db.query(ProjectAnalysis)
                            .filter(
                                ProjectAnalysis.project_id == project_id,
                                ProjectAnalysis.status == "ready",
                            )
                            .order_by(ProjectAnalysis.version.desc())
                            .first()
                        )
                        top_themes: list[str] = []
                        participant_count = 0
                        if latest:
                            participant_count = latest.participant_count or 0
                            try:
                                report = json.loads(latest.report) if latest.report else {}
                                themes = report.get("themes", []) or []
                                top_themes = [
                                    str(t.get("title", "")).strip()
                                    for t in themes
                                    if isinstance(t, dict) and t.get("title")
                                ][:5]
                            except Exception:
                                pass
                        slack_analysis_ready(
                            proj.company.slack_webhook_url,
                            project_name=proj.name,
                            project_url=project_url,
                            participant_count=participant_count,
                            top_themes=top_themes,
                        )
            except Exception:
                pass
        except Exception as exc:
            logger.error("Analysis failed for project %s: %s", project_id, exc, exc_info=True)
            try:
                analysis = (
                    bg_db.query(ProjectAnalysis)
                    .filter(ProjectAnalysis.project_id == project_id)
                    .order_by(ProjectAnalysis.version.desc())
                    .first()
                )
                if analysis:
                    analysis.status = "failed"
                    analysis.error = str(exc)
                    bg_db.commit()
            except Exception:
                pass
        finally:
            bg_db.close()

    # Run in background thread so the response returns immediately
    thread = threading.Thread(
        target=_run_with_timeout,
        args=(project_id, filter_by, filter_values),
        daemon=True,
    )
    thread.start()

    # Monitor timeout in a watchdog thread
    def _watchdog(t: threading.Thread, project_id: str):
        t.join(timeout=ANALYSIS_TIMEOUT_SECONDS)
        if t.is_alive():
            logger.error("Analysis timed out after 5 minutes for project %s", project_id)
            wd_db = SessionLocal()
            try:
                analysis = (
                    wd_db.query(ProjectAnalysis)
                    .filter(ProjectAnalysis.project_id == project_id)
                    .order_by(ProjectAnalysis.version.desc())
                    .first()
                )
                if analysis and analysis.status == "generating":
                    analysis.status = "failed"
                    analysis.error = "Analysis timed out after 5 minutes"
                    wd_db.commit()
            except Exception:
                pass
            finally:
                wd_db.close()

    watchdog = threading.Thread(target=_watchdog, args=(thread, project_id), daemon=True)
    watchdog.start()

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
        .order_by(ProjectAnalysis.version.desc())
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
            "filters": None,
            "error": None,
            "analysis_id": None,
            "version": None,
            "version_label": None,
        }

    active_filters = None
    if analysis.filters:
        try:
            active_filters = json.loads(analysis.filters)
        except Exception:
            pass

    return {
        "status": analysis.status,
        "completed_count": completed_count,
        "participant_count": analysis.participant_count,
        "generated_at": analysis.generated_at.isoformat() if analysis.generated_at else None,
        "report": json.loads(analysis.report) if analysis.report else None,
        "filters": active_filters,
        "error": analysis.error,
        "analysis_id": analysis.id,
        "version": analysis.version,
        "version_label": analysis.version_label,
    }


@router.get("/{project_id}/analysis/heatmap")
def get_heatmap(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Build a demographic × theme heatmap from the latest analysis report."""
    _get_project_or_404(project_id, company.id, db)

    analysis = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id, ProjectAnalysis.status == "ready")
        .order_by(ProjectAnalysis.version.desc())
        .first()
    )
    if analysis is None or not analysis.report:
        raise HTTPException(status_code=404, detail="No ready analysis found")

    report = json.loads(analysis.report)
    themes = report.get("themes", [])

    # Build participant map: id → {display_name, profession, age_range, country}
    participants = (
        db.query(Participant)
        .filter(Participant.project_id == project_id, Participant.status == "completed")
        .all()
    )

    # Collect all unique segments
    segments: list[str] = []
    seg_participants: dict[str, list[str]] = {}  # segment → list of display names

    for p in participants:
        for attr, val in [
            ("profession", p.profession),
            ("age_range", p.age_range),
            ("country", p.country),
        ]:
            if val:
                seg = f"{attr}:{val}"
                if seg not in seg_participants:
                    seg_participants[seg] = []
                    segments.append(seg)
                seg_participants[seg].append(p.display_name or f"Participant")

    # For each theme, count how many quotes mention a participant in each segment.
    # If the quotes are attributed objects, match by participant_display_name.
    # Fall back to counting unique segment members if quotes are plain strings.
    theme_rows = []
    for theme in themes:
        raw_quotes = theme.get("quotes", [])
        seg_counts: dict[str, int] = {}

        # Extract participant names mentioned in quotes
        mentioned_names: set[str] = set()
        for q in raw_quotes:
            if isinstance(q, dict):
                pname = q.get("participant_display_name", "")
                if pname:
                    mentioned_names.add(pname)

        for seg, names in seg_participants.items():
            if mentioned_names:
                # Count segment participants whose name appears in attributed quotes
                seg_counts[seg] = sum(1 for n in names if n in mentioned_names)
            else:
                # No attribution available — heuristic: flag all segments with any data
                seg_counts[seg] = 0

        theme_rows.append({
            "title": theme.get("title", ""),
            "segment_counts": seg_counts,
        })

    return {
        "segments": segments,
        "segment_participants": seg_participants,
        "themes": theme_rows,
    }


@router.get("/{project_id}/analysis/report.html", response_class=HTMLResponse)
def export_analysis_report(
    project_id: str,
    version: int | None = None,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Render a ready analysis as a standalone, print-ready HTML findings report.

    Declared before ``/{project_id}/analysis/{version_number}`` so the literal
    ``report.html`` segment isn't captured by the int path param (422).
    """
    project = _get_project_or_404(project_id, company.id, db)

    query = db.query(ProjectAnalysis).filter(
        ProjectAnalysis.project_id == project_id,
        ProjectAnalysis.status == "ready",
    )
    if version is not None:
        query = query.filter(ProjectAnalysis.version == version)
    analysis = query.order_by(ProjectAnalysis.version.desc()).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="No ready analysis to export.")

    participants = (
        db.query(Participant)
        .filter(Participant.project_id == project_id, Participant.status == "completed")
        .all()
    )
    annotations = (
        db.query(AnalysisThemeAnnotation)
        .filter(AnalysisThemeAnnotation.analysis_id == analysis.id)
        .all()
    )

    html_doc = render_analysis_report_html(
        project, analysis, participants, annotations, company_name=company.name
    )
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", project.name).strip("_") or "study"
    filename = f"{slug}_findings_v{analysis.version}.html"
    return HTMLResponse(
        content=html_doc,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{project_id}/analysis/versions")
def list_analysis_versions(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Return metadata for all saved analysis versions (up to 5), newest first."""
    _get_project_or_404(project_id, company.id, db)
    versions = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id, ProjectAnalysis.status == "ready")
        .order_by(ProjectAnalysis.version.desc())
        .all()
    )
    result = []
    for v in versions:
        active_filters = None
        if v.filters:
            try:
                active_filters = json.loads(v.filters)
            except Exception:
                pass

        # Resolve parent_version number if parent_version_id set
        parent_version_num = None
        if v.parent_version_id:
            parent_row = db.query(ProjectAnalysis).filter(ProjectAnalysis.id == v.parent_version_id).first()
            if parent_row:
                parent_version_num = parent_row.version

        # Count annotations for this version
        annotation_count = (
            db.query(AnalysisThemeAnnotation)
            .filter(AnalysisThemeAnnotation.analysis_id == v.id)
            .count()
        )

        result.append({
            "version": v.version,
            "generated_at": v.generated_at.isoformat() if v.generated_at else None,
            "participant_count": v.participant_count,
            "filters": active_filters,
            "version_label": v.version_label,
            "parent_version": parent_version_num,
            "annotation_count": annotation_count,
        })
    return result


@router.get("/{project_id}/analysis/{version_number}")
def get_analysis_by_version(
    project_id: str,
    version_number: int,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Return full AnalysisResponse for a specific version number."""
    _get_project_or_404(project_id, company.id, db)

    analysis = (
        db.query(ProjectAnalysis)
        .filter(
            ProjectAnalysis.project_id == project_id,
            ProjectAnalysis.version == version_number,
        )
        .first()
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found")

    active_filters = None
    if analysis.filters:
        try:
            active_filters = json.loads(analysis.filters)
        except Exception:
            pass

    completed_count = (
        db.query(Participant)
        .filter(Participant.project_id == project_id, Participant.status == "completed")
        .count()
    )

    return {
        "status": analysis.status,
        "completed_count": completed_count,
        "participant_count": analysis.participant_count,
        "generated_at": analysis.generated_at.isoformat() if analysis.generated_at else None,
        "report": json.loads(analysis.report) if analysis.report else None,
        "filters": active_filters,
        "error": analysis.error,
        "analysis_id": analysis.id,
        "version": analysis.version,
        "version_label": analysis.version_label,
    }


@router.post("/{project_id}/analysis/annotations")
def upsert_theme_annotation(
    project_id: str,
    body: AnnotationUpsertRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Upsert a theme annotation for a given analysis. Creates if not exists, updates if exists."""
    _get_project_or_404(project_id, company.id, db)

    # Validate the analysis belongs to this project
    analysis = db.query(ProjectAnalysis).filter(
        ProjectAnalysis.id == body.analysis_id,
        ProjectAnalysis.project_id == project_id,
    ).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if body.status not in ("confirmed", "disputed", "needs_evidence"):
        raise HTTPException(status_code=400, detail="Invalid status value")

    existing = (
        db.query(AnalysisThemeAnnotation)
        .filter(
            AnalysisThemeAnnotation.analysis_id == body.analysis_id,
            AnalysisThemeAnnotation.theme_title == body.theme_title,
        )
        .first()
    )

    now = datetime.utcnow()
    if existing:
        existing.status = body.status
        existing.researcher_note = body.researcher_note
        existing.updated_at = now
        annotation = existing
    else:
        annotation = AnalysisThemeAnnotation(
            analysis_id=body.analysis_id,
            theme_title=body.theme_title,
            status=body.status,
            researcher_note=body.researcher_note,
            created_at=now,
            updated_at=now,
        )
        db.add(annotation)

    db.commit()
    db.refresh(annotation)

    return {
        "id": annotation.id,
        "analysis_id": annotation.analysis_id,
        "theme_title": annotation.theme_title,
        "status": annotation.status,
        "researcher_note": annotation.researcher_note,
        "created_at": annotation.created_at.isoformat(),
        "updated_at": annotation.updated_at.isoformat(),
    }


@router.delete("/{project_id}/analysis/annotations/{annotation_id}")
def delete_theme_annotation(
    project_id: str,
    annotation_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Delete a theme annotation."""
    _get_project_or_404(project_id, company.id, db)

    annotation = db.query(AnalysisThemeAnnotation).filter(
        AnalysisThemeAnnotation.id == annotation_id,
    ).first()
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Verify the analysis belongs to this project
    analysis = db.query(ProjectAnalysis).filter(
        ProjectAnalysis.id == annotation.analysis_id,
        ProjectAnalysis.project_id == project_id,
    ).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    db.delete(annotation)
    db.commit()
    return {"message": "Annotation deleted"}


@router.get("/{project_id}/analysis/annotations/{analysis_id}")
def get_theme_annotations(
    project_id: str,
    analysis_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Return all theme annotations for a given analysis_id."""
    _get_project_or_404(project_id, company.id, db)

    # Verify the analysis belongs to this project
    analysis = db.query(ProjectAnalysis).filter(
        ProjectAnalysis.id == analysis_id,
        ProjectAnalysis.project_id == project_id,
    ).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    annotations = (
        db.query(AnalysisThemeAnnotation)
        .filter(AnalysisThemeAnnotation.analysis_id == analysis_id)
        .all()
    )

    return [
        {
            "id": a.id,
            "analysis_id": a.analysis_id,
            "theme_title": a.theme_title,
            "status": a.status,
            "researcher_note": a.researcher_note,
            "created_at": a.created_at.isoformat(),
            "updated_at": a.updated_at.isoformat(),
        }
        for a in annotations
    ]


@router.patch("/{project_id}/analysis/{version_number}/context")
def save_researcher_context(
    project_id: str,
    version_number: int,
    body: ResearcherContextRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Save researcher context to a specific analysis version."""
    _get_project_or_404(project_id, company.id, db)

    analysis = (
        db.query(ProjectAnalysis)
        .filter(
            ProjectAnalysis.project_id == project_id,
            ProjectAnalysis.version == version_number,
        )
        .first()
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found")

    analysis.researcher_context = body.researcher_context
    db.commit()

    return {"message": "Context saved", "version": version_number}


@router.post("/{project_id}/analysis/refine", status_code=status.HTTP_202_ACCEPTED)
def trigger_refined_analysis(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Create a refined analysis based on researcher annotations and context from the latest ready version."""
    _get_project_or_404(project_id, company.id, db)

    # Check for existing generating analysis
    generating = (
        db.query(ProjectAnalysis)
        .filter(
            ProjectAnalysis.project_id == project_id,
            ProjectAnalysis.status == "generating",
        )
        .first()
    )
    if generating:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An analysis is already being generated.",
        )

    # Get the latest ready analysis
    parent_analysis = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id, ProjectAnalysis.status == "ready")
        .order_by(ProjectAnalysis.version.desc())
        .first()
    )
    if parent_analysis is None:
        raise HTTPException(status_code=400, detail="No ready analysis to refine.")

    # Validate: at least one disputed/needs_evidence annotation OR non-empty researcher_context
    actionable_annotations = (
        db.query(AnalysisThemeAnnotation)
        .filter(
            AnalysisThemeAnnotation.analysis_id == parent_analysis.id,
            AnalysisThemeAnnotation.status.in_(["disputed", "needs_evidence"]),
        )
        .count()
    )
    has_context = bool(parent_analysis.researcher_context and parent_analysis.researcher_context.strip())

    if actionable_annotations == 0 and not has_context:
        raise HTTPException(
            status_code=400,
            detail=(
                "Add at least one disputed or needs-evidence annotation, "
                "or a researcher context note, before refining."
            ),
        )

    # Create the new analysis row
    last = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id)
        .order_by(ProjectAnalysis.version.desc())
        .first()
    )
    next_version = (last.version + 1) if last else 1

    completed_count = (
        db.query(Participant)
        .filter(Participant.project_id == project_id, Participant.status == "completed")
        .count()
    )

    new_analysis = ProjectAnalysis(
        project_id=project_id,
        version=next_version,
        status="generating",
        version_label="researcher_refined",
        parent_version_id=parent_analysis.id,
        participant_count=completed_count,
    )
    db.add(new_analysis)
    db.commit()
    db.refresh(new_analysis)

    new_analysis_id = new_analysis.id
    parent_analysis_id = parent_analysis.id

    def _run_refined(project_id: str, new_analysis_id: str, parent_analysis_id: str):
        bg_db = SessionLocal()
        try:
            logger.info("Refined analysis started for project %s (new version %s)", project_id, next_version)
            run_refined_analysis(project_id, new_analysis_id, parent_analysis_id, bg_db)
            logger.info("Refined analysis completed for project %s", project_id)
        except Exception as exc:
            logger.error("Refined analysis failed for project %s: %s", project_id, exc, exc_info=True)
            try:
                row = bg_db.query(ProjectAnalysis).filter(ProjectAnalysis.id == new_analysis_id).first()
                if row:
                    row.status = "failed"
                    row.error = str(exc)
                    bg_db.commit()
            except Exception:
                pass
        finally:
            bg_db.close()

    thread = threading.Thread(
        target=_run_refined,
        args=(project_id, new_analysis_id, parent_analysis_id),
        daemon=True,
    )
    thread.start()

    def _watchdog(t: threading.Thread, project_id: str, analysis_id: str):
        t.join(timeout=ANALYSIS_TIMEOUT_SECONDS)
        if t.is_alive():
            logger.error("Refined analysis timed out for project %s", project_id)
            wd_db = SessionLocal()
            try:
                row = wd_db.query(ProjectAnalysis).filter(ProjectAnalysis.id == analysis_id).first()
                if row and row.status == "generating":
                    row.status = "failed"
                    row.error = "Analysis timed out after 5 minutes"
                    wd_db.commit()
            except Exception:
                pass
            finally:
                wd_db.close()

    watchdog = threading.Thread(target=_watchdog, args=(thread, project_id, new_analysis_id), daemon=True)
    watchdog.start()

    return {"status": "generating", "message": "Refined analysis started", "version": next_version}


# ── Shareable report endpoints ────────────────────────────────────────────────

@router.post("/{project_id}/analysis/share")
def create_share_link(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Generate (or return existing) a public share token for the latest ready analysis."""
    import secrets
    _get_project_or_404(project_id, company.id, db)
    analysis = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id, ProjectAnalysis.status == "ready")
        .order_by(ProjectAnalysis.version.desc())
        .first()
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail="No ready analysis to share.")
    if not analysis.share_token:
        analysis.share_token = secrets.token_urlsafe(32)
        db.commit()
    return {"share_token": analysis.share_token}


@router.delete("/{project_id}/analysis/share")
def revoke_share_link(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Revoke the public share link for the latest analysis."""
    _get_project_or_404(project_id, company.id, db)
    analysis = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id, ProjectAnalysis.status == "ready")
        .order_by(ProjectAnalysis.version.desc())
        .first()
    )
    if analysis and analysis.share_token:
        analysis.share_token = None
        db.commit()
    return {"message": "Share link revoked."}
