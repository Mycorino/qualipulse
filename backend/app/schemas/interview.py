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

    model_config = {"from_attributes": True}


class TranscriptTurnResponse(BaseModel):
    turn_index: int
    question_text: str
    response_transcript: str | None = None
    is_follow_up: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TranscriptResponse(BaseModel):
    participant: ParticipantResponse
    turns: list[TranscriptTurnResponse] = []
