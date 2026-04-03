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


class StartInterviewResponse(BaseModel):
    participant_id: str
    first_question: str
    tts_audio_url: str | None = None


class TurnResponse(BaseModel):
    question_text: str
    tts_audio_url: str | None = None
    is_complete: bool


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

    model_config = {"from_attributes": True}


class TranscriptResponse(BaseModel):
    participant: ParticipantResponse
    turns: list[TranscriptTurnResponse] = []


class QualityAssessment(BaseModel):
    quality_score: float          # 0.0 - 1.0
    quality_label: str            # "low" | "fair" | "good" | "strong"
    summary: str                  # 2-3 sentence overall assessment
    strengths: list[str]          # What the participant did well
    issues: list[str]             # Problems: too brief, evasive, off-topic, etc.
    avg_response_words: float     # Average word count per answer
    short_answer_pct: float       # % of answers that are very short (<10 words)
