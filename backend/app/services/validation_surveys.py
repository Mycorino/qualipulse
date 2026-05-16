"""Validation micro-surveys — closing the loop (Sprint 14).

The roadmap's last sprint locks the marketing narrative:

    quantify → explain → validate.

Mechanically: take a Quantified Themes report, spawn a new Survey
with one Likert "Does this resonate?" question per theme. The
researcher tweaks copy, publishes, shares the link. Responses come
back keyed to the theme, the Report tab shows agreement % alongside
each theme card.

Design constraints (from Decision 4 + the roadmap):
  - Manual trigger (no auto-send on every interview).
  - Per-theme Likert (5-point, anchors locked to "Doesn't resonate at
    all" → "Resonates strongly").
  - Survey starts in "draft" status so the researcher reviews + edits
    before going live.
  - Validation survey lives in the same Study as its source analysis,
    so the same StudyParticipant identity carries across instruments.

We mark each generated question's config with a `theme_index` so the
read-side service (compute_validation_summary) knows which validation
response belongs to which theme — no fragile prompt-text matching.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.study import StudyAnalysis
from app.models.survey import (
    Survey,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)
from app.services.stats import DEFAULT_MIN_N, wilson_proportion

logger = logging.getLogger(__name__)

VALIDATION_ANCHORS = ("Doesn't resonate at all", "Resonates strongly")


def generate_validation_survey(
    db: Session,
    analysis: StudyAnalysis,
    *,
    name_override: str | None = None,
) -> Survey:
    """Spawn a new Survey from an analysis report. One question per theme.

    Returns the saved Survey (in draft status). Idempotency is the
    caller's job — this always creates a new row so researchers can
    regenerate after editing themes.
    """

    if not analysis.report:
        raise ValueError("Analysis has no report payload to validate against")

    try:
        report = json.loads(analysis.report)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Analysis report is not valid JSON: {exc}") from exc

    themes = report.get("themes", []) or []
    if not themes:
        raise ValueError("Analysis report has no themes to validate")

    name = name_override or _default_validation_name(analysis)
    survey = Survey(
        study_id=analysis.study_id,
        company_id=_company_id_for_analysis(db, analysis),
        name=name,
        description=(
            f"Validates {len(themes)} theme{'' if len(themes) == 1 else 's'} from "
            f"the v{analysis.version} report. Each question asks how strongly "
            "respondents agree with one theme."
        ),
        role="validation",
        source_analysis_id=analysis.id,
    )
    db.add(survey)
    db.flush()

    for idx, theme in enumerate(themes):
        prompt = (
            theme.get("title")
            or theme.get("survey_signal", {}).get("summary")
            or "This finding resonates with my experience."
        )
        config = {
            "scale": 5,
            "anchors": list(VALIDATION_ANCHORS),
            "reverse_coded": False,
            # The bookkeeping that makes summarisation cheap on the read side.
            "validation": {
                "theme_index": idx,
                "source_analysis_id": analysis.id,
            },
        }
        db.add(
            SurveyQuestion(
                survey_id=survey.id,
                sort_order=(idx + 1) * 10,
                type="likert",
                prompt=prompt,
                is_required=True,
                config=json.dumps(config),
            )
        )

    db.commit()
    db.refresh(survey)
    return survey


def _default_validation_name(analysis: StudyAnalysis) -> str:
    return f"Theme validation — v{analysis.version} report"


def _company_id_for_analysis(db: Session, analysis: StudyAnalysis) -> str:
    """Resolve the workspace owner via Study.company_id."""

    from app.models.study import Study  # local import to keep module load order light
    study = db.query(Study).filter(Study.id == analysis.study_id).first()
    if not study:
        raise ValueError("Analysis is orphaned — study not found")
    return study.company_id


# ── Read side: per-theme validation summary ──────────────────────────


@dataclass
class ThemeValidationSnapshot:
    """One row of validation evidence for a theme on the Report tab.

    `agreement_pct` is the share of completed responses with a Likert
    value of 4 or 5 (the "agree" half of the 5-point scale). None when
    the responding sample is below the inference threshold — same
    contract as the rest of the methodology stack.
    """

    theme_index: int
    n_answered: int
    agreement_pct: float | None
    ci_low: float | None
    ci_high: float | None
    distribution: dict[int, int]


@dataclass
class ValidationSummary:
    """All-themes summary attached to an analysis."""

    survey_id: str
    survey_name: str
    survey_status: str
    n_responses: int
    n_completed: int
    per_theme: dict[int, ThemeValidationSnapshot]


def find_validation_survey(
    db: Session, analysis: StudyAnalysis
) -> Survey | None:
    """Returns the most recent validation survey for this analysis (if any)."""

    return (
        db.query(Survey)
        .filter(
            Survey.source_analysis_id == analysis.id,
            Survey.archived_at.is_(None),
        )
        .order_by(Survey.created_at.desc())
        .first()
    )


def compute_validation_summary(
    db: Session, analysis: StudyAnalysis
) -> ValidationSummary | None:
    """Compute per-theme agreement for the validation survey attached to an analysis.

    Returns None when no validation survey exists yet. When the survey
    exists but has no responses, returns a summary with empty per_theme
    entries — the UI uses that to render "Awaiting responses" labels.
    """

    survey = find_validation_survey(db, analysis)
    if not survey:
        return None

    n_responses = (
        db.query(func.count(SurveyResponse.id))
        .filter(SurveyResponse.survey_id == survey.id)
        .scalar()
        or 0
    )
    n_completed = (
        db.query(func.count(SurveyResponse.id))
        .filter(
            SurveyResponse.survey_id == survey.id,
            SurveyResponse.completed_at.isnot(None),
        )
        .scalar()
        or 0
    )

    questions = (
        db.query(SurveyQuestion)
        .filter(
            SurveyQuestion.survey_id == survey.id,
            SurveyQuestion.deprecated_at.is_(None),
        )
        .order_by(SurveyQuestion.sort_order)
        .all()
    )

    per_theme: dict[int, ThemeValidationSnapshot] = {}
    for q in questions:
        cfg = q.config_dict
        theme_index = cfg.get("validation", {}).get("theme_index")
        if theme_index is None:
            continue
        answers = (
            db.query(SurveyResponseAnswer)
            .join(SurveyResponse, SurveyResponseAnswer.response_id == SurveyResponse.id)
            .filter(
                SurveyResponseAnswer.question_id == q.id,
                SurveyResponse.completed_at.isnot(None),
                SurveyResponse.is_excluded.is_(False),
            )
            .all()
        )
        values = [int(round(a.value_numeric)) for a in answers if a.value_numeric is not None]
        agree_count = sum(1 for v in values if v >= 4)
        wilson = wilson_proportion(agree_count, len(values))
        distribution = {b: 0 for b in (1, 2, 3, 4, 5)}
        for v in values:
            if v in distribution:
                distribution[v] += 1
        per_theme[theme_index] = ThemeValidationSnapshot(
            theme_index=theme_index,
            n_answered=len(values),
            agreement_pct=wilson.percentage,
            ci_low=wilson.ci_low,
            ci_high=wilson.ci_high,
            distribution=distribution,
        )

    return ValidationSummary(
        survey_id=survey.id,
        survey_name=survey.name,
        survey_status=survey.status,
        n_responses=n_responses,
        n_completed=n_completed,
        per_theme=per_theme,
    )


__all__ = [
    "VALIDATION_ANCHORS",
    "generate_validation_survey",
    "find_validation_survey",
    "compute_validation_summary",
    "ThemeValidationSnapshot",
    "ValidationSummary",
]
