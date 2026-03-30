from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.schemas.auth import (
    CompanyResponse,
    LoginRequest,
    SignupRequest,
    TokenResponse,
)
from app.services.auth import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(Company).filter(Company.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this email already exists",
        )

    company = Company(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    token = create_access_token({"sub": company.id})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    company = db.query(Company).filter(Company.email == body.email).first()
    if not company or not verify_password(body.password, company.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token({"sub": company.id})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=CompanyResponse)
def get_me(company: Company = Depends(get_current_company)) -> CompanyResponse:
    return CompanyResponse.model_validate(company)
