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
    return db.query(Company).filter(Company.id == company_id).first()
