"""Research Copilot — request/response schemas.

The API is stateless: the frontend holds the chat thread and sends the
full message history on every turn. The copilot's per-workspace memory is
the only server-persisted state.
"""

from typing import Literal

from pydantic import BaseModel, Field


class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    # Bounded — the request body is client-controlled and goes straight
    # into an Opus prompt; unbounded content is an open cost hole.
    content: str = Field(..., max_length=8_000)


class CopilotRequest(BaseModel):
    """One turn: the full chat history, latest user message last.

    ``active_section`` tells the copilot which tab/section the researcher
    is looking at right now (e.g. "Setup", "Analysis"). ``mission`` is the
    one-line job the copilot is helping with on this surface (e.g. "Turn
    transcripts into decisions"). Both are optional — they let the agent
    bias its help toward where the researcher sits.

    ``messages`` is capped: the server only feeds the recent tail to the
    model anyway (see ``copilot.MAX_MODEL_MESSAGES``), so a longer history
    in the request is pure cost with no benefit.
    """

    messages: list[CopilotMessage] = Field(..., min_length=1, max_length=60)
    active_section: str | None = Field(default=None, max_length=200)
    mission: str | None = Field(default=None, max_length=500)


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
    """The persisted chat thread for a copilot panel.

    ``version`` enables optimistic concurrency — the client sends back
    the version it loaded, and the server rejects stale writes.
    """

    thread: list[dict] = Field(default_factory=list)
    version: int = 0
