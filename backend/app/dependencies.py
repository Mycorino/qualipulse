from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.company import Company
from app.services.auth import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_accessible_project_or_404(project_id: str, company_id: str, db: Session):
    """Fetch a project this caller may access — as owner OR workspace member.

    Direct ownership is the fast path; otherwise the caller is resolved to a
    Company and checked against every workspace they belong to. Raises 404
    (never 403) so existence isn't leaked across tenants. This is the single
    canonical project-access check shared by every project-scoped router.
    """
    from app.models.project import Project
    from app.services.workspace import accessible_workspace_ids

    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is not None:
        return project

    caller = db.query(Company).filter(Company.id == company_id).first()
    if caller is not None:
        workspace_ids = accessible_workspace_ids(db, caller)
        project = (
            db.query(Project)
            .filter(Project.id == project_id, Project.company_id.in_(workspace_ids))
            .first()
        )
        if project is not None:
            return project

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def get_current_company(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Company:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    company_id: str | None = payload.get("sub")
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Company not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    is_impersonation = payload.get("impersonation", False)
    if is_impersonation:
        company._is_impersonation = True  # type: ignore[attr-defined]
        company._impersonation_admin = payload.get("admin_identity")  # type: ignore[attr-defined]
    elif company.suspended_at is not None:
        reason = company.suspension_reason or "Contact support for details."
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account suspended: {reason}",
        )

    return company


def require_verified_company(
    company: Company = Depends(get_current_company),
) -> Company:
    """Like ``get_current_company`` but also requires a verified email.

    Used to gate outward-facing, data-collecting actions (creating a study,
    creating an interview link) behind email verification — so a participant
    can never invest effort in a study owned by an unverified researcher, and
    unverified accounts can't spin up collection links. Exploring the seeded
    demo project stays open; only *creating* is gated.
    """
    if not company.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "email_unverified",
                "message": "Please verify your email address to create studies and interview links.",
            },
        )
    return company


def get_current_company_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Company | None:
    """Return the authenticated company if the request carries a valid token.

    Unlike ``get_current_company`` this dependency never raises — it just
    hands back ``None`` for anonymous or invalid-token calls. Endpoints that
    work for both marketing visitors and signed-in users (e.g. the public
    ``/templates`` list, which should localise for logged-in users) use
    this to avoid duplicating the decode logic.
    """
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except HTTPException:
        # decode_access_token raises HTTPException(401) for bad/expired
        # tokens. We silently fall back to anonymous here — but we
        # deliberately don't swallow other exceptions (e.g. DB errors) so
        # they surface to the caller with proper 500s.
        return None
    company_id: str | None = payload.get("sub")
    if company_id is None:
        return None
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        return None
    if not payload.get("impersonation", False) and company.suspended_at is not None:
        return None
    return company
