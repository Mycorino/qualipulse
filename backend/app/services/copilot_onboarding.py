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
            "website_url": company.website_url or "",
            "business_summary": (company.business_summary or "")[:600],
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
- For profile questions (role, team size, industry, use case) you MUST \
also call `suggest_replies` with the canonical option set listed in that \
tool's description — same labels every time, so the UI is predictable. \
The user can still type freely if none fit; always include "Other" as \
the last chip. For non-profile discrete questions, invent 3-5 short \
options of your own. Never call `suggest_replies` for open free-text \
questions (the opening research goal, study objective, etc.).
- When you want to know about their company, call `request_website` \
instead of asking them to describe it from scratch. The user can paste a \
URL and we'll read their site for you. Use this AT MOST ONCE per \
onboarding, and only after they've answered the opening research goal.
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

_SUGGEST_REPLIES_TOOL = {
    "name": "suggest_replies",
    "description": (
        "Attach short tap-to-answer chips under your current message. "
        "The user can still type freely — chips are a shortcut. Always "
        "include 'Other' as the last chip.\n\n"
        "For profile questions, USE THESE CANONICAL OPTIONS verbatim "
        "(same labels every time so the UI is predictable):\n"
        "- role: 'Product Manager', 'UX Researcher', 'Designer', "
        "'Founder / CEO', 'Marketing', 'Other'\n"
        "- company_size: '1–10', '11–50', '51–200', '201–1000', "
        "'1000+', 'Other'\n"
        "- industry: 'SaaS / Tech', 'E-commerce / Retail', 'Financial "
        "services', 'Healthcare', 'Consumer goods', 'Media / Education', "
        "'Other'\n"
        "- use_case: 'Product discovery', 'Concept testing', "
        "'Onboarding research', 'Brand / messaging', 'Usability', "
        "'Other'\n\n"
        "For other discrete questions, invent 3-5 short options yourself."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "context": {
                "type": "string",
                "enum": [
                    "role",
                    "company_size",
                    "industry",
                    "use_case",
                    "custom",
                ],
                "description": (
                    "What the chips answer. Use the matching key for "
                    "profile questions; 'custom' for everything else."
                ),
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-6 short answer chips. Each ≤ 40 chars.",
            },
        },
        "required": ["context", "options"],
    },
}

_REQUEST_WEBSITE_TOOL = {
    "name": "request_website",
    "description": (
        "Surface a website-lookup card under your current message. The "
        "user pastes their company URL and we'll read the site to fill in "
        "what their company does. Use this instead of asking them to "
        "describe their company from scratch. At most once per onboarding."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "Short label for the card — e.g. 'Drop in your "
                    "company URL and I'll take a look.'"
                ),
            },
        },
    },
}

_ONBOARDING_TOOLS = [
    _SAVE_PROFILE_TOOL,
    _PROPOSE_STUDY_TOOL,
    _SUGGEST_REPLIES_TOOL,
    _REQUEST_WEBSITE_TOOL,
    remember_tool("company"),
]

_PROFILE_FIELDS = ("role", "company_size", "industry", "use_case")

# Canonical chip sets. These are enforced server-side whenever the agent
# calls `suggest_replies` with a profile `context`, so the UI is identical
# every time regardless of what the model happened to emit.
_CANONICAL_REPLIES: dict[str, list[str]] = {
    "role": [
        "Product Manager",
        "UX Researcher",
        "Designer",
        "Founder / CEO",
        "Marketing",
        "Other",
    ],
    "company_size": [
        "1–10",
        "11–50",
        "51–200",
        "201–1000",
        "1000+",
        "Other",
    ],
    "industry": [
        "SaaS / Tech",
        "E-commerce / Retail",
        "Financial services",
        "Healthcare",
        "Consumer goods",
        "Media / Education",
        "Other",
    ],
    "use_case": [
        "Product discovery",
        "Concept testing",
        "Onboarding research",
        "Brand / messaging",
        "Usability",
        "Other",
    ],
}


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

    if name == "suggest_replies":
        context = (tool_input.get("context") or "").strip()
        # For the four profile questions, ignore what the model emitted
        # and use the canonical set — UI is then identical every time.
        if context in _CANONICAL_REPLIES:
            options = list(_CANONICAL_REPLIES[context])
        else:
            options = [
                (opt or "").strip()
                for opt in (tool_input.get("options") or [])
                if (opt or "").strip()
            ][:6]
            # Always finish a custom set with "Other" so the user has a
            # clear escape hatch.
            if options and "Other" not in options and "other" not in options:
                options.append("Other")
        if not options:
            return "No chip options provided — skipping."
        turn.actions.append(
            {
                "type": "suggest_replies",
                "context": context,
                "options": options,
            }
        )
        return f"Attached {len(options)} reply chip(s) to this turn."

    if name == "request_website":
        turn.actions.append(
            {
                "type": "request_website",
                "prompt": (
                    tool_input.get("prompt")
                    or "Paste your company URL and I'll take a quick look."
                ).strip(),
            }
        )
        return "Attached a website-lookup card to this turn."

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
