"""Recontact invitations — the send side of the participant panel.

The capture side (post-interview opt-in, PanelProfile enrichment) has existed
for a while; this module adds the workspace-scoped pool and the study-invite
flow on top of it.

Scoping rule: a workspace may only recontact people who took part in one of
**its own** studies and consented to future contact. The platform-wide panel
(public /panel/join signups) is deliberately NOT exposed here — that pool is
Qualipulse's, not the workspace's.

Guardrails, all enforced server-side:
- consent is the base filter (``PanelProfile.panel_consent``)
- someone already invited to a study can never be re-invited to it
  (unique constraint on ``(project_id, email)``)
- a platform-wide cooldown (``INVITE_COOLDOWN_DAYS``) so no panelist is
  emailed twice within the window, regardless of which workspace asks
- a per-workspace daily send cap (``settings.INVITE_DAILY_LIMIT``)
- every email carries a one-click opt-out link (signed token, 1y validity)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.interview import Participant
from app.models.panel import PanelProfile, StudyInvite
from app.models.project import Project

# No panelist receives more than one invite (from any workspace) per window.
INVITE_COOLDOWN_DAYS = 7
# Hard per-request batch bound — keeps the synchronous send loop sane.
INVITE_BATCH_MAX = 100


def _workspace_participant_emails(company_id: str):
    """Selectable of lowercased emails that appear on any participant row of
    this workspace's projects."""
    return (
        select(func.lower(Participant.email))
        .join(Project, Participant.project_id == Project.id)
        .where(Project.company_id == company_id, Participant.email.isnot(None))
    )


def workspace_pool(db: Session, company_id: str) -> list[PanelProfile]:
    """All consented panelists who participated in this workspace's studies."""
    return (
        db.query(PanelProfile)
        .filter(
            PanelProfile.panel_consent.is_(True),
            func.lower(PanelProfile.email).in_(_workspace_participant_emails(company_id)),
        )
        .order_by(PanelProfile.last_active.desc().nullslast())
        .all()
    )


def _cooldown_cutoff() -> datetime:
    return datetime.utcnow() - timedelta(days=INVITE_COOLDOWN_DAYS)


def emails_in_cooldown(db: Session, emails: set[str]) -> set[str]:
    """Subset of ``emails`` invited (by anyone) within the cooldown window."""
    if not emails:
        return set()
    rows = (
        db.query(StudyInvite.email)
        .filter(StudyInvite.email.in_(emails), StudyInvite.sent_at >= _cooldown_cutoff())
        .all()
    )
    return {r[0] for r in rows}


def eligible_candidates(db: Session, project: Project) -> list[dict]:
    """The workspace pool, minus everyone this study must not (re)contact.

    Returns serialised candidate rows; ``blocked_reason`` is set (and the row
    still returned) for pool members currently excluded, so the UI can show
    "3 more in cooldown" instead of silently shrinking the list.
    """
    pool = workspace_pool(db, project.company_id)
    if not pool:
        return []

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
    cooled = emails_in_cooldown(db, {p.email.lower() for p in pool})

    out = []
    for p in pool:
        email = p.email.lower()
        blocked = None
        if email in project_emails:
            blocked = "already_participated"
        elif email in invited_emails:
            blocked = "already_invited"
        elif email in cooled:
            blocked = "cooldown"
        row = serialize_profile(p)
        row["blocked_reason"] = blocked
        out.append(row)
    return out


def serialize_profile(p: PanelProfile) -> dict:
    return {
        "profile_id": p.id,
        "email": p.email,
        "first_name": p.first_name,
        "preferred_language": p.preferred_language,
        "age_range": p.age_range,
        "country": p.country,
        "job_function": p.job_function,
        "seniority": p.seniority,
        "industry": p.industry,
        "company_size": p.company_size,
        "last_active": p.last_active.isoformat() if p.last_active else None,
        "consent_at": p.consent_at.isoformat() if p.consent_at else None,
    }


def invites_sent_today(db: Session, company_id: str) -> int:
    since = datetime.utcnow() - timedelta(hours=24)
    return (
        db.query(StudyInvite)
        .filter(StudyInvite.company_id == company_id, StudyInvite.sent_at >= since)
        .count()
    )


def derive_funnel(db: Session, project_id: str) -> dict:
    """Invite list + funnel for one study, derived by joining participants on
    (project_id, lower(email)) — never stored, so it can't drift."""
    invites = (
        db.query(StudyInvite)
        .filter(StudyInvite.project_id == project_id)
        .order_by(StudyInvite.sent_at.desc())
        .all()
    )
    if not invites:
        return {"invites": [], "summary": {"invited": 0, "started": 0, "completed": 0}}

    participants = {
        (p.email or "").lower(): p.status
        for p in db.query(Participant)
        .filter(Participant.project_id == project_id, Participant.email.isnot(None))
        .all()
    }
    rows = []
    started = completed = 0
    for inv in invites:
        status = participants.get(inv.email)
        if status == "completed":
            state = "completed"
            completed += 1
            started += 1
        elif status is not None:
            state = "started"
            started += 1
        else:
            state = "sent"
        rows.append(
            {
                "id": inv.id,
                "email": inv.email,
                "sent_at": inv.sent_at.isoformat() if inv.sent_at else None,
                "language": inv.language,
                "status": state,
            }
        )
    return {
        "invites": rows,
        "summary": {"invited": len(invites), "started": started, "completed": completed},
    }
