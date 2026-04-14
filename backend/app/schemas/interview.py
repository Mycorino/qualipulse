from datetime import datetime

from pydantic import BaseModel


class LinkCreate(BaseModel):
    pass


class LinkResponse(BaseModel):
    id: str
    token: str
    url: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StartInterviewRequest(BaseModel):
    display_name: str | None = None
    age_range: str | None = None
    profession: str | None = None
    country: str | None = None
    email: str | None = None
    session_token: str | None = None  # JWT from email verification


class StartInterviewResponse(BaseModel):
    participant_id: str
    first_question: str
    tts_audio_url: str | None = None


class TurnResponse(BaseModel):
    question_text: str
    tts_audio_url: str | None = None
    is_complete: bool
    is_follow_up: bool = False
    question_index: int = 0
    elapsed_seconds: int = 0
    total_seconds: int = 0


class ParticipantResponse(BaseModel):
    id: str
    display_name: str | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    turn_count: int
    age_range: str | None = None
    profession: str | None = None
    country: str | None = None
    quality_score: float | None = None
    quality_label: str | None = None
    quality_summary: str | None = None
    quality_strengths: list[str] | None = None
    quality_issues: list[str] | None = None
    avg_response_words: float | None = None
    short_answer_pct: float | None = None

    model_config = {"from_attributes": True}


class TranscriptTurnResponse(BaseModel):
    id: str
    turn_index: int
    question_text: str
    response_transcript: str | None = None
    is_follow_up: bool
    manually_edited: bool = False
    edited_at: datetime | None = None
    created_at: datetime
    audio_recording_url: str | None = None
    tts_audio_url: str | None = None
    translated_response: str | None = None
    translated_question: str | None = None
    translation_language: str | None = None

    model_config = {"from_attributes": True}


class TranscriptResponse(BaseModel):
    participant: ParticipantResponse
    turns: list[TranscriptTurnResponse] = []
    translation_language: str | None = None


class ResumeCheckResponse(BaseModel):
    found: bool
    participant_id: str | None = None
    last_question: str | None = None
    turn_count: int = 0
    question_index: int = 0

class ResumeSummaryResponse(BaseModel):
    questions_covered: list[str]
    last_question: str | None = None
    turn_count: int
    elapsed_minutes: float


class QualityAssessment(BaseModel):
    quality_score: float          # 0.0 - 1.0
    quality_label: str            # "low" | "fair" | "good" | "strong"
    summary: str                  # 2-3 sentence overall assessment
    strengths: list[str]          # What the participant did well
    issues: list[str]             # Problems: too brief, evasive, off-topic, etc.
    avg_response_words: float     # Average word count per answer
    short_answer_pct: float       # % of answers that are very short (<10 words)
