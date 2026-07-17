"""Pydantic schemas for Studies — the research-workspace surface.

A Study is the parent of a research effort (see docs/quanti-roadmap.md
section 1.1 + Sprint 9.5). Studies are auto-created on first survey or
project creation; this module models the read views, not creation.

The progress signal drives the Study Overview page's recommended-action
chip and progress checklist:
  - has_live_survey:        ≥1 Survey in the study is currently published
  - total_completed_responses: sum across all surveys' completed responses
  - segments_identified:    placeholder = total_completed_responses ≥ 30
  - interviews_completed:   count of completed Participants in sibling Projects
  - report_ready:           True iff a StudyAnalysis exists with status="ready"
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProjectMini(BaseModel):
    """Minimal Project representation for the Study Overview tabs.

    Avoids round-tripping the whole Project tree just to show interview
    counts on the Study page.
    """

    id: str
    name: str
    language: str
    interview_link_count: int = 0
    completed_participant_count: int = 0
    in_progress_participant_count: int = 0
    # True when the round has a ready ProjectAnalysis — the study's Reports
    # tab uses it to badge per-round analyses as ready vs not-yet-run.
    has_ready_analysis: bool = False


class SurveyMini(BaseModel):
    """Minimal Survey representation for the Study Overview tabs."""

    id: str
    name: str
    role: str
    status: str
    question_count: int = 0
    response_count: int = 0
    completed_count: int = 0


class StudyProgress(BaseModel):
    """Five-step progress signal driving the Study Overview checklist.

    The Sprint 9.5 page uses these to render the progress strip; future
    sprints flesh out the two `_placeholder` flags (segments + report)
    with real signal.
    """

    has_live_survey: bool
    total_completed_responses: int
    segments_identified_placeholder: bool
    interviews_completed: int
    report_ready_placeholder: bool


class SoleInstrument(BaseModel):
    """The one instrument of a single-instrument study.

    Present on StudySummary only when the study holds exactly one
    instrument. The Studies list uses it to open that instrument
    directly instead of forcing a hop through the study workspace
    (still reachable via the instrument's breadcrumb).
    """

    kind: Literal["survey", "interview"]
    id: str
    # Survey status routes the click: draft → builder, live/closed → results.
    survey_status: str | None = None


class StudySummary(BaseModel):
    """List item shape for GET /studies — drives the Studies-list home cards.

    `survey_count` + `project_count` give the instrument-mix badge
    (survey-only / interview-only / hybrid). The completion counts +
    `has_report` let the card show a one-line progress state.
    """

    id: str
    name: str
    created_at: datetime
    archived_at: datetime | None = None
    survey_count: int = 0
    project_count: int = 0
    participant_count: int = 0
    # Sprint 17: richer card signals.
    completed_response_count: int = 0
    completed_interview_count: int = 0
    has_report: bool = False
    # Eligible for a cross-study decision memo (any ready analysis —
    # qualitative ProjectAnalysis or mixed-methods StudyAnalysis).
    has_ready_analysis: bool = False
    # True when this Study holds seeded showcase content. The list UI badges
    # demo rows and keeps demo evidence out of workspace-level totals so the
    # researcher's own progress isn't inflated by tour data.
    is_demo: bool = False
    # Set only when the study has exactly one instrument — lets the list
    # link straight to it.
    sole_instrument: SoleInstrument | None = None


class ReportCatalogEntry(BaseModel):
    """One generated report document in the workspace Reports hub.

    The hub lists every ready report by its type — qualitative findings
    (green), survey results (blue), and the mixed-methods Decision report
    (bordeaux) — each opening its own standalone print-ready document:

      • qualitative → GET /projects/{project_id}/analysis/report.html
      • survey      → GET /surveys/{survey_id}/dashboard/report.html
      • decision    → GET /studies/{study_id}/analyses/{analysis_id}/report.html

    A mixed-methods study contributes all three: the two single-method
    component reports plus the Decision report that supersets them.
    """

    kind: Literal["qualitative", "survey", "decision"]
    study_id: str
    study_name: str
    is_demo: bool = False
    # Exactly one of these is set, per `kind`, and names the document to open.
    project_id: str | None = None
    survey_id: str | None = None
    analysis_id: str | None = None
    interviews: int = 0
    responses: int = 0


class StudyDetail(BaseModel):
    """Full detail for GET /studies/{id} — drives the Study Overview page."""

    id: str
    name: str
    created_at: datetime
    archived_at: datetime | None = None
    surveys: list[SurveyMini]
    projects: list[ProjectMini]
    progress: StudyProgress
    # True when this Study holds seeded showcase content (a demo project).
    # The UI suppresses billing/quota chrome on demo studies — they're a
    # guided tour, not the researcher's real, quota-consuming work.
    is_demo: bool = False
    # Researcher-facing recommended next action ("Invite N detractors to interview" etc).
    # Computed server-side based on progress flags; Sprint 10 widens the cases.
    # `recommended_action` is the English fallback text; the frontend prefers
    # `recommended_action_key` (+ params) so the prompt renders in the UI
    # language instead of hardcoded English.
    recommended_action: str | None = None
    recommended_action_key: str | None = None
    recommended_action_params: dict[str, int] | None = None


# ── Sprint 11: Quantified Themes report ───────────────────────────────


Confidence = Literal["directional", "supported", "strong"]
RecommendationKind = Literal["product", "marketing", "next_research"]


class SurveySignal(BaseModel):
    """Numeric signal a theme rests on.

    `percentage` is None when the supporting n is below the methodology
    threshold — same contract as everywhere else in the codebase.
    `segment_over_index` is the lift ratio when the theme is segment-
    specific (e.g. 'PMs over-index 3.1× on…'); None when the theme is
    workspace-wide.
    """

    summary: str = Field(..., description="One-line numeric anchor, e.g. '40% selected mobile setup'.")
    n: int
    percentage: float | None = None
    segment_label: str | None = None
    segment_over_index: float | None = None


class InterviewEvidence(BaseModel):
    """Qualitative anchor for a theme.

    `x_of_y` reads as "this came up in X of Y interviews." The
    `anchor_quote` is a verbatim from one of those interviews — never
    paraphrased, AND it must be a verbatim substring of an actual
    InterviewTurn.response_transcript on the same study's projects.
    """

    x_of_y: str  # e.g. "7 of 12"
    interview_count: int
    anchor_quote: str
    segments_mentioned: list[str] = Field(default_factory=list)


class ThemeRecommendation(BaseModel):
    """The 'so what' line — what should the team do?"""

    kind: RecommendationKind
    action: str
    rationale: str | None = None
    # Falsifiable outcome that would confirm the action worked (or prove it
    # wrong). Optional so reports generated before this field keep validating.
    success_test: str | None = None


class QuantifiedTheme(BaseModel):
    """One theme combining survey signal + interview evidence + a recommendation.

    The 4-part shape comes from the consultant audit: every theme must
    answer "what did we see in the data, what did people say about it,
    what should we do, and how strong is the evidence?"
    """

    title: str
    survey_signal: SurveySignal | None = None
    interview_evidence: InterviewEvidence | None = None
    # Divergent voice or signal that cuts against the theme — honesty rule
    # inherited from the qualitative analysis's disconfirming_evidence.
    counter_evidence: str | None = None
    recommendation: ThemeRecommendation
    confidence: Confidence


class QuantifiedThemeReport(BaseModel):
    """The full report payload stored in `study_analyses.report`."""

    executive_summary: str
    # Decision-oriented bottom line — answers the study's stated decision
    # when one exists. Optional: pre-existing reports don't carry it.
    verdict: str | None = None
    themes: list[QuantifiedTheme]
    # What the data cannot answer (unmeasured effects, missing segments).
    gaps: list[str] = Field(default_factory=list)
    methodology_note: str
    generated_with_survey_count: int = 0
    generated_with_response_count: int = 0
    generated_with_interview_count: int = 0


class StudyAnalysisSummary(BaseModel):
    """List item shape for GET /studies/{id}/analyses."""

    id: str
    study_id: str
    version: int
    status: Literal["generating", "ready", "failed"]
    error: str | None = None
    created_at: datetime
    generated_at: datetime | None = None


class StudyAnalysisDetail(StudyAnalysisSummary):
    """Full payload — report blob is parsed + returned as a typed object."""

    report: QuantifiedThemeReport | None = None


# ── Sprint 14: Theme validation (closing the loop) ─────────────────


class ThemeValidationSnapshotSchema(BaseModel):
    """Validation agreement for one theme in a `QuantifiedThemeReport`."""

    theme_index: int
    n_answered: int
    agreement_pct: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    distribution: dict[int, int] = Field(default_factory=dict)


class ValidationSummarySchema(BaseModel):
    """Read-side payload attached to an analysis with a validation survey."""

    survey_id: str
    survey_name: str
    survey_status: str
    n_responses: int
    n_completed: int
    per_theme: dict[int, ThemeValidationSnapshotSchema]


class GeneratedValidationSurvey(BaseModel):
    """Returned by POST /analyses/{id}/validation-survey — just enough for
    the frontend to navigate the researcher to the editor."""

    survey_id: str
    study_id: str
    name: str
    question_count: int
