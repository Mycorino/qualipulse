"""Qualitative coding endpoints — researcher-defined codes and quote tagging."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.coding import ManualCode, QuoteTag
from app.models.interview import InterviewTurn, Participant
from app.models.project import Project

router = APIRouter(prefix="/projects", tags=["coding"])

PRESET_COLORS = [
    "#6366f1", "#ec4899", "#f59e0b", "#10b981",
    "#3b82f6", "#8b5cf6", "#ef4444", "#14b8a6",
]


# ── Schemas ────────────────────────────────────────────────────────────────

class CodeCreate(BaseModel):
    name: str
    color: str = "#6366f1"


class TagCreate(BaseModel):
    manual_code_id: str
    selected_text: str
    start_index: int
    end_index: int


# ── Code endpoints ─────────────────────────────────────────────────────────

@router.get("/{project_id}/codes")
def list_codes(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    _get_project_or_404(project_id, company.id, db)
    codes = (
        db.query(ManualCode)
        .filter(ManualCode.project_id == project_id)
        .order_by(ManualCode.sort_order, ManualCode.created_at)
        .all()
    )
    return [_code_to_dict(c, db) for c in codes]


@router.post("/{project_id}/codes", status_code=status.HTTP_201_CREATED)
def create_code(
    project_id: str,
    body: CodeCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    _get_project_or_404(project_id, company.id, db)
    # sort_order = next available
    max_order = (
        db.query(ManualCode)
        .filter(ManualCode.project_id == project_id)
        .count()
    )
    code = ManualCode(
        project_id=project_id,
        name=body.name,
        color=body.color,
        sort_order=max_order,
    )
    db.add(code)
    db.commit()
    db.refresh(code)
    return _code_to_dict(code, db)


class CodePatch(BaseModel):
    name: str | None = None
    color: str | None = None


@router.patch("/{project_id}/codes/{code_id}")
def rename_code(
    project_id: str,
    code_id: str,
    body: CodePatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    _get_project_or_404(project_id, company.id, db)
    code = (
        db.query(ManualCode)
        .filter(ManualCode.id == code_id, ManualCode.project_id == project_id)
        .first()
    )
    if code is None:
        raise HTTPException(status_code=404, detail="Code not found")
    if body.name is not None:
        code.name = body.name.strip()
    if body.color is not None:
        code.color = body.color
    db.commit()
    db.refresh(code)
    return _code_to_dict(code, db)


@router.delete("/{project_id}/codes/{code_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_code(
    project_id: str,
    code_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    _get_project_or_404(project_id, company.id, db)
    code = (
        db.query(ManualCode)
        .filter(ManualCode.id == code_id, ManualCode.project_id == project_id)
        .first()
    )
    if code is None:
        raise HTTPException(status_code=404, detail="Code not found")
    db.delete(code)
    db.commit()


# ── Tag endpoints ──────────────────────────────────────────────────────────

@router.get("/{project_id}/tags")
def list_tags(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """List all tags for a project with turn and participant info."""
    _get_project_or_404(project_id, company.id, db)

    # Get all participant IDs for this project
    participant_ids = [
        p.id for p in db.query(Participant).filter(Participant.project_id == project_id).all()
    ]
    # Get all turn IDs for these participants
    turn_ids = [
        t.id for t in db.query(InterviewTurn)
        .filter(InterviewTurn.participant_id.in_(participant_ids))
        .all()
    ]

    tags = (
        db.query(QuoteTag)
        .filter(QuoteTag.turn_id.in_(turn_ids))
        .all()
    )

    result = []
    for tag in tags:
        turn = db.query(InterviewTurn).filter(InterviewTurn.id == tag.turn_id).first()
        participant = db.query(Participant).filter(Participant.id == turn.participant_id).first() if turn else None
        code = db.query(ManualCode).filter(ManualCode.id == tag.manual_code_id).first()
        result.append({
            "id": tag.id,
            "turn_id": tag.turn_id,
            "manual_code_id": tag.manual_code_id,
            "code_name": code.name if code else None,
            "code_color": code.color if code else None,
            "selected_text": tag.selected_text,
            "start_index": tag.start_index,
            "end_index": tag.end_index,
            "participant_id": participant.id if participant else None,
            "participant_display_name": participant.display_name if participant else None,
            "created_at": tag.created_at.isoformat(),
        })
    return result


@router.post("/{project_id}/turns/{turn_id}/tags", status_code=status.HTTP_201_CREATED)
def create_tag(
    project_id: str,
    turn_id: str,
    body: TagCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Tag a quote in an interview turn."""
    project = _get_project_or_404(project_id, company.id, db)

    turn = db.query(InterviewTurn).filter(InterviewTurn.id == turn_id).first()
    if turn is None:
        raise HTTPException(status_code=404, detail="Turn not found")

    # Verify turn belongs to a participant of this project
    participant = db.query(Participant).filter(
        Participant.id == turn.participant_id,
        Participant.project_id == project_id,
    ).first()
    if participant is None:
        raise HTTPException(status_code=404, detail="Turn not found in this project")

    code = db.query(ManualCode).filter(
        ManualCode.id == body.manual_code_id,
        ManualCode.project_id == project_id,
    ).first()
    if code is None:
        raise HTTPException(status_code=404, detail="Code not found")

    tag = QuoteTag(
        turn_id=turn_id,
        manual_code_id=body.manual_code_id,
        selected_text=body.selected_text,
        start_index=body.start_index,
        end_index=body.end_index,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)

    return {
        "id": tag.id,
        "turn_id": tag.turn_id,
        "manual_code_id": tag.manual_code_id,
        "code_name": code.name,
        "code_color": code.color,
        "selected_text": tag.selected_text,
        "start_index": tag.start_index,
        "end_index": tag.end_index,
        "created_at": tag.created_at.isoformat(),
    }


@router.delete("/{project_id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    project_id: str,
    tag_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    _get_project_or_404(project_id, company.id, db)
    tag = db.query(QuoteTag).filter(QuoteTag.id == tag_id).first()
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_project_or_404(project_id: str, company_id: str, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _code_to_dict(code: ManualCode, db: Session) -> dict:
    tag_count = db.query(QuoteTag).filter(QuoteTag.manual_code_id == code.id).count()
    return {
        "id": code.id,
        "project_id": code.project_id,
        "name": code.name,
        "color": code.color,
        "sort_order": code.sort_order,
        "tag_count": tag_count,
        "created_at": code.created_at.isoformat(),
    }
