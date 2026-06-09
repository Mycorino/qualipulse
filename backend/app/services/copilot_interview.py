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
from app.models.study import Study
from app.models.survey import Survey, SurveyResponse
from app.services.copilot import CopilotAdapter, remember_tool
from app.services.segment_discoveries import compute_discoveries


def _live_guide(project: Project) -> list:
    return sorted(
        [q for q in project.guide_questions if q.deprecated_at is None],
        key=lambda q: (q.section_index, q.question_index),
    )


def _guide_snapshot(project: Project) -> dict:
    """Compact JSON view of the whole interview-round setup — guide,
    framing, the configurable settings, and the screener — fed to the
    model every turn so it can SEE what already exists (and never re-ask
    or blindly propose a duplicate)."""
    active_links = sum(1 for link in project.interview_links if link.is_active)
    return {
        "name": project.name,
        "language": project.language,
        "research_objective": project.research_objective or "",
        "research_context": project.research_context or "",
        "decision_to_inform": project.decision_to_inform or "",
        "timeline": project.timeline or "",
        "success_criteria": project.success_criteria or "",
        "target_customer_description": project.target_customer_description or "",
        # Configurable settings the copilot can recommend + change.
        "settings": {
            "interview_duration_minutes": project.interview_duration_minutes,
            "target_participants": project.target_participants,
            "warmup_enabled": project.warmup_enabled,
        },
        # The screener — runs BEFORE the interview to filter who gets in.
        # `[]` means there is no screener yet.
        "screening_questions": [
            {
                "id": sq.id,
                "question": sq.question,
                "options": sq.options_list,
                "disqualifying_options": sq.disqualifying_options_list,
            }
            for sq in sorted(project.screening_questions, key=lambda s: s.sort_order)
        ],
        "interview_links": {
            "total": len(list(project.interview_links)),
            "active": active_links,
        },
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


def _study_snapshot(db: Session, project: Project) -> dict:
    """The rest of the Study this interview round belongs to — sibling
    surveys (questions, response counts, findings) and other interview
    rounds. Lets the copilot act as the deep-dive arm of a mixed-methods
    study instead of cold-starting."""
    study = (
        db.query(Study).filter(Study.id == project.study_id).first()
        if project.study_id
        else None
    )
    if study is None:
        return {"surveys": [], "interview_rounds": []}

    surveys: list[dict] = []
    for s in study.surveys:
        if s.archived_at is not None:
            continue
        completed = (
            db.query(SurveyResponse)
            .filter(
                SurveyResponse.survey_id == s.id,
                SurveyResponse.completed_at.isnot(None),
            )
            .count()
        )
        entry: dict = {
            "name": s.name,
            "role": s.role,
            "status": s.status,
            "completed_responses": completed,
            "questions": [
                q.prompt for q in s.questions if q.deprecated_at is None
            ],
        }
        # The survey's findings — what the interviews should dig into.
        if completed > 0:
            try:
                entry["findings"] = [
                    {
                        "title": d.title,
                        "detail": d.description,
                        "confidence": d.confidence,
                    }
                    for d in compute_discoveries(db, s)[:5]
                ]
            except Exception:  # noqa: BLE001 — findings are best-effort
                entry["findings"] = []
        surveys.append(entry)

    rounds = [
        {"name": p.name}
        for p in study.projects
        if p.id != project.id and p.archived_at is None
    ]
    return {"study_name": study.name, "surveys": surveys, "interview_rounds": rounds}


# ── Results: reading this round's conducted interviews + analysis ────────────

_TRANSCRIPT_BUDGET = 9000  # chars per single transcript fed to the model


def _progress_snapshot(project: Project) -> dict:
    """Counts + quality spread for this round's interviews."""
    parts = list(project.participants)
    completed = [p for p in parts if p.status == "completed"]
    spread: dict[str, int] = {}
    for p in completed:
        label = p.quality_label or "unrated"
        spread[label] = spread.get(label, 0) + 1
    return {
        "completed_interviews": len(completed),
        "in_progress": sum(1 for p in parts if p.status == "in_progress"),
        "quality_spread": spread,
        "has_analysis": any(a.status == "ready" for a in project.analyses),
    }


def _interviews_index(project: Project) -> list[dict]:
    """Compact per-participant index — NO transcript text. The copilot
    reads full transcripts on demand via read_interview."""
    return [
        {
            "id": p.id,
            "name": p.display_name or "(anonymous)",
            "profession": p.profession,
            "age_range": p.age_range,
            "country": p.country,
            "quality": p.quality_label,
            "turns": len(list(p.turns)),
        }
        for p in project.participants
        if p.status == "completed"
    ]


def _one_interview(project: Project, participant_id: str) -> dict:
    """One full transcript, truncated to a char budget."""
    p = next((x for x in project.participants if x.id == participant_id), None)
    if p is None:
        return {"error": "No completed interview with that id in this round."}
    parts: list[str] = []
    total = 0
    for t in sorted(p.turns, key=lambda t: t.turn_index):
        if not t.response_transcript:
            continue
        block = f"Q: {t.question_text}\nA: {t.response_transcript}"
        if total + len(block) > _TRANSCRIPT_BUDGET:
            parts.append("[… transcript truncated …]")
            break
        parts.append(block)
        total += len(block)
    return {
        "name": p.display_name or "(anonymous)",
        "segments": {
            "profession": p.profession,
            "age_range": p.age_range,
            "country": p.country,
        },
        "quality": p.quality_label,
        "transcript": "\n\n".join(parts),
    }


def _analysis_snapshot(project: Project) -> dict:
    """The latest ready AI analysis report for this round."""
    ready = sorted(
        (a for a in project.analyses if a.status == "ready"),
        key=lambda a: a.version,
        reverse=True,
    )
    if not ready:
        return {"status": "none"}
    latest = ready[0]
    try:
        report = json.loads(latest.report) if latest.report else {}
    except (json.JSONDecodeError, TypeError):
        report = {}
    return {"status": "ready", "version": latest.version, "report": report}


_INTERVIEW_METHODOLOGY = """Methodology contract for interview guides \
(non-negotiable):

DISCOVERY FIRST — understand the problem before you propose anything:
- Ask ONE question per turn (two only if they are genuinely inseparable). \
NEVER bundle a numbered list of questions ("1. Who... 2. Which decision... \
3. How many...") into a single turn — that is forbidden.
- After each answer, ask a SHARPER follow-up on the same thread until the \
real problem is clear — what decision rides on this, who exactly they \
need to hear from, and what would change their mind. Keep probing up to \
THREE exchanges; do not propose a guide on turn one.
- Once it IS clear (or after ~3 exchanges), STOP asking and propose — \
objective first, then the guide. Don't interrogate forever.
- Open easy: ground your first question in what you already know (the \
snapshot, the study, the survey) instead of a cold generic prompt.

- Call `read_study` EARLY. If this study already has a survey, you are \
the deep-dive arm of a mixed-methods study: ground the guide in the \
survey's questions and findings, and do not ask the researcher what the \
survey already establishes. Open by referencing what the survey shows and \
propose a guide that digs into the "why" behind it.
- If the research objective is empty, propose one FIRST with \
`propose_objective` — a single sharp, decision-oriented sentence — before \
drafting questions. Use the research context if it is provided.

SETTINGS — you can see them in the snapshot under `settings`, and you can \
recommend AND change them with `propose_settings`:
- Match interview LENGTH to depth: an in-depth qualitative interview runs \
45-60 min; a focused discovery interview 20-30 min; a quick reaction \
check 10-15 min. If the researcher wants depth, recommend ~60 min and set \
it — don't leave it at the default.
- Recommend a SAMPLE SIZE (`target_participants`) grounded in the goal: \
~6-10 for early discovery, ~12-20 to reach saturation across a couple of \
segments. Say WHY ("with two segments, ~12 gets you saturation"), then \
set it. Be interactive — react to what they tell you and adjust.
- Only propose a setting CHANGE when it differs from the current value, \
and always explain the trade-off in your reply before the researcher \
accepts.

SCREENING — the snapshot's `screening_questions` shows the current \
screener (`[]` = none yet):
- The screener runs BEFORE the interview to filter who gets in; it is NOT \
part of the interview guide. Closed, factual questions (have they done X, \
how often, role, recency) with disqualifying options for wrong-fit \
profiles. Never put rating scales or open narrative there.
- When fit matters and there is no screener, propose 2-4 screening \
questions with `propose_screening_questions` and flag which options \
disqualify. Don't silently assume a screener exists — check the snapshot.

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
- Call `read_guide` first if you need the current state.

When the researcher asks about RESULTS (what the interviews found, who \
said what, what to do next):
- Call `read_progress` first to see how much data exists. With a small n \
(say under 5 interviews) be explicit that findings are directional, not \
conclusive — never report a count as a rate or imply statistical weight.
- Use `read_interviews` to scan the index, then `read_interview` to read \
specific transcripts before making any claim about a participant.
- If an AI analysis exists, `read_analysis` gives you themes with \
confidence scores — respect those scores and do not upgrade a \
low-confidence theme into a certainty.
- Quote participants verbatim from the transcript; never paraphrase a \
quote into something they did not say. Attribute quotes to the segment \
(profession/age/country), not just a name.
- Keep observation separate from recommendation: state what the data \
shows, then — clearly flagged as your suggestion — what the researcher \
might do next. Do not present an inference as a finding.
- You can move the work forward: when enough interviews are in and no \
analysis exists yet, offer `propose_run_analysis`. When a ready analysis \
exists and the researcher has annotated themes or you have spotted gaps, \
offer `propose_refine_analysis`. Always explain why in the rationale and \
let the researcher accept — never imply it has already run."""


_INTERVIEW_TOOLS = [
    {
        "name": "read_guide",
        "description": "Return the interview guide's sections and questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_study",
        "description": (
            "Return the rest of this Study — sibling surveys (their "
            "questions, response counts, and findings) and other interview "
            "rounds. Use it to ground the guide in what's already known."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_progress",
        "description": (
            "Return how many interviews this round has collected — completed "
            "and in-progress counts, the quality spread, and whether an AI "
            "analysis already exists. Call this first when asked about "
            "results."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_interviews",
        "description": (
            "Return a compact index of every completed interview in this "
            "round — id, name, segments (profession/age/country), quality "
            "label, turn count. NO transcript text. Use read_interview to "
            "read one in full."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_interview",
        "description": (
            "Return one completed interview's full transcript (Q/A turns), "
            "segments, and quality. Get the participant_id from "
            "read_interviews."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "participant_id": {"type": "string"},
            },
            "required": ["participant_id"],
        },
    },
    {
        "name": "read_analysis",
        "description": (
            "Return the latest ready AI analysis report for this round — "
            "themes, JTBDs, tensions, recommendations with confidence "
            "scores. Returns status 'none' if no analysis has been run."
        ),
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
    {
        "name": "propose_settings",
        "description": (
            "Propose changing this interview round's settings — interview "
            "length, target sample size, and/or the opening warm-up. Staged "
            "for the researcher to accept. Only include the fields you are "
            "actually changing, and only when they differ from the current "
            "values in the snapshot."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "interview_duration_minutes": {
                    "type": "integer",
                    "description": "Target length of each interview, in minutes.",
                },
                "target_participants": {
                    "type": "integer",
                    "description": "How many completed interviews to aim for.",
                },
                "warmup_enabled": {
                    "type": "boolean",
                    "description": "Open with a light warm-up question before the guide.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why these values fit the research goal.",
                },
            },
            "required": ["rationale"],
        },
    },
    {
        "name": "propose_screening_questions",
        "description": (
            "Propose screening questions that run BEFORE the interview to "
            "filter who qualifies. Staged for the researcher to accept — not "
            "added directly. Use closed, factual questions and mark which "
            "options disqualify. Check the snapshot first so you don't "
            "duplicate an existing screener."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "The closed answer choices.",
                            },
                            "disqualifying_options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Subset of options that screen the "
                                    "participant OUT."
                                ),
                            },
                            "rationale": {"type": "string"},
                        },
                        "required": ["question", "options"],
                    },
                }
            },
            "required": ["questions"],
        },
    },
    {
        "name": "propose_run_analysis",
        "description": (
            "Propose running the AI analysis pipeline over this round's "
            "completed interviews — synthesises themes, JTBDs, tensions, and "
            "recommendations. Staged for the researcher to accept. Only "
            "propose this when interviews have been completed (check "
            "read_progress first)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rationale": {
                    "type": "string",
                    "description": "Why now — e.g. enough interviews collected.",
                },
            },
            "required": ["rationale"],
        },
    },
    {
        "name": "propose_refine_analysis",
        "description": (
            "Propose a refined analysis pass that re-synthesises using the "
            "researcher's theme annotations and context. Staged for the "
            "researcher to accept. Only propose this when a ready analysis "
            "already exists (check read_analysis first)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rationale": {"type": "string"},
            },
            "required": ["rationale"],
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

    if name == "read_study":
        return json.dumps(_study_snapshot(db, project), ensure_ascii=False)

    if name == "read_progress":
        return json.dumps(_progress_snapshot(project), ensure_ascii=False)

    if name == "read_interviews":
        return json.dumps(_interviews_index(project), ensure_ascii=False)

    if name == "read_interview":
        return json.dumps(
            _one_interview(project, tool_input.get("participant_id") or ""),
            ensure_ascii=False,
        )

    if name == "read_analysis":
        return json.dumps(_analysis_snapshot(project), ensure_ascii=False)

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

    if name == "propose_settings":
        settings: dict = {}
        if tool_input.get("interview_duration_minutes") is not None:
            try:
                settings["interview_duration_minutes"] = int(
                    tool_input["interview_duration_minutes"]
                )
            except (TypeError, ValueError):
                pass
        if tool_input.get("target_participants") is not None:
            try:
                settings["target_participants"] = int(
                    tool_input["target_participants"]
                )
            except (TypeError, ValueError):
                pass
        if tool_input.get("warmup_enabled") is not None:
            settings["warmup_enabled"] = bool(tool_input["warmup_enabled"])
        if not settings:
            return "No settings to change were provided. Not recorded."
        turn.actions.append(
            {
                "type": "edit_settings",
                "settings": settings,
                "rationale": (tool_input.get("rationale") or "").strip(),
            }
        )
        return "Recorded the proposed settings change."

    if name == "propose_screening_questions":
        added = 0
        for q in tool_input.get("questions", []):
            question = (q.get("question") or "").strip()
            if not question:
                continue
            options = [
                str(o).strip()
                for o in (q.get("options") or [])
                if str(o).strip()
            ]
            disqualifying = [
                d for d in (q.get("disqualifying_options") or []) if d in options
            ]
            turn.actions.append(
                {
                    "type": "add_screening_question",
                    "screening": {
                        "question": question,
                        "options": options,
                        "disqualifying_options": disqualifying,
                        "rationale": (q.get("rationale") or "").strip(),
                    },
                }
            )
            added += 1
        return f"Recorded {added} proposed screening question(s) for review."

    if name == "propose_run_analysis":
        progress = _progress_snapshot(project)
        if progress["completed_interviews"] == 0:
            return (
                "No completed interviews yet — analysis needs data. "
                "Not recorded."
            )
        turn.actions.append(
            {
                "type": "run_analysis",
                "rationale": (tool_input.get("rationale") or "").strip(),
            }
        )
        return "Recorded the proposed analysis run."

    if name == "propose_refine_analysis":
        if _analysis_snapshot(project)["status"] != "ready":
            return (
                "No ready analysis to refine — run the analysis first. "
                "Not recorded."
            )
        turn.actions.append(
            {
                "type": "refine_analysis",
                "rationale": (tool_input.get("rationale") or "").strip(),
            }
        )
        return "Recorded the proposed refined-analysis run."

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
