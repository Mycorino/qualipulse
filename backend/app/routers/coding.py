"""Qualitative coding endpoints — researcher-defined codes and quote tagging."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.coding import ManualCode, QuoteTag
from app.models.interview import InterviewTurn, Participant, ProjectAnalysis
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
    tagged_from_translation: bool = False


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

    # Batch-load related objects to avoid N+1 queries
    all_turn_ids = list({tag.turn_id for tag in tags})
    all_code_ids = list({tag.manual_code_id for tag in tags})

    turns_by_id = {}
    if all_turn_ids:
        turns_list = db.query(InterviewTurn).filter(InterviewTurn.id.in_(all_turn_ids)).all()
        turns_by_id = {t.id: t for t in turns_list}

    all_participant_ids = list({t.participant_id for t in turns_by_id.values()})
    participants_by_id = {}
    if all_participant_ids:
        participants_list = db.query(Participant).filter(Participant.id.in_(all_participant_ids)).all()
        participants_by_id = {p.id: p for p in participants_list}

    codes_by_id = {}
    if all_code_ids:
        codes_list = db.query(ManualCode).filter(ManualCode.id.in_(all_code_ids)).all()
        codes_by_id = {c.id: c for c in codes_list}

    result = []
    for tag in tags:
        turn = turns_by_id.get(tag.turn_id)
        participant = participants_by_id.get(turn.participant_id) if turn else None
        code = codes_by_id.get(tag.manual_code_id)
        result.append({
            "id": tag.id,
            "turn_id": tag.turn_id,
            "manual_code_id": tag.manual_code_id,
            "code_name": code.name if code else None,
            "code_color": code.color if code else None,
            "selected_text": tag.selected_text,
            "start_index": tag.start_index,
            "end_index": tag.end_index,
            "tagged_from_translation": tag.tagged_from_translation,
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
        tagged_from_translation=body.tagged_from_translation,
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
        "tagged_from_translation": tag.tagged_from_translation,
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


# ── Theme → Code promotion ─────────────────────────────────────────────────
#
# The Analysis tab can surface AI-generated themes; one of the most common
# researcher workflows is "this theme is real — I want to tag quotes with it
# going forward". Before this endpoint, they had to retype the theme title
# into the codebook. Now it's one click.
#
# This endpoint:
#   1. Looks up the theme in the latest ready analysis for the project.
#   2. Creates a new ManualCode using the theme title + the next preset color.
#   3. Pre-tags every quote the AI attributed to that theme, matching quotes
#      back to the participant's turn text via substring search.
#
# Quotes that can't be matched (speech-to-text drift, edited transcript)
# are returned in the response as ``unmatched_quotes`` so the UI can show
# "we couldn't auto-tag 2 quotes — here they are, click a turn to place them".

class ThemeToCodeRequest(BaseModel):
    analysis_id: str
    theme_title: str
    color: str | None = None  # optional override


@router.post(
    "/{project_id}/analysis/themes/promote-to-code",
    status_code=status.HTTP_201_CREATED,
)
def promote_theme_to_code(
    project_id: str,
    body: ThemeToCodeRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Create a codebook code from an analysis theme + auto-tag its quotes.

    Returns the created code, a list of successfully created tags, and a
    list of quotes that couldn't be matched to any turn so the UI can
    surface them for manual placement.
    """
    project = _get_project_or_404(project_id, company.id, db)

    # 1. Find the analysis and theme.
    analysis = (
        db.query(ProjectAnalysis)
        .filter(
            ProjectAnalysis.id == body.analysis_id,
            ProjectAnalysis.project_id == project_id,
        )
        .first()
    )
    if analysis is None or not analysis.report:
        raise HTTPException(status_code=404, detail="Analysis not found")

    try:
        report = json.loads(analysis.report)
    except Exception:
        raise HTTPException(status_code=500, detail="Analysis report is malformed")

    theme = next(
        (t for t in (report.get("themes") or []) if t.get("title") == body.theme_title),
        None,
    )
    if theme is None:
        raise HTTPException(status_code=404, detail="Theme not found in analysis")

    # 2. Create a ManualCode if one doesn't exist yet. We reuse by exact name
    #    so clicking "promote" twice doesn't create duplicates.
    existing = (
        db.query(ManualCode)
        .filter(ManualCode.project_id == project_id, ManualCode.name == body.theme_title)
        .first()
    )
    if existing is not None:
        code = existing
    else:
        # Pick the next preset colour that isn't already used (nice default).
        used_colors = {
            c.color
            for c in db.query(ManualCode).filter(ManualCode.project_id == project_id).all()
        }
        chosen_color = body.color or next(
            (c for c in PRESET_COLORS if c not in used_colors),
            PRESET_COLORS[0],
        )
        max_order = (
            db.query(ManualCode).filter(ManualCode.project_id == project_id).count()
        )
        code = ManualCode(
            project_id=project_id,
            name=body.theme_title.strip() or "Untitled theme",
            color=chosen_color,
            sort_order=max_order,
        )
        db.add(code)
        db.flush()

    # 3. Walk the theme's quotes and try to auto-tag them. Two lookups:
    #    - ``participant_display_name`` to narrow to one participant
    #    - ``.find(quote_text)`` on each of their turns to locate offsets
    #
    # ``participants_by_name`` is a dict so we eat the N+1 for names we
    # actually need.
    participants_by_name: dict[str, Participant] = {}
    for p in project.participants:
        name = (p.display_name or "").strip()
        if name and name not in participants_by_name:
            participants_by_name[name] = p

    created_tags: list[dict] = []
    unmatched: list[dict] = []

    for quote in theme.get("quotes") or []:
        if not isinstance(quote, dict):
            unmatched.append({"text": str(quote), "reason": "not a structured quote"})
            continue
        text = (quote.get("text") or "").strip()
        if not text:
            continue

        display_name = (quote.get("participant_display_name") or "").strip()
        candidate_participants: list[Participant]
        if display_name and display_name in participants_by_name:
            candidate_participants = [participants_by_name[display_name]]
        else:
            candidate_participants = list(project.participants)

        match_turn = None
        match_start = -1
        for p in candidate_participants:
            for turn in p.turns:
                body_text = turn.response_transcript or ""
                if not body_text:
                    continue
                idx = body_text.find(text)
                if idx >= 0:
                    match_turn = turn
                    match_start = idx
                    break
            if match_turn is not None:
                break

        if match_turn is None:
            unmatched.append({
                "text": text,
                "participant_display_name": display_name or None,
                "reason": "quote text not found in any transcript",
            })
            continue

        # Avoid creating a duplicate tag for the exact same slice.
        duplicate = (
            db.query(QuoteTag)
            .filter(
                QuoteTag.turn_id == match_turn.id,
                QuoteTag.manual_code_id == code.id,
                QuoteTag.start_index == match_start,
                QuoteTag.end_index == match_start + len(text),
            )
            .first()
        )
        if duplicate is not None:
            created_tags.append({
                "id": duplicate.id,
                "turn_id": duplicate.turn_id,
                "selected_text": duplicate.selected_text,
                "already_existed": True,
            })
            continue

        tag = QuoteTag(
            turn_id=match_turn.id,
            manual_code_id=code.id,
            selected_text=text,
            start_index=match_start,
            end_index=match_start + len(text),
        )
        db.add(tag)
        db.flush()
        created_tags.append({
            "id": tag.id,
            "turn_id": tag.turn_id,
            "selected_text": tag.selected_text,
            "already_existed": False,
        })

    db.commit()
    db.refresh(code)

    return {
        "code": _code_to_dict(code, db),
        "tags_created": created_tags,
        "unmatched_quotes": unmatched,
    }


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
