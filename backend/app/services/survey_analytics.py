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


def build_dashboard(db: Session, survey: Survey, *, min_n: int = DEFAULT_MIN_N) -> SurveyDashboardPayload:
    """Build the dashboard payload for a survey."""

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
        qa.append(_analytics_for_question(q, answers, min_n=min_n))

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
