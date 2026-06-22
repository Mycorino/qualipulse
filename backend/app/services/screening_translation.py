"""Screening-question translation via Claude.

Localizes screening question text + option labels into the 6 supported
participant languages so the qualification step is native. Mirrors
translation.py (batched Claude call, cached on the row, fire-and-forget).

The canonical `question`/`options` stay the source of truth AND the stable
identity for the disqualification gate — this only fills the display-only
`translations` JSON. Option labels are aligned by index to the canonical
options; if a model response doesn't line up, we keep the canonical labels.
"""
import json
import logging
import threading

from sqlalchemy.orm import Session

from app.models.project import Project, ScreeningQuestion
from app.services import ai_models
from app.services._clients import get_anthropic_client
from app.services.usage_logger import log_claude_usage

logger = logging.getLogger(__name__)

SUPPORTED_LANGS = ["en", "fr", "de", "es", "it", "pt"]
_LANG_NAMES = {
    "en": "English", "fr": "French", "de": "German",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese",
}


def schedule_screening_translation(project_id: str) -> None:
    """Spawn a daemon thread (fresh DB session) to translate a project's
    participant-facing copy (study name + screening questions) into all
    supported languages. Fire-and-forget — never blocks the request; a
    container shutdown won't hang on it."""
    def _run() -> None:
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            translate_project_name(project_id, db)
            translate_project_research_context(project_id, db)
            translate_project_screening(project_id, db)
        finally:
            db.close()
    threading.Thread(target=_run, daemon=True, name=f"screen-i18n-{project_id[:8]}").start()


def translate_project_screening(project_id: str, db: Session, langs: list[str] | None = None) -> None:
    """Fire-and-forget: ensure every screening question has translations for the
    supported languages. Never raises (safe for a background thread)."""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project is None or not project.screening_questions:
            return
        src = (project.language or "en").lower()[:2]
        for lang in (langs or SUPPORTED_LANGS):
            if lang != src:
                _ensure_lang(db, project, lang)
    except Exception:
        logger.exception("screening translation failed for project %s", project_id)


def ensure_screening_language(project: Project, lang: str, db: Session) -> None:
    """On-demand: make sure this project's screening questions are translated
    into `lang` (no-op if already present or lang is the source). Best-effort."""
    lang = (lang or "").lower()[:2]
    if not lang or lang not in _LANG_NAMES:
        return
    if lang == (project.language or "en").lower()[:2]:
        return
    try:
        _ensure_lang(db, project, lang)
    except Exception:
        logger.exception("on-demand screening translation failed (%s)", lang)


def _ensure_lang(db: Session, project: Project, lang: str) -> None:
    questions = list(project.screening_questions)
    pending = [q for q in questions if lang not in q.translations_dict and q.question.strip()]
    if not pending:
        return

    items = [{"id": q.id, "question": q.question, "options": q.options_list} for q in pending]
    target = _LANG_NAMES.get(lang, "English")
    prompt = f"""<role>
You translate market-research screening questions into {target} for survey participants.
Translate naturally and idiomatically — natural {target} a native speaker would read, not a
literal word-for-word rendering. Keep it concise and neutral.
</role>

<rules>
- Translate each question's text and EACH option label into {target}.
- Return the options in the SAME ORDER and the SAME COUNT as the input — one translated
  label per input option, index-aligned. Never add, drop, merge, or reorder options.
- If an item is already in {target}, return it unchanged.
- Do not add commentary.
</rules>

<input>
{json.dumps(items, ensure_ascii=False)}
</input>

Return ONLY a JSON array of the same length and order. Each item:
{{"id": "<id>", "question": "<translated>", "options": ["<translated option>", ...]}}"""

    client = get_anthropic_client(120.0)
    response = client.messages.create(
        model=ai_models.sonnet(),
        max_tokens=4096,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    log_claude_usage(
        db, response, "screening_translation",
        company_id=getattr(project, "company_id", None), project_id=project.id,
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```")).strip()
    parsed = json.loads(raw)
    by_id = {it["id"]: it for it in parsed if isinstance(it, dict) and "id" in it}

    for q in pending:
        item = by_id.get(q.id)
        if not item:
            continue
        canonical = q.options_list
        tr_opts = item.get("options") or []
        # Only keep translated labels when they line up 1:1 with the canonical
        # options; otherwise fall back to canonical (localized() handles gaps).
        opts = tr_opts if len(tr_opts) == len(canonical) else canonical
        d = q.translations_dict
        d[lang] = {"question": item.get("question") or q.question, "options": opts}
        q.translations = json.dumps(d, ensure_ascii=False)

    db.commit()


# ---------------------------------------------------------------------------
# Study name — participant-facing display only (canonical `name` is identity)
# ---------------------------------------------------------------------------

def translate_project_name(project_id: str, db: Session, langs: list[str] | None = None) -> None:
    """Fire-and-forget: ensure a project's study name has translations for the
    supported languages. Never raises (safe for a background thread)."""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project is None or not (project.name or "").strip():
            return
        src = (project.language or "en").lower()[:2]
        for lang in (langs or SUPPORTED_LANGS):
            if lang != src:
                _ensure_name_lang(db, project, lang)
    except Exception:
        logger.exception("study-name translation failed for project %s", project_id)


def ensure_study_name_language(project: Project, lang: str, db: Session) -> None:
    """On-demand: make sure this project's study name is translated into `lang`
    (no-op if already present or lang is the source). Best-effort."""
    lang = (lang or "").lower()[:2]
    if not lang or lang not in _LANG_NAMES:
        return
    if lang == (project.language or "en").lower()[:2]:
        return
    if lang in project.name_translations_dict:
        return
    try:
        _ensure_name_lang(db, project, lang)
    except Exception:
        logger.exception("on-demand study-name translation failed (%s)", lang)


def _ensure_name_lang(db: Session, project: Project, lang: str) -> None:
    if lang in project.name_translations_dict or not (project.name or "").strip():
        return
    target = _LANG_NAMES.get(lang, "English")
    prompt = f"""Translate this market-research study title into {target} for survey
participants. Keep it concise and natural — a title a native speaker would read,
not a literal word-for-word rendering. If it's already in {target}, return it
unchanged. Return ONLY the translated title, no quotes or commentary.

Title: {project.name}"""

    client = get_anthropic_client(60.0)
    response = client.messages.create(
        model=ai_models.sonnet(),
        max_tokens=200,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    log_claude_usage(
        db, response, "study_name_translation",
        company_id=getattr(project, "company_id", None), project_id=project.id,
    )
    translated = (response.content[0].text or "").strip().strip('"').strip()
    if not translated:
        return
    d = project.name_translations_dict
    d[lang] = translated
    project.name_translations = json.dumps(d, ensure_ascii=False)
    db.commit()


# ---------------------------------------------------------------------------
# Research context — participant-facing free text shown on the consent screen
# ---------------------------------------------------------------------------

def translate_project_research_context(project_id: str, db: Session, langs: list[str] | None = None) -> None:
    """Fire-and-forget: ensure a project's research context has translations for
    the supported languages. Never raises (safe for a background thread)."""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project is None or not (project.research_context or "").strip():
            return
        src = (project.language or "en").lower()[:2]
        for lang in (langs or SUPPORTED_LANGS):
            if lang != src:
                _ensure_research_context_lang(db, project, lang)
    except Exception:
        logger.exception("research-context translation failed for project %s", project_id)


def ensure_research_context_language(project: Project, lang: str, db: Session) -> None:
    """On-demand: make sure this project's research context is translated into
    `lang` (no-op if already present, lang is the source, or no context)."""
    lang = (lang or "").lower()[:2]
    if not lang or lang not in _LANG_NAMES:
        return
    if lang == (project.language or "en").lower()[:2]:
        return
    if not (project.research_context or "").strip():
        return
    if lang in project.research_context_translations_dict:
        return
    try:
        _ensure_research_context_lang(db, project, lang)
    except Exception:
        logger.exception("on-demand research-context translation failed (%s)", lang)


def _ensure_research_context_lang(db: Session, project: Project, lang: str) -> None:
    text = (project.research_context or "").strip()
    if not text or lang in project.research_context_translations_dict:
        return
    target = _LANG_NAMES.get(lang, "English")
    prompt = f"""Translate the following market-research context note into {target}
for survey participants. Keep it natural and faithful — natural {target} a native
speaker would read, preserving meaning and tone. If it's already in {target},
return it unchanged. Return ONLY the translated text, no quotes or commentary.

Text: {text}"""

    client = get_anthropic_client(60.0)
    response = client.messages.create(
        model=ai_models.sonnet(),
        max_tokens=1024,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    log_claude_usage(
        db, response, "research_context_translation",
        company_id=getattr(project, "company_id", None), project_id=project.id,
    )
    translated = (response.content[0].text or "").strip().strip('"').strip()
    if not translated:
        return
    d = project.research_context_translations_dict
    d[lang] = translated
    project.research_context_translations = json.dumps(d, ensure_ascii=False)
    db.commit()
