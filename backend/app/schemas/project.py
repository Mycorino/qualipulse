from datetime import datetime

from pydantic import BaseModel


class QuestionCreate(BaseModel):
    section_index: int
    section_title: str
    question_index: int
    main_question: str
    interview_notes: str | None = None
    desired_learning: str | None = None


class QuestionPatch(BaseModel):
    researcher_notes: str | None = None
    deprecated_at: datetime | None = None


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
    interview_duration_minutes: int = 20
    system_prompt: str | None = None
    research_objective: str | None = None
    questions: list[QuestionCreate] = []
    screening_questions: list[ScreeningQuestionCreate] = []


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


class ProjectResponse(BaseModel):
    id: str
    company_id: str
    name: str
    language: str
    interview_duration_minutes: int
    system_prompt: str | None = None
    research_objective: str | None = None
    created_at: datetime
    questions: list[QuestionResponse] = []
    screening_questions: list[ScreeningQuestionResponse] = []

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    id: str
    name: str
    language: str
    created_at: datetime
    question_count: int

    model_config = {"from_attributes": True}
