"""AI research assistant endpoints — powers the project creation wizard."""

import json

import anthropic
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.models.company import Company
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
    """Build a business context prefix to personalise AI suggestions."""
    parts = []
    if company.business_summary:
        parts.append(f"Context about this researcher's business: {company.business_summary}")
    if company.primary_region:
        parts.append(f"Their primary market: {company.primary_region}")
    if not parts:
        return ""
    parts.append("Use this context to make suggestions more specific and relevant to their business.")
    return "\n".join(parts) + "\n\n"


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
    response = _claude(512).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"{biz_ctx}"
                "You are a senior UX researcher. Read the following project brief and "
                "summarise the key business context in 2-3 sentences. Focus on: what "
                "the business does, what problem they want to understand, and what "
                "decision this research will inform.\n\n"
                f"BRIEF:\n{combined}\n\n"
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
    response = _claude(1024).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
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

    if not objective.strip():
        return {"audience": "", "duration_minutes": 20, "language": "en", "participant_count": 6}

    goals_str = "\n".join(f"- {g}" for g in learning_goals if g)

    biz_ctx = _business_context(company)
    response = _claude(512).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"{biz_ctx}"
                "You are a senior UX researcher. Given this research objective, recommend "
                "the ideal study scope.\n\n"
                f"OBJECTIVE: {objective}\n"
                f"LEARNING GOALS:\n{goals_str}\n"
                f"ADDITIONAL CONTEXT: {context or 'none'}\n\n"
                "Return ONLY a JSON object:\n"
                '{"audience": "brief profile of ideal participant (1-2 sentences)",'
                '"duration_minutes": 20 or 30 or 45,'
                '"language": "en",'
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
    language = body.get("language", "en")
    context = body.get("context", "")

    lang_name = LANGUAGES.get(language, "English")
    goals_str = "\n".join(f"- {g}" for g in learning_goals if g)
    lang_instruction = f"Write ALL question text in {lang_name}." if language != "en" else ""

    biz_ctx = _business_context(company)
    response = _claude(2048).messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
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
