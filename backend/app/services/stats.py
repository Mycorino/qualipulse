"""Statistics helpers — the single place the methodology contract lives in code.

The methodologist's hard line (per the agent reviews): any survey result
without sample size, completion rate, fielding window, and confidence
interval visible is untrustworthy. To enforce this server-side:

  - Wilson 95% CIs only. No normal-approximation anywhere in the codebase.
  - Below n=30 segments return `percentage=None` so the frontend has no
    path to render a forbidden percentage.

If you need a CI helper somewhere new, import from here. If you need a
new statistic, add it here. Do not inline-compute statistics in routers
or services — every query that surfaces percentages or CIs goes through
this module.

See docs/quanti-roadmap.md sections 1.7 and risk #12.
"""

from dataclasses import dataclass
from math import sqrt


# Minimum n for any percentage to be reported. Below this, callers must
# render counts ("8 of 28 respondents") instead of percentages.
DEFAULT_MIN_N = 30


@dataclass
class ProportionResult:
    """A proportion with its sample size and 95% Wilson CI.

    `percentage` and `ci_low` / `ci_high` are None when n < min_n. Callers
    must handle the None case by rendering counts. The frontend never
    bypasses this — its single source of truth is this dataclass shape.
    """

    successes: int
    n: int
    percentage: float | None
    ci_low: float | None
    ci_high: float | None
    min_n_threshold: int


def wilson_proportion(
    successes: int,
    n: int,
    *,
    confidence_z: float = 1.96,
    min_n: int = DEFAULT_MIN_N,
) -> ProportionResult:
    """Compute a Wilson 95% CI for a binomial proportion.

    Wilson is the right interval for survey research: well-behaved at the
    extremes (near 0% and 100%, where most interesting findings live) and
    no boundary violations like the normal approximation has.

    Returns a ProportionResult; if n < min_n, percentage and CI bounds are
    None and the caller must render counts.
    """

    if n <= 0:
        return ProportionResult(
            successes=0,
            n=0,
            percentage=None,
            ci_low=None,
            ci_high=None,
            min_n_threshold=min_n,
        )

    if n < min_n:
        return ProportionResult(
            successes=successes,
            n=n,
            percentage=None,
            ci_low=None,
            ci_high=None,
            min_n_threshold=min_n,
        )

    # Wilson score interval — Agresti-Coull's underlying formula without the
    # adjusted-Wald simplification. See Newcombe (1998) for derivation.
    p_hat = successes / n
    z2 = confidence_z * confidence_z
    denom = 1.0 + z2 / n
    centre = (p_hat + z2 / (2.0 * n)) / denom
    margin = (
        confidence_z * sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))
    ) / denom

    return ProportionResult(
        successes=successes,
        n=n,
        percentage=p_hat * 100.0,
        ci_low=max(0.0, (centre - margin) * 100.0),
        ci_high=min(100.0, (centre + margin) * 100.0),
        min_n_threshold=min_n,
    )


@dataclass
class CompletionRateResult:
    """Completion rate for a survey: how many started got to the end."""

    started: int
    completed: int
    rate_percentage: float | None
    min_n_threshold: int


def completion_rate(started: int, completed: int, *, min_n: int = DEFAULT_MIN_N) -> CompletionRateResult:
    """Completion rate as a percentage. None when started < min_n."""

    if started <= 0:
        return CompletionRateResult(0, 0, None, min_n)
    if started < min_n:
        return CompletionRateResult(started, completed, None, min_n)
    return CompletionRateResult(
        started=started,
        completed=completed,
        rate_percentage=(completed / started) * 100.0,
        min_n_threshold=min_n,
    )
