from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LinkCreate(BaseModel):
    pass


class LinkResponse(BaseModel):
    id: str
    token: str
    url: str
    is_active: bool
    # Optional ceiling on participants admitted through this link (None =
    # uncapped), plus the live count so the UI can show "12 / 50 used".
    max_participants: int | None = None
    participant_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class LinkUpdateRequest(BaseModel):
    """Partial update for a link. Omitted fields are left untouched.

    ``max_participants`` is tri-state: absent = unchanged, ``null`` = remove
    the cap, an integer = set it.
    """

    is_active: bool | None = None
    max_participants: int | None = Field(default=None, ge=1, le=10000)
    # Distinguishes "max_participants omitted" from "explicitly set to null",
    # which Pydantic alone can't express on a plain optional field.
    clear_max_participants: bool = False


class LinkInviteRequest(BaseModel):
    """Batch of participant emails to invite through an interview link."""

    emails: list[EmailStr] = Field(min_length=1, max_length=20)
    # Shown in the email body ("X has invited you..."). Defaults to the
    # project's researcher_name, then the company name.
    sender_name: str | None = Field(default=None, max_length=120)


class LinkInviteResponse(BaseModel):
    sent: int
    failed: list[str]


class StartInterviewRequest(BaseModel):
    display_name: str | None = None
    age_range: str | None = None
    profession: str | None = None
    country: str | None = None
    email: str | None = None
    session_token: str | None = None  # JWT from email verification
    # Participant-chosen interview language (en/fr/de/es/it/pt). Overrides
    # the study's default language for the AI interviewer + voice.
    preferred_language: str | None = None


class StartInterviewResponse(BaseModel):
    participant_id: str
    first_question: str
    tts_audio_url: str | None = None
    # PF-3: True when the engine is opening with a warm-up turn (low-stakes
    # icebreaker) before the first guide question. Frontend uses this to
    # soften the chrome on turn 0 — no progress count, no skip button.
    is_warmup: bool = False
    # The authoritative language the AI interviewer + voice are actually using
    # for this participant (participant choice, else the study default). The
    # frontend locks its UI chrome (progress labels, completion screen) to this
    # so the interface never drifts away from the language being spoken.
    language: str = "en"


class TurnResponse(BaseModel):
    question_text: str
    tts_audio_url: str | None = None
    is_complete: bool
    is_follow_up: bool = False
    question_index: int = 0
    elapsed_seconds: int = 0
    total_seconds: int = 0
    # PF-3: gentle in-flight tip rendered to the participant when their last
    # answers go short. Null when no coaching is needed. Frontend renders as a
    # dismissable inline banner above the record button.
    coaching_hint: str | None = None
    # What Whisper heard in the answer just submitted — powers the "We heard:
    # …" confirmation flash. Null on the dedupe/skip paths where no fresh
    # transcription happened.
    transcript: str | None = None
    # PF-3: marks the warm-up turn (turn_index=0) so the frontend can soften
    # the chrome (no progress count, no skip button) and the engine knows not
    # to count it against the time budget.
    is_warmup: bool = False


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
    email: str | None = None
    email_verified: bool = False
    # Denormalised recontact flag (see Participant.panel_consent):
    # True = agreed to follow-ups, False = declined, None = unknown.
    panel_consent: bool | None = None
    quality_score: float | None = None
    quality_label: str | None = None
    quality_summary: str | None = None
    quality_strengths: list[str] | None = None
    quality_issues: list[str] | None = None
    key_takeaways: list[str] | None = None
    notable_quotes: list[str] | None = None
    avg_response_words: float | None = None
    short_answer_pct: float | None = None
    # V4 paywall — True when this participant's transcript is locked
    # behind the free-preview paywall for the current workspace. The
    # frontend renders a paywall card instead of the transcript body.
    is_locked: bool = False

    model_config = {"from_attributes": True}


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptTurnResponse(BaseModel):
    id: str
    turn_index: int
    question_text: str
    response_transcript: str | None = None
    response_segments: list[TranscriptSegment] | None = None
    is_follow_up: bool
    manually_edited: bool = False
    edited_at: datetime | None = None
    created_at: datetime
    audio_recording_url: str | None = None
    tts_audio_url: str | None = None
    translated_response: str | None = None
    translated_question: str | None = None
    translation_language: str | None = None
    cleaned_response: str | None = None
    cleaned_at: datetime | None = None

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
    # Authoritative interview language (see StartInterviewResponse.language) so a
    # resumed session re-locks the UI to whatever language the AI is speaking.
    language: str = "en"


class QualityAssessment(BaseModel):
    quality_score: float          # 0.0 - 1.0
    quality_label: str            # "low" | "fair" | "good" | "strong"
    summary: str                  # 2-3 sentence overall assessment
    strengths: list[str]          # What the participant did well
    issues: list[str]             # Problems: too brief, evasive, off-topic, etc.
    avg_response_words: float     # Average word count per answer
    short_answer_pct: float       # % of answers that are very short (<10 words)
