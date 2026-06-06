"""V4 paywall — first-3-transcripts-free visibility model.

The pricing motion: free workspaces can RUN 3 interviews on starter
credits, but only the first 3 completed transcripts are viewable. The
remaining completed responses beyond the preview are paywall-locked —
unlocked by subscribing OR buying a credit pack.

Visibility is **derived, not stored** — a single source of truth based
on the workspace's payment status + the participant's completion
order. No flag column means no race conditions when participants
complete in parallel, no backfill on subscription state changes, and
ex-paying customers retain access automatically via the sticky
``Company.has_ever_paid`` flag.

The free-preview budget is **per workspace, not per study** — creating
a new study doesn't reset the 3 free slots. This is intentional: it
makes the abuse path of "new study = new free transcripts" impossible.

Decision points:
- "Has the workspace ever paid?" → ``has_ever_paid=True`` flag, set on
  the first paid subscription OR credit-pack purchase
- "Currently has an active paid plan?" → subscription_status in the
  paid set
- "Which 3 are visible for free?" → first 3 completed in the workspace
  ordered by ``completed_at`` ascending
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.interview import Participant
from app.models.project import Project

# Number of transcripts the free tier can view. Tunable — start at 3.
FREE_PREVIEW_COUNT = 3

# Subscription statuses that count as "currently has an active paid
# plan." Trial / canceled / unpaid do NOT — but if has_ever_paid is
# True they still get access via that path.
_PAID_STATUSES = frozenset({"active", "trialing-paid", "past_due"})


@dataclass
class VisibilityState:
    """Snapshot of the workspace's paywall state."""

    # True if everything is visible (paid OR ever-paid).
    fully_unlocked: bool
    # Count of currently-visible-for-free transcripts (caps at
    # FREE_PREVIEW_COUNT). Ignored when fully_unlocked is True.
    free_used: int
    # FREE_PREVIEW_COUNT - free_used, or None if fully_unlocked.
    free_remaining: Optional[int]


def get_visibility_state(db: Session, company: Company) -> VisibilityState:
    """Compute the workspace's overall paywall state.

    The two paths to ``fully_unlocked=True``:
    - currently paid (subscription_status in _PAID_STATUSES)
    - has_ever_paid sticky flag

    Otherwise we count how many of the FREE_PREVIEW_COUNT slots are
    currently consumed by completed participants.
    """
    if (
        company.has_ever_paid
        or (company.subscription_status or "") in _PAID_STATUSES
    ):
        return VisibilityState(
            fully_unlocked=True, free_used=0, free_remaining=None
        )

    completed_count = (
        db.query(Participant)
        .join(Project, Participant.project_id == Project.id)
        .filter(
            Project.company_id == company.id,
            Project.is_demo.is_(False),
            Participant.status == "completed",
        )
        .count()
    )
    free_used = min(completed_count, FREE_PREVIEW_COUNT)
    return VisibilityState(
        fully_unlocked=False,
        free_used=free_used,
        free_remaining=max(0, FREE_PREVIEW_COUNT - free_used),
    )


def is_participant_visible(
    db: Session, company: Company, participant: Participant
) -> bool:
    """Decide whether the researcher can see this participant's
    transcript + audio.

    Returns True if:
    - workspace has paid (active subscription) OR has ever paid OR
    - participant is among the first FREE_PREVIEW_COUNT completed in
      the workspace OR
    - participant is still in_progress (we always show in-progress —
      the paywall only gates completed data, not the recruitment view)
    """
    if (
        company.has_ever_paid
        or (company.subscription_status or "") in _PAID_STATUSES
    ):
        return True

    # In-progress participants are always visible (no body to gate).
    if participant.status != "completed":
        return True

    # Otherwise check if this participant is among the first
    # FREE_PREVIEW_COUNT completed in the workspace by completion time.
    if participant.completed_at is None:
        # Completed without a timestamp — shouldn't happen but be safe.
        return True

    earlier_or_equal_count = (
        db.query(Participant)
        .join(Project, Participant.project_id == Project.id)
        .filter(
            Project.company_id == company.id,
            Project.is_demo.is_(False),
            Participant.status == "completed",
            Participant.completed_at <= participant.completed_at,
        )
        .count()
    )
    return earlier_or_equal_count <= FREE_PREVIEW_COUNT


def paywall_payload(
    company: Company,
    locked_completed_count: int,
) -> dict:
    """Standard response body for a paywalled transcript or analysis.

    Returned with HTTP 402 (Payment Required) so the frontend can
    differentiate from 403 (auth) and 404 (missing). Includes enough
    metadata for the FE to render a useful unlock card.
    """
    return {
        "paywall": True,
        "reason": "free_preview_exhausted",
        "free_preview_count": FREE_PREVIEW_COUNT,
        "locked_completed_count": locked_completed_count,
        "unlock_paths": ["subscription", "credit_pack"],
        "has_ever_paid": company.has_ever_paid,
    }
