"""AI research assistant endpoints — powers the project creation wizard."""

import json

import anthropic
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.services.business_context import company_context_block
from app.services.templates import match_templates_for_company
from app.services.usage_logger import log_claude_usage

router = APIRouter(prefix="/research", tags=["research"])

LANGUAGES = {
    "en": "English", "fr": "French", "es": "Spanish", "de": "German",
    "it": "Italian", "pt": "Portuguese", "nl": "Dutch",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
}


def _claude(max_tokens: int = 1024) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        return "\n".join(lines).strip()
    return text


def _business_context(company: Company) -> str:
    """Build a business context prefix to personalise AI suggestions.

    Delegates to the shared ``company_context_block`` helper so analysis.py
    and research_assistant.py always see the same grounding.
    """
    return company_context_block(company)


def _resolve_language(body_language: str | None, company: Company) -> str:
    """Pick the language to use for an AI generation.

    Order of precedence:
      1. ``language`` explicitly supplied in the request body (the wizard's
         language picker — lets users override their account default)
      2. ``company.preferred_language`` (set at signup or in account settings)
      3. ``"en"`` as a final fallback

    Returns a 2-letter ISO code that's guaranteed to be a key in ``LANGUAGES``.
    """
    candidates = [body_language, getattr(company, "preferred_language", None), "en"]
    for candidate in candidates:
        if candidate and isinstance(candidate, str):
            code = candidate.strip().lower()[:2]
            if code in LANGUAGES:
                return code
    return "en"


def _language_directive(language: str) -> str:
    """Build the "Respond in X" instruction we paste into Claude prompts.

    Returns an empty string for English so we don't bloat the prompt with
    a no-op directive on the default path.
    """
    if language == "en":
        return ""
    lang_name = LANGUAGES.get(language, "English")
    return (
        f"IMPORTANT: Respond entirely in {lang_name}. All prose, all JSON "
        f"string values, every word the user will read must be in "
        f"{lang_name}. JSON keys stay in English."
    )


# ---------------------------------------------------------------------------
# POST /research/parse-brief
# ---------------------------------------------------------------------------

@router.post("/parse-brief")
async def parse_brief(
    context: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Extract text from uploaded files and return a structured brief summary."""
    file_contents: list[str] = []
    for f in files:
        name = f.filename or ""
        if name.lower().endswith((".txt", ".md", ".csv")):
            raw = await f.read()
            text = raw.decode("utf-8", errors="ignore")[:4000]
            file_contents.append(f"--- {name} ---\n{text}")

    if not context.strip() and not file_contents:
        return {"summary": ""}

    combined = context.strip()
    if file_contents:
        combined += "\n\nUPLOADED DOCUMENTS:\n" + "\n\n".join(file_contents)

    biz_ctx = _business_context(company)
    language = _resolve_language(None, company)
    lang_directive = _language_directive(language)
    response = _claude(512).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        temperature=0.3,
        messages=[{
            "role": "user",
            "content": (
                f"{biz_ctx}"
                "You are a senior UX researcher. Read the following project brief and "
                "summarise the key business context in 2-3 sentences. Focus on: what "
                "the business does, what problem they want to understand, and what "
                "decision this research will inform.\n\n"
                f"BRIEF:\n{combined}\n\n"
                f"{lang_directive}\n"
                "Return ONLY the summary text, no headers or labels."
            ),
        }],
    )
    log_claude_usage(db, response, "research", company_id=company.id)
    return {"summary": response.content[0].text.strip()}


# ---------------------------------------------------------------------------
# POST /research/suggest-objective
# ---------------------------------------------------------------------------

@router.post("/suggest-objective")
def suggest_objective(
    body: dict,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Generate a sharp research objective and learning goals from project context."""
    context = body.get("context", "")
    brief_summary = body.get("brief_summary", "")
    combined = "\n\n".join(filter(None, [brief_summary, context]))

    if not combined.strip():
        return {
            "objective": "",
            "learning_goals": ["", "", ""],
            "study_type": "exploratory",
            "rationale": "",
        }

    biz_ctx = _business_context(company)
    language = _resolve_language(body.get("language"), company)
    lang_directive = _language_directive(language)
    response = _claude(1024).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        temperature=0.7,
        messages=[{
            "role": "user",
            "content": (
                f"{biz_ctx}"
                "You are a senior product researcher with expertise in Jobs-to-be-Done "
                "and qualitative research design.\n\n"
                "Based on the following project context, propose a sharp research "
                "objective and exactly 3 secondary learning goals. The objective must be:\n"
                "- Specific enough to know when it's been answered\n"
                "- Focused on human behaviour and motivations, not just opinions\n"
                "- Grounded in what decisions the research will inform\n"
                "- Realistic for 5–8 qualitative voice interviews of 20–30 minutes\n\n"
                f"PROJECT CONTEXT:\n{combined}\n\n"
                f"{lang_directive}\n"
                "Return ONLY a JSON object with this exact structure:\n"
                '{"objective": "one clear sentence","learning_goals": ["goal 1","goal 2","goal 3"],'
                '"study_type": "exploratory|evaluative|generative",'
                '"rationale": "2 sentences explaining why this framing yields the most useful insights"}'
            ),
        }],
    )

    log_claude_usage(db, response, "research", company_id=company.id)
    return json.loads(_strip_fences(response.content[0].text.strip()))


# ---------------------------------------------------------------------------
# POST /research/suggest-scope
# ---------------------------------------------------------------------------

@router.post("/suggest-scope")
def suggest_scope(
    body: dict,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Recommend audience, duration, language, and participant count from the objective."""
    objective = body.get("objective", "")
    learning_goals = body.get("learning_goals", [])
    context = body.get("context", "")
    language = _resolve_language(body.get("language"), company)

    if not objective.strip():
        return {
            "audience": "",
            "duration_minutes": 20,
            "language": language,
            "participant_count": 6,
        }

    goals_str = "\n".join(f"- {g}" for g in learning_goals if g)

    biz_ctx = _business_context(company)
    lang_directive = _language_directive(language)
    response = _claude(512).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        temperature=0.5,
        messages=[{
            "role": "user",
            "content": (
                f"{biz_ctx}"
                "You are a senior UX researcher. Given this research objective, recommend "
                "the ideal study scope.\n\n"
                f"OBJECTIVE: {objective}\n"
                f"LEARNING GOALS:\n{goals_str}\n"
                f"ADDITIONAL CONTEXT: {context or 'none'}\n\n"
                f"{lang_directive}\n"
                "Return ONLY a JSON object:\n"
                '{"audience": "brief profile of ideal participant (1-2 sentences)",'
                '"duration_minutes": 20 or 30 or 45,'
                f'"language": "{language}",'
                '"participant_count": 5 or 6 or 8,'
                '"audience_rationale": "one sentence why this audience"}'
            ),
        }],
    )

    log_claude_usage(db, response, "research", company_id=company.id)
    return json.loads(_strip_fences(response.content[0].text.strip()))


# ---------------------------------------------------------------------------
# POST /research/suggest-questions
# ---------------------------------------------------------------------------

@router.post("/suggest-questions")
def suggest_questions(
    body: dict,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Generate a full structured interview guide from objective and scope."""
    objective = body.get("objective", "")
    learning_goals: list[str] = body.get("learning_goals", [])
    audience = body.get("audience", "")
    duration_minutes = body.get("duration_minutes", 20)
    language = _resolve_language(body.get("language"), company)
    context = body.get("context", "")

    lang_name = LANGUAGES.get(language, "English")
    goals_str = "\n".join(f"- {g}" for g in learning_goals if g)
    lang_instruction = (
        f"Write ALL question text, section titles, interview_notes, and "
        f"desired_learning fields in {lang_name}. JSON keys stay in English."
        if language != "en"
        else ""
    )

    biz_ctx = _business_context(company)
    response = _claude(2048).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        temperature=0.6,
        messages=[{
            "role": "user",
            "content": (
                f"{biz_ctx}"
                "You are a senior qualitative researcher. Design a voice interview guide "
                "following best product research practices.\n\n"
                f"RESEARCH OBJECTIVE: {objective}\n"
                f"LEARNING GOALS:\n{goals_str}\n"
                f"TARGET AUDIENCE: {audience or 'general users'}\n"
                f"INTERVIEW DURATION: {duration_minutes} minutes\n"
                f"ADDITIONAL CONTEXT: {context or 'none'}\n"
                f"{lang_instruction}\n\n"
                "Rules:\n"
                "- Open-ended questions only (never yes/no)\n"
                "- Avoid 'why' — use 'what led you to', 'walk me through', 'tell me about'\n"
                "- Funnel from broad to specific within each section\n"
                "- Start with a warm-up section to build rapport\n"
                "- Each section: 1-2 questions max to stay within time\n"
                "- Every question must directly serve a learning goal\n"
                "- interview_notes: practical probing tips for the interviewer\n"
                "- desired_learning: what insight this question aims to uncover\n\n"
                "Return ONLY a JSON array:\n"
                '[{"section_index":0,"section_title":"Section Name","question_index":0,'
                '"main_question":"The question","interview_notes":"Probing tips",'
                '"desired_learning":"What insight this uncovers"}]'
            ),
        }],
    )

    log_claude_usage(db, response, "research", company_id=company.id)
    questions = json.loads(_strip_fences(response.content[0].text.strip()))
    return {"questions": questions}


# ---------------------------------------------------------------------------
# POST /research/refine-question
# ---------------------------------------------------------------------------
#
# Scoped, non-destructive AI refinement of a single guide question.
#
# The entire point of this endpoint is that refining Q5 never touches Q1-Q4
# or Q6+. We enforce that at the contract level: the request accepts a
# single question object, and the response returns a single refined
# question object. There is no list parameter on the way out — a well-
# behaved client literally cannot get sibling questions back by calling
# this endpoint, which is the guarantee researchers kept asking for.
#
# The surrounding guide (objective, learning goals, audience, the full
# list of other questions) is passed *into* the prompt so Claude can keep
# the refined question coherent with the rest of the study, but that
# context is read-only — Claude is instructed not to suggest changes to
# anything else, and even if it did we wouldn't propagate them because we
# only pluck the one refined question out of the response.
#
# The frontend is responsible for "undo": it snapshots the original
# question before calling this endpoint and swaps back if the researcher
# dislikes the refinement.

@router.post("/refine-question")
def refine_question(
    body: dict,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Refine a single interview guide question without touching its siblings.

    Expected body shape::

        {
          "question": {
            "section_title": str,
            "main_question": str,
            "interview_notes": str,
            "desired_learning": str
          },
          "question_index": int,           # 0-based position in the full guide
          "objective": str,                # research objective for context
          "learning_goals": list[str],     # learning goals for context
          "audience": str,                 # target audience for context
          "all_questions": list[{          # read-only siblings for coherence
            "section_title": str,
            "main_question": str
          }],
          "language": str | None,          # project language (overrides account)
          "instruction": str | None        # optional user steering
        }

    Returns::

        {
          "refined": { ...same shape as input question... },
          "rationale": "Short explanation of what changed and why."
        }
    """
    question = body.get("question") or {}
    if not isinstance(question, dict) or not question.get("main_question", "").strip():
        # Nothing to refine — don't burn a Claude call.
        return {
            "refined": question,
            "rationale": "",
        }

    question_index = body.get("question_index", 0)
    objective = (body.get("objective") or "").strip()
    learning_goals = body.get("learning_goals") or []
    audience = (body.get("audience") or "").strip()
    all_questions = body.get("all_questions") or []
    user_instruction = (body.get("instruction") or "").strip()

    language = _resolve_language(body.get("language"), company)
    lang_directive = _language_directive(language)

    # Build a compact read-only view of the other questions so Claude can
    # keep the refined question coherent (no duplicates, no gaps) without
    # being tempted to rewrite them. We deliberately omit interview_notes
    # and desired_learning from the siblings — they're noise for this call
    # and every extra token makes the refinement slower + costlier.
    siblings_view_lines: list[str] = []
    for idx, q in enumerate(all_questions):
        if not isinstance(q, dict):
            continue
        marker = "→ THIS ONE" if idx == question_index else "  "
        section = (q.get("section_title") or "").strip() or "—"
        main = (q.get("main_question") or "").strip() or "(empty)"
        siblings_view_lines.append(f"{marker} [{idx + 1}] ({section}) {main}")
    siblings_view = "\n".join(siblings_view_lines) or "(no other questions yet)"

    goals_str = "\n".join(f"- {g}" for g in learning_goals if g) or "(none)"

    # Default steering when the researcher clicks "Refine" without typing
    # anything: the most common ask is "make it sharper and less leading".
    default_instruction = (
        "Make it sharper: more open-ended, less leading, better suited to "
        "eliciting a concrete story or example. Preserve the original intent "
        "(what the researcher was trying to learn) — don't pivot the topic."
    )
    instruction_block = user_instruction or default_instruction

    biz_ctx = _business_context(company)
    response = _claude(1024).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        temperature=0.6,
        messages=[{
            "role": "user",
            "content": (
                f"{biz_ctx}"
                "You are a senior qualitative researcher helping polish ONE "
                "question in an interview guide. The rest of the guide is "
                "shown only as context — you MUST NOT suggest changes to any "
                "other question. Your entire output is a refined version of "
                "the single target question.\n\n"
                f"RESEARCH OBJECTIVE: {objective or '(not set)'}\n"
                f"LEARNING GOALS:\n{goals_str}\n"
                f"TARGET AUDIENCE: {audience or '(not set)'}\n\n"
                "FULL GUIDE (read-only, for coherence):\n"
                f"{siblings_view}\n\n"
                "TARGET QUESTION (the one you are refining):\n"
                f"  Section: {question.get('section_title') or '(none)'}\n"
                f"  Main:    {question.get('main_question') or ''}\n"
                f"  Notes:   {question.get('interview_notes') or '(none)'}\n"
                f"  Learning: {question.get('desired_learning') or '(none)'}\n\n"
                f"INSTRUCTION: {instruction_block}\n\n"
                "Rules you MUST follow:\n"
                "- Open-ended only — never yes/no.\n"
                "- Avoid 'why' — prefer 'walk me through', 'tell me about', "
                "'what led you to'.\n"
                "- Don't duplicate what another question in the guide "
                "already asks.\n"
                "- Keep the same section_title unless the topic genuinely "
                "belongs elsewhere (rare — err on the side of keeping it).\n"
                "- interview_notes: 1-2 practical probes the interviewer "
                "can use as follow-ups.\n"
                "- desired_learning: one sentence on what insight this "
                "question is trying to uncover.\n"
                "- rationale: a short explanation for the researcher with "
                "three parts: (1) what was wrong with the original phrasing, "
                "(2) how the refinement fixes it, (3) which learning goal it "
                "now better serves. Use the format: 'Problem: … → Fix: … "
                "(serves: …)'. Keep it to 1-2 sentences.\n\n"
                f"{lang_directive}\n"
                "Return ONLY a JSON object with this exact shape:\n"
                '{"refined":{"section_title":"...","main_question":"...",'
                '"interview_notes":"...","desired_learning":"..."},'
                '"rationale":"..."}'
            ),
        }],
    )

    log_claude_usage(db, response, "research", company_id=company.id)
    parsed = json.loads(_strip_fences(response.content[0].text.strip()))

    # Defence in depth: even if Claude ignored the instructions and tried
    # to return extra fields, we only ever pluck the single refined
    # question back out. There is no code path where sibling data could
    # leak through this endpoint.
    refined = parsed.get("refined") or {}
    return {
        "refined": {
            "section_title": refined.get("section_title") or question.get("section_title", ""),
            "main_question": refined.get("main_question") or question.get("main_question", ""),
            "interview_notes": refined.get("interview_notes") or "",
            "desired_learning": refined.get("desired_learning") or "",
        },
        "rationale": (parsed.get("rationale") or "").strip(),
    }


# ---------------------------------------------------------------------------
# GET /research/recommended-studies
# ---------------------------------------------------------------------------
#
# Personalised Dashboard card: given what the company told us during
# onboarding (goals classification, product stage, customer type), return the
# top N templates that make sense for them *right now*, with human-readable
# reasons so the UI can show why each one matched.
#
# No Claude call — this is a deterministic scoring pass on the templates
# metadata (see ``match_templates_for_company``). That keeps it cheap enough
# to call on every Dashboard render.

@router.get("/recommended-studies")
def recommended_studies(
    company: Company = Depends(get_current_company),
    limit: int = 3,
):
    """Return the top templates that match this company's onboarding profile.

    Shape mirrors ``/templates`` so the Dashboard can reuse the same card
    component, plus a ``reasons`` array explaining the match and a
    ``match_score`` for debugging.
    """
    # Cap the limit so the endpoint can't be abused to fetch everything.
    limit = max(1, min(int(limit or 3), 6))
    matches = match_templates_for_company(
        company,
        limit=limit,
        lang=getattr(company, "preferred_language", None),
    )
    return {
        "recommendations": [
            {
                "id": t["id"],
                "name": t["name"],
                "category": t["category"],
                "icon": t["icon"],
                "description": t["description"],
                "best_for": t["best_for"],
                "duration_minutes": t["duration_minutes"],
                "question_count": len(t["questions"]),
                "has_screening": len(t["screening_questions"]) > 0,
                "reasons": reasons,
                "match_score": score,
            }
            for (t, score, reasons) in matches
        ],
        # Expose whether the match was personalised or a generic fallback so
        # the UI can reword the header ("Recommended for you" vs "Popular
        # starting points") without having to re-derive from match scores.
        "personalised": any(score > 0 for (_, score, _) in matches),
    }
