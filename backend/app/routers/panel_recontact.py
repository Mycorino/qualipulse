"""Recontact endpoints — researcher-facing send side of the participant panel.

- GET  /projects/{id}/invite-candidates : who this study may invite (+ why not)
- POST /projects/{id}/invites           : send invitations to selected panelists
- GET  /projects/{id}/invites           : invite list + derived funnel
- GET  /workspace/panel                 : the workspace's consented pool (V2 page)

See ``services/panel_invites.py`` for the eligibility and guardrail logic.
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import (
    get_accessible_project_or_404 as _get_project_or_404,
    get_editable_project_or_404 as _get_editable_project_or_404,
    get_current_company,
    get_db,
    require_verified_company,
)
from app.models.company import Company
from app.models.interview import InterviewLink, Participant
from app.models.panel import PanelProfile, StudyInvite
from app.models.project import Project
from app.services import panel_invites as pi
from app.services import panel_service as ps
from app.services.analytics import emit_event
from app.services.email import send_interview_invite

logger = logging.getLogger("auto_interview")

router = APIRouter(tags=["panel-recontact"])


class SendInvitesRequest(BaseModel):
    profile_ids: list[int] = Field(min_length=1, max_length=pi.INVITE_BATCH_MAX)


@router.get("/projects/{project_id}/invite-candidates")
def list_invite_candidates(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    project = _get_project_or_404(project_id, company.id, db)
    candidates = pi.eligible_candidates(db, project)
    sent_today = pi.invites_sent_today(db, project.company_id)
    return {
        "candidates": candidates,
        "cooldown_days": pi.INVITE_COOLDOWN_DAYS,
        "batch_max": pi.INVITE_BATCH_MAX,
        "daily_limit": settings.INVITE_DAILY_LIMIT,
        "daily_remaining": max(0, settings.INVITE_DAILY_LIMIT - sent_today),
    }


@router.get("/projects/{project_id}/invites")
def list_project_invites(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    project = _get_project_or_404(project_id, company.id, db)
    return pi.derive_funnel(db, project.id)


@router.post("/projects/{project_id}/invites", status_code=status.HTTP_201_CREATED)
def send_invites(
    project_id: str,
    body: SendInvitesRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(require_verified_company),
):
    """Invite selected consented panelists to this study.

    Each recipient is re-validated server-side (consent, no prior invite to
    this study, not already a participant, platform cooldown). The invite row
    is committed BEFORE the email goes out — under the unique constraint that
    claim is what makes concurrent double-sends impossible — and rolled back
    for that recipient if the provider refuses the send.
    """
    project = _get_editable_project_or_404(project_id, company.id, db)
    if project.is_demo:
        raise HTTPException(status_code=400, detail="demo_project")
    if settings.INVITE_DAILY_LIMIT <= 0:
        raise HTTPException(status_code=403, detail="recontact_disabled")

    link = (
        db.query(InterviewLink)
        .filter(InterviewLink.project_id == project.id, InterviewLink.is_active.is_(True))
        .order_by(InterviewLink.created_at.asc())
        .first()
    )
    if link is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "no_active_link", "message": "Create an active interview link first."},
        )

    sent_today = pi.invites_sent_today(db, project.company_id)
    remaining = settings.INVITE_DAILY_LIMIT - sent_today
    if remaining <= 0:
        raise HTTPException(
            status_code=429,
            detail={"code": "invite_daily_limit", "message": "Daily invitation limit reached."},
        )

    profiles = (
        db.query(PanelProfile)
        .filter(PanelProfile.id.in_(body.profile_ids))
        .all()
    )
    by_id = {p.id: p for p in profiles}

    # Recompute exclusions at send time — the candidates list the client is
    # holding may be minutes old.
    project_emails = {
        (e or "").lower()
        for (e,) in db.query(Participant.email)
        .filter(Participant.project_id == project.id, Participant.email.isnot(None))
        .all()
    }
    invited_emails = {
        r[0]
        for r in db.query(StudyInvite.email)
        .filter(StudyInvite.project_id == project.id)
        .all()
    }
    pool_emails = {p.email.lower() for p in pi.workspace_pool(db, project.company_id)}
    cooled = pi.emails_in_cooldown(db, {p.email.lower() for p in profiles})

    interview_url = f"{settings.APP_BASE_URL}/i/{link.token}"
    sender_name = (project.researcher_name or company.name or "").strip() or "The research team"

    sent: list[str] = []
    skipped: list[dict] = []
    for pid in dict.fromkeys(body.profile_ids):
        profile = by_id.get(pid)
        if profile is None or not profile.panel_consent:
            skipped.append({"profile_id": pid, "reason": "not_eligible"})
            continue
        email = profile.email.lower()
        if email not in pool_emails:
            skipped.append({"profile_id": pid, "reason": "not_in_pool"})
            continue
        if email in project_emails:
            skipped.append({"profile_id": pid, "reason": "already_participated"})
            continue
        if email in invited_emails:
            skipped.append({"profile_id": pid, "reason": "already_invited"})
            continue
        if email in cooled:
            skipped.append({"profile_id": pid, "reason": "cooldown"})
            continue
        if len(sent) >= remaining:
            skipped.append({"profile_id": pid, "reason": "daily_limit"})
            continue

        lang = (profile.preferred_language or project.language or "en")[:2]
        invite = StudyInvite(
            project_id=project.id,
            company_id=project.company_id,
            profile_id=profile.id,
            email=email,
            language=lang,
            sent_by=company.id,
            sent_at=datetime.utcnow(),
        )
        db.add(invite)
        try:
            db.commit()  # claim first — the unique constraint kills races
        except Exception:
            db.rollback()
            skipped.append({"profile_id": pid, "reason": "already_invited"})
            continue

        optout_url = f"{settings.APP_BASE_URL}/panel/optout?token={ps.create_optout_token(profile.email)}"
        ok = False
        try:
            ok = send_interview_invite(
                to=profile.email,
                project_name=project.name,
                interview_url=interview_url,
                sender_name=sender_name,
                lang=lang,
                optout_url=optout_url,
            )
        except Exception:  # pragma: no cover — provider hiccup
            logger.exception("recontact invite send failed for profile=%s", pid)
        if ok:
            sent.append(email)
            invited_emails.add(email)
        else:
            # Release the claim so a retry later can re-invite this person.
            db.delete(invite)
            db.commit()
            skipped.append({"profile_id": pid, "reason": "send_failed"})

    emit_event(
        "recontact_invites_sent",
        company=company,
        project_id=str(project.id),
        sent=len(sent),
        skipped=len(skipped),
    )
    return {"sent": len(sent), "skipped": skipped}


@router.get("/workspace/panel")
def workspace_panel(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """The workspace's consented participant pool, with per-person invite and
    participation history (V2 Participants page)."""
    pool = pi.workspace_pool(db, company.id)
    if not pool:
        return {"profiles": [], "stats": {"pool_size": 0, "invited_30d": 0}}

    emails = [p.email.lower() for p in pool]

    # Participation within this workspace, grouped by email.
    part_rows = (
        db.query(
            func.lower(Participant.email),
            func.count(func.distinct(Participant.project_id)),
            func.sum(case((Participant.status == "completed", 1), else_=0)),
        )
        .join(Project, Participant.project_id == Project.id)
        .filter(
            Project.company_id == company.id,
            func.lower(Participant.email).in_(emails),
        )
        .group_by(func.lower(Participant.email))
        .all()
    )
    participation = {r[0]: {"studies": r[1], "completed": int(r[2] or 0)} for r in part_rows}

    invite_rows = (
        db.query(
            StudyInvite.email,
            func.count(StudyInvite.id),
            func.max(StudyInvite.sent_at),
        )
        .filter(StudyInvite.company_id == company.id, StudyInvite.email.in_(emails))
        .group_by(StudyInvite.email)
        .all()
    )
    invites = {r[0]: {"count": r[1], "last": r[2]} for r in invite_rows}

    profiles = []
    for p in pool:
        row = pi.serialize_profile(p)
        email = p.email.lower()
        part = participation.get(email, {"studies": 0, "completed": 0})
        inv = invites.get(email)
        row["studies_participated"] = part["studies"]
        row["interviews_completed"] = part["completed"]
        row["invites_sent"] = inv["count"] if inv else 0
        row["last_invited_at"] = inv["last"].isoformat() if inv and inv["last"] else None
        profiles.append(row)

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    invited_30d = (
        db.query(StudyInvite)
        .filter(StudyInvite.company_id == company.id, StudyInvite.sent_at >= thirty_days_ago)
        .count()
    )
    return {
        "profiles": profiles,
        "stats": {"pool_size": len(profiles), "invited_30d": invited_30d},
    }
