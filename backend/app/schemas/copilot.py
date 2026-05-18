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
    is looking at right now (e.g. "Setup", "Analysis") so it can bias its
    help toward what is actionable from there. Optional — older clients
    and non-tabbed surfaces simply omit it.
    """

    messages: list[CopilotMessage] = Field(..., min_length=1)
    active_section: str | None = None


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


class ConversationState(BaseModel):
    """The persisted chat thread for a survey's copilot panel.

    `thread` is the panel's own thread-item structure — stored and
    returned verbatim so the conversation resumes on navigation. Opaque
    to the backend.
    """

    thread: list[dict] = Field(default_factory=list)
