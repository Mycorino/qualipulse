"""Workspace access helpers for team collaboration.

A user (`Company` row) can access projects from:
1. Their own company (they are the owner).
2. Any workspace they've been invited into (via `workspace_members`).

Feature-gate limits and billing always follow the *workspace owner* — never the
individual member — so a viewer on a Lab workspace sees Lab limits even if
their own Company is on the free tier.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.project import Project
from app.models.team import (
    INVITABLE_ROLES,
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_OWNER,
    WorkspaceMember,
)


def accessible_workspace_ids(db: Session, company: Company) -> list[str]:
    """Return all company IDs (workspaces) this user can see projects from.

    Always includes the user's own company id first.
    """
    ids: list[str] = [company.id]
    memberships = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.member_company_id == company.id)
        .all()
    )
    for m in memberships:
        if m.workspace_company_id not in ids:
            ids.append(m.workspace_company_id)
    return ids


def get_member_role(
    db: Session, workspace_company_id: str, member_company_id: str
) -> str | None:
    """Return the role of a member in a workspace, or None if not a member.

    The workspace owner (i.e. the Company that owns the workspace) always has
    role `owner` even though there's no `workspace_members` row for them.
    """
    if workspace_company_id == member_company_id:
        return ROLE_OWNER
    row = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_company_id == workspace_company_id,
            WorkspaceMember.member_company_id == member_company_id,
        )
        .first()
    )
    return row.role if row else None


def can_edit(role: str | None) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR)


def can_manage_team(role: str | None) -> bool:
    return role in (ROLE_OWNER, ROLE_ADMIN)


def project_workspace_owner(db: Session, project: Project) -> Company | None:
    """Fetch the billing owner for a given project (used by feature gates)."""
    return db.query(Company).filter(Company.id == project.company_id).first()


def workspace_member_count(db: Session, workspace_company_id: str) -> int:
    """Count seats in a workspace — owner + non-owner members."""
    count = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_company_id == workspace_company_id)
        .count()
    )
    return 1 + count  # +1 for the owner


__all__ = [
    "INVITABLE_ROLES",
    "ROLE_ADMIN",
    "ROLE_EDITOR",
    "ROLE_OWNER",
    "accessible_workspace_ids",
    "can_edit",
    "can_manage_team",
    "get_member_role",
    "project_workspace_owner",
    "workspace_member_count",
]
