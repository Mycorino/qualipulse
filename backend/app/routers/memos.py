"""Research memo endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.memo import ProjectMemo
from app.models.project import Project

router = APIRouter(prefix="/projects", tags=["memos"])


class MemoCreate(BaseModel):
    type: str = "general"  # "general" | "theme_note" | "tension_note" | "jtbd_note"
    linked_key: str | None = None
    content: str


class MemoUpdate(BaseModel):
    content: str


@router.get("/{project_id}/memos")
def list_memos(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    _get_project_or_404(project_id, company.id, db)
    memos = (
        db.query(ProjectMemo)
        .filter(ProjectMemo.project_id == project_id)
        .order_by(ProjectMemo.created_at)
        .all()
    )
    return [_memo_to_dict(m) for m in memos]


@router.post("/{project_id}/memos", status_code=status.HTTP_201_CREATED)
def create_memo(
    project_id: str,
    body: MemoCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    _get_project_or_404(project_id, company.id, db)
    memo = ProjectMemo(
        project_id=project_id,
        type=body.type,
        linked_key=body.linked_key,
        content=body.content,
    )
    db.add(memo)
    db.commit()
    db.refresh(memo)
    return _memo_to_dict(memo)


@router.put("/{project_id}/memos/{memo_id}")
def update_memo(
    project_id: str,
    memo_id: str,
    body: MemoUpdate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    _get_project_or_404(project_id, company.id, db)
    memo = (
        db.query(ProjectMemo)
        .filter(ProjectMemo.id == memo_id, ProjectMemo.project_id == project_id)
        .first()
    )
    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found")
    memo.content = body.content
    memo.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(memo)
    return _memo_to_dict(memo)


@router.delete("/{project_id}/memos/{memo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memo(
    project_id: str,
    memo_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    _get_project_or_404(project_id, company.id, db)
    memo = (
        db.query(ProjectMemo)
        .filter(ProjectMemo.id == memo_id, ProjectMemo.project_id == project_id)
        .first()
    )
    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found")
    db.delete(memo)
    db.commit()


def _get_project_or_404(project_id: str, company_id: str, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _memo_to_dict(memo: ProjectMemo) -> dict:
    return {
        "id": memo.id,
        "project_id": memo.project_id,
        "type": memo.type,
        "linked_key": memo.linked_key,
        "content": memo.content,
        "created_at": memo.created_at.isoformat(),
        "updated_at": memo.updated_at.isoformat(),
    }
