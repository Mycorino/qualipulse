import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import case, delete as sql_delete, func
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.limiter import limiter

logger = logging.getLogger(__name__)
from app.models.admin_audit import AdminAuditLog
from app.models.billing import CreditLedger
from app.models.coding import ManualCode, QuoteTag
from app.models.company import Company, EmailVerificationToken, PasswordResetToken
from app.services import billing_service
from app.services.auth import create_impersonation_token
from app.models.interview import (
    AnalysisThemeAnnotation,
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.memo import ProjectMemo
from app.models.panel import PanelAnswer, PanelProfile, ParticipantMagicToken
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion
from app.models.usage import AIUsageLog

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Auth dependency ───────────────────────────────────────────────────────────

def require_admin(
    authorization: Optional[str] = Header(default=None),
    x_admin_identity: Optional[str] = Header(default=None, alias="X-Admin-Identity"),
) -> str:
    """Validate admin key and return the admin identity string for audit logging."""
    if not settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is disabled")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required")
    token = authorization[len("Bearer "):]
    # Compare bytes, not str — compare_digest raises TypeError (→ 500) on
    # non-ASCII str input, and a crafted header shouldn't crash the guard.
    if not hmac.compare_digest(token.encode("utf-8"), settings.ADMIN_SECRET_KEY.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")
    return (x_admin_identity or "unknown").strip()[:100]


# ── Audit helper ─────────────────────────────────────────────────────────────

def _record_audit(
    db: Session,
    admin_identity: str,
    action: str,
    target_company_id: str | None,
    target_company_email: str,
    details: dict | None = None,
    is_impersonation: bool = False,
) -> None:
    db.add(AdminAuditLog(
        id=str(uuid.uuid4()),
        admin_identity=admin_identity,
        action=action,
        target_company_id=target_company_id,
        target_company_email=target_company_email,
        details=json.dumps(details) if details else None,
        is_impersonation=is_impersonation,
    ))
    db.commit()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AdminProjectSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    participant_count: int


class AdminUserSummary(BaseModel):
    id: str
    name: str
    email: str
    subscription_tier: str
    subscription_status: str
    trial_ends_at: Optional[datetime]
    email_verified: bool
    onboarding_completed: bool
    created_at: datetime
    last_active: Optional[datetime]
    project_count: int
    interview_count: int
    business_summary: Optional[str] = None
    suspended_at: Optional[datetime] = None
    suspension_reason: Optional[str] = None


class AdminUserDetail(AdminUserSummary):
    projects: list[AdminProjectSummary]


class TierUpdate(BaseModel):
    tier: str  # "solo" | "team" | "lab" | "enterprise"


class TrialUpdate(BaseModel):
    action: str  # "extend_7" | "extend_14" | "extend_30" | "reset" | "expire"


class CreditAdjustment(BaseModel):
    credits_delta: int
    reason: str


class SuspendRequest(BaseModel):
    reason: str


class AdminStats(BaseModel):
    total_users: int
    users_by_tier: dict[str, int]
    active_trials: int
    total_projects: int
    total_interviews_completed: int
    signups_last_7_days: int
    signups_last_30_days: int


class AuditLogEntry(BaseModel):
    id: str
    admin_identity: str
    action: str
    target_company_id: Optional[str]
    target_company_email: str
    details: Optional[dict] = None
    is_impersonation: bool
    created_at: datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _batch_user_stats(db: Session, company_ids: list[str]) -> dict[str, tuple[int, int, Optional[datetime]]]:
    """(project_count, completed_interviews, last_project_at) per company —
    two grouped queries total, however many rows the page holds."""
    if not company_ids:
        return {}
    stats: dict[str, tuple[int, int, Optional[datetime]]] = {}
    project_rows = (
        db.query(Project.company_id, func.count(Project.id), func.max(Project.created_at))
        .filter(Project.company_id.in_(company_ids))
        .group_by(Project.company_id)
        .all()
    )
    completed_rows = dict(
        db.query(Project.company_id, func.count(Participant.id))
        .join(Participant, Participant.project_id == Project.id)
        .filter(Project.company_id.in_(company_ids), Participant.status == "completed")
        .group_by(Project.company_id)
        .all()
    )
    for company_id, project_count, last_project_at in project_rows:
        stats[company_id] = (
            int(project_count or 0),
            int(completed_rows.get(company_id, 0)),
            last_project_at,
        )
    return stats


def _user_summary_from_stats(
    company: Company,
    stats: dict[str, tuple[int, int, Optional[datetime]]],
) -> AdminUserSummary:
    project_count, completed_count, last_project_at = stats.get(company.id, (0, 0, None))
    return AdminUserSummary(
        id=company.id,
        name=company.name,
        email=company.email,
        subscription_tier=company.subscription_tier,
        subscription_status=company.subscription_status,
        trial_ends_at=company.trial_ends_at,
        email_verified=company.email_verified,
        onboarding_completed=company.onboarding_completed,
        created_at=company.created_at,
        last_active=last_project_at,
        project_count=project_count,
        interview_count=completed_count,
        business_summary=company.business_summary,
        suspended_at=company.suspended_at,
        suspension_reason=company.suspension_reason,
    )


def _build_user_summary(company: Company, db: Session) -> AdminUserSummary:
    return _user_summary_from_stats(company, _batch_user_stats(db, [company.id]))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[AdminUserSummary])
@limiter.limit("30/minute")
def list_users(
    request: Request,
    search: Optional[str] = Query(default=None),
    tier: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> list[AdminUserSummary]:
    q = db.query(Company)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            Company.email.ilike(pattern) | Company.name.ilike(pattern)
        )
    if tier:
        q = q.filter(Company.subscription_tier == tier)
    q = q.order_by(Company.created_at.desc())
    offset = (page - 1) * limit
    companies = q.offset(offset).limit(limit).all()
    stats = _batch_user_stats(db, [c.id for c in companies])
    return [_user_summary_from_stats(c, stats) for c in companies]


@router.get("/users/{company_id}", response_model=AdminUserDetail)
@limiter.limit("30/minute")
def get_user(
    request: Request,
    company_id: str,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> AdminUserDetail:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")

    summary = _build_user_summary(company, db)

    projects_q = (
        db.query(Project, func.count(Participant.id).label("pcount"))
        .outerjoin(Participant, Participant.project_id == Project.id)
        .filter(Project.company_id == company_id)
        .group_by(Project.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    projects = [
        AdminProjectSummary(
            id=p.id,
            name=p.name,
            created_at=p.created_at,
            participant_count=pcount,
        )
        for p, pcount in projects_q
    ]

    return AdminUserDetail(**summary.model_dump(), projects=projects)


@router.patch("/users/{company_id}/tier", response_model=AdminUserSummary)
@limiter.limit("30/minute")
def update_tier(
    request: Request,
    company_id: str,
    body: TierUpdate,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> AdminUserSummary:
    valid_tiers = {"free", "starter", "solo", "team", "lab", "enterprise"}
    if body.tier not in valid_tiers:
        raise HTTPException(status_code=422, detail=f"tier must be one of {sorted(valid_tiers)}")

    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")

    old_tier = company.subscription_tier
    company.subscription_tier = body.tier
    # Deliberately leave subscription_status alone — forcing "active" here
    # used to mask real Stripe states (past_due / canceled) until the next
    # webhook overwrote it again.
    db.commit()
    db.refresh(company)

    _record_audit(db, admin_id, "tier_change", company.id, company.email,
                  {"old_tier": old_tier, "new_tier": body.tier})

    return _build_user_summary(company, db)


@router.patch("/users/{company_id}/trial", response_model=AdminUserSummary)
@limiter.limit("30/minute")
def update_trial(
    request: Request,
    company_id: str,
    body: TrialUpdate,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> AdminUserSummary:
    valid_actions = {"extend_7", "extend_14", "extend_30", "reset", "expire"}
    if body.action not in valid_actions:
        raise HTTPException(status_code=422, detail=f"action must be one of {sorted(valid_actions)}")

    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    if body.action == "extend_7":
        base = company.trial_ends_at if company.trial_ends_at and company.trial_ends_at > now else now
        company.trial_ends_at = base + timedelta(days=7)
    elif body.action == "extend_14":
        base = company.trial_ends_at if company.trial_ends_at and company.trial_ends_at > now else now
        company.trial_ends_at = base + timedelta(days=14)
    elif body.action == "extend_30":
        base = company.trial_ends_at if company.trial_ends_at and company.trial_ends_at > now else now
        company.trial_ends_at = base + timedelta(days=30)
    elif body.action == "reset":
        company.trial_ends_at = now + timedelta(days=14)
    elif body.action == "expire":
        company.trial_ends_at = now

    db.commit()
    db.refresh(company)

    _record_audit(db, admin_id, "trial_change", company.id, company.email,
                  {"action": body.action})

    return _build_user_summary(company, db)


@router.post("/workspaces/{workspace_id}/credits/adjust")
@limiter.limit("30/minute")
def adjust_credits(
    request: Request,
    workspace_id: str,
    body: CreditAdjustment,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
):
    if body.credits_delta == 0:
        raise HTTPException(status_code=422, detail="credits_delta must be non-zero")
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=422, detail="reason is required")

    company = db.query(Company).filter(Company.id == workspace_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    sub = billing_service.get_current_subscription(db, workspace_id)
    plan = billing_service.get_plan(db, sub.plan_id) if sub else None
    if plan is None or plan.is_legacy:
        raise HTTPException(
            status_code=400,
            detail="Workspace is on a legacy plan; credits don't apply.",
        )

    balance = billing_service.get_active_balance(db, workspace_id)
    if balance is None:
        raise HTTPException(
            status_code=400,
            detail="No active credit balance to adjust.",
        )

    if body.credits_delta > 0:
        balance.purchased_credits = (balance.purchased_credits or 0) + body.credits_delta
    else:
        # Clawback: shrink the grant buckets (purchased → rollover → included)
        # rather than inflating used_credits. Inflated usage gets attributed
        # to buckets at period rollover, which would let clawed-back purchased
        # credits resurrect in the next period's rollover grant.
        remaining = abs(body.credits_delta)
        for bucket in ("purchased_credits", "rollover_credits", "included_credits"):
            take = min(getattr(balance, bucket) or 0, remaining)
            setattr(balance, bucket, (getattr(balance, bucket) or 0) - take)
            remaining -= take
            if remaining == 0:
                break
        if remaining:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot remove {abs(body.credits_delta)} credits; only "
                    f"{abs(body.credits_delta) - remaining} granted credits remain this period."
                ),
            )
    balance.updated_at = datetime.utcnow()

    db.add(
        CreditLedger(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            balance_id=balance.id,
            event_type=billing_service.EVT_ADJUSTMENT_ADMIN,
            credits_delta=body.credits_delta,
            balance_after=balance.available,
            source="admin_manual",
            event_metadata={"reason": body.reason.strip()},
        )
    )
    db.commit()
    db.refresh(balance)

    _record_audit(db, admin_id, "credit_adjust", company.id, company.email,
                  {"delta": body.credits_delta, "reason": body.reason.strip()})

    logger.info(
        "ADMIN_CREDIT_ADJUSTMENT: workspace=%s delta=%d reason=%r balance_after=%d",
        workspace_id, body.credits_delta, body.reason, balance.available,
    )

    return {
        "workspace_id": workspace_id,
        "credits_delta": body.credits_delta,
        "reason": body.reason,
        "balance": {
            "included_credits": balance.included_credits,
            "purchased_credits": balance.purchased_credits,
            "rollover_credits": balance.rollover_credits,
            "used_credits": balance.used_credits,
            "overage_credits": balance.overage_credits,
            "available_credits": balance.available,
            "period_start": balance.period_start.isoformat() if balance.period_start else None,
            "period_end": balance.period_end.isoformat() if balance.period_end else None,
        },
    }


@router.delete("/users/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
def delete_user(
    request: Request,
    company_id: str,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> None:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")

    email_snapshot = company.email
    name_snapshot = company.name

    logger.warning(
        "ADMIN_USER_DELETION: company_id=%s email=%s name=%s admin=%s timestamp=%s",
        company.id, email_snapshot, name_snapshot, admin_id,
        datetime.utcnow().isoformat(),
    )

    # Research plans have no ondelete on their FKs (company_id, step→project_id),
    # so Postgres would refuse the company/project deletes below if any rows
    # exist. Steps go first (they reference both plans and projects).
    from app.models.research_plan import ResearchPlan, ResearchPlanStep

    plan_ids = [
        row[0]
        for row in db.query(ResearchPlan.id).filter(ResearchPlan.company_id == company_id).all()
    ]
    if plan_ids:
        db.execute(sql_delete(ResearchPlanStep).where(ResearchPlanStep.plan_id.in_(plan_ids)))
        db.execute(sql_delete(ResearchPlan).where(ResearchPlan.id.in_(plan_ids)))

    project_ids = [
        row[0]
        for row in db.query(Project.id).filter(Project.company_id == company_id).all()
    ]

    if project_ids:
        participant_ids = [
            row[0]
            for row in db.query(Participant.id)
            .filter(Participant.project_id.in_(project_ids))
            .all()
        ]

        if participant_ids:
            turn_ids = [
                row[0]
                for row in db.query(InterviewTurn.id)
                .filter(InterviewTurn.participant_id.in_(participant_ids))
                .all()
            ]
            if turn_ids:
                db.execute(sql_delete(QuoteTag).where(QuoteTag.turn_id.in_(turn_ids)))
            db.execute(
                sql_delete(InterviewTurn).where(
                    InterviewTurn.participant_id.in_(participant_ids)
                )
            )

        db.execute(
            sql_delete(Participant).where(Participant.project_id.in_(project_ids))
        )

        analysis_ids = [
            row[0]
            for row in db.query(ProjectAnalysis.id)
            .filter(ProjectAnalysis.project_id.in_(project_ids))
            .all()
        ]
        if analysis_ids:
            db.execute(
                sql_delete(AnalysisThemeAnnotation).where(
                    AnalysisThemeAnnotation.analysis_id.in_(analysis_ids)
                )
            )

        db.execute(
            sql_delete(ProjectAnalysis).where(
                ProjectAnalysis.project_id.in_(project_ids)
            )
        )
        db.execute(
            sql_delete(ManualCode).where(ManualCode.project_id.in_(project_ids))
        )
        db.execute(
            sql_delete(ProjectMemo).where(ProjectMemo.project_id.in_(project_ids))
        )
        db.execute(
            sql_delete(InterviewGuideQuestion).where(
                InterviewGuideQuestion.project_id.in_(project_ids)
            )
        )
        db.execute(
            sql_delete(ScreeningQuestion).where(
                ScreeningQuestion.project_id.in_(project_ids)
            )
        )
        db.execute(
            sql_delete(InterviewLink).where(InterviewLink.project_id.in_(project_ids))
        )
        db.execute(sql_delete(Project).where(Project.company_id == company_id))

    db.execute(
        sql_delete(EmailVerificationToken).where(
            EmailVerificationToken.company_id == company_id
        )
    )
    db.execute(
        sql_delete(PasswordResetToken).where(
            PasswordResetToken.company_id == company_id
        )
    )
    db.execute(sql_delete(Company).where(Company.id == company_id))
    db.commit()

    _record_audit(db, admin_id, "user_delete", None, email_snapshot,
                  {"name": name_snapshot, "company_id": company_id})


# ── Consumer / panelist deletion ─────────────────────────────────────────────

@router.delete("/panel/{email}")
@limiter.limit("20/minute")
def delete_panelist(
    request: Request,
    email: str,
    include_interviews: bool = False,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> dict:
    """Delete a consumer / panelist account by email — their panel profile,
    all enrichment answers, and outstanding magic tokens. Doubles as GDPR
    right-to-erasure and a clean testing reset (removing the PanelProfile makes
    magic-link verify stop reporting ``profile_complete`` so the questionnaire
    shows again).

    By default leaves Participant interview records intact (they belong to the
    researcher's study). Pass ``?include_interviews=true`` to also delete the
    participant's interview turns + records across all studies.
    """
    email = email.strip().lower()
    deleted = {"panel_profile": 0, "panel_answers": 0, "magic_tokens": 0, "participants": 0, "interview_turns": 0}

    profile = db.query(PanelProfile).filter(func.lower(PanelProfile.email) == email).first()
    if profile is not None:
        deleted["panel_answers"] = db.query(PanelAnswer).filter(PanelAnswer.profile_id == profile.id).count()
        db.delete(profile)  # cascades answers + tag links via ORM relationships

    deleted["magic_tokens"] = db.execute(
        sql_delete(ParticipantMagicToken).where(func.lower(ParticipantMagicToken.email) == email)
    ).rowcount or 0

    if include_interviews:
        pids = [r[0] for r in db.query(Participant.id).filter(func.lower(Participant.email) == email).all()]
        if pids:
            deleted["interview_turns"] = db.execute(
                sql_delete(InterviewTurn).where(InterviewTurn.participant_id.in_(pids))
            ).rowcount or 0
            deleted["participants"] = db.execute(
                sql_delete(Participant).where(Participant.id.in_(pids))
            ).rowcount or 0

    deleted["panel_profile"] = 1 if profile is not None else 0
    db.commit()

    logger.warning(
        "ADMIN_PANELIST_DELETION: email=%s admin=%s deleted=%s timestamp=%s",
        email, admin_id, deleted, datetime.utcnow().isoformat(),
    )
    _record_audit(db, admin_id, "panelist_delete", None, email, deleted)
    return {"deleted": True, "email": email, **deleted}


# ── Suspend / Unsuspend ──────────────────────────────────────────────────────

@router.post("/users/{company_id}/suspend", response_model=AdminUserSummary)
@limiter.limit("30/minute")
def suspend_user(
    request: Request,
    company_id: str,
    body: SuspendRequest,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> AdminUserSummary:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")
    if company.suspended_at is not None:
        raise HTTPException(status_code=409, detail="Account is already suspended")

    company.suspended_at = datetime.utcnow()
    company.suspension_reason = body.reason.strip()
    # No token_version bump needed: get_current_company checks suspended_at
    # on every request, so existing tokens are already blocked (and start
    # working again on unsuspend, which a version bump would prevent).
    db.commit()
    db.refresh(company)

    _record_audit(db, admin_id, "suspend", company.id, company.email,
                  {"reason": body.reason.strip()})

    return _build_user_summary(company, db)


@router.post("/users/{company_id}/unsuspend", response_model=AdminUserSummary)
@limiter.limit("30/minute")
def unsuspend_user(
    request: Request,
    company_id: str,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> AdminUserSummary:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")
    if company.suspended_at is None:
        raise HTTPException(status_code=409, detail="Account is not suspended")

    old_reason = company.suspension_reason
    company.suspended_at = None
    company.suspension_reason = None
    db.commit()
    db.refresh(company)

    _record_audit(db, admin_id, "unsuspend", company.id, company.email,
                  {"previous_reason": old_reason})

    return _build_user_summary(company, db)


# ── Impersonation ────────────────────────────────────────────────────────────

@router.post("/users/{company_id}/impersonate")
@limiter.limit("10/minute")
def impersonate_user(
    request: Request,
    company_id: str,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_impersonation_token(company.id, admin_id)

    _record_audit(db, admin_id, "impersonation_start", company.id, company.email)

    return {
        "access_token": token,
        "company_name": company.name,
        "company_email": company.email,
    }


# ── Audit Log ────────────────────────────────────────────────────────────────

@router.get("/audit-log", response_model=list[AuditLogEntry])
@limiter.limit("30/minute")
def get_audit_log(
    request: Request,
    action: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> list[AuditLogEntry]:
    q = db.query(AdminAuditLog)
    if action:
        q = q.filter(AdminAuditLog.action == action)
    if search:
        pattern = f"%{search}%"
        q = q.filter(AdminAuditLog.target_company_email.ilike(pattern))
    q = q.order_by(AdminAuditLog.created_at.desc())
    offset = (page - 1) * limit
    rows = q.offset(offset).limit(limit).all()
    return [
        AuditLogEntry(
            id=r.id,
            admin_identity=r.admin_identity,
            action=r.action,
            target_company_id=r.target_company_id,
            target_company_email=r.target_company_email,
            details=json.loads(r.details) if r.details else None,
            is_impersonation=r.is_impersonation,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── Cost reporting ────────────────────────────────────────────────────────────

def _costs_report(db: Session, company_id: str | None = None) -> dict:
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_cost = db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0))
    if company_id is not None:
        total_cost = total_cost.filter(AIUsageLog.company_id == company_id)
    total_cost_usd = float(total_cost.scalar() or 0.0)

    month_cost = db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).filter(
        AIUsageLog.created_at >= month_start
    )
    if company_id is not None:
        month_cost = month_cost.filter(AIUsageLog.company_id == company_id)
    this_month_usd = float(month_cost.scalar() or 0.0)

    op_rows = (
        db.query(
            AIUsageLog.operation,
            func.count(AIUsageLog.id).label("count"),
            func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0).label("cost"),
        )
        .filter(*([AIUsageLog.company_id == company_id] if company_id else []))
        .group_by(AIUsageLog.operation)
        .all()
    )
    by_operation = {
        row.operation: {"cost_usd": round(float(row.cost), 6), "count": row.count}
        for row in op_rows
    }

    interview_ops = ("interview_turn", "tts", "stt")
    interview_cost_q = db.query(
        func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)
    ).filter(AIUsageLog.operation.in_(interview_ops))
    if company_id is not None:
        interview_cost_q = interview_cost_q.filter(AIUsageLog.company_id == company_id)
    interview_cost = float(interview_cost_q.scalar() or 0.0)

    interview_count_q = db.query(
        func.count(func.distinct(AIUsageLog.participant_id))
    ).filter(
        AIUsageLog.operation.in_(interview_ops),
        AIUsageLog.participant_id.isnot(None),
    )
    if company_id is not None:
        interview_count_q = interview_count_q.filter(AIUsageLog.company_id == company_id)
    total_interviews = int(interview_count_q.scalar() or 0)

    avg_cost = (interview_cost / total_interviews) if total_interviews > 0 else 0.0

    by_company = []
    if company_id is None:
        company_rows = (
            db.query(
                AIUsageLog.company_id,
                Company.name,
                Company.email,
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0).label("total_cost"),
                func.coalesce(
                    func.sum(
                        case(
                            (AIUsageLog.created_at >= month_start, AIUsageLog.cost_usd),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("month_cost"),
                func.count(
                    func.distinct(
                        case(
                            (AIUsageLog.operation.in_(interview_ops), AIUsageLog.participant_id),
                            else_=None,
                        )
                    )
                ).label("interview_count"),
            )
            .join(Company, AIUsageLog.company_id == Company.id)
            .filter(AIUsageLog.company_id.isnot(None))
            .group_by(AIUsageLog.company_id, Company.name, Company.email)
            .order_by(func.sum(AIUsageLog.cost_usd).desc())
            .all()
        )
        by_company = [
            {
                "company_id": row.company_id,
                "name": row.name,
                "email": row.email,
                "total_cost_usd": round(float(row.total_cost), 6),
                "this_month_usd": round(float(row.month_cost), 6),
                "interview_count": row.interview_count or 0,
            }
            for row in company_rows
        ]

    result = {
        "total_cost_usd": round(total_cost_usd, 6),
        "this_month_usd": round(this_month_usd, 6),
        "by_operation": by_operation,
        "avg_cost_per_interview_usd": round(avg_cost, 6),
        "total_interviews": total_interviews,
    }
    if company_id is None:
        result["by_company"] = by_company
    return result


@router.get("/costs")
@limiter.limit("30/minute")
def get_costs(
    request: Request,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> dict:
    return _costs_report(db)


@router.get("/costs/company/{company_id}")
@limiter.limit("30/minute")
def get_company_costs(
    request: Request,
    company_id: str,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> dict:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    report = _costs_report(db, company_id=company_id)

    project_rows = (
        db.query(
            AIUsageLog.project_id,
            Project.name,
            func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0).label("total_cost"),
            func.count(AIUsageLog.id).label("count"),
        )
        .join(Project, AIUsageLog.project_id == Project.id)
        .filter(
            AIUsageLog.company_id == company_id,
            AIUsageLog.project_id.isnot(None),
        )
        .group_by(AIUsageLog.project_id, Project.name)
        .order_by(func.sum(AIUsageLog.cost_usd).desc())
        .all()
    )
    report["by_project"] = [
        {
            "project_id": row.project_id,
            "name": row.name,
            "total_cost_usd": round(float(row.total_cost), 6),
            "count": row.count,
        }
        for row in project_rows
    ]
    return report


@router.get("/stats", response_model=AdminStats)
@limiter.limit("30/minute")
def get_stats(
    request: Request,
    db: Session = Depends(get_db),
    admin_id: str = Depends(require_admin),
) -> AdminStats:
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    total_users = db.query(func.count(Company.id)).scalar() or 0

    tier_rows = (
        db.query(Company.subscription_tier, func.count(Company.id))
        .group_by(Company.subscription_tier)
        .all()
    )
    users_by_tier = {tier: count for tier, count in tier_rows}

    active_trials = (
        db.query(func.count(Company.id))
        .filter(Company.trial_ends_at > now)
        .scalar() or 0
    )

    total_projects = db.query(func.count(Project.id)).scalar() or 0

    total_interviews_completed = (
        db.query(func.count(Participant.id))
        .filter(Participant.status == "completed")
        .scalar() or 0
    )

    signups_last_7_days = (
        db.query(func.count(Company.id))
        .filter(Company.created_at >= seven_days_ago)
        .scalar() or 0
    )

    signups_last_30_days = (
        db.query(func.count(Company.id))
        .filter(Company.created_at >= thirty_days_ago)
        .scalar() or 0
    )

    return AdminStats(
        total_users=total_users,
        users_by_tier=users_by_tier,
        active_trials=active_trials,
        total_projects=total_projects,
        total_interviews_completed=total_interviews_completed,
        signups_last_7_days=signups_last_7_days,
        signups_last_30_days=signups_last_30_days,
    )
