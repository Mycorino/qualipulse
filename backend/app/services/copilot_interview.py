"""Research Copilot — interview-guide adapter.

The interview-guide surface: a Project's interview guide. Reuses the
surface-agnostic agent core in ``copilot.py`` — this module only supplies
the snapshot, tools, methodology contract, tool executor, and stub.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.project import Project
from app.services.copilot import CopilotAdapter, remember_tool


def _live_guide(project: Project) -> list:
    return sorted(
        [q for q in project.guide_questions if q.deprecated_at is None],
        key=lambda q: (q.section_index, q.question_index),
    )


def _guide_snapshot(project: Project) -> dict:
    """Compact JSON view of the interview guide — fed to the model."""
    return {
        "name": project.name,
        "language": project.language,
        "research_objective": project.research_objective or "",
        "research_context": project.research_context or "",
        "questions": [
            {
                "id": q.id,
                "section": q.section_title,
                "main_question": q.main_question,
                "desired_learning": q.desired_learning or "",
            }
            for q in _live_guide(project)
        ],
    }


_INTERVIEW_METHODOLOGY = """Methodology contract for interview guides \
(non-negotiable):
- If the research objective is empty, propose one FIRST with \
`propose_objective` — a single sharp, decision-oriented sentence — before \
drafting questions. Use the research context if it is provided.
- Questions must be OPEN and non-leading — "Tell me about..." / "Walk me \
through..." not "Don't you think...".
- One idea per question — never double-barrelled.
- Grand-tour sequencing: broad, easy context questions first; narrow or \
sensitive ones later. Group related questions into named sections.
- Keep it lean: ~5-8 main questions for a 20-30 minute interview. Depth \
comes from the live AI interviewer's adaptive follow-up probes, not from \
piling on main questions — if asked for many more, push back.
- Every question needs a `desired_learning`: what it is meant to surface.
- Rating scales, NPS, and multiple-choice belong in a SURVEY, not an \
interview guide. If the researcher wants to quantify something, say so and \
suggest adding a survey to the study instead.
- Call `read_guide` first if you need the current state."""


_INTERVIEW_TOOLS = [
    {
        "name": "read_guide",
        "description": "Return the interview guide's sections and questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "propose_objective",
        "description": (
            "Propose the research objective for this interview round — a "
            "sharp, decision-oriented sentence. Staged for the researcher "
            "to accept."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["objective", "rationale"],
        },
    },
    {
        "name": "propose_guide_questions",
        "description": (
            "Propose new interview-guide questions to add. Staged for the "
            "researcher to accept — not added directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
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
                }
            },
            "required": ["questions"],
        },
    },
    {
        "name": "edit_guide_question",
        "description": "Propose an edit to an existing guide question (by id).",
        "input_schema": {
            "type": "object",
            "properties": {
                "question_id": {"type": "string"},
                "new_main_question": {"type": "string"},
                "new_desired_learning": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["question_id", "rationale"],
        },
    },
    {
        "name": "remove_guide_question",
        "description": "Propose removing an existing guide question (by id).",
        "input_schema": {
            "type": "object",
            "properties": {
                "question_id": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["question_id", "rationale"],
        },
    },
    remember_tool("project"),
]


def _guide_run_tool(
    db: Session,
    company: Company,
    project: Project,
    turn,
    name: str,
    tool_input: dict,
) -> str:
    """Execute an interview-guide tool. `remember` is handled by the core."""
    if name == "read_guide":
        return json.dumps(_guide_snapshot(project), ensure_ascii=False)

    if name == "propose_objective":
        objective = (tool_input.get("objective") or "").strip()
        if not objective:
            return "No objective text provided."
        turn.actions.append(
            {
                "type": "edit_objective",
                "new_objective": objective,
                "rationale": (tool_input.get("rationale") or "").strip(),
            }
        )
        return "Recorded the proposed research objective."

    if name == "propose_guide_questions":
        added = 0
        for q in tool_input.get("questions", []):
            section = (q.get("section_title") or "").strip()
            main = (q.get("main_question") or "").strip()
            if not section or not main:
                continue
            turn.actions.append(
                {
                    "type": "add_guide_question",
                    "question": {
                        "section_title": section,
                        "main_question": main,
                        "desired_learning": (q.get("desired_learning") or "").strip(),
                        "rationale": (q.get("rationale") or "").strip(),
                    },
                }
            )
            added += 1
        return f"Recorded {added} proposed guide question(s) for review."

    if name == "edit_guide_question":
        action: dict = {
            "type": "edit_guide_question",
            "question_id": tool_input.get("question_id"),
            "rationale": (tool_input.get("rationale") or "").strip(),
        }
        if tool_input.get("new_main_question"):
            action["new_main_question"] = tool_input["new_main_question"].strip()
        if tool_input.get("new_desired_learning"):
            action["new_desired_learning"] = tool_input["new_desired_learning"].strip()
        turn.actions.append(action)
        return "Recorded the proposed edit."

    if name == "remove_guide_question":
        turn.actions.append(
            {
                "type": "remove_guide_question",
                "question_id": tool_input.get("question_id"),
                "rationale": (tool_input.get("rationale") or "").strip(),
            }
        )
        return "Recorded the proposed removal."

    return f"Unknown tool: {name}"


def _guide_stub(project: Project, history: list[dict]) -> dict:
    """Deterministic offline response so the UI + tests work without an API key."""
    if _live_guide(project):
        return {
            "reply": (
                "(Offline stub — set ANTHROPIC_API_KEY for the real copilot.) "
                "Tell me what you'd like to change and I'll propose guide edits."
            ),
            "proposed_actions": [],
            "memory_updated": False,
        }
    proposed: list[dict] = []
    if not (project.research_objective or "").strip():
        proposed.append(
            {
                "type": "edit_objective",
                "new_objective": (
                    "Understand how this audience makes the decision at the "
                    "centre of this study, and what drives or blocks it."
                ),
                "rationale": "Every interview round needs a clear objective to anchor the guide.",
            }
        )
    return {
        "reply": (
            "(Offline stub — set ANTHROPIC_API_KEY for the real copilot.) "
            "Here is a starting objective and two interview questions to review."
        ),
        "proposed_actions": proposed
        + [
            {
                "type": "add_guide_question",
                "question": {
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
            },
            {
                "type": "add_guide_question",
                "question": {
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
            },
        ],
        "memory_updated": False,
    }


INTERVIEW_ADAPTER = CopilotAdapter(
    kind="interview",
    instrument_scope_kind="project",
    instrument_memory_label="Memory for this interview round",
    methodology=_INTERVIEW_METHODOLOGY,
    tools=_INTERVIEW_TOOLS,
    snapshot=_guide_snapshot,
    run_tool=_guide_run_tool,
    stub=_guide_stub,
    default_reply="Done — review the proposed changes in your interview guide.",
)
