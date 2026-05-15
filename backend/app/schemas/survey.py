"""Pydantic schemas for surveys + survey questions + responses.

Per-question-type config validation lives here. The router calls
`validate_question_config(type, config)` before write, which dispatches
to a type-specific validator. This keeps the methodology guardrails
(scale balance, required-field checks) at the API boundary, not in the
DB.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Mirrors models.survey.QUESTION_TYPES.
QuestionType = Literal[
    "likert", "mc_single", "mc_multi", "nps", "open_text", "short_text"
]
SurveyRole = Literal["screener", "validation", "standalone"]
SurveyStatus = Literal["draft", "live", "closed"]


# ── Survey ────────────────────────────────────────────────────────────


class SurveyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    study_id: str | None = None
    role: SurveyRole = "standalone"


class SurveyPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    role: SurveyRole | None = None
    status: SurveyStatus | None = None


class SurveyResponse(BaseModel):
    id: str
    study_id: str
    company_id: str
    name: str
    description: str | None
    role: SurveyRole
    status: SurveyStatus
    fielding_started_at: datetime | None
    fielding_ended_at: datetime | None
    created_at: datetime
    archived_at: datetime | None
    question_count: int = 0
    response_count: int = 0
    completed_count: int = 0

    model_config = {"from_attributes": True}


# ── Question ──────────────────────────────────────────────────────────


class QuestionConfigLikert(BaseModel):
    scale: Literal[5, 7] = 5
    anchors: tuple[str, str] = ("Strongly disagree", "Strongly agree")
    reverse_coded: bool = False


class QuestionConfigChoice(BaseModel):
    id: str
    label: str


class QuestionConfigMcSingle(BaseModel):
    choices: list[QuestionConfigChoice] = Field(..., min_length=2, max_length=20)
    randomize: bool = True
    has_other: bool = False


class QuestionConfigMcMulti(BaseModel):
    choices: list[QuestionConfigChoice] = Field(..., min_length=2, max_length=20)
    randomize: bool = True
    has_other: bool = False
    max_selectable: int | None = Field(None, ge=1)


class QuestionConfigNps(BaseModel):
    context: str = ""


class QuestionConfigOpenText(BaseModel):
    max_chars: int = Field(500, ge=50, le=5000)
    ai_cluster: bool = False  # opt-in per Decision 5


class QuestionConfigShortText(BaseModel):
    max_chars: int = Field(120, ge=10, le=500)


def validate_question_config(question_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to the right Pydantic validator and return a clean dict.

    Raises pydantic.ValidationError on malformed config — the router
    converts this to HTTP 422.
    """

    validators: dict[str, type[BaseModel]] = {
        "likert": QuestionConfigLikert,
        "mc_single": QuestionConfigMcSingle,
        "mc_multi": QuestionConfigMcMulti,
        "nps": QuestionConfigNps,
        "open_text": QuestionConfigOpenText,
        "short_text": QuestionConfigShortText,
    }
    validator = validators.get(question_type)
    if validator is None:
        raise ValueError(f"Unknown question type: {question_type}")
    return validator(**config).model_dump()


class QuestionCreate(BaseModel):
    # `prompt` allows empty during draft authoring — the editor creates a
    # blank question and the researcher fills the prompt as they go.
    # Non-empty enforcement happens at publish time (Sprint 8 wires the
    # status-transition validator).
    type: QuestionType
    prompt: str = ""
    is_required: bool = False
    sort_order: int = 0
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config", mode="after")
    @classmethod
    def _validate_config(cls, v, info):
        question_type = info.data.get("type")
        if question_type is None:
            return v
        return validate_question_config(question_type, v)


class QuestionPatch(BaseModel):
    prompt: str | None = None
    is_required: bool | None = None
    sort_order: int | None = None
    config: dict[str, Any] | None = None


class QuestionResponse(BaseModel):
    id: str
    survey_id: str
    sort_order: int
    type: QuestionType
    prompt: str
    is_required: bool
    config: dict[str, Any]
    created_at: datetime
    deprecated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Survey Link ───────────────────────────────────────────────────────


class SurveyLinkCreate(BaseModel):
    is_anonymous: bool = False  # Decision 3 — identified by default
    target_n: int | None = None
    response_cap: int | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None


class SurveyLinkResponse(BaseModel):
    id: str
    survey_id: str
    token: str
    is_active: bool
    is_anonymous: bool
    target_n: int | None
    response_cap: int | None
    opens_at: datetime | None
    closes_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Response submission ───────────────────────────────────────────────


class AnswerSubmission(BaseModel):
    """One question's answer, as posted by the public response page.

    Exactly one of value_numeric / value_text / value_choice_ids must be
    populated. Validated server-side against the question's type.
    """

    question_id: str
    value_numeric: float | None = None
    value_text: str | None = None
    value_choice_ids: list[str] | None = None
    time_to_answer_ms: int | None = None


class ResponseSubmission(BaseModel):
    """Public response page payload.

    `study_participant_id` is server-resolved from the magic_token in the URL
    or from the email; clients never set it. `link_token` is the URL token.
    """

    link_token: str
    answers: list[AnswerSubmission] = Field(default_factory=list)
    email: str | None = None
    display_name: str | None = None
    magic_token: str | None = None
    is_complete: bool = True
    submission_metadata: dict[str, Any] = Field(default_factory=dict)


class ResponseAck(BaseModel):
    """Returned by POST /surveys/{id}/responses."""

    response_id: str
    study_participant_id: str | None
    is_complete: bool
    received_at: datetime


# ── Dashboard / analytics ─────────────────────────────────────────────


class QuestionAnalyticsSchema(BaseModel):
    """Per-question dashboard analytics. Shape varies by `type` via `breakdown`."""

    question_id: str
    type: QuestionType
    prompt: str
    is_required: bool
    sort_order: int
    n_answered: int
    min_n_threshold: int
    breakdown: dict[str, Any]
    mean: float | None = None
    takeaway: str | None = None


class SurveyDashboardSchema(BaseModel):
    """Top-level /surveys/{id}/dashboard payload."""

    survey_id: str
    name: str
    role: SurveyRole
    status: SurveyStatus
    fielding_started_at: str | None
    fielding_ended_at: str | None
    n_started: int
    n_completed: int
    completion_rate_percentage: float | None
    min_n_threshold: int
    questions: list[QuestionAnalyticsSchema]


# ── Public survey shape (no-auth view of a live link) ────────────────


class PublicQuestion(BaseModel):
    """Subset of SurveyQuestion safe to return to anonymous respondents."""

    id: str
    sort_order: int
    type: QuestionType
    prompt: str
    is_required: bool
    config: dict[str, Any]


class PublicSurvey(BaseModel):
    """No-auth payload describing a live survey to a respondent.

    Returned by GET /r/{token}. Does NOT include workspace ids, internal
    company_id, or any methodology metadata. Constant-time "not available"
    for any unhappy state (closed, capped, draft).
    """

    name: str
    description: str | None
    is_anonymous: bool
    questions: list[PublicQuestion]
