import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.interview import InterviewLink
from app.models.project import Project
from app.schemas.interview import LinkResponse

router = APIRouter(tags=["links"])


@router.post(
    "/projects/{project_id}/links",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_link(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> LinkResponse:
    project = _get_project_or_404(project_id, company.id, db)

    _BASE58 = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
    token = "".join(secrets.choice(_BASE58) for _ in range(43))
    link = InterviewLink(
        project_id=project.id,
        token=token,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    return _link_to_response(link)


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
    return [_link_to_response(link) for link in links]


@router.patch("/links/{link_id}", response_model=LinkResponse)
def toggle_link(
    link_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> LinkResponse:
    link = db.query(InterviewLink).filter(InterviewLink.id == link_id).first()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    # Verify ownership
    project = (
        db.query(Project)
        .filter(Project.id == link.project_id, Project.company_id == company.id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    link.is_active = not link.is_active
    db.commit()
    db.refresh(link)

    return _link_to_response(link)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_or_404(project_id: str, company_id: str, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _link_to_response(link: InterviewLink) -> LinkResponse:
    return LinkResponse(
        id=link.id,
        token=link.token,
        url=f"/interview/{link.token}",
        is_active=link.is_active,
        created_at=link.created_at,
    )
