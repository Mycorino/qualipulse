"""Survey dashboard aggregations.

Per-question analytics for the /surveys/{id}/dashboard endpoint. Each
question type has its own aggregation shape:

  - likert/nps: histogram by bucket + mean (when n>=min_n)
  - mc_single/mc_multi: choice counts + Wilson 95% CI per choice
  - open_text: raw responses (sampled, max 50) for the editor; AI
    clustering is opt-in and shipped in Sprint 13
  - short_text: raw responses (sampled, max 50)

ALL aggregations respect the methodology contract from services/stats.py:
percentages are None below n=30, Wilson CIs only, no normal approx.
Frontend has no path to render forbidden values because we don't return
them from the backend.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.survey import (
    Survey,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)
from app.services.stats import DEFAULT_MIN_N, completion_rate, wilson_proportion

# Deterministic per-question takeaway lines (the editorial anchor above each
# chart, both in the dashboard UI and in the exported reports). Built only
# from values the stats layer released — a suppressed percentage can never
# leak into a takeaway.
_TAKEAWAYS = {
    "en": {
        "mc_pct": "“{label}” leads — {pct}% of {n} respondents ({count} answers).",
        "mc_count": "“{label}” leads with {count} of {n} answers.",
        "likert_mean": "Average rating {mean} on a 1–{scale} scale (n={n}).",
        "likert_mode": "Most common rating: {bucket} of {scale} ({count} of {n} answers).",
        "nps": "NPS {score} — {p} promoters vs {d} detractors out of {n} respondents.",
    },
    "fr": {
        "mc_pct": "« {label} » arrive en tête — {pct} % des {n} répondants ({count} réponses).",
        "mc_count": "« {label} » arrive en tête avec {count} réponses sur {n}.",
        "likert_mean": "Note moyenne de {mean} sur une échelle de 1 à {scale} (n={n}).",
        "likert_mode": "Note la plus fréquente : {bucket} sur {scale} ({count} réponses sur {n}).",
        "nps": "NPS {score} — {p} promoteurs contre {d} détracteurs sur {n} répondants.",
    },
}


def _takeaway_for(qa: "QuestionAnalytics", lang: str) -> str | None:
    """One-sentence deterministic takeaway for a question, or None."""
    T = _TAKEAWAYS["fr" if (lang or "en").lower().startswith("fr") else "en"]
    n = qa.n_answered
    if n == 0:
        return None

    if qa.type in ("mc_single", "mc_multi"):
        choices = (qa.breakdown or {}).get("choices") or []
        if not choices:
            return None
        top = choices[0]  # already sorted by count desc
        if not top.get("count"):
            return None
        if top.get("percentage") is not None:
            return T["mc_pct"].format(
                label=top.get("label", ""), pct=round(top["percentage"]),
                n=n, count=top["count"],
            )
        return T["mc_count"].format(label=top.get("label", ""), count=top["count"], n=n)

    if qa.type == "nps":
        b = qa.breakdown or {}
        if b.get("nps_score") is not None:
            return T["nps"].format(
                score=f"{b['nps_score']:+d}", p=b.get("promoters", 0),
                d=b.get("detractors", 0), n=n,
            )
        return None

    if qa.type == "likert":
        hist = (qa.breakdown or {}).get("histogram") or []
        if not hist:
            return None
        scale = max((h.get("bucket") or 0) for h in hist)
        if qa.mean is not None:
            return T["likert_mean"].format(mean=f"{qa.mean:.1f}", scale=scale, n=n)
        top = max(hist, key=lambda h: h.get("count") or 0)
        if not top.get("count"):
            return None
        return T["likert_mode"].format(
            bucket=top.get("bucket"), scale=scale, count=top["count"], n=n
        )

    return None


@dataclass
class QuestionAnalytics:
    """Aggregated analytics for a single question.

    Shape is type-specific via the `breakdown` field. The frontend reads
    `type`, `breakdown`, and the methodology fields on every render.
    """

    question_id: str
    type: str
    prompt: str
    is_required: bool
    sort_order: int
    n_answered: int
    min_n_threshold: int
    breakdown: dict[str, Any] = field(default_factory=dict)
    mean: float | None = None
    takeaway: str | None = None


@dataclass
class SurveyDashboardPayload:
    """Top-level payload for /surveys/{id}/dashboard."""

    survey_id: str
    name: str
    role: str
    status: str
    fielding_started_at: str | None
    fielding_ended_at: str | None
    n_started: int
    n_completed: int
    completion_rate_percentage: float | None
    min_n_threshold: int
    questions: list[QuestionAnalytics]


def build_dashboard(
    db: Session,
    survey: Survey,
    *,
    min_n: int = DEFAULT_MIN_N,
    lang: str = "en",
) -> SurveyDashboardPayload:
    """Build the dashboard payload for a survey.

    ``lang`` localises the deterministic per-question takeaway lines (en/fr).
    """

    # All responses for the survey — partial + completed.
    all_responses = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == survey.id, SurveyResponse.is_excluded.is_(False))
        .all()
    )
    n_started = len(all_responses)
    n_completed = sum(1 for r in all_responses if r.completed_at is not None)
    cr = completion_rate(n_started, n_completed, min_n=min_n)

    questions = (
        db.query(SurveyQuestion)
        .filter(
            SurveyQuestion.survey_id == survey.id,
            SurveyQuestion.deprecated_at.is_(None),
        )
        .order_by(SurveyQuestion.sort_order)
        .all()
    )

    qa: list[QuestionAnalytics] = []
    for q in questions:
        answers = (
            db.query(SurveyResponseAnswer)
            .filter(SurveyResponseAnswer.question_id == q.id)
            .all()
        )
        analytics = _analytics_for_question(q, answers, min_n=min_n)
        analytics.takeaway = _takeaway_for(analytics, lang)
        qa.append(analytics)

    return SurveyDashboardPayload(
        survey_id=survey.id,
        name=survey.name,
        role=survey.role,
        status=survey.status,
        fielding_started_at=survey.fielding_started_at.isoformat() if survey.fielding_started_at else None,
        fielding_ended_at=survey.fielding_ended_at.isoformat() if survey.fielding_ended_at else None,
        n_started=n_started,
        n_completed=n_completed,
        completion_rate_percentage=cr.rate_percentage,
        min_n_threshold=min_n,
        questions=qa,
    )


def _analytics_for_question(
    question: SurveyQuestion,
    answers: list[SurveyResponseAnswer],
    *,
    min_n: int,
) -> QuestionAnalytics:
    n = len(answers)
    base = QuestionAnalytics(
        question_id=question.id,
        type=question.type,
        prompt=question.prompt,
        is_required=question.is_required,
        sort_order=question.sort_order,
        n_answered=n,
        min_n_threshold=min_n,
    )

    if question.type in ("likert", "nps"):
        numeric_values = [a.value_numeric for a in answers if a.value_numeric is not None]
        if not numeric_values:
            return base
        cfg = question.config_dict
        if question.type == "likert":
            scale = int(cfg.get("scale", 5))
            buckets = list(range(1, scale + 1))
        else:
            buckets = list(range(0, 11))

        counts = {b: 0 for b in buckets}
        for v in numeric_values:
            ib = int(round(v))
            if ib in counts:
                counts[ib] += 1

        breakdown = []
        for b in buckets:
            c = counts[b]
            prop = wilson_proportion(c, n, min_n=min_n)
            breakdown.append({
                "bucket": b,
                "count": c,
                "percentage": prop.percentage,
                "ci_low": prop.ci_low,
                "ci_high": prop.ci_high,
            })
        base.breakdown = {"histogram": breakdown}
        # Mean is meaningful at any n but we keep the same n>=min_n guard
        # for consistency with the percentage contract.
        if n >= min_n:
            base.mean = sum(numeric_values) / len(numeric_values)

        if question.type == "nps" and n >= min_n:
            detractors = sum(1 for v in numeric_values if v <= 6)
            promoters = sum(1 for v in numeric_values if v >= 9)
            base.breakdown["nps_score"] = round(
                ((promoters - detractors) / n) * 100
            )
            base.breakdown["detractors"] = detractors
            base.breakdown["passives"] = n - detractors - promoters
            base.breakdown["promoters"] = promoters

        return base

    if question.type in ("mc_single", "mc_multi"):
        cfg = question.config_dict
        choices = cfg.get("choices", [])
        # Count per choice id. For mc_multi, one answer row may have multiple choice IDs.
        counts: dict[str, int] = {c["id"]: 0 for c in choices if isinstance(c, dict) and "id" in c}
        for a in answers:
            for cid in a.choice_ids_list:
                if cid in counts:
                    counts[cid] += 1

        breakdown = []
        for c in choices:
            if not isinstance(c, dict):
                continue
            cid = c.get("id")
            label = c.get("label")
            if cid is None:
                continue
            cnt = counts.get(cid, 0)
            prop = wilson_proportion(cnt, n, min_n=min_n)
            breakdown.append({
                "choice_id": cid,
                "label": label,
                "count": cnt,
                "percentage": prop.percentage,
                "ci_low": prop.ci_low,
                "ci_high": prop.ci_high,
            })
        # Sort descending by count for the dashboard.
        breakdown.sort(key=lambda x: x["count"], reverse=True)
        base.breakdown = {"choices": breakdown}
        return base

    if question.type in ("open_text", "short_text"):
        texts = [a.value_text for a in answers if a.value_text]
        # Cap at 50 — full pagination ships in Sprint 13 with clustering.
        sample = texts[:50]
        base.breakdown = {"sample": sample, "total_texts": len(texts)}
        return base

    return base
