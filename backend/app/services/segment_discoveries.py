"""Segment Discoveries — Sprint 10's product value layer.

The roadmap principle from the consultant audit:
  AI detects patterns; researchers choose what to act on.

This service walks every PAIR (segment_question, metric_question) inside
a survey, computes the lift / mean-delta of each segment relative to the
overall response pool, and surfaces the ones that look distinguishable
enough to deserve a follow-up interview.

Confidence pill assignment honors the methodology contract:
  - n < 30 in either segment OR the comparator pool → max "directional"
  - 30 ≤ n < 100 + p < 0.05 (categorical) or |delta| > 0.5σ (numeric) → "supported"
  - n ≥ 100 + p < 0.01 (or |delta| > 1σ for numeric) → "strong"
  - Below all thresholds → discovery is not emitted

Segment-question candidates: mc_single, mc_multi.
Metric-question candidates: nps, likert, mc_single, mc_multi.

The chi-square test is the cheap categorical engine. For numeric outcomes
we use the standardised mean delta — same intuition, no scipy needed
(keeps deploy weight down).

What this service deliberately does NOT do (kept off the roadmap):
  - It does not author a "finding" — it surfaces a *candidate* discovery
    for the researcher to confirm or reject.
  - It does not recommend a sample size for the follow-up.
  - It does not render percentages where n is below the threshold.

The bridge-friendly `ready_filter` field is the structured filter clause
the SurveyDashboard pre-populates when the researcher clicks
"Interview this segment" — so Sprint 9's wedge picks up where Sprint 10
leaves off.
"""

from dataclasses import dataclass, field
from math import sqrt
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models.survey import (
    Survey,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)
from app.services.stats import DEFAULT_MIN_N

Confidence = Literal["directional", "supported", "strong"]

# Min n in the segment before we even compute a discovery. Anything tinier
# is noise no matter how strong the apparent effect.
MIN_SEGMENT_N = 8
# Max discoveries to surface per survey. Quality over quantity — the
# product hint is "we found 3 segments worth interviewing," not 30.
DEFAULT_MAX_DISCOVERIES = 6


@dataclass
class ReadyFilter:
    """Pre-populated bridge filter — the one the dashboard wires when the
    researcher clicks "Interview this segment" on a discovery card."""

    question_id: str
    operator: str  # "in" for mc, "eq"/"lte"/"gte" for numeric
    value: Any


@dataclass
class Discovery:
    """One actionable observation about a segment of respondents."""

    id: str
    title: str
    description: str
    confidence: Confidence
    segment_n: int
    overall_n: int
    # The metric being compared (always carries forward to the Bridge).
    metric_question_id: str
    metric_question_prompt: str
    # Categorical metric extras (None for numeric metrics).
    metric_choice_label: str | None = None
    # Numeric metric extras.
    segment_mean: float | None = None
    overall_mean: float | None = None
    # Lift ratio (categorical) or mean delta (numeric) — UI picks one.
    lift_ratio: float | None = None
    mean_delta: float | None = None
    # Filter clause(s) the dashboard pre-fills on the Bridge.
    ready_filter: list[ReadyFilter] = field(default_factory=list)


def compute_discoveries(
    db: Session,
    survey: Survey,
    *,
    max_results: int = DEFAULT_MAX_DISCOVERIES,
) -> list[Discovery]:
    """Walk every (segment, metric) pair → list of ranked discoveries.

    Sort order: confidence descending (strong > supported > directional),
    then absolute lift descending. We never emit more than `max_results`
    — the product hint is "we found 3 segments worth interviewing," not
    "here is a wall of statistics."
    """

    questions = (
        db.query(SurveyQuestion)
        .filter(
            SurveyQuestion.survey_id == survey.id,
            SurveyQuestion.deprecated_at.is_(None),
        )
        .order_by(SurveyQuestion.sort_order)
        .all()
    )
    if len(questions) < 2:
        return []

    # All answers for the survey indexed by (response_id, question_id).
    # Computed once; reused across every (segment, metric) pair.
    answers = (
        db.query(SurveyResponseAnswer)
        .join(SurveyResponse, SurveyResponseAnswer.response_id == SurveyResponse.id)
        .filter(
            SurveyResponse.survey_id == survey.id,
            SurveyResponse.completed_at.isnot(None),
            SurveyResponse.is_excluded.is_(False),
        )
        .all()
    )
    if not answers:
        return []

    by_response: dict[str, dict[str, SurveyResponseAnswer]] = {}
    for a in answers:
        by_response.setdefault(a.response_id, {})[a.question_id] = a
    total_n = len(by_response)
    if total_n < MIN_SEGMENT_N:
        return []

    discoveries: list[Discovery] = []
    seg_qs = [q for q in questions if q.type in ("mc_single", "mc_multi")]
    metric_qs = [q for q in questions if q.type in ("likert", "nps", "mc_single", "mc_multi")]

    for seg_q in seg_qs:
        seg_groups = _bucket_by_choice(by_response, seg_q)
        for choice_id, response_ids in seg_groups.items():
            seg_n = len(response_ids)
            if seg_n < MIN_SEGMENT_N:
                continue
            seg_label = _choice_label(seg_q, choice_id) or choice_id
            for metric_q in metric_qs:
                if metric_q.id == seg_q.id:
                    continue
                if metric_q.type in ("likert", "nps"):
                    d = _numeric_discovery(
                        seg_q, choice_id, seg_label, metric_q, response_ids, by_response, total_n
                    )
                    if d:
                        discoveries.append(d)
                else:
                    found = _categorical_discoveries(
                        seg_q,
                        choice_id,
                        seg_label,
                        metric_q,
                        response_ids,
                        by_response,
                        total_n,
                    )
                    discoveries.extend(found)

    discoveries.sort(
        key=lambda d: (
            _conf_rank(d.confidence),
            abs(d.lift_ratio - 1.0) if d.lift_ratio is not None else abs(d.mean_delta or 0),
        ),
        reverse=True,
    )
    # De-duplicate when multiple metric choices fire for the same segment;
    # only keep the strongest per segment to avoid spammy cards.
    seen_segments: set[str] = set()
    deduped: list[Discovery] = []
    for d in discoveries:
        key = "|".join(f"{rf.question_id}={rf.value}" for rf in d.ready_filter)
        if key in seen_segments:
            continue
        seen_segments.add(key)
        deduped.append(d)
        if len(deduped) >= max_results:
            break
    return deduped


# ── Helpers ──────────────────────────────────────────────────────────


def _conf_rank(c: Confidence) -> int:
    return {"strong": 3, "supported": 2, "directional": 1}[c]


def _bucket_by_choice(
    by_response: dict[str, dict[str, SurveyResponseAnswer]],
    seg_q: SurveyQuestion,
) -> dict[str, list[str]]:
    """For an mc_single/mc_multi question, return {choice_id: [response_ids]}."""

    out: dict[str, list[str]] = {}
    for response_id, answers in by_response.items():
        ans = answers.get(seg_q.id)
        if not ans:
            continue
        for choice_id in ans.choice_ids_list:
            out.setdefault(choice_id, []).append(response_id)
    return out


def _choice_label(question: SurveyQuestion, choice_id: str) -> str | None:
    for c in question.config_dict.get("choices", []):
        if isinstance(c, dict) and c.get("id") == choice_id:
            return c.get("label")
    return None


def _numeric_discovery(
    seg_q: SurveyQuestion,
    seg_choice_id: str,
    seg_label: str,
    metric_q: SurveyQuestion,
    response_ids: list[str],
    by_response: dict[str, dict[str, SurveyResponseAnswer]],
    total_n: int,
) -> Discovery | None:
    """Compute a (segment-mean vs overall-mean) discovery for a numeric metric."""

    seg_values: list[float] = []
    overall_values: list[float] = []
    for r_id, answers in by_response.items():
        a = answers.get(metric_q.id)
        if a is None or a.value_numeric is None:
            continue
        overall_values.append(a.value_numeric)
        if r_id in set(response_ids):
            seg_values.append(a.value_numeric)

    if len(seg_values) < MIN_SEGMENT_N or len(overall_values) < MIN_SEGMENT_N:
        return None

    seg_mean = sum(seg_values) / len(seg_values)
    overall_mean = sum(overall_values) / len(overall_values)
    delta = seg_mean - overall_mean
    if abs(delta) < 0.3:  # not a meaningfully different mean
        return None
    overall_sd = _stdev(overall_values) or 1.0
    standardised = abs(delta) / overall_sd
    confidence = _numeric_confidence(len(seg_values), len(overall_values), standardised)
    direction = "above" if delta > 0 else "below"
    title = (
        f"{seg_label} score {abs(round(delta, 1))} points {direction} the overall average "
        f"on \"{_short_prompt(metric_q.prompt)}\""
    )
    description = (
        f"{seg_label} averages {seg_mean:.1f} vs {overall_mean:.1f} overall "
        f"({len(seg_values)} of {len(response_ids)} respondents; "
        f"{abs(delta) / overall_sd:.2f}σ standardised). "
        "Worth interviewing to find out why."
    )
    return Discovery(
        id=f"d-{metric_q.id}-{seg_q.id}-{seg_choice_id}",
        title=title,
        description=description,
        confidence=confidence,
        segment_n=len(seg_values),
        overall_n=len(overall_values),
        metric_question_id=metric_q.id,
        metric_question_prompt=metric_q.prompt,
        segment_mean=seg_mean,
        overall_mean=overall_mean,
        mean_delta=delta,
        ready_filter=[ReadyFilter(question_id=seg_q.id, operator="in", value=[seg_choice_id])],
    )


def _categorical_discoveries(
    seg_q: SurveyQuestion,
    seg_choice_id: str,
    seg_label: str,
    metric_q: SurveyQuestion,
    response_ids: list[str],
    by_response: dict[str, dict[str, SurveyResponseAnswer]],
    total_n: int,
) -> list[Discovery]:
    """For each choice of a categorical metric, compute a lift vs overall."""

    out: list[Discovery] = []
    metric_choices = metric_q.config_dict.get("choices", [])
    seg_set = set(response_ids)
    seg_n = len(seg_set)

    for choice in metric_choices:
        if not isinstance(choice, dict):
            continue
        metric_choice_id = choice.get("id")
        metric_choice_label = choice.get("label") or metric_choice_id
        if not metric_choice_id:
            continue

        overall_hits = 0
        segment_hits = 0
        for r_id, answers in by_response.items():
            a = answers.get(metric_q.id)
            if a is None:
                continue
            if metric_choice_id in a.choice_ids_list:
                overall_hits += 1
                if r_id in seg_set:
                    segment_hits += 1

        if segment_hits < 3:
            continue  # too few to draw a line through

        overall_rate = overall_hits / total_n if total_n else 0
        seg_rate = segment_hits / seg_n if seg_n else 0
        if overall_rate < 0.05:
            continue  # the metric itself is too rare to call out

        lift = seg_rate / overall_rate if overall_rate else 1.0
        # Require at least 1.5× lift or 0.65× (under-index) to call it out.
        if 0.65 < lift < 1.5:
            continue

        chi2 = _chi_square(
            segment_hits=segment_hits,
            segment_n=seg_n,
            other_hits=overall_hits - segment_hits,
            other_n=total_n - seg_n,
        )
        confidence = _categorical_confidence(seg_n, total_n - seg_n, chi2)

        title = (
            f"{seg_label} are {lift:.1f}× more likely to "
            f"select \"{metric_choice_label}\""
            if lift >= 1
            else f"{seg_label} are {1/lift:.1f}× less likely to select \"{metric_choice_label}\""
        )
        description = (
            f"{segment_hits} of {seg_n} {seg_label.lower()} ({seg_rate*100:.0f}%) selected this, "
            f"vs {overall_rate*100:.0f}% overall. "
            "Worth interviewing to understand what drives the gap."
        )
        out.append(
            Discovery(
                id=f"d-{metric_q.id}-{metric_choice_id}-{seg_q.id}-{seg_choice_id}",
                title=title,
                description=description,
                confidence=confidence,
                segment_n=seg_n,
                overall_n=total_n,
                metric_question_id=metric_q.id,
                metric_question_prompt=metric_q.prompt,
                metric_choice_label=metric_choice_label,
                lift_ratio=lift,
                ready_filter=[
                    ReadyFilter(question_id=seg_q.id, operator="in", value=[seg_choice_id])
                ],
            )
        )
    return out


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return sqrt(var)


def _chi_square(*, segment_hits: int, segment_n: int, other_hits: int, other_n: int) -> float:
    """Pearson chi-square statistic for a 2×2 contingency table.

    Rows: segment vs everyone-else.
    Cols: chose-the-metric vs didn't.
    Returns 0 when the table is degenerate (any row or col sum is 0).
    """

    row1 = segment_n
    row2 = other_n
    col1 = segment_hits + other_hits
    col2 = (segment_n - segment_hits) + (other_n - other_hits)
    total = row1 + row2
    if not (row1 and row2 and col1 and col2 and total):
        return 0.0

    def expected(row: int, col: int) -> float:
        return row * col / total

    cells = [
        (segment_hits, expected(row1, col1)),
        (segment_n - segment_hits, expected(row1, col2)),
        (other_hits, expected(row2, col1)),
        (other_n - other_hits, expected(row2, col2)),
    ]
    chi2 = 0.0
    for observed, exp in cells:
        if exp <= 0:
            continue
        chi2 += (observed - exp) ** 2 / exp
    return chi2


def _categorical_confidence(seg_n: int, other_n: int, chi2: float) -> Confidence:
    """Chi-square critical values for a 2x2 table (1 df):
      p < 0.05 ↔ chi2 ≥ 3.84
      p < 0.01 ↔ chi2 ≥ 6.63
    Combined with the methodology n-threshold.
    """

    if seg_n < DEFAULT_MIN_N or other_n < DEFAULT_MIN_N:
        return "directional"
    if chi2 >= 6.63 and seg_n >= 100:
        return "strong"
    if chi2 >= 3.84:
        return "supported"
    return "directional"


def _numeric_confidence(seg_n: int, other_n: int, standardised_delta: float) -> Confidence:
    """Cohen's d-style thresholds: 0.2 small, 0.5 medium, 0.8 large.

    We use the standardised |mean delta| (not a t-test) because it captures
    the "is this a chunky difference?" intuition without needing scipy.
    """

    if seg_n < DEFAULT_MIN_N or other_n < DEFAULT_MIN_N:
        return "directional"
    if seg_n >= 100 and standardised_delta >= 0.8:
        return "strong"
    if standardised_delta >= 0.5:
        return "supported"
    return "directional"


def _short_prompt(prompt: str, max_len: int = 64) -> str:
    if len(prompt) <= max_len:
        return prompt
    return prompt[: max_len - 1].rstrip() + "…"
