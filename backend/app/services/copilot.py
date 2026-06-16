"""Research Copilot — the in-context AI assistant.

A surface-agnostic agent core plus per-surface *adapters*. Today the
survey builder runs on the ``SURVEY_ADAPTER``; the interview guide and
later surfaces add their own adapter — the loop, memory, conversation
persistence, and prompt assembly stay generic.

Design notes
------------
- Model: ``claude-opus-4-7`` with adaptive thinking — research-grade
  qualitative reasoning (reading transcripts, respecting confidence
  levels, separating observation from recommendation). Adaptive thinking
  self-moderates, so trivial guide-edit turns stay fast while results
  turns think as hard as they need to.
- Memory: scoped ``CopilotMemory`` (company / study / instrument), read
  into every system prompt and appended via the `remember` tool.
- The copilot PROPOSES; it never mutates the instrument. Proposed actions
  are returned to the frontend, which stages them as pending cards.
- Stub mode: with no ``ANTHROPIC_API_KEY`` the agent returns a
  deterministic canned proposal so the UI and tests work without an AI
  dependency. Production always has the key.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.logging_config import logger
from app.models.company import Company
from app.models.copilot import CopilotConversation, CopilotMemory
from app.models.survey import QUESTION_TYPES, Survey
from app.services.usage_logger import log_claude_usage

MODEL = "claude-opus-4-7"
MAX_AGENT_TURNS = 8


# ── Memory (scoped: company / study / instrument) ────────────────────────────


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


MAX_MEMORY_CHARS = 10_000


def append_memory(
    db: Session,
    company_id: str,
    scope_kind: str,
    scope_id: str,
    note: str,
) -> None:
    """Append a durable fact to memory at a given scope (creates the row once).

    Uses a single-statement UPDATE for existing rows to avoid a
    read-modify-write race when concurrent requests append to the same
    scope. Memory is capped at ``MAX_MEMORY_CHARS`` (keeping the most
    recent tail) to prevent unbounded growth from long conversations.
    """
    note = (note or "").strip()
    if not note:
        return
    row = get_memory(db, scope_kind, scope_id)
    if row is None:
        content = f"- {note}"
        if len(content) > MAX_MEMORY_CHARS:
            content = content[-MAX_MEMORY_CHARS:]
        row = CopilotMemory(
            company_id=company_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            content=content,
        )
        db.add(row)
        db.commit()
    else:
        # Append in SQL to avoid read-modify-write race, then truncate
        # in Python on the refreshed row.
        (
            db.query(CopilotMemory)
            .filter(CopilotMemory.id == row.id)
            .update(
                {
                    CopilotMemory.content: CopilotMemory.content + "\n- " + note,
                    CopilotMemory.updated_at: datetime.utcnow(),
                },
                synchronize_session="fetch",
            )
        )
        db.commit()
        # Re-read and truncate if over the cap (keeps the most recent tail).
        db.refresh(row)
        if row.content and len(row.content) > MAX_MEMORY_CHARS:
            row.content = row.content[-MAX_MEMORY_CHARS:]
            db.commit()


# ── Conversation persistence (keyed by scope_kind / scope_id) ────────────────


MAX_CONVERSATION_TURNS = 200


def get_conversation(
    db: Session, scope_kind: str, scope_id: str
) -> tuple[list, int]:
    """Return (thread, version) for an instrument. Empty list + version 0
    when no conversation exists yet."""
    row = (
        db.query(CopilotConversation)
        .filter(
            CopilotConversation.scope_kind == scope_kind,
            CopilotConversation.scope_id == scope_id,
        )
        .first()
    )
    if row is None:
        return [], 0
    try:
        thread = json.loads(row.thread)
    except (json.JSONDecodeError, TypeError):
        thread = []
    return thread, row.version


def save_conversation(
    db: Session,
    company_id: str,
    scope_kind: str,
    scope_id: str,
    thread: list,
    expected_version: int | None = None,
) -> int:
    """Persist the panel thread with optimistic concurrency.

    Returns the new version number. If ``expected_version`` is given and
    doesn't match the stored version, the save is skipped (stale-write
    protection). Threads exceeding ``MAX_CONVERSATION_TURNS`` are pruned.
    """
    if len(thread) > MAX_CONVERSATION_TURNS:
        thread = thread[-MAX_CONVERSATION_TURNS:]
    payload = json.dumps(thread, ensure_ascii=False)
    row = (
        db.query(CopilotConversation)
        .filter(
            CopilotConversation.scope_kind == scope_kind,
            CopilotConversation.scope_id == scope_id,
        )
        .first()
    )
    if row is None:
        row = CopilotConversation(
            company_id=company_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            thread=payload,
            version=1,
        )
        db.add(row)
        db.commit()
        return 1
    if expected_version is not None and row.version != expected_version:
        logger.warning(
            "Stale conversation write discarded: scope=%s/%s expected_v=%d actual_v=%d",
            scope_kind, scope_id, expected_version, row.version,
        )
        return row.version
    row.thread = payload
    row.version += 1
    row.updated_at = datetime.utcnow()
    db.commit()
    return row.version


# ── Surface adapter ──────────────────────────────────────────────────────────


# When a primary proposal (research plan or first study) is in a turn,
# strip secondary lightweight-capture chips so the user's attention
# stays on the accept CTA. Belt-and-suspenders to the methodology rule.
_PRIMARY_PROPOSAL_TYPES = {"create_research_plan", "create_first_study"}
_SIDE_CAPTURE_CONTEXTS = {
    "referral_source",
    "current_tool",
    "research_experience",
}


def _filter_proposal_turn_actions(actions: list[dict]) -> list[dict]:
    """If this turn contains a primary proposal card, drop any
    lightweight-signal suggest_replies chip groups so the proposal
    owns the screen. Pure function — easy to test."""
    has_primary = any(
        a.get("type") in _PRIMARY_PROPOSAL_TYPES for a in actions
    )
    if not has_primary:
        return list(actions)
    return [
        a for a in actions
        if not (
            a.get("type") == "suggest_replies"
            and a.get("context") in _SIDE_CAPTURE_CONTEXTS
        )
    ]


def _suppress_opening_chips(
    actions: list[dict], adapter: "CopilotAdapter", is_first_turn: bool
) -> list[dict]:
    """The interview opener must be a single OPEN context question in free
    text — never a chip-based targeting question. The methodology says so,
    but the model doesn't always obey, so we hard-strip any suggest_replies
    on the very first turn of an interview-guide conversation. Other
    surfaces (e.g. onboarding) keep their first-turn chips."""
    if not (is_first_turn and adapter.kind == "interview"):
        return actions
    return [a for a in actions if a.get("type") != "suggest_replies"]


@dataclass
class CopilotAdapter:
    """Everything surface-specific. The agent core is generic over this.

    An ``instrument`` is a Survey or a Project — both expose ``.id`` and
    ``.study_id``, which is all the core needs.
    """

    kind: str  # "survey" | "interview"
    instrument_scope_kind: str  # memory/conversation tier: "survey" | "project"
    instrument_memory_label: str  # e.g. "Memory for this survey"
    methodology: str  # system-prompt fragment (the methodology contract)
    tools: list[dict]
    snapshot: Callable[[object], dict]
    # (db, company, instrument, turn, tool_name, tool_input) -> tool_result str
    run_tool: Callable[..., str]
    # (instrument, history) -> {reply, proposed_actions, memory_updated}
    stub: Callable[..., dict]
    default_reply: str


def remember_tool(instrument_scope: str) -> dict:
    """Build the `remember` tool with the scope enum for this surface."""
    return {
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
                    "enum": ["company", "study", instrument_scope],
                    "description": (
                        f"company = workspace-wide; study = this research "
                        f"effort; {instrument_scope} = this {instrument_scope} "
                        f"only. Defaults to company."
                    ),
                },
            },
            "required": ["note"],
        },
    }


# ── System prompt ────────────────────────────────────────────────────────────

_BASE_SYSTEM = """You are the Research Copilot inside QualiPulse — an AI \
assistant embedded in the research tools. You help researchers (often \
beginners) build methodologically sound studies.

How you work:
- You PROPOSE changes; you never apply them. The researcher reviews every \
proposal as a pending card and accepts or rejects it.
- When the researcher's goal is vague, ask ONE round of 2-4 sharp \
clarifying questions — audience, the decision the research informs, and \
roughly how much data they expect — then stop asking. The moment the \
researcher answers, or says to go ahead / draft it / skip, you MUST start \
proposing in that same turn. Never ask a second round of clarifying \
questions; if something is still unclear, state your assumption out loud \
and propose anyway.
- Use `remember` to save durable facts — never transient details — and \
pick the scope: "company" for workspace-wide preferences (house style, \
recurring audiences, tone), "study" for facts about this whole research \
effort, or the instrument scope for facts specific to this one survey or \
interview guide. You already see everything in memory below; don't \
re-save what's there.
- Every proposed item carries a one-line rationale.

Be concise and warm. The chat is for clarifying intent — the instrument \
itself is where your work lands."""


def _memory_block(db: Session, label: str, scope_kind: str, scope_id: str) -> str:
    row = get_memory(db, scope_kind, scope_id)
    if row and row.content.strip():
        return f"\n\n{label}:\n{row.content}"
    return ""


def _system_prompt(
    db: Session, company: Company, instrument, adapter: CopilotAdapter
) -> str:
    # Stack every applicable memory tier, broadest first. The onboarding
    # surface's "instrument" is the Company itself — it has no study_id,
    # and its instrument scope would duplicate the workspace block — so
    # both are guarded.
    study_id = getattr(instrument, "study_id", None)
    blocks = _memory_block(
        db, "Workspace memory (applies to every study)", "company", company.id
    )
    if study_id:
        blocks += _memory_block(db, "Memory for this study", "study", study_id)
    if not (
        adapter.instrument_scope_kind == "company"
        and instrument.id == company.id
    ):
        blocks += _memory_block(
            db,
            adapter.instrument_memory_label,
            adapter.instrument_scope_kind,
            instrument.id,
        )
    if not blocks:
        blocks = "\n\nYou have no saved memory yet."
    snapshot = json.dumps(adapter.snapshot(instrument), ensure_ascii=False)
    return (
        f"{_BASE_SYSTEM}\n\n{adapter.methodology}{blocks}"
        f"\n\nThe instrument right now:\n{snapshot}"
    )


# ── Agent loop ───────────────────────────────────────────────────────────────


class _Turn:
    """Mutable accumulator for one copilot turn."""

    def __init__(self) -> None:
        self.actions: list[dict] = []
        self.memory_updated = False


def _handle_remember(
    db: Session,
    company: Company,
    instrument,
    adapter: CopilotAdapter,
    turn: _Turn,
    tool_input: dict,
) -> str:
    """Core `remember` handler — shared across surfaces."""
    allowed = ("company", "study", adapter.instrument_scope_kind)
    scope = tool_input.get("scope") or "company"
    if scope not in allowed:
        scope = "company"
    # The onboarding surface's instrument is the Company — no study_id.
    # Resolve lazily so an absent attribute can't crash an unused branch.
    scope_id = {
        "company": company.id,
        "study": getattr(instrument, "study_id", None),
        adapter.instrument_scope_kind: instrument.id,
    }[scope]
    if scope_id is None:
        scope = "company"
        scope_id = company.id
    append_memory(db, company.id, scope, scope_id, tool_input.get("note", ""))
    turn.memory_updated = True
    return f"Saved to {scope} memory."


# Human labels for the agent's tool calls — surfaced live as the copilot
# narrates "what it's doing right now" while a turn is running. Unmapped
# tools fall back to a generic "Working…".
_TOOL_LABELS: dict[str, str] = {
    "remember": "Noting that down",
    # interview reads
    "read_guide": "Reading your guide",
    "read_study": "Reading the rest of your study",
    "read_progress": "Checking progress",
    "read_interviews": "Reading your interviews",
    "read_interview": "Reading a transcript",
    "read_analysis": "Reading your analysis",
    # interview proposals
    "propose_objective": "Drafting the objective",
    "propose_guide_questions": "Drafting questions",
    "edit_guide_question": "Revising a question",
    "remove_guide_question": "Removing a question",
    "propose_settings": "Tuning the setup",
    "propose_screening_questions": "Drafting a screener",
    "propose_run_analysis": "Setting up the analysis",
    "propose_refine_analysis": "Setting up the refined analysis",
    # survey
    "add_question": "Drafting a question",
    "edit_question": "Revising a question",
    "remove_question": "Removing a question",
    # onboarding
    "save_profile": "Noting your profile",
    "propose_study": "Drafting your study",
    "suggest_replies": "Lining up some options",
    "request_website": "Checking your site",
    "propose_participant_demo": "Spinning up a participant preview",
}

# French equivalents — picked when the company's preferred_language is "fr"
# so the streamed status line matches the rest of the localized UI.
_TOOL_LABELS_FR: dict[str, str] = {
    "remember": "Je note ça",
    "read_guide": "Lecture de votre guide",
    "read_study": "Lecture du reste de votre étude",
    "read_progress": "Vérification de l'avancement",
    "read_interviews": "Lecture de vos entretiens",
    "read_interview": "Lecture d'une transcription",
    "read_analysis": "Lecture de votre analyse",
    "propose_objective": "Rédaction de l'objectif",
    "propose_guide_questions": "Rédaction des questions",
    "edit_guide_question": "Révision d'une question",
    "remove_guide_question": "Suppression d'une question",
    "propose_settings": "Ajustement des réglages",
    "propose_screening_questions": "Rédaction du filtre",
    "propose_run_analysis": "Préparation de l'analyse",
    "propose_refine_analysis": "Préparation de l'analyse affinée",
    "add_question": "Rédaction d'une question",
    "edit_question": "Révision d'une question",
    "remove_question": "Suppression d'une question",
    "save_profile": "Enregistrement de votre profil",
    "propose_study": "Rédaction de votre étude",
    "suggest_replies": "Préparation de quelques options",
    "request_website": "Consultation de votre site",
    "propose_participant_demo": "Préparation d'un aperçu participant",
}

_TOOL_LABEL_FALLBACK = {"en": "Working…", "fr": "En cours…"}


def _tool_label(name: str, lang: str | None) -> str:
    """Status label for a tool call, localized to the company's language."""
    if (lang or "en").startswith("fr"):
        return _TOOL_LABELS_FR.get(name, _TOOL_LABEL_FALLBACK["fr"])
    return _TOOL_LABELS.get(name, _TOOL_LABEL_FALLBACK["en"])


def _build_system_blocks(
    db: Session,
    company: Company,
    instrument,
    adapter: CopilotAdapter,
    active_section: str | None,
    mission: str | None,
) -> list[dict]:
    """The cached system prefix + the volatile tab/mission block."""
    system = [
        {
            "type": "text",
            "text": _system_prompt(db, company, instrument, adapter),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    context_bits: list[str] = []
    if active_section:
        context_bits.append(
            f'The researcher is on the "{active_section}" tab of this '
            f"{adapter.kind}."
        )
    if mission:
        context_bits.append(f"Your mission here: {mission}")
    if context_bits:
        system.append(
            {
                "type": "text",
                "text": (
                    " ".join(context_bits)
                    + " Bias your help toward what is actionable from where "
                    "they sit — but still propose anything relevant if they ask."
                ),
            }
        )
    return system


def run_copilot_turn_stream(
    db: Session,
    company: Company,
    instrument,
    adapter: CopilotAdapter,
    messages: list,
    active_section: str | None = None,
    mission: str | None = None,
):
    """Run one copilot turn as a generator of SSE event dicts.

    Yields:
      - {"type": "status", "label": str}  — one per tool call.
      - {"type": "delta",  "text":  str}  — reply text chunks.
      - {"type": "done",   "reply", "proposed_actions", "memory_updated"}
        — exactly one terminal event, always (even on error). This is the
        authoritative final state the client persists.

    The non-streaming ``run_copilot_turn`` below drains this generator and
    returns the final dict — same contract as before for non-HTTP callers
    and existing tests that call it directly.
    """
    history = [{"role": m.role, "content": m.content} for m in messages]
    # First turn = the opening user message is the only user turn so far.
    # Used to keep the interview opener chip-free (open context question).
    is_first_turn = sum(1 for m in messages if m.role == "user") <= 1

    if not settings.ANTHROPIC_API_KEY:
        # Stub path — no streaming, just emit the canned final.
        result = adapter.stub(instrument, history)
        yield {"type": "done", **result}
        return

    import anthropic  # noqa: WPS433 — lazy import keeps tests AI-free

    from app.services._clients import get_anthropic_client

    client = get_anthropic_client(300.0)
    system = _build_system_blocks(
        db, company, instrument, adapter, active_section, mission
    )
    turn = _Turn()
    reply_parts: list[str] = []

    try:
        for _ in range(MAX_AGENT_TURNS):
            iteration_text: list[str] = []
            with client.messages.stream(
                model=MODEL,
                max_tokens=16000,
                system=system,
                tools=adapter.tools,
                thinking={"type": "adaptive"},
                output_config={"effort": "high"},
                messages=history,
            ) as stream:
                for text in stream.text_stream:
                    iteration_text.append(text)
                    yield {"type": "delta", "text": text}
                response = stream.get_final_message()

            log_claude_usage(db, response, "copilot", company_id=company.id)

            joined = "".join(iteration_text).strip()
            if joined:
                reply_parts.append(joined)

            if response.stop_reason == "max_tokens":
                logger.warning(
                    "Copilot turn hit max_tokens (company=%s) — output may be "
                    "truncated.",
                    company.id,
                )
                break

            if response.stop_reason != "tool_use":
                break

            history.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                # Narrate the agent's action BEFORE running the tool so the
                # status sits on the wire while the next iteration thinks.
                yield {
                    "type": "status",
                    "label": _tool_label(
                        block.name, getattr(company, "preferred_language", None)
                    ),
                }
                tool_input = block.input or {}
                try:
                    if block.name == "remember":
                        result = _handle_remember(
                            db, company, instrument, adapter, turn, tool_input
                        )
                    else:
                        result = adapter.run_tool(
                            db, company, instrument, turn, block.name, tool_input
                        )
                except Exception as tool_exc:
                    logger.error(
                        "Copilot tool %s failed (company=%s): %s",
                        block.name, company.id, tool_exc,
                    )
                    result = f"Tool error: {block.name} failed."
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
            history.append({"role": "user", "content": tool_results})
    except anthropic.APIError as exc:
        logger.error(
            "Copilot turn failed (company=%s, request_id=%s): %s",
            company.id,
            getattr(exc, "request_id", None),
            exc,
        )
        yield {
            "type": "done",
            "reply": (
                "\n\n".join(reply_parts).strip()
                or "The copilot is briefly unavailable — please try again in a "
                "moment."
            ),
            "proposed_actions": [],
            "memory_updated": turn.memory_updated,
        }
        return
    except Exception as exc:
        logger.error(
            "Copilot turn unexpected error (company=%s): %s",
            company.id, exc,
        )
        yield {
            "type": "done",
            "reply": (
                "\n\n".join(reply_parts).strip()
                or "Something went wrong — please try again."
            ),
            "proposed_actions": [],
            "memory_updated": turn.memory_updated,
        }
        return

    yield {
        "type": "done",
        "reply": "\n\n".join(reply_parts).strip() or adapter.default_reply,
        "proposed_actions": _filter_proposal_turn_actions(
            _suppress_opening_chips(turn.actions, adapter, is_first_turn)
        ),
        "memory_updated": turn.memory_updated,
    }


def run_copilot_turn(
    db: Session,
    company: Company,
    instrument,
    adapter: CopilotAdapter,
    messages: list,
    active_section: str | None = None,
    mission: str | None = None,
) -> dict:
    """Drain ``run_copilot_turn_stream`` and return the final dict. Kept
    so non-HTTP callers (and tests calling this directly) see the same
    contract as before the streaming refactor."""
    final = {
        "reply": adapter.default_reply,
        "proposed_actions": [],
        "memory_updated": False,
    }
    for event in run_copilot_turn_stream(
        db, company, instrument, adapter, messages, active_section, mission
    ):
        if event.get("type") == "done":
            final = {k: v for k, v in event.items() if k != "type"}
    return final


# ═════════════════════════════════════════════════════════════════════════════
# Survey adapter
# ═════════════════════════════════════════════════════════════════════════════

# Choice-bearing question types — the only ones that take a `choices` list.
_CHOICE_TYPES = ("mc_single", "mc_multi")


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


_SURVEY_METHODOLOGY = """Methodology contract for surveys (non-negotiable):
- Only these six question types exist: likert, mc_single, mc_multi, nps, \
open_text, short_text. If asked for MaxDiff, ranking, conjoint, or sliders, \
explain they are unsupported and offer the nearest sound alternative.
- Never write leading, double-barrelled, or unbalanced questions.
- If the researcher expects fewer than ~30 responses, do not pad the survey \
with fine-grained segmentation questions that cannot be cut at that n.
- Call `read_survey` first if you need the current state."""


_SURVEY_TOOLS = [
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
    remember_tool("survey"),
]


def _survey_run_tool(
    db: Session,
    company: Company,
    survey: Survey,
    turn: _Turn,
    name: str,
    tool_input: dict,
) -> str:
    """Execute a survey-surface tool. `remember` is handled by the core."""
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

    return f"Unknown tool: {name}"


def _survey_stub(survey: Survey, history: list[dict]) -> dict:
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


SURVEY_ADAPTER = CopilotAdapter(
    kind="survey",
    instrument_scope_kind="survey",
    instrument_memory_label="Memory for this survey",
    methodology=_SURVEY_METHODOLOGY,
    tools=_SURVEY_TOOLS,
    snapshot=_survey_snapshot,
    run_tool=_survey_run_tool,
    stub=_survey_stub,
    default_reply="Done — review the proposed changes in your question list.",
)
