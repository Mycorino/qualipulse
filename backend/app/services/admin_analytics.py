"""Admin-dashboard analytics: growth KPIs + AI unit economics.

Everything here is read-only and windowed. A *window* is the last ``days``
days; every KPI also reports the value for the window immediately before
it so the UI can show a delta instead of a bare number.

Unit-economics vocabulary used throughout:

- **Completed interview**: ``Participant.status == "completed"`` on a
  non-demo project. Demo fixtures are seeded "completed" with zero AI
  spend and would otherwise drag every average toward zero.
- **Interview cost**: every ``AIUsageLog`` row carrying a
  ``participant_id`` (turns, STT, TTS, warmup, transcript cleanup,
  quality). That is the fully loaded cost of running one interview; it
  deliberately excludes study-level spend (analysis, copilot, translation)
  which is reported separately as *overhead*.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.billing import Plan, WorkspaceSubscription
from app.models.company import Company
from app.models.interview import InterviewTurn, Participant
from app.models.project import Project
from app.models.usage import AIUsageLog

# Operations that make up the fully-loaded cost of one interview, in the
# order the UI stacks them. Anything else with a participant_id lands in
# "other".
INTERVIEW_COST_BUCKETS = ("interview_turn", "stt", "tts", "interview_warmup", "transcript_cleanup", "quality")

# Operation → product area, for the "where does the money go" rollup.
OPERATION_AREAS: dict[str, str] = {
    "interview_turn": "interviews",
    "interview_warmup": "interviews",
    "stt": "interviews",
    "tts": "interviews",
    "transcript_cleanup": "interviews",
    "quality": "interviews",
    "analysis": "analysis",
    "study_analysis": "analysis",
    "cross_synthesis": "analysis",
    "segment_reco": "analysis",
    "tag_suggest": "analysis",
    "codebook_suggest": "analysis",
    "copilot": "copilot",
    "question_coach": "copilot",
    "project_state": "copilot",
    "translation": "translation",
    "study_name_translation": "translation",
    "screening_translation": "translation",
    "research_context_translation": "translation",
    "website_intel": "onboarding",
    "name_lookup": "onboarding",
    "goals_classification": "onboarding",
    "onboarding_suggestions": "onboarding",
    "welcome_email": "onboarding",
}


def _window(days: int) -> tuple[datetime, datetime, datetime]:
    """Return (prev_start, start, now) for a trailing window of ``days``."""
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    prev_start = start - timedelta(days=days)
    return prev_start, start, now


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round(100.0 * (current - previous) / previous, 1)


def _kpi(current: float, previous: float) -> dict:
    return {"value": current, "previous": previous, "change_pct": _pct_change(current, previous)}


def _date_keys(start: datetime, now: datetime) -> list[str]:
    days = (now.date() - start.date()).days
    return [str(start.date() + timedelta(days=i)) for i in range(days + 1)]


def _by_day(rows) -> dict[str, float]:
    return {str(day): float(val or 0) for day, val in rows}


# ── Overview ────────────────────────────────────────────────────────────────

def overview_report(db: Session, days: int) -> dict:
    prev_start, start, now = _window(days)

    real_project = Project.is_demo.is_(False)
    completed = Participant.status == "completed"

    def count_in(model_col, lo, hi, *extra):
        q = db.query(func.count()).select_from(model_col.class_).filter(
            model_col >= lo, model_col < hi, *extra
        )
        return int(q.scalar() or 0)

    def interviews_in(lo, hi) -> int:
        return int(
            db.query(func.count(Participant.id))
            .join(Project, Participant.project_id == Project.id)
            .filter(completed, real_project, Participant.completed_at >= lo, Participant.completed_at < hi)
            .scalar() or 0
        )

    def cost_in(lo, hi, *extra) -> float:
        return float(
            db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0))
            .filter(AIUsageLog.created_at >= lo, AIUsageLog.created_at < hi, *extra)
            .scalar() or 0.0
        )

    signups = count_in(Company.created_at, start, now)
    signups_prev = count_in(Company.created_at, prev_start, start)
    activated = count_in(Company.created_at, start, now, Company.onboarding_completed.is_(True))
    activated_prev = count_in(Company.created_at, prev_start, start, Company.onboarding_completed.is_(True))
    studies = count_in(Project.created_at, start, now, real_project)
    studies_prev = count_in(Project.created_at, prev_start, start, real_project)
    interviews = interviews_in(start, now)
    interviews_prev = interviews_in(prev_start, start)
    cost = cost_in(start, now)
    cost_prev = cost_in(prev_start, start)
    interview_cost = cost_in(start, now, AIUsageLog.participant_id.isnot(None))
    interview_cost_prev = cost_in(prev_start, start, AIUsageLog.participant_id.isnot(None))

    # Workspaces that completed at least one interview in the window: the
    # most honest "active customer" signal we have (logins aren't logged).
    def active_workspaces(lo, hi) -> int:
        return int(
            db.query(func.count(func.distinct(Project.company_id)))
            .join(Participant, Participant.project_id == Project.id)
            .filter(completed, real_project, Participant.completed_at >= lo, Participant.completed_at < hi)
            .scalar() or 0
        )

    active = active_workspaces(start, now)
    active_prev = active_workspaces(prev_start, start)

    total_users = int(db.query(func.count(Company.id)).scalar() or 0)
    paying = int(db.query(func.count(Company.id)).filter(Company.has_ever_paid.is_(True)).scalar() or 0)
    total_interviews = int(
        db.query(func.count(Participant.id))
        .join(Project, Participant.project_id == Project.id)
        .filter(completed, real_project)
        .scalar() or 0
    )
    total_cost = float(db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).scalar() or 0.0)

    # Daily series — zero-filled so the chart has one bar per day.
    keys = _date_keys(start, now)
    signups_by_day = _by_day(
        db.query(func.date(Company.created_at), func.count(Company.id))
        .filter(Company.created_at >= start)
        .group_by(func.date(Company.created_at)).all()
    )
    interviews_by_day = _by_day(
        db.query(func.date(Participant.completed_at), func.count(Participant.id))
        .join(Project, Participant.project_id == Project.id)
        .filter(completed, real_project, Participant.completed_at >= start)
        .group_by(func.date(Participant.completed_at)).all()
    )
    cost_by_day = _by_day(
        db.query(func.date(AIUsageLog.created_at), func.sum(AIUsageLog.cost_usd))
        .filter(AIUsageLog.created_at >= start)
        .group_by(func.date(AIUsageLog.created_at)).all()
    )
    daily = [
        {
            "date": k,
            "signups": int(signups_by_day.get(k, 0)),
            "interviews": int(interviews_by_day.get(k, 0)),
            "cost_usd": round(cost_by_day.get(k, 0.0), 4),
        }
        for k in keys
    ]

    # Plan mix from the real subscription table (what customers are gated on).
    plan_rows = (
        db.query(Plan.public_name, Plan.is_legacy, func.count(WorkspaceSubscription.id))
        .join(Plan, WorkspaceSubscription.plan_id == Plan.id)
        .filter(WorkspaceSubscription.status.notin_(("canceled",)))
        .group_by(Plan.public_name, Plan.is_legacy)
        .order_by(func.count(WorkspaceSubscription.id).desc())
        .all()
    )
    plan_mix = [
        {"label": name, "legacy": bool(legacy), "count": int(n)} for name, legacy, n in plan_rows
    ]

    # Most active workspaces this window, with what they cost us.
    cost_sub = (
        db.query(AIUsageLog.company_id.label("cid"), func.sum(AIUsageLog.cost_usd).label("cost"))
        .filter(AIUsageLog.created_at >= start)
        .group_by(AIUsageLog.company_id)
        .subquery()
    )
    top_rows = (
        db.query(
            Company.id, Company.name, Company.email,
            func.count(Participant.id).label("interviews"),
            func.coalesce(cost_sub.c.cost, 0.0).label("cost"),
        )
        .join(Project, Project.company_id == Company.id)
        .join(Participant, Participant.project_id == Project.id)
        .outerjoin(cost_sub, cost_sub.c.cid == Company.id)
        .filter(completed, real_project, Participant.completed_at >= start)
        .group_by(Company.id, Company.name, Company.email, cost_sub.c.cost)
        .order_by(func.count(Participant.id).desc())
        .limit(8)
        .all()
    )
    top_workspaces = [
        {
            "company_id": cid, "name": name, "email": email,
            "interviews": int(n), "cost_usd": round(float(c), 4),
        }
        for cid, name, email, n, c in top_rows
    ]

    # Funnel for the cohort that signed up in the window.
    cohort_ids = [cid for (cid,) in db.query(Company.id).filter(Company.created_at >= start).all()]
    cohort_studies = 0
    cohort_interviewed = 0
    if cohort_ids:
        cohort_studies = int(
            db.query(func.count(func.distinct(Project.company_id)))
            .filter(Project.company_id.in_(cohort_ids), real_project)
            .scalar() or 0
        )
        cohort_interviewed = int(
            db.query(func.count(func.distinct(Project.company_id)))
            .join(Participant, Participant.project_id == Project.id)
            .filter(Project.company_id.in_(cohort_ids), real_project, completed)
            .scalar() or 0
        )
    funnel = [
        {"step": "signed_up", "count": signups},
        {"step": "onboarded", "count": activated},
        {"step": "created_study", "count": cohort_studies},
        {"step": "first_interview", "count": cohort_interviewed},
    ]

    return {
        "days": days,
        "kpis": {
            "signups": _kpi(signups, signups_prev),
            "activated": _kpi(activated, activated_prev),
            "studies_created": _kpi(studies, studies_prev),
            "interviews_completed": _kpi(interviews, interviews_prev),
            "active_workspaces": _kpi(active, active_prev),
            "ai_cost_usd": _kpi(round(cost, 4), round(cost_prev, 4)),
            "cost_per_interview_usd": _kpi(
                round(interview_cost / interviews, 4) if interviews else 0.0,
                round(interview_cost_prev / interviews_prev, 4) if interviews_prev else 0.0,
            ),
        },
        "totals": {
            "users": total_users,
            "paying_customers": paying,
            "interviews_completed": total_interviews,
            "ai_cost_usd": round(total_cost, 4),
        },
        "daily": daily,
        "plan_mix": plan_mix,
        "top_workspaces": top_workspaces,
        "funnel": funnel,
    }


# ── Costs ───────────────────────────────────────────────────────────────────

def _percentiles(values: list[float]) -> dict:
    if not values:
        return {"avg": 0.0, "median": 0.0, "p90": 0.0, "max": 0.0}
    vals = sorted(values)
    p90 = vals[min(len(vals) - 1, int(round(0.9 * (len(vals) - 1))))]
    return {
        "avg": round(sum(vals) / len(vals), 4),
        "median": round(median(vals), 4),
        "p90": round(p90, 4),
        "max": round(vals[-1], 4),
    }


def _interview_economics(db: Session, start: datetime | None, company_id: str | None = None) -> dict:
    """Per-interview cost distribution + what each interview is made of."""
    filters = [AIUsageLog.participant_id.isnot(None)]
    if start is not None:
        filters.append(AIUsageLog.created_at >= start)
    if company_id is not None:
        filters.append(AIUsageLog.company_id == company_id)

    per_participant = (
        db.query(AIUsageLog.participant_id, func.sum(AIUsageLog.cost_usd))
        .filter(*filters)
        .group_by(AIUsageLog.participant_id)
        .all()
    )
    costs = [float(c or 0) for _, c in per_participant]
    interviews_with_cost = len(costs)

    bucket_rows = (
        db.query(
            AIUsageLog.operation,
            func.sum(AIUsageLog.cost_usd),
            func.sum(AIUsageLog.audio_seconds),
            func.sum(AIUsageLog.characters),
            func.sum(AIUsageLog.input_tokens),
            func.sum(AIUsageLog.output_tokens),
        )
        .filter(*filters)
        .group_by(AIUsageLog.operation)
        .all()
    )
    breakdown: dict[str, float] = {b: 0.0 for b in INTERVIEW_COST_BUCKETS}
    breakdown["other"] = 0.0
    audio_seconds = 0.0
    tts_chars = 0
    for op, cost, secs, chars, _i, _o in bucket_rows:
        key = op if op in breakdown else "other"
        breakdown[key] += float(cost or 0)
        audio_seconds += float(secs or 0)
        tts_chars += int(chars or 0)

    # Completed interviews + their shape (turns, minutes), from the source of
    # truth rather than the usage log.
    p_filters = [Participant.status == "completed", Project.is_demo.is_(False)]
    if start is not None:
        p_filters.append(Participant.completed_at >= start)
    if company_id is not None:
        p_filters.append(Project.company_id == company_id)
    completed_count = int(
        db.query(func.count(Participant.id))
        .join(Project, Participant.project_id == Project.id)
        .filter(*p_filters)
        .scalar() or 0
    )
    turns_sub = (
        db.query(InterviewTurn.participant_id.label("pid"), func.count(InterviewTurn.id).label("turns"))
        .group_by(InterviewTurn.participant_id)
        .subquery()
    )
    shape = (
        db.query(func.avg(turns_sub.c.turns))
        .select_from(Participant)
        .join(Project, Participant.project_id == Project.id)
        .join(turns_sub, turns_sub.c.pid == Participant.id)
        .filter(*p_filters)
        .scalar()
    )
    avg_turns = round(float(shape or 0), 1)

    total_interview_cost = sum(costs)
    return {
        "completed_interviews": completed_count,
        "interviews_with_cost": interviews_with_cost,
        "total_cost_usd": round(total_interview_cost, 4),
        "cost_per_completed_usd": round(total_interview_cost / completed_count, 4) if completed_count else 0.0,
        "per_interview": _percentiles(costs),
        "breakdown": {k: round(v, 4) for k, v in breakdown.items()},
        "avg_turns": avg_turns,
        "avg_audio_minutes": round(audio_seconds / 60 / interviews_with_cost, 1) if interviews_with_cost else 0.0,
        "avg_tts_characters": int(tts_chars / interviews_with_cost) if interviews_with_cost else 0,
    }


def costs_report(db: Session, days: int | None) -> dict:
    """Platform AI spend. ``days=None`` means all time."""
    now = datetime.utcnow()
    start = (now - timedelta(days=days)) if days else None
    prev_start = (start - timedelta(days=days)) if (start and days) else None
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    win = [AIUsageLog.created_at >= start] if start else []

    def total(*extra) -> float:
        return float(db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).filter(*extra).scalar() or 0.0)

    window_cost = total(*win)
    prev_cost = total(AIUsageLog.created_at >= prev_start, AIUsageLog.created_at < start) if prev_start else 0.0
    all_time = total()
    this_month = total(AIUsageLog.created_at >= month_start)

    op_rows = (
        db.query(
            AIUsageLog.operation,
            func.count(AIUsageLog.id),
            func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.audio_seconds), 0.0),
            func.coalesce(func.sum(AIUsageLog.characters), 0),
        )
        .filter(*win)
        .group_by(AIUsageLog.operation)
        .order_by(func.sum(AIUsageLog.cost_usd).desc())
        .all()
    )
    by_operation = [
        {
            "operation": op,
            "area": OPERATION_AREAS.get(op, "other"),
            "calls": int(n),
            "cost_usd": round(float(c), 6),
            "avg_cost_usd": round(float(c) / n, 6) if n else 0.0,
            "input_tokens": int(ti),
            "output_tokens": int(to),
            "audio_seconds": round(float(secs), 1),
            "characters": int(chars),
        }
        for op, n, c, ti, to, secs, chars in op_rows
    ]
    by_area: dict[str, float] = {}
    for row in by_operation:
        by_area[row["area"]] = by_area.get(row["area"], 0.0) + row["cost_usd"]
    by_area_list = sorted(
        ({"area": a, "cost_usd": round(c, 6)} for a, c in by_area.items()),
        key=lambda r: -r["cost_usd"],
    )

    model_rows = (
        db.query(
            AIUsageLog.model,
            func.count(AIUsageLog.id),
            func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
        )
        .filter(*win)
        .group_by(AIUsageLog.model)
        .order_by(func.sum(AIUsageLog.cost_usd).desc())
        .all()
    )
    by_model = [
        {"model": m or "(unknown)", "calls": int(n), "cost_usd": round(float(c), 6)}
        for m, n, c in model_rows
    ]

    daily = []
    if start is not None:
        by_day = _by_day(
            db.query(func.date(AIUsageLog.created_at), func.sum(AIUsageLog.cost_usd))
            .filter(*win)
            .group_by(func.date(AIUsageLog.created_at)).all()
        )
        int_by_day = _by_day(
            db.query(func.date(AIUsageLog.created_at), func.sum(AIUsageLog.cost_usd))
            .filter(*win, AIUsageLog.participant_id.isnot(None))
            .group_by(func.date(AIUsageLog.created_at)).all()
        )
        daily = [
            {
                "date": k,
                "cost_usd": round(by_day.get(k, 0.0), 4),
                "interview_cost_usd": round(int_by_day.get(k, 0.0), 4),
            }
            for k in _date_keys(start, now)
        ]

    economics = _interview_economics(db, start)

    # Per-workspace rows: window cost, all-time cost, completed interviews
    # (real ones), cost per interview, plan.
    win_cost_sub = (
        db.query(AIUsageLog.company_id.label("cid"), func.sum(AIUsageLog.cost_usd).label("cost"))
        .filter(*win, AIUsageLog.company_id.isnot(None))
        .group_by(AIUsageLog.company_id).subquery()
    )
    win_int_cost_sub = (
        db.query(AIUsageLog.company_id.label("cid"), func.sum(AIUsageLog.cost_usd).label("cost"))
        .filter(*win, AIUsageLog.company_id.isnot(None), AIUsageLog.participant_id.isnot(None))
        .group_by(AIUsageLog.company_id).subquery()
    )
    all_cost_sub = (
        db.query(AIUsageLog.company_id.label("cid"), func.sum(AIUsageLog.cost_usd).label("cost"))
        .filter(AIUsageLog.company_id.isnot(None))
        .group_by(AIUsageLog.company_id).subquery()
    )
    p_win = [Participant.status == "completed", Project.is_demo.is_(False)]
    if start is not None:
        p_win.append(Participant.completed_at >= start)
    win_int_sub = (
        db.query(Project.company_id.label("cid"), func.count(Participant.id).label("n"))
        .join(Participant, Participant.project_id == Project.id)
        .filter(*p_win)
        .group_by(Project.company_id).subquery()
    )
    all_int_sub = (
        db.query(Project.company_id.label("cid"), func.count(Participant.id).label("n"))
        .join(Participant, Participant.project_id == Project.id)
        .filter(Participant.status == "completed", Project.is_demo.is_(False))
        .group_by(Project.company_id).subquery()
    )
    last_activity_sub = (
        db.query(Project.company_id.label("cid"), func.max(Participant.completed_at).label("last"))
        .join(Participant, Participant.project_id == Project.id)
        .group_by(Project.company_id).subquery()
    )
    sub_alias = (
        db.query(WorkspaceSubscription.workspace_id.label("cid"), Plan.public_name.label("plan"), Plan.is_legacy.label("legacy"))
        .join(Plan, WorkspaceSubscription.plan_id == Plan.id)
        .subquery()
    )
    company_rows = (
        db.query(
            Company.id, Company.name, Company.email, Company.has_ever_paid, Company.created_at,
            func.coalesce(win_cost_sub.c.cost, 0.0),
            func.coalesce(win_int_cost_sub.c.cost, 0.0),
            func.coalesce(all_cost_sub.c.cost, 0.0),
            func.coalesce(win_int_sub.c.n, 0),
            func.coalesce(all_int_sub.c.n, 0),
            last_activity_sub.c.last,
            sub_alias.c.plan, sub_alias.c.legacy,
        )
        .outerjoin(win_cost_sub, win_cost_sub.c.cid == Company.id)
        .outerjoin(win_int_cost_sub, win_int_cost_sub.c.cid == Company.id)
        .outerjoin(all_cost_sub, all_cost_sub.c.cid == Company.id)
        .outerjoin(win_int_sub, win_int_sub.c.cid == Company.id)
        .outerjoin(all_int_sub, all_int_sub.c.cid == Company.id)
        .outerjoin(last_activity_sub, last_activity_sub.c.cid == Company.id)
        .outerjoin(sub_alias, sub_alias.c.cid == Company.id)
        .filter((all_cost_sub.c.cost > 0) | (all_int_sub.c.n > 0))
        .order_by(func.coalesce(win_cost_sub.c.cost, 0.0).desc(), func.coalesce(all_cost_sub.c.cost, 0.0).desc())
        .all()
    )
    by_company = []
    seen: set[str] = set()
    for cid, name, email, paid, created, wc, wic, ac, wn, an, last, plan, legacy in company_rows:
        if cid in seen:  # a workspace with several subscription rows
            continue
        seen.add(cid)
        by_company.append({
            "company_id": cid,
            "name": name,
            "email": email,
            "has_ever_paid": bool(paid),
            "plan_name": plan,
            "plan_is_legacy": bool(legacy) if legacy is not None else None,
            "created_at": created.isoformat() if created else None,
            "last_interview_at": last.isoformat() if last else None,
            "window_cost_usd": round(float(wc), 4),
            "total_cost_usd": round(float(ac), 4),
            "window_interviews": int(wn),
            "total_interviews": int(an),
            "window_cost_per_interview_usd": round(float(wic) / wn, 4) if wn else None,
        })

    return {
        "days": days,
        "window_cost_usd": round(window_cost, 4),
        "previous_window_cost_usd": round(prev_cost, 4),
        "change_pct": _pct_change(window_cost, prev_cost) if prev_start else None,
        "all_time_cost_usd": round(all_time, 4),
        "this_month_usd": round(this_month, 4),
        "by_operation": by_operation,
        "by_area": by_area_list,
        "by_model": by_model,
        "daily": daily,
        "interview_economics": economics,
        "by_company": by_company,
    }


def company_costs_report(db: Session, company: Company, days: int | None, interview_limit: int = 50) -> dict:
    """One workspace: spend by study, per-interview cost rows, economics."""
    now = datetime.utcnow()
    start = (now - timedelta(days=days)) if days else None
    win = [AIUsageLog.created_at >= start] if start else []
    cid = company.id

    total_cost = float(
        db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0))
        .filter(AIUsageLog.company_id == cid).scalar() or 0.0
    )
    window_cost = float(
        db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0))
        .filter(AIUsageLog.company_id == cid, *win).scalar() or 0.0
    )

    op_rows = (
        db.query(AIUsageLog.operation, func.count(AIUsageLog.id), func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0))
        .filter(AIUsageLog.company_id == cid, *win)
        .group_by(AIUsageLog.operation)
        .order_by(func.sum(AIUsageLog.cost_usd).desc())
        .all()
    )
    by_operation = [
        {"operation": op, "area": OPERATION_AREAS.get(op, "other"), "calls": int(n), "cost_usd": round(float(c), 6)}
        for op, n, c in op_rows
    ]

    cost_by_project = (
        db.query(AIUsageLog.project_id.label("pid"), func.sum(AIUsageLog.cost_usd).label("cost"))
        .filter(AIUsageLog.company_id == cid, AIUsageLog.project_id.isnot(None), *win)
        .group_by(AIUsageLog.project_id).subquery()
    )
    completed_by_project = (
        db.query(Participant.project_id.label("pid"), func.count(Participant.id).label("n"))
        .filter(Participant.status == "completed")
        .group_by(Participant.project_id).subquery()
    )
    project_rows = (
        db.query(
            Project.id, Project.name, Project.is_demo, Project.created_at, Project.archived_at,
            func.coalesce(cost_by_project.c.cost, 0.0),
            func.coalesce(completed_by_project.c.n, 0),
        )
        .outerjoin(cost_by_project, cost_by_project.c.pid == Project.id)
        .outerjoin(completed_by_project, completed_by_project.c.pid == Project.id)
        .filter(Project.company_id == cid)
        .order_by(func.coalesce(cost_by_project.c.cost, 0.0).desc(), Project.created_at.desc())
        .all()
    )
    by_project = [
        {
            "project_id": pid, "name": name, "is_demo": bool(demo),
            "created_at": created.isoformat() if created else None,
            "archived": archived is not None,
            "cost_usd": round(float(c), 4),
            "completed_interviews": int(n),
            "cost_per_interview_usd": round(float(c) / n, 4) if n and not demo else None,
        }
        for pid, name, demo, created, archived, c, n in project_rows
    ]

    # Per-interview rows: most recent participants with cost split.
    per_op = (
        db.query(
            AIUsageLog.participant_id.label("pid"),
            func.sum(AIUsageLog.cost_usd).label("cost"),
            func.sum(case((AIUsageLog.operation == "stt", AIUsageLog.cost_usd), else_=0.0)).label("stt"),
            func.sum(case((AIUsageLog.operation == "tts", AIUsageLog.cost_usd), else_=0.0)).label("tts"),
            func.sum(case((AIUsageLog.operation.in_(("interview_turn", "interview_warmup")), AIUsageLog.cost_usd), else_=0.0)).label("llm"),
            func.sum(AIUsageLog.audio_seconds).label("audio"),
        )
        .filter(AIUsageLog.company_id == cid, AIUsageLog.participant_id.isnot(None))
        .group_by(AIUsageLog.participant_id).subquery()
    )
    turns_sub = (
        db.query(InterviewTurn.participant_id.label("pid"), func.count(InterviewTurn.id).label("turns"))
        .group_by(InterviewTurn.participant_id).subquery()
    )
    p_filters = [Project.company_id == cid, Project.is_demo.is_(False)]
    if start is not None:
        p_filters.append(Participant.started_at >= start)
    interview_rows = (
        db.query(
            Participant.id, Participant.display_name, Participant.status, Participant.quality_label,
            Participant.started_at, Participant.completed_at, Project.name,
            func.coalesce(per_op.c.cost, 0.0), func.coalesce(per_op.c.stt, 0.0),
            func.coalesce(per_op.c.tts, 0.0), func.coalesce(per_op.c.llm, 0.0),
            func.coalesce(per_op.c.audio, 0.0), func.coalesce(turns_sub.c.turns, 0),
        )
        .join(Project, Participant.project_id == Project.id)
        .outerjoin(per_op, per_op.c.pid == Participant.id)
        .outerjoin(turns_sub, turns_sub.c.pid == Participant.id)
        .filter(*p_filters)
        .order_by(Participant.started_at.desc())
        .limit(interview_limit)
        .all()
    )
    interviews = []
    for pid, name, st, ql, started, done, pname, cost, stt, tts, llm, audio, turns in interview_rows:
        minutes = None
        if started and done:
            minutes = round((done - started).total_seconds() / 60, 1)
        interviews.append({
            "participant_id": pid,
            "display_name": name,
            "project_name": pname,
            "status": st,
            "quality_label": ql,
            "started_at": started.isoformat() if started else None,
            "duration_minutes": minutes,
            "turns": int(turns),
            "audio_minutes": round(float(audio) / 60, 1),
            "cost_usd": round(float(cost), 4),
            "stt_usd": round(float(stt), 4),
            "tts_usd": round(float(tts), 4),
            "llm_usd": round(float(llm), 4),
            "other_usd": round(float(cost) - float(stt) - float(tts) - float(llm), 4),
        })

    return {
        "company_id": cid,
        "name": company.name,
        "email": company.email,
        "days": days,
        "window_cost_usd": round(window_cost, 4),
        "total_cost_usd": round(total_cost, 4),
        "by_operation": by_operation,
        "by_project": by_project,
        "interview_economics": _interview_economics(db, start, company_id=cid),
        "interviews": interviews,
    }
