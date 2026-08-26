import re
from datetime import datetime

from pydantic import BaseModel, field_validator

BRANDING_MODES = {"standard", "branded", "anonymous"}
# Curated font-stack keys — resolved to CSS stacks client-side so the
# participant page never loads external fonts.
BRAND_FONTS = {"system", "humanist", "serif", "elegant"}
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandingFieldsMixin(BaseModel):
    """Shared validation for the participant-facing branding fields."""

    branding_mode: str | None = None
    brand_primary_color: str | None = None
    brand_font: str | None = None
    researcher_name: str | None = None
    researcher_logo_url: str | None = None
    privacy_policy_url: str | None = None
    incentive_text: str | None = None

    @field_validator("branding_mode")
    @classmethod
    def _valid_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in BRANDING_MODES:
            raise ValueError(f"branding_mode must be one of {sorted(BRANDING_MODES)}")
        return v

    @field_validator("brand_primary_color")
    @classmethod
    def _valid_color(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not _HEX_COLOR_RE.match(v):
            raise ValueError("brand_primary_color must be a #rrggbb hex color")
        return v.lower()

    @field_validator("brand_font")
    @classmethod
    def _valid_font(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if v not in BRAND_FONTS:
            raise ValueError(f"brand_font must be one of {sorted(BRAND_FONTS)}")
        return v


class BrandingDefaultsPayload(BrandingFieldsMixin):
    """Workspace-level branding defaults (PUT /auth/branding-defaults) —
    same fields and validation as per-project branding."""


class QuestionCreate(BaseModel):
    section_index: int
    section_title: str
    question_index: int
    main_question: str
    interview_notes: str | None = None
    desired_learning: str | None = None


class GuideQuestionAdd(BaseModel):
    """Add a single interview-guide question. Section/question indices are
    computed server-side from the section title, so the Research Copilot
    (and any caller) only needs to name the section."""

    section_title: str
    main_question: str
    desired_learning: str | None = None
    interview_notes: str | None = None
    # The Copilot's "why" for this question — persisted as the question's
    # researcher note so the reasoning survives the accept flow.
    researcher_notes: str | None = None


class QuestionPatch(BaseModel):
    main_question: str | None = None
    question_index: int | None = None
    section_title: str | None = None
    section_index: int | None = None
    researcher_notes: str | None = None
    deprecated_at: datetime | None = None
    interview_notes: str | None = None
    desired_learning: str | None = None


class ScreeningQuestionCreate(BaseModel):
    question: str
    options: list[str] = []
    disqualifying_options: list[str] = []


class ScreeningQuestionResponse(BaseModel):
    id: str
    question: str
    options: list[str]
    disqualifying_options: list[str]
    sort_order: int
    # Per-language localizations: {"fr": {"question": str, "options": [str]}}.
    # Auto-generated on save; researcher-editable.
    translations: dict = {}

    model_config = {"from_attributes": True}


class ScreeningTranslationPatch(BaseModel):
    """Researcher edit of one language's localized screening text."""
    lang: str
    question: str
    options: list[str] = []


class ProjectCreate(BrandingFieldsMixin):
    name: str
    # None => inherit the creating company's preferred_language (so a French
    # researcher gets French participant-facing content by default). An
    # explicit "en"/"fr" is always respected.
    language: str | None = None
    # Sprint 15: when set, the project joins this existing Study (e.g. an
    # interview round added from inside a Study). When omitted, a Study is
    # auto-created named after the project — Decision 8, implicit creation.
    study_id: str | None = None
    interview_duration_minutes: int = 20
    system_prompt: str | None = None
    research_objective: str | None = None
    welcome_message: str | None = None
    panel_collection_enabled: bool = True
    warmup_enabled: bool = True
    profile_before_interview: bool = False
    # Study grounding — used by AI analysis + interview engine
    decision_to_inform: str | None = None
    target_customer_description: str | None = None
    # Participant-facing context blurb. Set through PATCH /settings in the UI,
    # but PUT /projects/{id} reuses this schema and reads the field, so it has
    # to exist here.
    research_context: str | None = None
    questions: list[QuestionCreate] = []
    screening_questions: list[ScreeningQuestionCreate] = []


class ProjectSettingsPatch(BrandingFieldsMixin):
    name: str | None = None
    panel_collection_enabled: bool | None = None
    warmup_enabled: bool | None = None
    profile_before_interview: bool | None = None
    # How long each interview should run and how many we're aiming to
    # collect. The Research Copilot recommends + sets these so it can own
    # interview-round setup ("let's do 1h in-depth interviews, ~10 people").
    interview_duration_minutes: int | None = None
    target_participants: int | None = None
    # Granular updates to the research framing — the Research Copilot sets
    # these so it can own interview-round setup without the old wizard.
    research_objective: str | None = None
    research_context: str | None = None
    # Strategic capture (V2): the decision, when it's due, how they'll
    # know we helped. Surfaces the WHY/HOW that drives email cadence,
    # plan recommendation, and the eventual analysis output.
    decision_to_inform: str | None = None
    timeline: str | None = None
    success_criteria: str | None = None
    target_customer_description: str | None = None


class QuestionResponse(BaseModel):
    id: str
    section_index: int
    section_title: str
    question_index: int
    main_question: str
    interview_notes: str | None = None
    desired_learning: str | None = None
    researcher_notes: str | None = None
    deprecated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PlanContext(BaseModel):
    """Wave E — when a Project is the drafted step of a ResearchPlan,
    this surfaces the plan context so dashboard cards + the project
    header can render 'Step N of M in <plan name>'."""

    plan_id: str
    plan_name: str
    step_index: int  # 1-based, the order_index of this step
    total_steps: int  # how many steps the plan has total
    step_method: str  # e.g. 'voice_interview'


class ProjectResponse(BaseModel):
    id: str
    company_id: str
    # Sprint 16: the parent Study — lets the interview detail page render
    # the `Studies › <study> › <interview>` breadcrumb without an extra fetch.
    study_id: str | None = None
    study_name: str | None = None
    name: str
    language: str
    interview_duration_minutes: int
    system_prompt: str | None = None
    research_objective: str | None = None
    welcome_message: str | None = None
    panel_collection_enabled: bool = True
    warmup_enabled: bool = True
    profile_before_interview: bool = False
    decision_to_inform: str | None = None
    target_customer_description: str | None = None
    target_participants: int | None = None
    is_demo: bool = False
    branding_mode: str = "standard"
    brand_primary_color: str | None = None
    brand_font: str | None = None
    researcher_name: str | None = None
    researcher_logo_url: str | None = None
    privacy_policy_url: str | None = None
    incentive_text: str | None = None
    created_at: datetime
    questions: list[QuestionResponse] = []
    screening_questions: list[ScreeningQuestionResponse] = []
    plan_context: PlanContext | None = None

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    id: str
    name: str
    language: str
    created_at: datetime
    archived_at: datetime | None = None
    question_count: int
    completed_count: int = 0
    in_progress_count: int = 0
    analysis_status: str | None = None
    # Most-recent participant completion time. ``None`` when no one has
    # completed an interview yet. Dashboard cards use this to show a
    # "N days since last response" stale nudge without having to fetch
    # a full project-state (and the Claude headline) for every tile.
    last_response_at: datetime | None = None
    is_demo: bool = False
    plan_context: PlanContext | None = None

    model_config = {"from_attributes": True}
