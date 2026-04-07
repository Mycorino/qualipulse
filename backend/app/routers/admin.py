from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, func
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.models.coding import ManualCode, QuoteTag
from app.models.company import Company, EmailVerificationToken, PasswordResetToken
from app.models.interview import (
    AnalysisThemeAnnotation,
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.memo import ProjectMemo
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Auth dependency ───────────────────────────────────────────────────────────

def require_admin(authorization: Optional[str] = Header(default=None)) -> None:
    if not settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is disabled")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required")
    token = authorization[len("Bearer "):]
    if token != settings.ADMIN_SECRET_KEY:
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


class AdminUserDetail(AdminUserSummary):
    projects: list[AdminProjectSummary]


class TierUpdate(BaseModel):
    tier: str  # "solo" | "team" | "lab" | "enterprise"


class TrialUpdate(BaseModel):
    action: str  # "extend_7" | "extend_14" | "extend_30" | "reset" | "expire"


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
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[AdminUserSummary])
def list_users(
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
def get_user(
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
def update_tier(
    company_id: str,
    body: TierUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> AdminUserSummary:
    valid_tiers = {"solo", "team", "lab", "enterprise"}
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
def update_trial(
    company_id: str,
    body: TrialUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
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
    return _build_user_summary(company, db)


@router.delete("/users/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    company_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> None:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="User not found")

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


@router.get("/stats", response_model=AdminStats)
def get_stats(
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
