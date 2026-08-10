import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import (
    get_accessible_project_or_404 as _get_project_or_404,
    get_editable_project_or_404 as _get_editable_project_or_404,
    get_current_company,
    require_verified_company,
    get_db,
)
from app.models.company import Company
from app.models.interview import InterviewLink, Participant
from app.models.project import Project
from app.schemas.interview import LinkResponse, LinkUpdateRequest
from app.services.analytics import emit_event

router = APIRouter(tags=["links"])


@router.post(
    "/projects/{project_id}/links",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_link(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(require_verified_company),
) -> LinkResponse:
    project = _get_editable_project_or_404(project_id, company.id, db)

    _BASE58 = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
    token = "".join(secrets.choice(_BASE58) for _ in range(43))
    link = InterviewLink(
        project_id=project.id,
        token=token,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    # Activation funnel marker — "researcher has a shareable link in hand".
    existing_links = (
        db.query(InterviewLink)
        .filter(InterviewLink.project_id == project.id)
        .count()
    )
    emit_event(
        "link_shared",
        company=company,
        project_id=str(project.id),
        link_id=str(link.id),
        is_first_link_on_project=existing_links == 1,
    )

    return _link_to_response(link, db)


@router.get(
    "/projects/{project_id}/links",
    response_model=list[LinkResponse],
)
def list_links(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[LinkResponse]:
    _get_project_or_404(project_id, company.id, db)

    links = (
        db.query(InterviewLink)
        .filter(InterviewLink.project_id == project_id)
        .order_by(InterviewLink.created_at.desc())
        .all()
    )
    return [_link_to_response(link, db) for link in links]


@router.patch("/links/{link_id}", response_model=LinkResponse)
def update_link(
    link_id: str,
    body: LinkUpdateRequest | None = None,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> LinkResponse:
    """Update a link. A bodyless PATCH flips ``is_active`` (legacy toggle)."""
    link = db.query(InterviewLink).filter(InterviewLink.id == link_id).first()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    # Workspace access + edit-role check (owner/admin/editor; viewers 403).
    _get_editable_project_or_404(link.project_id, company.id, db)

    if body is None or (
        body.is_active is None
        and body.max_participants is None
        and not body.clear_max_participants
    ):
        link.is_active = not link.is_active
    else:
        if body.is_active is not None:
            link.is_active = body.is_active
        if body.clear_max_participants:
            link.max_participants = None
        elif body.max_participants is not None:
            # Refuse a cap already behind the participants admitted so far —
            # it would read as "0 remaining" and silently close a live link.
            admitted = _participant_count(link, db)
            if body.max_participants < admitted:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "cap_below_current",
                        "message": (
                            f"This link already has {admitted} participants. "
                            f"Set a limit of at least {admitted}, or deactivate the link."
                        ),
                        "current": admitted,
                    },
                )
            link.max_participants = body.max_participants

    db.commit()
    db.refresh(link)

    return _link_to_response(link, db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _participant_count(link: InterviewLink, db: Session) -> int:
    return (
        db.query(Participant)
        .filter(Participant.link_id == link.id)
        .count()
    )


def _link_to_response(link: InterviewLink, db: Session | None = None) -> LinkResponse:
    return LinkResponse(
        id=link.id,
        token=link.token,
        url=f"/interview/{link.token}",
        is_active=link.is_active,
        max_participants=link.max_participants,
        participant_count=_participant_count(link, db) if db is not None else 0,
        created_at=link.created_at,
    )
