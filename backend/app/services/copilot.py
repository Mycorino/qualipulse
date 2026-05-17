"""Research Copilot — the in-context AI assistant (survey surface).

A server-side agent loop behind ``POST /surveys/{id}/copilot``. The copilot
reads the live survey, asks clarifying questions, and *proposes* question
changes — it never mutates the survey directly. Proposed actions are
returned to the frontend, which stages them as pending cards the
researcher accepts or rejects.

Design notes
------------
- Model: ``claude-sonnet-4-6`` — fast enough for an interactive,
  type-alongside assistant doing tool-use loops.
- Memory: per-workspace ``CopilotMemory``, read into every system prompt
  and appended via the `remember` tool. Keeps the copilot consistent
  across studies and surfaces.
- Methodology guardrails: the copilot is bound to the same contract the
  survey builder enforces — only the six sanctioned question types, no
  leading / double-barrelled questions.
- Stub mode: with no ``ANTHROPIC_API_KEY`` the agent returns a
  deterministic canned proposal so the UI and tests work without an AI
  dependency. Production always has the key.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models.company import Company
from app.models.copilot import MEMORY_SCOPES, CopilotConversation, CopilotMemory
from app.models.survey import QUESTION_TYPES, Survey
from app.services.usage_logger import log_claude_usage

MODEL = "claude-sonnet-4-6"
MAX_AGENT_TURNS = 8

# Choice-bearing question types — the only ones that take a `choices` list.
_CHOICE_TYPES = ("mc_single", "mc_multi")


# ── Memory (scoped: company / study / survey) ────────────────────────────────


def get_memory(
    db: Session, scope_kind: str, scope_id: str
) -> CopilotMemory | None:
    return (
        db.query(CopilotMemory)
        .filter(
            CopilotMemory.scope_kind == scope_kind,
            CopilotMemory.scope_id == scope_id,
        )
        .first()
    )


def append_memory(
    db: Session,
    company_id: str,
    scope_kind: str,
    scope_id: str,
    note: str,
) -> None:
    """Append a durable fact to memory at a given scope (creates the row once)."""
    note = (note or "").strip()
    if not note:
        return
    row = get_memory(db, scope_kind, scope_id)
    if row is None:
        row = CopilotMemory(
            company_id=company_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            content=f"- {note}",
        )
        db.add(row)
    else:
        row.content = f"{row.content}\n- {note}".strip()
        row.updated_at = datetime.utcnow()
    db.commit()


# ── Conversation persistence ─────────────────────────────────────────────────


def get_conversation(db: Session, survey_id: str) -> list:
    """Return the persisted panel thread for a survey (empty if none)."""
    row = (
        db.query(CopilotConversation)
        .filter(CopilotConversation.survey_id == survey_id)
        .first()
    )
    if row is None:
        return []
    try:
        return json.loads(row.thread)
    except (json.JSONDecodeError, TypeError):
        return []


def save_conversation(
    db: Session, company_id: str, survey_id: str, thread: list
) -> None:
    """Persist the panel thread for a survey so it resumes on navigation."""
    row = (
        db.query(CopilotConversation)
        .filter(CopilotConversation.survey_id == survey_id)
        .first()
    )
    payload = json.dumps(thread, ensure_ascii=False)
    if row is None:
        db.add(
            CopilotConversation(
                company_id=company_id, survey_id=survey_id, thread=payload
            )
        )
    else:
        row.thread = payload
        row.updated_at = datetime.utcnow()
    db.commit()


# ── Survey snapshot ──────────────────────────────────────────────────────────


def _live_questions(survey: Survey) -> list:
    return [q for q in survey.questions if q.deprecated_at is None]


def _survey_snapshot(survey: Survey) -> dict:
    """Compact JSON view of the survey — fed to the model as grounding."""
    return {
        "name": survey.name,
        "status": survey.status,
        "role": survey.role,
        "questions": [
            {
                "id": q.id,
                "type": q.type,
                "prompt": q.prompt,
                "is_required": q.is_required,
                "config": q.config_dict,
            }
            for q in _live_questions(survey)
        ],
    }


def _slug(label: str, index: int) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")[:24]
    return s or f"opt{index + 1}"


def _config_for(qtype: str, choices: list[str] | None) -> dict:
    """Build a SurveyQuestion config from the copilot's tool input."""
    if qtype in _CHOICE_TYPES and choices:
        return {
            "choices": [
                {"id": _slug(c, i), "label": c} for i, c in enumerate(choices)
            ],
            "randomize": False,
            "has_other": False,
        }
    return {}


# ── System prompt ────────────────────────────────────────────────────────────

_SYSTEM = """You are the Research Copilot inside QualiPulse — an AI \
assistant embedded in the survey builder. You help researchers (often \
beginners) build methodologically sound surveys.

How you work:
- You PROPOSE changes; you never apply them. The researcher reviews every \
proposal as a pending card and accepts or rejects it.
- When the researcher's goal is vague, ask ONE round of 2-4 sharp \
clarifying questions — audience, the decision the survey informs, and \
roughly how many responses they expect — then stop asking. The moment the \
researcher answers, or says to go ahead / draft it / skip, you MUST call \
propose_questions in that same turn. Never ask a second round of \
clarifying questions; if something is still unclear, state your \
assumption out loud and propose anyway.
- Call `read_survey` first if you need the current state.
- Use `remember` to save durable facts — never transient details — and \
pick the scope: "company" for workspace-wide preferences (house style, \
recurring audiences, tone), "study" for facts about this whole research \
effort, "survey" for facts specific to this one survey. You already see \
everything currently in memory below; don't re-save what's there.

Methodology contract (non-negotiable):
- Only these six question types exist: likert, mc_single, mc_multi, nps, \
open_text, short_text. If asked for MaxDiff, ranking, conjoint, or sliders, \
explain they are unsupported and offer the nearest sound alternative.
- Never write leading, double-barrelled, or unbalanced questions.
- If the researcher expects fewer than ~30 responses, do not pad the survey \
with fine-grained segmentation questions that cannot be cut at that n.
- Every proposed question carries a one-line rationale.

Be concise and warm. The chat is for clarifying intent — the survey itself \
is where your work lands."""


def _memory_block(db: Session, label: str, scope_kind: str, scope_id: str) -> str:
    row = get_memory(db, scope_kind, scope_id)
    if row and row.content.strip():
        return f"\n\n{label}:\n{row.content}"
    return ""


def _system_prompt(db: Session, company: Company, survey: Survey) -> str:
    # Stack every applicable memory tier, broadest first.
    blocks = (
        _memory_block(db, "Workspace memory (applies to every study)", "company", company.id)
        + _memory_block(db, "Memory for this study", "study", survey.study_id)
        + _memory_block(db, "Memory for this survey", "survey", survey.id)
    )
    if not blocks:
        blocks = "\n\nYou have no saved memory yet."
    snapshot = json.dumps(_survey_snapshot(survey), ensure_ascii=False)
    return f"{_SYSTEM}{blocks}\n\nThe survey right now:\n{snapshot}"


# ── Tools ────────────────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": "read_survey",
        "description": "Return the survey's current name, status, and questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_questions",
        "description": (
            "Propose one or more new questions to add to the survey. These "
            "are staged for the researcher to accept — not added directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": list(QUESTION_TYPES),
                            },
                            "prompt": {"type": "string"},
                            "choices": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Required for mc_single / mc_multi.",
                            },
                            "rationale": {"type": "string"},
                        },
                        "required": ["type", "prompt", "rationale"],
                    },
                }
            },
            "required": ["questions"],
        },
    },
    {
        "name": "edit_question",
        "description": "Propose an edit to an existing question (by id).",
        "input_schema": {
            "type": "object",
            "properties": {
                "question_id": {"type": "string"},
                "new_prompt": {"type": "string"},
                "new_choices": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
            "required": ["question_id", "rationale"],
        },
    },
    {
        "name": "remove_question",
        "description": "Propose removing an existing question (by id).",
        "input_schema": {
            "type": "object",
            "properties": {
                "question_id": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["question_id", "rationale"],
        },
    },
    {
        "name": "remember",
        "description": (
            "Save a durable fact to memory so you stay consistent later. "
            "Use sparingly — only durable facts, never transient details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string"},
                "scope": {
                    "type": "string",
                    "enum": list(MEMORY_SCOPES),
                    "description": (
                        "company = workspace-wide; study = this research "
                        "effort; survey = this survey only. Defaults to company."
                    ),
                },
            },
            "required": ["note"],
        },
    },
]


# ── Agent loop ───────────────────────────────────────────────────────────────


class _Turn:
    """Mutable accumulator for one copilot turn."""

    def __init__(self) -> None:
        self.actions: list[dict] = []
        self.memory_updated = False


def _run_tool(
    db: Session,
    company: Company,
    survey: Survey,
    turn: _Turn,
    name: str,
    tool_input: dict,
) -> str:
    """Execute a tool call. Returns the tool_result string for the model."""
    if name == "read_survey":
        return json.dumps(_survey_snapshot(survey), ensure_ascii=False)

    if name == "propose_questions":
        added = 0
        for q in tool_input.get("questions", []):
            qtype = q.get("type")
            prompt = (q.get("prompt") or "").strip()
            if qtype not in QUESTION_TYPES or not prompt:
                continue
            turn.actions.append(
                {
                    "type": "add_question",
                    "question": {
                        "type": qtype,
                        "prompt": prompt,
                        "config": _config_for(qtype, q.get("choices")),
                        "rationale": (q.get("rationale") or "").strip(),
                    },
                }
            )
            added += 1
        return f"Recorded {added} proposed question(s) for the researcher to review."

    if name == "edit_question":
        action: dict = {
            "type": "edit_question",
            "question_id": tool_input.get("question_id"),
            "rationale": (tool_input.get("rationale") or "").strip(),
        }
        if tool_input.get("new_prompt"):
            action["new_prompt"] = tool_input["new_prompt"].strip()
        if tool_input.get("new_choices"):
            action["new_config"] = _config_for("mc_single", tool_input["new_choices"])
        turn.actions.append(action)
        return "Recorded the proposed edit."

    if name == "remove_question":
        turn.actions.append(
            {
                "type": "remove_question",
                "question_id": tool_input.get("question_id"),
                "rationale": (tool_input.get("rationale") or "").strip(),
            }
        )
        return "Recorded the proposed removal."

    if name == "remember":
        scope = tool_input.get("scope") or "company"
        if scope not in MEMORY_SCOPES:
            scope = "company"
        scope_id = {
            "company": company.id,
            "study": survey.study_id,
            "survey": survey.id,
        }[scope]
        append_memory(db, company.id, scope, scope_id, tool_input.get("note", ""))
        turn.memory_updated = True
        return f"Saved to {scope} memory."

    return f"Unknown tool: {name}"


def run_copilot_turn(
    db: Session, company: Company, survey: Survey, messages: list
) -> dict:
    """Run one copilot turn. ``messages`` is the full chat history (objects
    with ``.role`` / ``.content``). Returns {reply, proposed_actions,
    memory_updated}."""
    history = [{"role": m.role, "content": m.content} for m in messages]

    if not settings.ANTHROPIC_API_KEY:
        return _stub_turn(survey, history)

    import anthropic  # noqa: WPS433 — lazy import keeps tests AI-free

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    system = _system_prompt(db, company, survey)
    turn = _Turn()
    reply_parts: list[str] = []

    for _ in range(MAX_AGENT_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system,
            tools=_TOOLS,
            messages=history,
        )
        log_claude_usage(db, response, "copilot", company_id=company.id)

        for block in response.content:
            if block.type == "text" and block.text.strip():
                reply_parts.append(block.text.strip())

        if response.stop_reason != "tool_use":
            break

        history.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _run_tool(
                    db, company, survey, turn, block.name, block.input or {}
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
        history.append({"role": "user", "content": tool_results})

    return {
        "reply": "\n\n".join(reply_parts).strip()
        or "Done — review the proposed changes in your question list.",
        "proposed_actions": turn.actions,
        "memory_updated": turn.memory_updated,
    }


# ── Stub mode ────────────────────────────────────────────────────────────────


def _stub_turn(survey: Survey, history: list[dict]) -> dict:
    """Deterministic offline response so the UI + tests work without an API
    key. NOT a real synthesis — a structural placeholder."""
    if _live_questions(survey):
        return {
            "reply": (
                "(Offline stub — set ANTHROPIC_API_KEY for the real copilot.) "
                "Tell me what you'd like to change and I'll propose edits."
            ),
            "proposed_actions": [],
            "memory_updated": False,
        }
    return {
        "reply": (
            "(Offline stub — set ANTHROPIC_API_KEY for the real copilot.) "
            "Here are two starter questions to review."
        ),
        "proposed_actions": [
            {
                "type": "add_question",
                "question": {
                    "type": "mc_single",
                    "prompt": "Which best describes you?",
                    "config": _config_for(
                        "mc_single", ["First option", "Second option"]
                    ),
                    "rationale": "A screener so the sample is the right audience.",
                },
            },
            {
                "type": "add_question",
                "question": {
                    "type": "nps",
                    "prompt": "How likely are you to recommend us to a friend?",
                    "config": {},
                    "rationale": "A standard outcome metric to anchor the survey.",
                },
            },
        ],
        "memory_updated": False,
    }
