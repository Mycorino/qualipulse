import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, func
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.limiter import limiter

logger = logging.getLogger(__name__)
from app.models.billing import CreditLedger
from app.models.coding import ManualCode, QuoteTag
from app.models.company import Company, EmailVerificationToken, PasswordResetToken
from app.services import billing_service
from app.models.interview import (
    AnalysisThemeAnnotation,
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.memo import ProjectMemo
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion
from app.models.usage import AIUsageLog

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Auth dependency ───────────────────────────────────────────────────────────

def require_admin(authorization: Optional[str] = Header(default=None)) -> None:
    if not settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is disabled")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required")
    token = authorization[len("Bearer "):]
    # Use constant-time comparison — a naive `!=` leaks timing info that can
    # be used to recover the secret key character by character over many
    # requests. hmac.compare_digest is the stdlib-approved fix.
    if not hmac.compare_digest(token, settings.ADMIN_SECRET_KEY):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")


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


class AdminUserDetail(AdminUserSummary):
    projects: list[AdminProjectSummary]


class TierUpdate(BaseModel):
    tier: str  # "solo" | "team" | "lab" | "enterprise"


class TrialUpdate(BaseModel):
    action: str  # "extend_7" | "extend_14" | "extend_30" | "reset" | "expire"


class CreditAdjustment(BaseModel):
    """Manual credit adjustment from the admin panel.

    ``credits_delta`` can be positive (goodwill grant, refund) or negative
    (clawback). Always recorded in ``credit_ledger`` with
    ``event_type='adjustment_admin'`` and the reason in metadata.
    """
    credits_delta: int
    reason: str


class AdminStats(BaseModel):
    total_users: int
    users_by_tier: dict[str, int]
    active_trials: int
    total_projects: int
    total_interviews_completed: int
    signups_last_7_days: int
    signups_last_30_days: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_user_summary(company: Company, db: Session) -> AdminUserSummary:
    project_count = db.query(func.count(Project.id)).filter(
        Project.company_id == company.id
    ).scalar() or 0

    completed_count = (
        db.query(func.count(Participant.id))
        .join(Project, Participant.project_id == Project.id)
        .filter(Project.company_id == company.id, Participant.status == "completed")
        .scalar() or 0
    )

    last_project_at = db.query(func.max(Project.created_at)).filter(
        Project.company_id == company.id
    ).scalar()

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
    )


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
    _: None = Depends(require_admin),
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
    return [_build_user_summary(c, db) for c in companies]


@router.get("/users/{company_id}", response_model=AdminUserDetail)
@limiter.limit("30/minute")
def get_user(
    request: Request,
    company_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
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
    _: None = Depends(require_admin),
) -> AdminUserSummary:
    valid_tiers = {"free", "starter", "solo", "team", "lab", "enterprise"}
    if body.tier not in valid_tiers:
        raise HTTPException(status_code=422, detail=f"tier must be one of {sorted(valid_tiers)}")

    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")

    company.subscription_tier = body.tier
    company.subscription_status = "active"
    db.commit()
    db.refresh(company)
    return _build_user_summary(company, db)


@router.patch("/users/{company_id}/trial", response_model=AdminUserSummary)
@limiter.limit("30/minute")
def update_trial(
    request: Request,
    company_id: str,
    body: TrialUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> AdminUserSummary:
    """Extend/reset/expire the legacy calendar trial (trial_ends_at).

    DEPRECATED for new accounts — they use credits-based trials where access
    is gated by credit balance, not calendar. This endpoint only has a real
    effect on legacy accounts with ``trial_ends_at`` set. For new accounts,
    use ``POST /admin/workspaces/{id}/credits/adjust`` to grant additional
    credits instead.
    """
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
    return _build_user_summary(company, db)


@router.post("/workspaces/{workspace_id}/credits/adjust")
@limiter.limit("30/minute")
def adjust_credits(
    request: Request,
    workspace_id: str,
    body: CreditAdjustment,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Manually grant or claw back credits for a workspace.

    Used for support cases (failed interview refund, goodwill grant,
    legacy migration top-up). Always writes a ``credit_ledger`` row with
    ``event_type='adjustment_admin'`` and the reason in metadata so the
    movement is auditable. Returns the updated balance snapshot.

    Refuses to adjust workspaces on legacy plans — those don't track
    credits and the adjustment would be meaningless. Returns 400 in
    that case.
    """
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

    # Apply the adjustment to the balance. Positive deltas grow the
    # ``purchased`` bucket so they survive rollover; negative deltas
    # increment ``used`` so the available math stays simple.
    if body.credits_delta > 0:
        balance.purchased_credits = (balance.purchased_credits or 0) + body.credits_delta
    else:
        balance.used_credits = (balance.used_credits or 0) + abs(body.credits_delta)
    balance.updated_at = datetime.utcnow()

    db.add(
        CreditLedger(
            id=str(__import__("uuid").uuid4()),
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
    _: None = Depends(require_admin),
) -> None:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")

    logger.warning(
        "ADMIN_USER_DELETION: company_id=%s email=%s name=%s timestamp=%s",
        company.id,
        company.email,
        company.name,
        datetime.utcnow().isoformat(),
    )

    # Collect IDs for cascade deletes in correct FK order
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


# ── Cost reporting ────────────────────────────────────────────────────────────

def _costs_report(db: Session, company_id: str | None = None) -> dict:
    """Build the cost report dict, optionally filtered to a single company."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    base_q = db.query(AIUsageLog)
    if company_id is not None:
        base_q = base_q.filter(AIUsageLog.company_id == company_id)

    # Total and monthly spend
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

    # By operation
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

    # Interview-level cost and count (STT + TTS + interview_turn)
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

    # By company (only for platform-wide report)
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
                        func.case(
                            (AIUsageLog.created_at >= month_start, AIUsageLog.cost_usd),
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("month_cost"),
                func.count(
                    func.distinct(
                        func.case(
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
    _: None = Depends(require_admin),
) -> dict:
    """Platform-wide AI cost report."""
    return _costs_report(db)


@router.get("/costs/company/{company_id}")
@limiter.limit("30/minute")
def get_company_costs(
    request: Request,
    company_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    """AI cost report for a single company, with per-project breakdown."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    report = _costs_report(db, company_id=company_id)

    # Add per-project breakdown
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
    _: None = Depends(require_admin),
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
