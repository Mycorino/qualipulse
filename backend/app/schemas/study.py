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
  - report_ready:           placeholder until Sprint 11 lands StudyAnalysis
"""

from datetime import datetime

from pydantic import BaseModel


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


class StudySummary(BaseModel):
    """List item shape for GET /studies."""

    id: str
    name: str
    created_at: datetime
    archived_at: datetime | None = None
    survey_count: int = 0
    project_count: int = 0
    participant_count: int = 0


class StudyDetail(BaseModel):
    """Full detail for GET /studies/{id} — drives the Study Overview page."""

    id: str
    name: str
    created_at: datetime
    archived_at: datetime | None = None
    surveys: list[SurveyMini]
    projects: list[ProjectMini]
    progress: StudyProgress
    # Researcher-facing recommended next action ("Invite N detractors to interview" etc).
    # Computed server-side based on progress flags; Sprint 10 widens the cases.
    recommended_action: str | None = None
