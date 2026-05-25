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
            # V2 capture — informs marketing attribution + sales positioning.
            "referral_source": company.referral_source or "",
            "current_tool": company.current_tool or "",
            # V3 capture — calibrates the agent's communication style
            # (first-time researcher needs scaffolding) and qualifies
            # the lead for sales (decision-maker vs evaluator).
            "research_experience": company.research_experience or "",
            "decision_role": company.decision_role or "",
        },
    }


_ONBOARDING_METHODOLOGY = """Onboarding contract (non-negotiable):

You are meeting this researcher for the FIRST time. This conversation is \
their first impression of the whole product — and the start of your \
memory of them. Get them from a blank workspace to a real first study.

═══════════════════════════════════════════════════════════════════════
TWO HARD RULES THAT OVERRIDE EVERYTHING ELSE:
═══════════════════════════════════════════════════════════════════════

RULE 1 — ONE QUESTION PER TURN. Never ask two questions in the same \
assistant turn, even if related. If two are needed, ask the higher- \
leverage one NOW and queue the other for the next turn. Bundling \
questions ("1. Quel canal... 2. Quelle décision...") is FORBIDDEN.

RULE 2 — EVERY DISCRETE QUESTION ATTACHES `suggest_replies`. A \
discrete question is one whose natural answer is one of a small enum: \
channels, timelines, decision types, success-criterion archetypes, \
audience segments. Chip set = 3-5 short options + an "Other"/"Autre" \
escape (match the user's locale). Free-text ONLY for genuinely open \
questions (research goal, success-criterion wording, study objective).

CANONICAL CHIP SETS for common framing questions (adapt to the user's \
product surfaces and locale):
  • Channels: [In-station kiosks, Mobile app, Website, End-to-end \
journey, Other]
  • Decision types: [Rebuild a specific channel, Prioritise an \
improvement backlog, Justify an investment, Validate or kill a \
concept, Other]
  • Timelines: [2 weeks, 1 month, 1 quarter, No deadline]
  • Audience archetypes: [Daily power users, Occasional users, Lapsed \
users, Brand-new prospects, Other]
  • Success-criterion (RESEARCH outcomes, NOT product KPIs — see \
section below): [Ranked friction list with evidence, Clear decision: \
rebuild vs iterate, Quotes I can cite in the deck, User mental models \
I can segment by, Other]

EXAMPLE — BAD (rejected): "Deux choses : 1. Quel canal... 2. Quelle \
décision..." (no chips, two questions stacked).
EXAMPLE — GOOD: "Quel canal voulez-vous creuser en priorité ?" + \
suggest_replies [Distributeurs en station, Appli mobile, Site web, \
Parcours end-to-end, Autre]. Decision question goes in the NEXT turn.

═══════════════════════════════════════════════════════════════════════
RESEARCH SUCCESS CRITERIA — RESEARCH outcomes, NOT business KPIs:
═══════════════════════════════════════════════════════════════════════

When asking "how will you know this research delivered?", chips MUST \
be about evidence + decisions, NOT business metrics. Conversion lift, \
NPS, CSAT, ticket reduction are outcomes of the PRODUCT CHANGE the \
research informs — they happen months later. The study itself can't \
move them, so they're the wrong success criterion for the research.

If the user volunteers a KPI ("we want to lift conversion 10%"), \
acknowledge then redirect: "That'll be the proof later — but for the \
research itself to count as delivered, what evidence will you walk \
away with?" Then surface the canonical success-criterion chip set.

═══════════════════════════════════════════════════════════════════════
THE REST OF THE FLOW:
═══════════════════════════════════════════════════════════════════════

- The welcome screen has ALREADY introduced you and asked the opening \
question — "what's the most important thing you need to learn about your \
users right now?". The researcher's first message is their answer to it. \
Do NOT re-introduce yourself or re-ask the opening question; engage with \
their answer directly. Never ask company-profile questions first.
- HYBRID ONBOARDING — a 3-step structured wizard runs BEFORE this \
conversation. By the time you're called, the snapshot already has \
``profile.role``, ``profile.company_size``, ``profile.use_case``, and \
often ``profile.decision_role`` populated. NEVER re-ask for these — in \
your FIRST reply, reference what you already know naturally ("Got it — \
a {role} at a {company_size} {industry} company, focused on {use_case}…") \
and then dive straight into the research goal. Skipping the redundant \
capture is what makes the hybrid feel premium instead of bureaucratic.
- HARD CAP: at most 4 exchanges before you call `propose_study`. If the \
researcher is vague or unsure, offer 3 concrete example goals to pick \
from rather than interrogating them.
- IMMEDIATELY after the researcher's FIRST message (i.e. in your second \
turn overall), call `propose_participant_demo` to offer them an \
iPhone-framed preview of what their participants will experience. \
Engage briefly with their goal first ("Great starting point — onboarding \
drop-off is a rich area"), then surface the demo card with a warm \
lead-in. This is the wow moment of the entire flow — call it exactly \
once and call it early. After the user dismisses or completes the demo, \
pick up where you left off with profile capture + study draft.
- In exchange 2 or 3 — once you've engaged with their goal but before \
proposing — plant ONE short value beat that distinguishes this product \
from a survey tool. Something like: *"Most teams would send a survey \
here — but voice interviews surface the why, not just the what. The \
follow-ups are where the real insight lives."* One line, not a pitch. \
This is the only marketing you do in the whole conversation.
- STRATEGIC CONTEXT (non-optional) — before proposing, you MUST have \
captured: (1) the **decision** the researcher needs to make (e.g. \
"rebuild onboarding vs polish"), (2) the **timeline** for that \
decision (e.g. "decision in 2 weeks"), and (3) the **success \
criterion** they'll use to know the research helped. These three plus \
the audience description go into `propose_study` and drive every \
downstream personalisation. If the user gives you a goal but no \
decision, briefly ask: *"What's the decision that hangs on this?"* — \
do NOT propose a study until you have it. Same for timeline: if \
missing, ask "When do you need to land this?" with a chip set \
(*2 weeks · 1 month · 1 quarter · No deadline*). Same for success \
criterion: *"How will you know this research delivered?"*
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
- If the snapshot's ``profile.business_summary`` is ALREADY populated, \
we pre-fetched it from the email domain at signup. In that case, do \
NOT call `request_website`. Instead, reference what you know naturally \
in your second message — e.g. *"I see you're at {company} — that's \
helpful context for the study."* Don't recite the summary verbatim, \
just show you read it. This is the highest-leverage trust moment.
- If the snapshot's ``profile.business_summary`` is EMPTY (gmail / \
free-text signup / prefetch missed), you MUST call `request_website` \
exactly once between exchange 2 and exchange 3 — never zero times. The \
card lets the user paste a URL and we'll read it; if they decline, \
they can describe their company in chat instead. Don't propose a study \
before you have at least the chat-described version of what their \
company does.
- Also capture four LIGHTWEIGHT signals naturally during the \
conversation, with `suggest_replies` chips: (1) **how they found us** \
— `referral_source` [Google, LinkedIn, Colleague, Other]; (2) **what \
they use today for research** — `current_tool` [SurveyMonkey, Typeform, \
User interviews on my own, Nothing yet, Other]; (3) **how experienced \
they are** — `research_experience` [First study, A few past projects, \
Seasoned researcher]; (4) **whether the decision is theirs** — \
`decision_role` [I'll decide, I'm helping someone decide, Just \
exploring]. Combine into TWO light questions max ("How did you find us, \
and what do you use today?" then "Quick context — is this your first \
project, and is the decision yours?") so it doesn't feel like a form.
- Once `research_experience` is captured, adapt your communication \
style: first-time researchers need brief explanations of why each \
question matters ("interviews surface the *why*, not the *what*"); \
seasoned researchers want you to be terse and get to the proposal \
faster. Don't repeat this calibration aloud — just use it.
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
            "referral_source": {
                "type": "string",
                "description": (
                    "How the researcher found us. Use the canonical "
                    "set (Google / LinkedIn / Colleague / Other) when "
                    "the user picks from chips; pass their free-text "
                    "answer otherwise."
                ),
            },
            "current_tool": {
                "type": "string",
                "description": (
                    "What they use today for research, if anything. "
                    "Canonical chips: SurveyMonkey / Typeform / User "
                    "interviews on my own / Nothing yet / Other."
                ),
            },
            "research_experience": {
                "type": "string",
                "description": (
                    "How experienced they are at running research. "
                    "Canonical chips: First study / A few past "
                    "projects / Seasoned researcher. Drives the "
                    "agent's communication style going forward."
                ),
            },
            "decision_role": {
                "type": "string",
                "description": (
                    "Who's making the call on what to do with the "
                    "research findings. Canonical chips: I'll decide / "
                    "I'm helping someone decide / Just exploring. "
                    "Critical sales / CSM qualification signal."
                ),
            },
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
            "recommended_participants": {
                "type": "integer",
                "description": (
                    "Suggested number of participants for this first "
                    "study, based on team size. The server will "
                    "normalise this value against the captured "
                    "company_size — use 10 for solo, 25 for small "
                    "teams, 50 for mid-market, 100 for enterprise. "
                    "If you're unsure, omit and the server will pick."
                ),
            },
            "decision_to_inform": {
                "type": "string",
                "description": (
                    "The concrete business decision the research will "
                    "feed into — e.g. 'rebuild onboarding vs polish' "
                    "or 'kill or scale feature X'. Captured from the "
                    "conversation. Required."
                ),
            },
            "timeline": {
                "type": "string",
                "description": (
                    "When the researcher needs to land the decision. "
                    "Canonical chips: '2 weeks', '1 month', "
                    "'1 quarter', 'No deadline'."
                ),
            },
            "success_criteria": {
                "type": "string",
                "description": (
                    "How they'll know the research delivered — e.g. "
                    "'trial-to-paid lifts by 5 points' or 'leadership "
                    "signs off on the redesign'. Captured from the "
                    "conversation. Anchors the analysis output later."
                ),
            },
            "target_customer_description": {
                "type": "string",
                "description": (
                    "Who they need to interview — e.g. 'lapsed trial "
                    "users from the last 60 days' or 'PMs at 50-200 "
                    "person companies'. Drives recruitment guidance."
                ),
            },
        },
        "required": [
            "study_name",
            "objective",
            "questions",
            "decision_to_inform",
        ],
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
        "'Other'\n"
        "- referral_source: 'Google', 'LinkedIn', 'Colleague', 'Other'\n"
        "- current_tool: 'SurveyMonkey', 'Typeform', 'User interviews "
        "on my own', 'Nothing yet', 'Other'\n"
        "- timeline: '2 weeks', '1 month', '1 quarter', 'No deadline'\n"
        "- research_experience: 'First study', 'A few past projects', "
        "'Seasoned researcher'\n"
        "- decision_role: 'I'll decide', 'I'm helping someone decide', "
        "'Just exploring'\n\n"
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
                    "referral_source",
                    "current_tool",
                    "timeline",
                    "research_experience",
                    "decision_role",
                    "custom",
                ],
                "description": (
                    "What the chips answer. Use the matching key for "
                    "profile or strategic-context questions; 'custom' "
                    "for everything else."
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

_PROPOSE_PARTICIPANT_DEMO_TOOL = {
    "name": "propose_participant_demo",
    "description": (
        "Surface an iPhone-framed demo modal showing the researcher "
        "what their participants will experience. The user records a "
        "20-30s answer to a meta-question ('best onboarding you had '"
        "recently'), then sees their own transcript with a highlighted "
        "quote + code tag — exactly what they'll see for real "
        "interviews. Call this AT MOST ONCE per onboarding, after the "
        "user has shared their research goal but BEFORE you start "
        "asking for profile fields. It is the wow moment — don't skip "
        "it. The user can decline; the modal has a skip path."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intro": {
                "type": "string",
                "description": (
                    "One-line lead-in shown above the demo card in the "
                    "chat, e.g. 'Before I draft your study, want to "
                    "see what this will feel like for your "
                    "participants?'"
                ),
            },
        },
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
    _PROPOSE_PARTICIPANT_DEMO_TOOL,
    remember_tool("company"),
]

_PROFILE_FIELDS = (
    "role",
    "company_size",
    "industry",
    "use_case",
    "referral_source",
    "current_tool",
    "research_experience",
    "decision_role",
)

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
    "referral_source": [
        "Google",
        "LinkedIn",
        "Colleague",
        "Other",
    ],
    "current_tool": [
        "SurveyMonkey",
        "Typeform",
        "User interviews on my own",
        "Nothing yet",
        "Other",
    ],
    "timeline": [
        "2 weeks",
        "1 month",
        "1 quarter",
        "No deadline",
    ],
    "research_experience": [
        "First study",
        "A few past projects",
        "Seasoned researcher",
    ],
    "decision_role": [
        "I'll decide",
        "I'm helping someone decide",
        "Just exploring",
    ],
}

# Recommended participant N per company-size bucket. The agent can emit
# its own `recommended_participants` but the server normalises it to the
# bucket so the suggestion stays predictable across sessions — same
# two-layer pattern as the canonical chip sets.
_RECOMMENDED_N_BY_SIZE: dict[str, int] = {
    "1–10": 10,
    "11–50": 25,
    "51–200": 50,
    "201–1000": 75,
    "1000+": 100,
}
_DEFAULT_RECOMMENDED_N = 20


def _recommended_participants_for(company: Company | None) -> int:
    """Pick the recommended N based on captured company_size. Falls back
    to a safe mid-bucket value when nothing's captured yet."""
    if company is None:
        return _DEFAULT_RECOMMENDED_N
    size = (company.company_size or "").strip()
    return _RECOMMENDED_N_BY_SIZE.get(size, _DEFAULT_RECOMMENDED_N)


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
        # Normalise the recommended N: if the captured company_size maps
        # to a bucket, that wins over whatever the model emitted (same
        # two-layer pattern as the canonical chips). Otherwise honour
        # the model's value, clamped to a sane range.
        size_recommended = _recommended_participants_for(company)
        captured_size = (
            (company.company_size or "").strip() if company is not None else ""
        )
        model_recommended = tool_input.get("recommended_participants")
        if captured_size in _RECOMMENDED_N_BY_SIZE:
            recommended_n = size_recommended
        elif isinstance(model_recommended, int) and 5 <= model_recommended <= 500:
            recommended_n = model_recommended
        else:
            recommended_n = _DEFAULT_RECOMMENDED_N
        turn.actions.append(
            {
                "type": "create_first_study",
                "study_name": study_name,
                "objective": objective,
                "questions": questions,
                "rationale": (tool_input.get("rationale") or "").strip(),
                "recommended_participants": recommended_n,
                "decision_to_inform": (
                    tool_input.get("decision_to_inform") or ""
                ).strip(),
                "timeline": (tool_input.get("timeline") or "").strip(),
                "success_criteria": (
                    tool_input.get("success_criteria") or ""
                ).strip(),
                "target_customer_description": (
                    tool_input.get("target_customer_description") or ""
                ).strip(),
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

    if name == "propose_participant_demo":
        turn.actions.append(
            {
                "type": "propose_participant_demo",
                "intro": (
                    tool_input.get("intro")
                    or "Before I draft your study — want to see what your "
                    "participants will experience? Takes 30 seconds."
                ).strip(),
            }
        )
        return "Attached a participant-demo card to this turn."

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
                "decision_to_inform": "Whether to proceed, refine, or pivot.",
                "timeline": "No deadline",
                "success_criteria": (
                    "Clear themes across at least 5 participants."
                ),
                "target_customer_description": "Recent users of the experience.",
                "rationale": "Every study needs a clear objective to anchor the guide.",
                "recommended_participants": _recommended_participants_for(company),
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
