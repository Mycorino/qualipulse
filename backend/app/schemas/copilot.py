"""Research Copilot — request/response schemas.

The API is stateless: the frontend holds the chat thread and sends the
full message history on every turn. The copilot's per-workspace memory is
the only server-persisted state.
"""

from typing import Literal

from pydantic import BaseModel, Field


class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CopilotRequest(BaseModel):
    """One turn: the full chat history, latest user message last.

    ``active_section`` tells the copilot which tab/section the researcher
    is looking at right now (e.g. "Setup", "Analysis"). ``mission`` is the
    one-line job the copilot is helping with on this surface (e.g. "Turn
    transcripts into decisions"). Both are optional — they let the agent
    bias its help toward where the researcher sits.
    """

    messages: list[CopilotMessage] = Field(..., min_length=1)
    active_section: str | None = None
    mission: str | None = None


class CopilotResponse(BaseModel):
    """The copilot's reply plus any proposed survey changes.

    `proposed_actions` are intents, not mutations — the frontend stages
    them as pending cards for the researcher to accept or reject. Each
    action is a dict whose shape depends on `type`:
      - add_question:    {type, question: {type, prompt, config, rationale}}
      - edit_question:   {type, question_id, new_prompt?, new_config?, rationale}
      - remove_question: {type, question_id, rationale}
    """

    reply: str
    proposed_actions: list[dict] = Field(default_factory=list)
    memory_updated: bool = False


class OnboardingStudyQuestion(BaseModel):
    section_title: str
    main_question: str
    desired_learning: str | None = None


class OnboardingStudyCreate(BaseModel):
    """Atomic study creation — project + settings + guide in one call."""

    study_name: str
    objective: str | None = None
    decision_to_inform: str | None = None
    timeline: str | None = None
    success_criteria: str | None = None
    target_customer_description: str | None = None
    questions: list[OnboardingStudyQuestion] = []
    language: str = "en"


class ConversationState(BaseModel):
    """The persisted chat thread for a copilot panel.

    ``version`` enables optimistic concurrency — the client sends back
    the version it loaded, and the server rejects stale writes.
    """

    thread: list[dict] = Field(default_factory=list)
    version: int = 0
