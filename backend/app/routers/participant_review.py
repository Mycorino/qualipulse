"""Researcher tools for compensated studies: review queue + reward list.

We track the promise, never the money. A study opts in by setting
`Project.incentive_text`; from then on completions land as
`review_status="pending"` and the researcher approves / rejects them here.
Rejected interviews drop out of every research output (see
`Participant.counts_for_research`) but keep their credit: rejecting is a
data-quality decision, not a refund.
"""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import (
    get_editable_project_or_404 as _get_editable_project_or_404,
    get_accessible_project_or_404 as _get_project_or_404,
    get_current_company,
    get_db,
)
from app.models.company import Company
from app.models.interview import (
    REVIEW_APPROVED,
    REVIEW_REJECTED,
    REVIEW_STATUSES,
    Participant,
)

router = APIRouter(prefix="/projects", tags=["participant-review"])


class ReviewRequest(BaseModel):
    status: str = Field(..., description="pending | approved | rejected")
    note: str | None = Field(default=None, max_length=1000)


class RewardRequest(BaseModel):
    sent: bool = True


class BulkRewardRequest(BaseModel):
    participant_ids: list[str] = Field(..., min_length=1, max_length=500)
    sent: bool = True


class ReviewStateResponse(BaseModel):
    id: str
    review_status: str
    review_note: str | None = None
    reviewed_at: datetime | None = None
    reward_sent_at: datetime | None = None

    model_config = {"from_attributes": True}


def _participant_or_404(db: Session, project_id: str, participant_id: str) -> Participant:
    p = (
        db.query(Participant)
        .filter(Participant.id == participant_id, Participant.project_id == project_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
    return p


@router.patch(
    "/{project_id}/participants/{participant_id}/review",
    response_model=ReviewStateResponse,
)
def review_participant(
    project_id: str,
    participant_id: str,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ReviewStateResponse:
    project = _get_editable_project_or_404(project_id, company.id, db)
    if body.status not in REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="invalid_review_status")
    p = _participant_or_404(db, project.id, participant_id)
    if p.status != "completed":
        # Nothing to review until the interview exists as a whole.
        raise HTTPException(status_code=400, detail="participant_not_completed")
    p.review_status = body.status
    p.review_note = (body.note or "").strip() or None
    p.reviewed_at = datetime.utcnow()
    if body.status == REVIEW_REJECTED:
        # A rejected participant owes nothing; clear any stale reward stamp.
        p.reward_sent_at = None
    db.commit()
    db.refresh(p)
    return ReviewStateResponse.model_validate(p)


@router.patch(
    "/{project_id}/participants/{participant_id}/reward",
    response_model=ReviewStateResponse,
)
def mark_reward(
    project_id: str,
    participant_id: str,
    body: RewardRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ReviewStateResponse:
    project = _get_editable_project_or_404(project_id, company.id, db)
    p = _participant_or_404(db, project.id, participant_id)
    if body.sent and p.review_status != REVIEW_APPROVED:
        raise HTTPException(status_code=400, detail="participant_not_approved")
    p.reward_sent_at = datetime.utcnow() if body.sent else None
    db.commit()
    db.refresh(p)
    return ReviewStateResponse.model_validate(p)


@router.post(
    "/{project_id}/participants/rewards/bulk",
    response_model=list[ReviewStateResponse],
)
def mark_rewards_bulk(
    project_id: str,
    body: BulkRewardRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[ReviewStateResponse]:
    """Mark several approved participants' rewards as sent (or unsent) in
    one call. Non-approved ids are skipped silently rather than failing the
    whole batch."""
    project = _get_editable_project_or_404(project_id, company.id, db)
    rows = (
        db.query(Participant)
        .filter(
            Participant.project_id == project.id,
            Participant.id.in_(body.participant_ids),
        )
        .all()
    )
    now = datetime.utcnow()
    out: list[Participant] = []
    for p in rows:
        if body.sent and p.review_status != REVIEW_APPROVED:
            continue
        p.reward_sent_at = now if body.sent else None
        out.append(p)
    db.commit()
    return [ReviewStateResponse.model_validate(p) for p in out]


@router.get("/{project_id}/participants/rewards.csv")
def export_rewards_csv(
    project_id: str,
    pending_only: bool = True,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """The payout list: approved participants with the contact details the
    researcher needs to send the incentive through whatever tool they use.
    Viewer-accessible (read only). Not gated behind the CSV-export
    entitlement: this is the reward list, not the transcript export."""
    project = _get_project_or_404(project_id, company.id, db)
    q = db.query(Participant).filter(
        Participant.project_id == project.id,
        Participant.review_status == REVIEW_APPROVED,
    )
    if pending_only:
        q = q.filter(Participant.reward_sent_at.is_(None))
    rows = q.order_by(Participant.reviewed_at.asc().nullsfirst(), Participant.completed_at.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["participant_id", "display_name", "email", "completed_at", "approved_at", "incentive", "reward_sent_at"]
    )
    for p in rows:
        writer.writerow(
            [
                p.id,
                _csv_safe(p.display_name),
                _csv_safe(p.email),
                _fmt(p.completed_at),
                _fmt(p.reviewed_at),
                _csv_safe(project.incentive_text),
                _fmt(p.reward_sent_at),
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rewards-{project.id}.csv"'},
    )


def _fmt(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def _csv_safe(value) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @ prefixes)."""
    if value is None:
        return ""
    s = str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s
