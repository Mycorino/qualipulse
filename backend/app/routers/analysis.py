"""Analysis endpoints — generate and retrieve AI synthesis for a project."""

import json
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.interview import Participant, ProjectAnalysis
from app.models.project import Project
from app.services.analysis import run_analysis

logger = logging.getLogger("auto_interview.analysis")
router = APIRouter(prefix="/projects", tags=["analysis"])

ANALYSIS_TIMEOUT_SECONDS = 300  # 5 minutes


class AnalysisTriggerRequest(BaseModel):
    filter_by: str | None = None       # e.g. "profession"
    filter_values: list[str] = []      # e.g. ["Engineer", "Designer"]


@router.post("/{project_id}/analysis", status_code=status.HTTP_202_ACCEPTED)
def trigger_analysis(
    project_id: str,
    body: AnalysisTriggerRequest | None = None,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Kick off (or re-run) AI synthesis. Optionally filter participants by an attribute."""
    project = _get_project_or_404(project_id, company.id, db)

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

    def _run_with_timeout(project_id: str, db: Session, filter_by, filter_values):
        try:
            logger.info("Analysis started for project %s", project_id)
            run_analysis(project_id, db, filter_by, filter_values)
            logger.info("Analysis completed for project %s", project_id)
            # Notify company that analysis is ready
            try:
                from app.models.project import Project as ProjectModel
                from app.services.email import send_analysis_ready
                proj = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
                if proj and proj.company:
                    project_url = f"https://app.autointerview.com/projects/{project_id}?tab=analysis"
                    send_analysis_ready(proj.company.email, proj.name, project_url)
            except Exception:
                pass
        except Exception as exc:
            logger.error("Analysis failed for project %s: %s", project_id, exc, exc_info=True)
            try:
                analysis = (
                    db.query(ProjectAnalysis)
                    .filter(ProjectAnalysis.project_id == project_id)
                    .order_by(ProjectAnalysis.version.desc())
                    .first()
                )
                if analysis:
                    analysis.status = "failed"
                    analysis.error = str(exc)
                    db.commit()
            except Exception:
                pass

    # Run in background thread so the response returns immediately
    thread = threading.Thread(
        target=_run_with_timeout,
        args=(project_id, db, filter_by, filter_values),
        daemon=True,
    )
    thread.start()

    # Monitor timeout in a watchdog thread
    def _watchdog(t: threading.Thread, project_id: str, db: Session):
        t.join(timeout=ANALYSIS_TIMEOUT_SECONDS)
        if t.is_alive():
            logger.error("Analysis timed out after 5 minutes for project %s", project_id)
            try:
                analysis = (
                    db.query(ProjectAnalysis)
                    .filter(ProjectAnalysis.project_id == project_id)
                    .order_by(ProjectAnalysis.version.desc())
                    .first()
                )
                if analysis and analysis.status == "generating":
                    analysis.status = "failed"
                    analysis.error = "Analysis timed out after 5 minutes"
                    db.commit()
            except Exception:
                pass

    watchdog = threading.Thread(target=_watchdog, args=(thread, project_id, db), daemon=True)
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


@router.get("/{project_id}/analysis/versions")
def list_analysis_versions(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Return metadata for all saved analysis versions (up to 3), newest first."""
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
        result.append({
            "version": v.version,
            "generated_at": v.generated_at.isoformat() if v.generated_at else None,
            "participant_count": v.participant_count,
            "filters": active_filters,
        })
    return result


def _get_project_or_404(project_id: str, company_id: str, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


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
