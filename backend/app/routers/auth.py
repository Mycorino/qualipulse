import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.limiter import limiter
from app.models.company import Company, PasswordResetToken
from app.schemas.auth import (
    CompanyResponse,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.services.email import send_password_reset, send_welcome

logger = logging.getLogger("auto_interview.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def signup(request: Request, body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(Company).filter(Company.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this email already exists",
        )

    company = Company(
        name=body.name.strip(),
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    logger.info("New company signup: %s", company.email)
    send_welcome(company.email, company.name)

    return TokenResponse(
        access_token=create_access_token({"sub": company.id}),
        refresh_token=create_refresh_token({"sub": company.id}),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    company = db.query(Company).filter(Company.email == body.email.lower().strip()).first()
    if not company or not verify_password(body.password, company.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    logger.info("Login: %s", company.email)
    return TokenResponse(
        access_token=create_access_token({"sub": company.id}),
        refresh_token=create_refresh_token({"sub": company.id}),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    payload = decode_refresh_token(body.refresh_token)
    company_id: str | None = payload.get("sub")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return TokenResponse(
        access_token=create_access_token({"sub": company.id}),
        refresh_token=create_refresh_token({"sub": company.id}),
    )


@router.post("/password-reset/request")
@limiter.limit("5/minute")
def request_password_reset(request: Request, body: PasswordResetRequest, db: Session = Depends(get_db)):
    """Always returns 200 to prevent email enumeration."""
    company = db.query(Company).filter(Company.email == body.email.lower().strip()).first()
    if company:
        # Expire any existing tokens
        db.query(PasswordResetToken).filter(
            PasswordResetToken.company_id == company.id,
            PasswordResetToken.used.is_(False),
        ).delete()
        token = PasswordResetToken(
            company_id=company.id,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.add(token)
        db.commit()
        reset_url = f"https://app.autointerview.com/reset-password?token={token.token}"
        send_password_reset(company.email, reset_url)
        logger.info("Password reset requested for %s", company.email)
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/password-reset/confirm")
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    token_row = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == body.token,
        PasswordResetToken.used.is_(False),
    ).first()
    if not token_row or token_row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
    company = db.query(Company).filter(Company.id == token_row.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    company.password_hash = hash_password(body.new_password)
    token_row.used = True
    db.commit()
    logger.info("Password reset completed for %s", company.email)
    return {"message": "Password updated successfully"}


@router.get("/me", response_model=CompanyResponse)
def get_me(company: Company = Depends(get_current_company)) -> CompanyResponse:
    return CompanyResponse.model_validate(company)
