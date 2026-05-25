from datetime import datetime

from pydantic import BaseModel


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

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str
    language: str = "en"
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
    # Study grounding — used by AI analysis + interview engine
    decision_to_inform: str | None = None
    target_customer_description: str | None = None
    questions: list[QuestionCreate] = []
    screening_questions: list[ScreeningQuestionCreate] = []


class ProjectSettingsPatch(BaseModel):
    name: str | None = None
    panel_collection_enabled: bool | None = None
    warmup_enabled: bool | None = None
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
    decision_to_inform: str | None = None
    target_customer_description: str | None = None
    is_demo: bool = False
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
