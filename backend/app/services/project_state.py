"""State-of-the-study summary for a single project.

Given a Project row, this service computes a snapshot of where the study
stands right now — participants collected, whether analysis is stale
relative to new data, when the last activity happened — and (optionally)
asks Claude for a one-sentence "what's going on" summary that the
ProjectDetail Overview and the Dashboard stale-project card can surface.

The goal is to give the researcher a "glanceable" line like:

  "6 interviews collected, analysis is 2 versions behind the latest data —
   run a refresh to pull in the 3 new responses."

The numeric parts (counts, gaps, staleness flags) are computed
deterministically in Python. The one-sentence prose is an optional Claude
call the router can skip if it doesn't want to pay for tokens.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import anthropic
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.company import Company
from app.models.interview import Participant, ProjectAnalysis
from app.models.project import Project
from app.services.business_context import full_context_block
from app.services.usage_logger import log_claude_usage

logger = logging.getLogger("auto_interview.project_state")

# Claude is cheap but not free. Only call it when there's actually something
# to summarise (at least one completed participant). The helper below handles
# the "return early with a deterministic fallback" path too.
_STATE_MODEL = "claude-sonnet-4-20250514"
_STATE_MAX_TOKENS = 256


def _utcnow() -> datetime:
    # Models store naive UTC (SQLite legacy). Keep consistent so timedeltas
    # don't explode when comparing naive vs aware datetimes.
    return datetime.utcnow()


def _days_since(dt: Optional[datetime]) -> Optional[int]:
    if dt is None:
        return None
    # Normalise to naive UTC so the subtraction never raises.
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    delta = _utcnow() - dt
    return max(0, int(delta.total_seconds() // 86400))


def compute_project_state(
    project: Project,
    db: Session,
    *,
    include_ai_summary: bool = True,
) -> dict:
    """Return a dict summarising the current state of a project.

    Shape:
        {
          "completed_count": int,
          "in_progress_count": int,
          "target_count": int | None,        # best-effort from link cap / 6
          "last_response_at": iso8601 | None,
          "days_since_last_response": int | None,
          "is_stale": bool,                  # >14 days no new responses
          "latest_analysis": {
              "version": int | None,
              "status": str | None,
              "generated_at": iso8601 | None,
              "participant_count": int | None,
              "is_behind": bool,             # fewer participants than current
              "gap": int,                    # completed_count - analysis.participant_count
          } | None,
          "headline": str,                   # AI-written one-liner OR deterministic fallback
          "suggested_next_action": str,      # e.g. "Refresh analysis", "Recruit more"
        }
    """
    participants = list(project.participants or [])
    completed = [p for p in participants if p.status == "completed"]
    in_progress = [p for p in participants if p.status == "in_progress"]

    # Last completion timestamp — drives staleness.
    last_completed_at = None
    for p in completed:
        if p.completed_at is not None:
            if last_completed_at is None or p.completed_at > last_completed_at:
                last_completed_at = p.completed_at

    days_since_last = _days_since(last_completed_at)
    is_stale = bool(
        completed
        and days_since_last is not None
        and days_since_last >= 14
    )

    # Latest analysis (any status — so "generating" is visible).
    latest = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project.id)
        .order_by(ProjectAnalysis.version.desc())
        .first()
    )

    latest_info: Optional[dict] = None
    if latest is not None:
        analysis_pc = latest.participant_count or 0
        gap = max(0, len(completed) - analysis_pc)
        latest_info = {
            "version": latest.version,
            "status": latest.status,
            "generated_at": latest.generated_at.isoformat() if latest.generated_at else None,
            "participant_count": analysis_pc,
            "is_behind": gap > 0 and latest.status == "ready",
            "gap": gap,
        }

    # Deterministic headline + next-action fallback, always populated so the
    # UI has something to show even when Claude is disabled.
    headline, next_action = _fallback_headline(
        completed_count=len(completed),
        in_progress_count=len(in_progress),
        days_since_last=days_since_last,
        is_stale=is_stale,
        latest_info=latest_info,
    )

    # If there's a completed analysis + at least 1 new thing to summarise,
    # upgrade the headline with a Claude call. Skip for fresh projects with
    # no data — no point paying for "No interviews yet."
    if include_ai_summary and settings.ANTHROPIC_API_KEY and len(completed) >= 1:
        ai_headline = _generate_ai_headline(
            project=project,
            db=db,
            completed_count=len(completed),
            in_progress_count=len(in_progress),
            days_since_last=days_since_last,
            latest_info=latest_info,
        )
        if ai_headline:
            headline = ai_headline

    return {
        "completed_count": len(completed),
        "in_progress_count": len(in_progress),
        "target_count": None,  # reserved — populated from link caps in a future iteration
        "last_response_at": last_completed_at.isoformat() if last_completed_at else None,
        "days_since_last_response": days_since_last,
        "is_stale": is_stale,
        "latest_analysis": latest_info,
        "headline": headline,
        "suggested_next_action": next_action,
    }


# ---------------------------------------------------------------------------
# Fallbacks + AI helpers
# ---------------------------------------------------------------------------


def _fallback_headline(
    *,
    completed_count: int,
    in_progress_count: int,
    days_since_last: Optional[int],
    is_stale: bool,
    latest_info: Optional[dict],
) -> tuple[str, str]:
    """Deterministic headline + suggested next action.

    This is what we show when Claude is disabled (tests, missing API key,
    empty project). It's intentionally short and prescriptive — the whole
    point of this card is to tell the researcher what to do next.
    """
    if completed_count == 0 and in_progress_count == 0:
        return (
            "No interviews collected yet — share your link to start gathering data.",
            "Share interview link",
        )

    if completed_count == 0 and in_progress_count > 0:
        return (
            f"{in_progress_count} interview(s) in progress — waiting for participants to finish.",
            "Check back soon",
        )

    # From here on, at least one completed interview.
    if latest_info is None:
        if completed_count >= 3:
            return (
                f"{completed_count} interviews collected — enough signal to run a first analysis.",
                "Run AI analysis",
            )
        return (
            f"{completed_count} interview(s) collected — keep recruiting for a richer analysis.",
            "Recruit more participants",
        )

    # There's an analysis row.
    if latest_info["status"] == "generating":
        return (
            f"Analysis running on {latest_info['participant_count']} participants — this usually takes under a minute.",
            "Wait for analysis",
        )

    if latest_info["status"] == "failed":
        return (
            "The last analysis run failed. Retry to pick up any new interviews.",
            "Retry analysis",
        )

    # status == "ready"
    gap = latest_info["gap"]
    if gap > 0:
        return (
            f"Analysis is behind by {gap} interview(s) — refresh to include the latest data.",
            "Refresh analysis",
        )

    if is_stale:
        return (
            f"Last response was {days_since_last} days ago — push your link or recruit a new batch.",
            "Recruit more participants",
        )

    return (
        f"Analysis is up to date with {completed_count} interview(s).",
        "Review findings",
    )


def _generate_ai_headline(
    *,
    project: Project,
    db: Session,
    completed_count: int,
    in_progress_count: int,
    days_since_last: Optional[int],
    latest_info: Optional[dict],
) -> Optional[str]:
    """Ask Claude for a single-sentence state-of-study headline.

    Returns None on any failure so the caller falls back to the
    deterministic headline. Every failure is logged at WARN level — we
    never want this to break the project-state endpoint.
    """
    try:
        company = db.query(Company).filter(Company.id == project.company_id).first()
        context = full_context_block(company, project)

        latest_block = ""
        if latest_info:
            latest_block = (
                f"LATEST ANALYSIS: v{latest_info['version']} "
                f"({latest_info['status']}, "
                f"{latest_info['participant_count']} participants"
                f"{', behind current data by ' + str(latest_info['gap']) + ' interviews' if latest_info['is_behind'] else ''}).\n\n"
            )

        system_msg = (
            "You write the study-state headline a researcher reads on their dashboard. "
            "Voice: a research-ops colleague glancing at the data and telling them what to "
            "do next. Concrete, prescriptive, no fluff. ONE sentence, ≤25 words. No "
            "preamble, no surrounding quotes, no exclamation marks."
        )

        prompt = (
            f"{context}"
            f"{latest_block}"
            f"<state>\n"
            f"- Completed interviews: {completed_count}\n"
            f"- In progress: {in_progress_count}\n"
            f"- Days since last response: {days_since_last if days_since_last is not None else '—'}\n"
            f"</state>\n\n"
            "Write ONE sentence that tells the researcher (a) the most important thing about "
            "where this study stands AND (b) the single most useful next action. Always "
            "reference at least one concrete number. If analysis is behind the data, say "
            "\"refresh analysis\". If responses have stalled, say \"recruit\". If too thin "
            "to analyse yet, say so."
        )

        client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=httpx.Timeout(20.0),
        )
        response = client.messages.create(
            model=_STATE_MODEL,
            max_tokens=_STATE_MAX_TOKENS,
            temperature=0.3,
            system=system_msg,
            messages=[{"role": "user", "content": prompt}],
        )

        log_claude_usage(
            db,
            response,
            "project_state",
            company_id=project.company_id,
            project_id=project.id,
        )

        text = (response.content[0].text or "").strip()
        # Strip surrounding quotes some models add despite the instruction.
        if text and text[0] in '"\'' and text[-1] in '"\'':
            text = text[1:-1].strip()
        return text or None
    except Exception as exc:
        logger.warning("Project state AI headline failed: %s", exc)
        return None
