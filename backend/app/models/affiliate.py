import secrets
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Affiliate(Base):
    __tablename__ = "affiliates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    how_they_found_us: Mapped[str | None] = mapped_column(Text, nullable=True)
    commission_pct: Mapped[float] = mapped_column(Float, default=20.0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # pending | active | rejected
    payout_threshold: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    total_earned: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_paid: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    referrals = relationship("AffiliateReferral", back_populates="affiliate", cascade="all, delete-orphan")
    payouts = relationship("AffiliatePayout", back_populates="affiliate", cascade="all, delete-orphan")


class AffiliateReferral(Base):
    __tablename__ = "affiliate_referrals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    affiliate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    referred_company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    signed_up_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False
    )
    converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    commission_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="signed_up", nullable=False)
    # signed_up | converted | paid

    # Relationships
    affiliate = relationship("Affiliate", back_populates="referrals")


class AffiliatePayout(Base):
    __tablename__ = "affiliate_payouts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    affiliate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    paid_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    affiliate = relationship("Affiliate", back_populates="payouts")
