"""Team collaboration endpoints.

All routes require authentication. Most require the caller to be the owner or
an admin of the target workspace — see `require_team_admin`.

Workspace limit: capped by the billing owner's tier (`team_members`). An owner
on the `team` tier can invite up to 3 seats total (themselves + 2 members).
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.team import (
    INVITABLE_ROLES,
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_OWNER,
    WorkspaceInvitation,
    WorkspaceMember,
)
from app.services.email import send_team_invite
from app.services.feature_gates import get_effective_limits
from app.services.workspace import (
    can_manage_team,
    get_member_role,
    workspace_member_count,
)

logger = logging.getLogger("auto_interview.team")
router = APIRouter(prefix="/team", tags=["team"])


INVITATION_EXPIRY_DAYS = 7


# ── Schemas ─────────────────────────────────────────────────────────────────


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = ROLE_EDITOR


class AcceptRequest(BaseModel):
    token: str


class InvitationPreviewResponse(BaseModel):
    workspace_name: str
    inviter_name: str | None
    role: str
    email: str
    expires_at: datetime
    already_member: bool = False


class MemberResponse(BaseModel):
    id: str  # workspace_member row id, or "owner" for the owner
    company_id: str
    name: str
    email: str
    role: str
    joined_at: datetime


class InvitationResponse(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime
    created_at: datetime


# ── Helpers ─────────────────────────────────────────────────────────────────


def _get_workspace_owner_for(company: Company, db: Session) -> Company:
    """Return the Company whose workspace the given company is an admin/owner of.

    Every Company has its own workspace (they are the owner). Members of OTHER
    workspaces can't invite into those workspaces unless they're admins — that
    check is done via `require_team_admin`.
    """
    return company  # simplification: /team/* always acts on the caller's own workspace


def _require_admin(workspace_company_id: str, caller: Company, db: Session) -> None:
    role = get_member_role(db, workspace_company_id, caller.id)
    if not can_manage_team(role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the workspace owner or an admin can manage the team.",
        )


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/members", response_model=list[MemberResponse])
def list_members(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """List all members of the caller's own workspace (they are the owner)."""
    owner = company  # the workspace this endpoint manages is always the caller's own

    # Owner is always the first row
    result: list[MemberResponse] = [
        MemberResponse(
            id="owner",
            company_id=owner.id,
            name=owner.name,
            email=owner.email,
            role=ROLE_OWNER,
            joined_at=owner.created_at,
        )
    ]

    rows = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_company_id == owner.id)
        .all()
    )
    for row in rows:
        member = db.query(Company).filter(Company.id == row.member_company_id).first()
        if not member:
            continue
        result.append(
            MemberResponse(
                id=row.id,
                company_id=member.id,
                name=member.name,
                email=member.email,
                role=row.role,
                joined_at=row.created_at,
            )
        )
    return result


@router.delete("/members/{member_row_id}")
def remove_member(
    member_row_id: str,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Remove a non-owner from the caller's workspace."""
    _require_admin(company.id, company, db)

    row = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.id == member_row_id,
            WorkspaceMember.workspace_company_id == company.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(row)
    db.commit()
    logger.info(
        "Team: %s removed member %s from workspace %s",
        company.email,
        row.member_company_id,
        company.id,
    )
    return {"message": "Member removed"}


@router.get("/invitations", response_model=list[InvitationResponse])
def list_invitations(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """List pending (non-accepted, non-expired) invitations for the caller's workspace."""
    _require_admin(company.id, company, db)
    now = datetime.utcnow()
    rows = (
        db.query(WorkspaceInvitation)
        .filter(
            WorkspaceInvitation.workspace_company_id == company.id,
            WorkspaceInvitation.accepted.is_(False),
            WorkspaceInvitation.expires_at > now,
        )
        .order_by(WorkspaceInvitation.created_at.desc())
        .all()
    )
    return [
        InvitationResponse(
            id=r.id,
            email=r.email,
            role=r.role,
            expires_at=r.expires_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/invite", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
def invite_member(
    body: InviteRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Invite an email to join the caller's workspace."""
    _require_admin(company.id, company, db)

    role = (body.role or ROLE_EDITOR).strip().lower()
    if role not in INVITABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(INVITABLE_ROLES)}",
        )

    email = body.email.lower().strip()

    # Cannot invite self
    if email == company.email.lower():
        raise HTTPException(status_code=400, detail="You can't invite yourself.")

    # Already a member?
    existing_member_company = (
        db.query(Company).filter(Company.email == email).first()
    )
    if existing_member_company:
        already = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_company_id == company.id,
                WorkspaceMember.member_company_id == existing_member_company.id,
            )
            .first()
        )
        if already:
            raise HTTPException(
                status_code=409, detail="This person is already in your workspace."
            )

    # Enforce team_members limit from workspace owner's tier
    limits = get_effective_limits(company)
    max_seats = limits.team_members  # -1 = unlimited
    current_seats = workspace_member_count(db, company.id)
    pending_count = (
        db.query(WorkspaceInvitation)
        .filter(
            WorkspaceInvitation.workspace_company_id == company.id,
            WorkspaceInvitation.accepted.is_(False),
            WorkspaceInvitation.expires_at > datetime.utcnow(),
        )
        .count()
    )
    if max_seats != -1 and (current_seats + pending_count) >= max_seats:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Your {limits.name} plan includes {max_seats} team "
                f"member{'s' if max_seats != 1 else ''}. Upgrade to invite more."
            ),
        )

    # De-dupe: if a non-expired invitation already exists for this email, return it
    existing_invite = (
        db.query(WorkspaceInvitation)
        .filter(
            WorkspaceInvitation.workspace_company_id == company.id,
            WorkspaceInvitation.email == email,
            WorkspaceInvitation.accepted.is_(False),
            WorkspaceInvitation.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if existing_invite:
        invitation = existing_invite
    else:
        invitation = WorkspaceInvitation(
            workspace_company_id=company.id,
            email=email,
            role=role,
            expires_at=datetime.utcnow() + timedelta(days=INVITATION_EXPIRY_DAYS),
            invited_by_company_id=company.id,
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)

    # Send invitation email (fire-and-forget logic inside email service)
    try:
        accept_url = f"{settings.APP_BASE_URL}/team/accept?token={invitation.token}"
        send_team_invite(
            to=email,
            workspace_name=company.name,
            inviter_name=company.name,
            role=role,
            accept_url=accept_url,
        )
    except Exception as exc:
        logger.warning("Failed to send team invite email to %s: %s", email, exc)

    logger.info("Team: %s invited %s as %s to workspace %s", company.email, email, role, company.id)

    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@router.delete("/invitations/{invitation_id}")
def revoke_invitation(
    invitation_id: str,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Revoke a pending invitation."""
    _require_admin(company.id, company, db)
    row = (
        db.query(WorkspaceInvitation)
        .filter(
            WorkspaceInvitation.id == invitation_id,
            WorkspaceInvitation.workspace_company_id == company.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Invitation not found")
    db.delete(row)
    db.commit()
    return {"message": "Invitation revoked"}


@router.get("/invitations/preview/{token}", response_model=InvitationPreviewResponse)
def preview_invitation(
    token: str,
    db: Session = Depends(get_db),
):
    """Public: preview an invitation by token (used on the accept page before login)."""
    row = (
        db.query(WorkspaceInvitation)
        .filter(WorkspaceInvitation.token == token)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if row.accepted:
        raise HTTPException(status_code=410, detail="This invitation has already been used.")
    if row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="This invitation has expired.")

    workspace = db.query(Company).filter(Company.id == row.workspace_company_id).first()
    inviter = (
        db.query(Company).filter(Company.id == row.invited_by_company_id).first()
        if row.invited_by_company_id
        else None
    )

    return InvitationPreviewResponse(
        workspace_name=workspace.name if workspace else "a workspace",
        inviter_name=inviter.name if inviter else None,
        role=row.role,
        email=row.email,
        expires_at=row.expires_at,
    )


@router.post("/invitations/accept")
def accept_invitation(
    body: AcceptRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Accept an invitation. Requires that the caller is logged in with the invited email."""
    row = (
        db.query(WorkspaceInvitation)
        .filter(WorkspaceInvitation.token == body.token)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if row.accepted:
        raise HTTPException(status_code=410, detail="This invitation has already been used.")
    if row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="This invitation has expired.")

    if company.email.lower().strip() != row.email.lower().strip():
        raise HTTPException(
            status_code=403,
            detail=f"This invitation was sent to {row.email}. Sign in with that email first.",
        )

    # Can't join your own workspace
    if row.workspace_company_id == company.id:
        raise HTTPException(status_code=400, detail="You can't join your own workspace.")

    # Already a member?
    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_company_id == row.workspace_company_id,
            WorkspaceMember.member_company_id == company.id,
        )
        .first()
    )
    if existing:
        row.accepted = True
        row.accepted_at = datetime.utcnow()
        db.commit()
        return {"message": "Already a member", "workspace_id": row.workspace_company_id}

    membership = WorkspaceMember(
        workspace_company_id=row.workspace_company_id,
        member_company_id=company.id,
        role=row.role,
    )
    db.add(membership)
    row.accepted = True
    row.accepted_at = datetime.utcnow()
    db.commit()

    logger.info(
        "Team: %s accepted invitation to workspace %s as %s",
        company.email,
        row.workspace_company_id,
        row.role,
    )
    return {"message": "Joined workspace", "workspace_id": row.workspace_company_id}


@router.get("/workspaces")
def list_my_workspaces(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """List all workspaces the caller has access to (their own + any they've joined)."""
    result = [
        {
            "id": company.id,
            "name": company.name,
            "role": ROLE_OWNER,
        }
    ]
    memberships = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.member_company_id == company.id)
        .all()
    )
    for m in memberships:
        ws = db.query(Company).filter(Company.id == m.workspace_company_id).first()
        if ws:
            result.append({"id": ws.id, "name": ws.name, "role": m.role})
    return result
