"""Team collaboration models.

A "workspace" in QualiPulse is a Company. The Company record that owns the
workspace is the billing owner — their subscription tier governs the whole
team's limits. Additional users join a workspace via invitation and are
tracked in `workspace_members`.

Roles (v1):
- `owner`   — the original Company that signed up. Cannot be removed.
- `admin`   — full project access + can invite/remove members.
- `editor`  — full project access, cannot manage team.
- `viewer`  — read-only across the workspace.
"""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"

VALID_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER)
INVITABLE_ROLES = (ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER)


class WorkspaceMember(Base):
    """Join table: a Company (member) belongs to a workspace (owned by another Company)."""

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint(
            "workspace_company_id",
            "member_company_id",
            name="uq_workspace_member",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_EDITOR)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    workspace = relationship("Company", foreign_keys=[workspace_company_id])
    member = relationship("Company", foreign_keys=[member_company_id])


class WorkspaceInvitation(Base):
    """Pending invitation for an email address to join a workspace."""

    __tablename__ = "workspace_invitations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_EDITOR)
    token: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        default=lambda: secrets.token_urlsafe(32),
        nullable=False,
    )
    invited_by_company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    workspace = relationship("Company", foreign_keys=[workspace_company_id])
    invited_by = relationship("Company", foreign_keys=[invited_by_company_id])
