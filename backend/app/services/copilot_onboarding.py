"""Research Copilot — onboarding surface.

The new researcher's first conversation with the copilot. Instead of a
4-step form, the agent introduces itself, asks a couple of sharp
questions, records the profile, and proposes a real first study.

The "instrument" for this surface is the Company itself — the agent core
(``copilot.py``) is generic enough to run on it once ``_system_prompt``
tolerates an instrument with no ``study_id`` (it does).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.company import Company
from app.services.copilot import CopilotAdapter, remember_tool


def _onboarding_snapshot(company: Company) -> dict:
    """What the agent knows about the new researcher so far."""
    return {
        "first_name": company.first_name or company.name,
        "email_verified": company.email_verified,
        "profile": {
            "role": company.role or "",
            "company_size": company.company_size or "",
            "industry": company.industry or "",
            "use_case": company.use_case or "",
        },
    }


_ONBOARDING_METHODOLOGY = """Onboarding contract (non-negotiable):

You are meeting this researcher for the FIRST time. This conversation is \
their first impression of the whole product — and the start of your \
memory of them. Get them from a blank workspace to a real first study.

- The welcome screen has ALREADY introduced you and asked the opening \
question — "what's the most important thing you need to learn about your \
users right now?". The researcher's first message is their answer to it. \
Do NOT re-introduce yourself or re-ask the opening question; engage with \
their answer directly. Never ask company-profile questions first.
- HARD CAP: at most 3 exchanges before you call `propose_study`. If the \
researcher is vague or unsure, offer 3 concrete example goals to pick \
from rather than interrogating them.
- Weave the profile in naturally — ask their role and company as ONE \
light question, not a form. Call `save_profile` as you learn role, \
company size, industry, or use case. It saves directly; it is not a card.
- Call `remember` (scope "company") to durably record their research \
goal, audience, and what their company does — this is the memory you \
will carry into every future session.
- Then call `propose_study`: a study name, a sharp decision-oriented \
objective (one sentence), and a lean 5-7 question grand-tour interview \
guide. Open, non-leading questions; one idea each; broad context \
questions first. This is the one proposal card — make it genuinely good.
- If the researcher says they are just exploring or truly do not know \
what to research, do NOT force a study — say so and suggest they start \
from the worked example instead.

Be concise and warm. Three exchanges, then a real study on screen."""


_SAVE_PROFILE_TOOL = {
    "name": "save_profile",
    "description": (
        "Record what you've learned about the researcher and their "
        "company — role, company size, industry, and what they'll use "
        "QualiPulse for. Call it as you learn these in conversation. It "
        "saves directly to their profile; it is not a proposal card."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "role": {"type": "string"},
            "company_size": {"type": "string"},
            "industry": {"type": "string"},
            "use_case": {"type": "string"},
        },
    },
}

_PROPOSE_STUDY_TOOL = {
    "name": "propose_study",
    "description": (
        "Propose the researcher's first study — a name, a sharp research "
        "objective, and a starter interview guide. Staged as a single "
        "card the researcher accepts to create it for real."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "study_name": {"type": "string"},
            "objective": {
                "type": "string",
                "description": "One sharp, decision-oriented sentence.",
            },
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_title": {"type": "string"},
                        "main_question": {"type": "string"},
                        "desired_learning": {
                            "type": "string",
                            "description": "What this question is meant to surface.",
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": [
                        "section_title",
                        "main_question",
                        "desired_learning",
                        "rationale",
                    ],
                },
            },
            "rationale": {"type": "string"},
        },
        "required": ["study_name", "objective", "questions"],
    },
}

_ONBOARDING_TOOLS = [_SAVE_PROFILE_TOOL, _PROPOSE_STUDY_TOOL, remember_tool("company")]

_PROFILE_FIELDS = ("role", "company_size", "industry", "use_case")


def _onboarding_run_tool(
    db: Session,
    company: Company,
    instrument,  # the Company — same object as `company`
    turn,
    name: str,
    tool_input: dict,
) -> str:
    """Execute an onboarding tool. `remember` is handled by the core."""
    if name == "save_profile":
        saved = []
        for field in _PROFILE_FIELDS:
            value = (tool_input.get(field) or "").strip()
            if value:
                setattr(company, field, value)
                saved.append(field)
        if saved:
            db.commit()
            return f"Saved to the researcher's profile: {', '.join(saved)}."
        return "Nothing to save — no profile fields provided."

    if name == "propose_study":
        study_name = (tool_input.get("study_name") or "").strip()
        objective = (tool_input.get("objective") or "").strip()
        questions = []
        for q in tool_input.get("questions", []):
            section = (q.get("section_title") or "").strip()
            main = (q.get("main_question") or "").strip()
            if not section or not main:
                continue
            questions.append(
                {
                    "section_title": section,
                    "main_question": main,
                    "desired_learning": (q.get("desired_learning") or "").strip(),
                    "rationale": (q.get("rationale") or "").strip(),
                }
            )
        if not study_name or not objective or not questions:
            return "A study needs a name, an objective, and at least one question."
        turn.actions.append(
            {
                "type": "create_first_study",
                "study_name": study_name,
                "objective": objective,
                "questions": questions,
                "rationale": (tool_input.get("rationale") or "").strip(),
            }
        )
        return f"Proposed the first study with {len(questions)} question(s)."

    return f"Unknown tool: {name}"


def _onboarding_stub(company: Company, history: list[dict]) -> dict:
    """Deterministic offline onboarding — works with no API key (and tests)."""
    return {
        "reply": (
            "(Offline stub — set ANTHROPIC_API_KEY for the real copilot.) "
            "Here's a starter study to get you going — accept it to make it "
            "real, or tell me what you'd rather research."
        ),
        "proposed_actions": [
            {
                "type": "create_first_study",
                "study_name": "My first research study",
                "objective": (
                    "Understand how this audience makes the decision at the "
                    "centre of your research, and what drives or blocks it."
                ),
                "rationale": "Every study needs a clear objective to anchor the guide.",
                "questions": [
                    {
                        "section_title": "Background",
                        "main_question": (
                            "To start, tell me a bit about how this fits into "
                            "your day-to-day."
                        ),
                        "desired_learning": (
                            "Context and the participant's relationship to the topic."
                        ),
                        "rationale": "A warm grand-tour opener before narrower questions.",
                    },
                    {
                        "section_title": "Experience",
                        "main_question": (
                            "Walk me through the last time you did this — what "
                            "happened?"
                        ),
                        "desired_learning": (
                            "A concrete, recent story rather than generalities."
                        ),
                        "rationale": "Specific-incident questions surface real behaviour.",
                    },
                ],
            }
        ],
        "memory_updated": False,
    }


ONBOARDING_ADAPTER = CopilotAdapter(
    kind="onboarding",
    instrument_scope_kind="company",
    instrument_memory_label="Memory for this workspace",
    methodology=_ONBOARDING_METHODOLOGY,
    tools=_ONBOARDING_TOOLS,
    snapshot=_onboarding_snapshot,
    run_tool=_onboarding_run_tool,
    stub=_onboarding_stub,
    default_reply="Let's get your first study set up.",
)
