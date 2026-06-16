"""Core interview engine: orchestrates STT, Claude decision-making, and TTS."""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

import anthropic
import httpx

from app.services._clients import get_anthropic_client
from sqlalchemy.orm import Session

from app.config import settings
from app.models.interview import InterviewTurn, Participant
from app.models.panel import PanelProfile
from app.models.project import InterviewGuideQuestion, Project
from app.services.stt import transcribe_audio
from app.services.storage import upload_audio, download_audio
from app.services.tts import generate_speech
from app.services.usage_logger import log_claude_usage, log_stt_usage, log_tts_usage


class EmptyTranscriptError(Exception):
    """Raised when Whisper returns no speech in the participant's recording."""


INTERVIEWER_SYSTEM_PROMPT = """\
You are a senior qualitative interviewer running a live voice interview. You speak like a \
warm, curious peer — not a survey script and not a therapist. You are time-bounded and the \
participant can hear silence; aim for one focused question at a time.

Voice & stance:
- Express genuine interest in what the participant just said. Be brief — they speak more when you speak less.
- Stay neutral. Never approve or disapprove of an answer.
- Use the participant's own words and terminology. Mirror their language register.
- Avoid "why" questions — they invite rationalisation. Prefer "walk me through", "tell me about \
the last time", "what was happening when".
- Single concept per question. No double-barrelled questions, no preambles longer than one sentence.

Decision rules (you MUST output one of three actions):

1. follow_up — ask a probing question that stays on the current topic. Choose this when ANY of:
   - The answer was <40 words AND the topic is not yet exhausted.
   - The participant introduced a concrete claim, story, or emotion that needs unpacking ("it was frustrating", \
"we just stopped using it", "the team pushed back").
   - You heard a generic answer ("it's fine", "it works") that hasn't surfaced behaviour or example.
   - Pacing is on-track or ahead.

2. next_question — move to the next guide question. Choose this when ANY of:
   - The current topic has yielded a concrete example or behaviour AND you have nothing sharper to ask.
   - Pacing is behind (the host system will tell you).
   - You have already asked 2 follow-ups on this topic without new information.
   When transitioning, OPEN with a one-sentence callback to something specific the participant \
just said (use their exact words where natural), THEN introduce the new topic. This makes them feel heard.

3. close — wrap up warmly. ONLY available when the host system tells you the close gate is open \
(time-used ≥ 80% AND all main questions covered, OR time-used ≥ 95%). If the host says close is \
NOT available, you MUST NOT return "close" no matter how exhausted the conversation feels.

Output: ONE JSON object, nothing else:
{"action": "follow_up" | "next_question" | "close", "question": "<the question text the participant will hear>"}
"""

# Human-readable language names for prompting Claude. Keep in sync with the
# LANGUAGES list in frontend/src/pages/CreateProjectWizard.tsx
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese (Mandarin)",
}


CLOSING_MESSAGES: dict[str, str] = {
    "en": "That wraps up our interview. Thank you so much for your time and thoughtful responses — it's been really helpful!",
    "fr": "Voilà qui conclut notre entretien. Merci beaucoup pour votre temps et vos réponses — cela nous a été précieux !",
    "es": "Con esto cerramos la entrevista. Muchas gracias por su tiempo y sus respuestas — ha sido muy útil.",
    "de": "Damit beenden wir unser Interview. Vielen Dank für Ihre Zeit und Ihre durchdachten Antworten — das war sehr hilfreich!",
    "it": "Con questo concludiamo la nostra intervista. Grazie mille per il suo tempo e le sue risposte — è stato davvero utile!",
    "pt": "Com isto encerramos a entrevista. Muito obrigado pelo seu tempo e pelas suas respostas — foi muito útil!",
    "nl": "Daarmee sluiten we dit interview af. Heel erg bedankt voor uw tijd en doordachte antwoorden — het was enorm behulpzaam!",
    "ja": "以上でインタビューは終了です。お時間を割いて丁寧にお答えいただき、本当にありがとうございました。",
    "ko": "이것으로 인터뷰를 마치겠습니다. 시간을 내어 성의 있게 답해 주셔서 정말 감사합니다.",
    "zh": "我们的访谈到此结束。非常感谢您抽出宝贵时间并认真回答，这对我们非常有帮助！",
}


def _closing_message(language_code: str | None) -> str:
    code = (language_code or "en").lower()
    return CLOSING_MESSAGES.get(code, CLOSING_MESSAGES["en"])


def _language_instruction(language_code: str | None) -> str:
    """Build a short system-prompt suffix telling Claude what language to use.

    The interview guide may be written in one language while the project
    language is another — the project language is the source of truth for
    how the AI interviewer should speak. Whisper transcribes responses
    automatically; we don't need to translate those back.
    """
    code = (language_code or "en").lower()
    name = LANGUAGE_NAMES.get(code, "English")
    if code == "en":
        return ""  # default, no extra instruction
    return (
        f"\n\nIMPORTANT — Language: You MUST conduct this entire interview in {name}. "
        f"Ask every question in {name}, even if the interview guide questions are "
        f"written in another language (translate them naturally as you go). "
        f"If the participant replies in a different language, gently continue in {name} "
        f"unless they explicitly ask to switch. Keep your tone warm and idiomatic — "
        f"use natural {name} phrasing, not literal translations."
    )


def _build_interview_guide_str(project: Project) -> str:
    """Build a formatted string representation of the interview guide.

    Skips questions that have been deprecated by the researcher.
    """
    guide_questions: list[InterviewGuideQuestion] = sorted(
        [q for q in project.guide_questions if not getattr(q, "deprecated_at", None)],
        key=lambda q: (q.section_index, q.question_index),
    )
    if not guide_questions:
        return "(No interview guide questions configured.)"

    lines: list[str] = []
    current_section = -1
    for q in guide_questions:
        if q.section_index != current_section:
            current_section = q.section_index
            lines.append(f"\n## Section {q.section_index}: {q.section_title}")
        lines.append(f"  Q{q.question_index}: {q.main_question}")
        if q.interview_notes:
            lines.append(f"    Notes: {q.interview_notes}")
        if q.desired_learning:
            lines.append(f"    Desired learning: {q.desired_learning}")
    return "\n".join(lines)


def _build_conversation_history(turns: list[InterviewTurn]) -> str:
    """Build a conversation transcript from turns."""
    lines: list[str] = []
    for turn in sorted(turns, key=lambda t: t.turn_index):
        lines.append(f"Interviewer: {turn.question_text}")
        if turn.response_transcript:
            lines.append(f"Participant: {turn.response_transcript}")
    return "\n".join(lines)


# Human-readable labels for the coded panel-profile values. Kept terse —
# this becomes one advisory line in the interviewer prompt, not a form.
_PROFILE_LABELS = {
    "age_range": lambda v: f"{v}",
    "gender": {
        "male": "man", "female": "woman", "non_binary": "non-binary",
        "prefer_not": None,
    },
    "education": {
        "high_school": "high-school education", "bachelor": "bachelor's degree",
        "master": "master's degree", "phd": "PhD", "other": None,
    },
    "employment_status": {
        "full_time": "works full-time", "part_time": "works part-time",
        "freelance": "freelancer", "student": "student",
        "unemployed": "not currently employed", "retired": "retired",
    },
    "seniority": {
        "junior": "junior", "mid": "mid-level", "senior": "senior",
        "manager": "manager", "director": "director", "c_suite": "C-suite",
    },
}


def _build_participant_profile_context(participant, db: Session) -> str | None:
    """Build a short, advisory description of who the participant is from their
    saved panel profile, for the interviewer prompt. Returns None when no
    profile (or nothing meaningful) is on file. Privacy-safe: never includes
    email; the interviewer is told not to read it back.
    """
    email = getattr(participant, "email", None)
    if not email:
        return None
    profile = db.query(PanelProfile).filter(PanelProfile.email == email).first()
    if profile is None:
        return None

    bits: list[str] = []
    if profile.age_range:
        bits.append(f"{profile.age_range} years old")
    gender = _PROFILE_LABELS["gender"].get(profile.gender) if profile.gender else None
    if gender:
        bits.append(gender)
    emp = _PROFILE_LABELS["employment_status"].get(profile.employment_status) if profile.employment_status else None
    if emp:
        bits.append(emp)
    # Role detail only makes sense for workers.
    if profile.job_function and profile.job_function != "other":
        role = profile.job_function.replace("_", " ")
        sen = _PROFILE_LABELS["seniority"].get(profile.seniority) if profile.seniority else None
        bits.append(f"{sen} {role}".strip() if sen else f"works in {role}")
    if profile.industry:
        bits.append(f"in the {profile.industry} industry")
    edu = _PROFILE_LABELS["education"].get(profile.education) if profile.education else None
    if edu:
        bits.append(edu)
    if profile.country:
        loc = profile.country
        if profile.city:
            loc = f"{profile.city}, {profile.country}"
        bits.append(f"based in {loc}")

    if not bits:
        return None
    return ", ".join(bits)


def get_interview_context(
    participant_id: str, db: Session
) -> dict:
    """Return conversation history, interview guide, and metadata for a participant.

    Returns a dict with keys:
        conversation_history (str), interview_guide (str),
        elapsed_minutes (float), current_question_index (int | None),
        total_minutes (int), all_questions_done (bool),
        system_prompt (str), project (Project), participant (Participant),
        turns (list[InterviewTurn]), total_questions (int)
    """
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    project = participant.project
    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    guide_questions = sorted(
        [q for q in project.guide_questions if not getattr(q, "deprecated_at", None)],
        key=lambda q: (q.section_index, q.question_index),
    )
    total_questions = len(guide_questions)

    # Determine the highest question_index that has been asked
    asked_indices = {t.question_index for t in turns if t.question_index is not None}
    current_question_index = max(asked_indices) if asked_indices else 0

    # all_questions_done is True only when the last guide question has been both
    # asked AND has a participant response (i.e. it's been answered, not just reached).
    last_index = total_questions - 1
    if total_questions == 0:
        all_questions_done = True
    elif current_question_index < last_index:
        all_questions_done = False
    else:
        # We are on (or past) the last question — check it has a response
        last_q_turns = [t for t in turns if t.question_index == last_index]
        all_questions_done = any(t.response_transcript for t in last_q_turns)

    # Use naive UTC to match SQLite-stored timestamps (no tzinfo)
    now = datetime.utcnow()
    started = participant.started_at.replace(tzinfo=None) if participant.started_at.tzinfo else participant.started_at
    elapsed = (now - started).total_seconds() / 60.0

    # The participant's chosen language overrides the study default for the
    # AI interviewer + voice; fall back to the project language.
    language = (
        getattr(participant, "preferred_language", None)
        or project.language
        or "en"
    )

    return {
        "conversation_history": _build_conversation_history(turns),
        "interview_guide": _build_interview_guide_str(project),
        "elapsed_minutes": elapsed,
        "current_question_index": current_question_index,
        "total_minutes": project.interview_duration_minutes,
        "all_questions_done": all_questions_done,
        "system_prompt": project.system_prompt,
        "language": language,
        "participant_profile": _build_participant_profile_context(participant, db),
        "project": project,
        "participant": participant,
        "turns": turns,
        "total_questions": total_questions,
    }


def decide_next_action(
    system_prompt: str,
    interview_guide_str: str,
    conversation_history: str,
    current_question_index: int,
    elapsed_minutes: float,
    total_minutes: int,
    all_questions_done: bool,
    total_questions: int = 0,
    research_objective: str | None = None,
    language: str | None = None,
    short_answer_state: dict | None = None,
    participant_profile: str | None = None,
    db=None,
    company_id=None,
    project_id=None,
    participant_id=None,
) -> dict:
    """Call Claude to decide the next interview action.

    Returns a dict with keys: action ("follow_up"|"next_question"|"close"), question (str)
    """
    client = get_anthropic_client(60.0)

    # Compute how much of the allotted time has been used and questions answered
    time_used_pct = (elapsed_minutes / total_minutes * 100) if total_minutes > 0 else 100
    questions_answered = current_question_index + 1  # 1-based count of questions reached
    remaining_minutes = max(0.0, total_minutes - elapsed_minutes)

    # ── Pacing budget ──────────────────────────────────────────────────────
    # How far ahead/behind are we relative to an even spread of questions?
    if total_questions > 0 and total_minutes > 0:
        minutes_per_question = total_minutes / total_questions
        expected_q_index = elapsed_minutes / minutes_per_question
        pace_delta = current_question_index - expected_q_index  # positive = ahead
        questions_remaining = max(0, total_questions - current_question_index - 1)
        slack_minutes = remaining_minutes - (questions_remaining * minutes_per_question)
    else:
        pace_delta = 0.0
        slack_minutes = remaining_minutes

    if pace_delta < -1.5:
        pacing_instruction = (
            "⚠️ PACING ALERT: You are significantly behind schedule. "
            "Move to the NEXT main guide question immediately. "
            "Do NOT ask a follow-up under any circumstances."
        )
    elif pace_delta < -0.5:
        pacing_instruction = (
            "PACING: You are slightly behind schedule. "
            "Only ask a follow-up if the participant's answer was genuinely too brief or unclear. "
            "Otherwise move to the next main question now."
        )
    elif pace_delta > 1.0:
        pacing_instruction = (
            "PACING: You are ahead of schedule — you have time to explore. "
            "Feel free to ask a follow-up question if it would surface deeper insight."
        )
    else:
        fu_word = "may" if slack_minutes > 0 else "should not"
        pacing_instruction = (
            f"PACING: You are on schedule. "
            f"You {fu_word} ask one follow-up if it genuinely adds value, then move to the next question."
        )

    # ── Close gate ─────────────────────────────────────────────────────────
    can_close = all_questions_done or time_used_pct >= 95.0
    can_close = can_close and (time_used_pct >= 80.0)

    if can_close:
        close_instruction = '3. "close" — the interview is complete (all questions covered and/or time is up); wrap up warmly'
    else:
        close_instruction = (
            '3. "close" — NOT available yet. '
            f'Only {elapsed_minutes:.1f} of {total_minutes} minutes have elapsed '
            f'({questions_answered} of {total_questions} questions reached). '
            'Keep the conversation going.'
        )

    objective_block = ""
    if research_objective:
        objective_block = (
            f"<objective>\n{research_objective}\n\n"
            "Keep this objective top of mind: probe for the job-to-be-done behind behaviours, "
            "amplify emotional language, and steer toward concrete examples — without breaking "
            "the conversational flow.\n</objective>\n\n"
        )

    examples_block = """<examples>
PARTICIPANT: "It was kind of frustrating when the import didn't work."
DECISION: follow_up
QUESTION: "Can you tell me what was happening right before you tried that import?"
WHY: emotional language + concrete claim, no story yet — unpack before moving on.

PARTICIPANT: "Yeah, I use it every Monday morning. I open the dashboard, scan for anything red, then ping the team in Slack. Takes about ten minutes."
DECISION: next_question
QUESTION: "That ten-minute Monday scan is really useful to hear. Shifting gears — could you walk me through the last time you onboarded a new teammate?"
WHY: concrete behaviour with detail; topic is exhausted; open with a callback ("ten-minute Monday scan") then transition.

PARTICIPANT: "It's fine."
DECISION: follow_up
QUESTION: "What does 'fine' look like for you on a typical day with it?"
WHY: generic answer with no behaviour or example.
</examples>"""

    participant_block = ""
    if participant_profile:
        participant_block = (
            f"<participant>\n"
            f"You are speaking with: {participant_profile}.\n"
            f"Use this only to calibrate your tone, examples, and assumptions "
            f"(e.g. don't explain jargon they'd know, do unpack things they likely won't). "
            f"NEVER read these facts back to them or make them feel profiled.\n"
            f"</participant>\n\n"
        )

    user_message = (
        f"{examples_block}\n\n"
        f"{objective_block}"
        f"{participant_block}"
        f"<guide>\n{interview_guide_str}\n</guide>\n\n"
        f"<conversation>\n{conversation_history}\n</conversation>\n\n"
        f"<state>\n"
        f"- Questions reached: {questions_answered} of {total_questions}\n"
        f"- Elapsed: {elapsed_minutes:.1f} / {total_minutes} min ({time_used_pct:.0f}% used, {remaining_minutes:.1f} min left)\n"
        f"- All main questions covered: {all_questions_done}\n"
        f"- {pacing_instruction}\n"
        f"- Close gate: {'OPEN — you may close' if can_close else close_instruction}\n"
        f"</state>\n\n"
    )

    # PF-3: when the participant has been giving short answers, nudge Claude
    # to ask a more open / specific follow-up rather than rushing on. Pacing
    # alerts still take precedence — we only widen the follow-up bias when
    # the engine isn't already behind schedule.
    if short_answer_state and short_answer_state.get("is_short_run") and pace_delta >= -0.5:
        run = short_answer_state.get("run_length", 0)
        last_w = short_answer_state.get("last_words")
        user_message += (
            f"<engagement>\n"
            f"The participant's last {run} answer(s) were short "
            f"(most recent: ~{last_w} words). "
            f"Prefer a more open, specific follow-up that invites a story or example "
            f"(e.g. 'Walk me through the last time…', 'Tell me about a moment when…') "
            f"instead of moving to the next question.\n"
            f"</engagement>\n\n"
        )

    user_message += (
        "Decide the next action and write the question the participant will hear. "
        "Return ONLY: "
        '{"action": "follow_up" | "next_question" | "close", "question": "..."}'
    )

    # Append language instruction to the system prompt if the project uses a
    # non-English interview language.
    effective_system_prompt = (system_prompt or INTERVIEWER_SYSTEM_PROMPT) + _language_instruction(language)

    import time as _time

    _max_retries = 2
    response = None
    for _attempt in range(_max_retries + 1):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                temperature=0.4,
                system=effective_system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            break
        except (anthropic.APIStatusError, httpx.TimeoutException) as exc:
            if _attempt < _max_retries:
                _time.sleep(1.5 ** _attempt)
                continue
            raise RuntimeError(
                "Interview AI temporarily unavailable — please retry."
            ) from exc

    if db is not None:
        log_claude_usage(
            db, response, "interview_turn",
            company_id=company_id, project_id=project_id, participant_id=participant_id,
        )

    raw_text = response.content[0].text.strip()

    # Try to parse JSON from the response, handling potential markdown wrapping
    text_to_parse = raw_text
    if text_to_parse.startswith("```"):
        # Strip markdown code fences
        lines = text_to_parse.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text_to_parse = "\n".join(lines).strip()

    try:
        result = json.loads(text_to_parse)
    except json.JSONDecodeError:
        cleaned = raw_text.strip()
        if (
            len(cleaned) > 200
            or cleaned.startswith("{")
            or "```" in cleaned
            or "\n" in cleaned
        ):
            cleaned = "Could you tell me more about that?"
        result = {"action": "follow_up", "question": cleaned}

    if "action" not in result:
        result["action"] = "follow_up"
    if "question" not in result:
        result["question"] = "Could you tell me more about that?"

    return result


# Sentinel used in InterviewTurn.question_index to mark the warm-up turn
# (which isn't part of the guide). The next turn after a warm-up always
# advances to guide question 0 — the AI's decide-next-action step is
# skipped because the warm-up isn't a research probe.
WARMUP_QUESTION_INDEX = -1

# PF-3 thresholds. Tuned for typical interview pacing — anything tighter
# fires on legitimate short answers ("yes", "every day"), anything looser
# misses the actual signal of a disengaging participant.
SHORT_ANSWER_WORDS = 15
SHORT_ANSWER_RUN = 2  # need this many short answers in a row to flag


def _detect_short_answers(turns: list) -> dict:
    """Inspect the most recent N participant responses for engagement drop.

    Returns a dict with::

      {
        "is_short_run": bool,        # last `RUN` answers all under threshold
        "last_words":   int | None,  # word count of the most recent answer
        "run_length":   int,         # how many short answers in a row
      }

    Used downstream by ``decide_next_action`` (to bias Claude toward more
    open follow-ups instead of advancing) and by ``process_interview_turn``
    (to surface a gentle ``coaching_hint`` to the participant). All
    thresholds are best-effort — silence/skips are excluded.
    """
    answered = [t for t in turns if t.response_transcript and t.response_transcript.strip() and t.response_transcript.strip() != "[Skipped]"]
    if not answered:
        return {"is_short_run": False, "last_words": None, "run_length": 0}

    def _wc(t):
        return len((t.response_transcript or "").split())

    last_words = _wc(answered[-1])
    run = 0
    for t in reversed(answered):
        if _wc(t) <= SHORT_ANSWER_WORDS:
            run += 1
        else:
            break
    return {
        "is_short_run": run >= SHORT_ANSWER_RUN,
        "last_words": last_words,
        "run_length": run,
    }


def _coaching_hint_for(state: dict, language: str) -> str | None:
    """Build a soft, non-prescriptive coaching tip when the run is short.

    Returns None when no nudge is warranted. We only surface a tip after
    SHORT_ANSWER_RUN consecutive short answers so we don't pester
    participants who happen to answer one yes/no question tersely.
    """
    if not state.get("is_short_run"):
        return None
    lang = (language or "en")[:2].lower()
    hints = {
        "en": "Researchers learn most from specific moments. If a story or example comes to mind, take your time to share it.",
        "fr": "Les chercheurs apprennent surtout des moments concrets. Si un exemple ou une anecdote vous vient, n'hésitez pas à prendre le temps de la raconter.",
        "es": "Los investigadores aprenden más de momentos específicos. Si te viene a la mente un ejemplo, tómate tu tiempo para contarlo.",
        "de": "Forscher lernen am meisten aus konkreten Momenten. Wenn dir eine Geschichte oder ein Beispiel einfällt, nimm dir Zeit, sie zu teilen.",
    }
    return hints.get(lang, hints["en"])


def _get_warmup_question(
    project: Project,
    db=None,
    participant_id=None,
    language_override: str | None = None,
) -> str:
    """Generate a warm-up opener — a low-stakes invitation to start talking.

    The warm-up isn't from the guide. It's framed around the project topic
    so the participant can ease into the conversation before the research
    questions arrive. Falls back to a generic opener in the project language
    if Claude is unreachable.
    """
    language_code = (language_override or getattr(project, "language", None) or "en").lower()
    language_name = LANGUAGE_NAMES.get(language_code, "English")

    fallbacks = {
        "en": "Welcome! Before we dive into the questions, could you tell me a bit about your typical week — just so we ease in?",
        "fr": "Bienvenue ! Avant d'entrer dans les questions, pourriez-vous me parler un peu de votre semaine type — juste pour démarrer en douceur ?",
        "es": "¡Bienvenido! Antes de entrar en las preguntas, ¿podría contarme un poco de su semana típica para empezar con calma?",
        "de": "Willkommen! Bevor wir zu den Fragen kommen, könnten Sie mir kurz von Ihrer typischen Woche erzählen — einfach zum Einstieg?",
        "it": "Benvenuto! Prima di entrare nelle domande, può raccontarmi un po' della sua settimana tipo, giusto per iniziare?",
        "pt": "Bem-vindo! Antes de entrar nas perguntas, poderia me contar um pouco sobre sua semana típica — só para começar?",
    }
    fallback = fallbacks.get(language_code, fallbacks["en"])

    # Best-effort topic extraction so the warm-up references what the
    # participant is here to talk about. Falls through silently to the
    # generic fallback if anything goes wrong.
    topic_hint = (
        getattr(project, "research_objective", None)
        or getattr(project, "research_context", None)
        or getattr(project, "name", None)
        or ""
    ).strip()

    if not topic_hint or not settings.ANTHROPIC_API_KEY:
        return fallback

    try:
        client = get_anthropic_client(60.0)
        effective_system_prompt = INTERVIEWER_SYSTEM_PROMPT + _language_instruction(language_code)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=180,
            temperature=0.6,
            system=effective_system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"You are about to start a research interview about this topic:\n"
                        f'"{topic_hint[:400]}"\n\n'
                        f"Write a WARM-UP opener in {language_name}. The goal is to put the "
                        f"participant at ease before the real questions begin. One short sentence "
                        f"of welcome, then ONE simple, low-stakes question that gently touches the "
                        f"topic — something they can answer without thinking hard. Avoid 'why'. "
                        f"Avoid asking for opinions or evaluations. Under 28 words. "
                        f"Return ONLY the spoken text — no JSON, no quotes, no preamble."
                    ),
                }
            ],
        )
        text = response.content[0].text.strip()
        if db is not None:
            log_claude_usage(
                db, response, "interview_warmup",
                company_id=getattr(project, "company_id", None),
                project_id=getattr(project, "id", None),
                participant_id=participant_id,
            )
        return text or fallback
    except Exception:
        return fallback


def _get_first_question(
    project: Project,
    db=None,
    participant_id=None,
    language_override: str | None = None,
) -> tuple[str, int]:
    """Get the first non-deprecated question from the interview guide, rephrased as an opener."""
    guide_questions = sorted(
        [q for q in project.guide_questions if not getattr(q, "deprecated_at", None)],
        key=lambda q: (q.section_index, q.question_index),
    )
    language_code = (language_override or getattr(project, "language", None) or "en").lower()
    language_name = LANGUAGE_NAMES.get(language_code, "English")

    if not guide_questions:
        fallbacks = {
            "en": "Thank you for joining. Could you start by telling me a bit about yourself?",
            "fr": "Merci de nous rejoindre. Pour commencer, pourriez-vous me parler un peu de vous ?",
            "es": "Gracias por participar. Para empezar, ¿podría contarme un poco sobre usted?",
            "de": "Danke, dass Sie dabei sind. Könnten Sie mir zunächst etwas über sich erzählen?",
            "it": "Grazie per essere qui. Per iniziare, può raccontarmi un po' di lei?",
            "pt": "Obrigado por participar. Para começar, poderia me contar um pouco sobre você?",
            "nl": "Bedankt dat u meedoet. Kunt u om te beginnen iets over uzelf vertellen?",
            "ja": "ご参加ありがとうございます。まずはご自身について少しお話しいただけますか？",
            "ko": "참여해 주셔서 감사합니다. 먼저 본인에 대해 간단히 소개해 주시겠어요?",
            "zh": "感谢您的参与。首先，能否简单介绍一下您自己？",
        }
        return fallbacks.get(language_code, fallbacks["en"]), 0

    first_q = guide_questions[0]

    # Use Claude to rephrase the first question as a natural conversation opener
    client = get_anthropic_client(60.0)

    effective_system_prompt = INTERVIEWER_SYSTEM_PROMPT + _language_instruction(language_code)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        temperature=0.5,
        system=effective_system_prompt,
        messages=[
            {
                "role": "user",
                "content": (
                    f"You are starting an interview. The first question from the guide is:\n"
                    f'"{first_q.main_question}"\n\n'
                    f"Rephrase as a warm, natural OPENER in {language_name}. One short sentence "
                    f"of welcome (no name needed), then the question, phrased conversationally. "
                    f"Avoid 'why'. Single concept. Under 30 words. "
                    f"Return ONLY the spoken text — no JSON, no quotes, no preamble."
                ),
            }
        ],
    )

    question_text = response.content[0].text.strip()

    if db is not None:
        log_claude_usage(
            db, response, "interview_turn",
            company_id=getattr(project, "company_id", None),
            project_id=getattr(project, "id", None),
            participant_id=participant_id,
        )

    return question_text, 0


def start_interview(participant_id: str, db: Session) -> dict:
    """Generate the first question and TTS for a new interview.

    PF-3: when ``project.warmup_enabled`` is True (default), the very first
    turn is a warm-up — a low-stakes invitation to get the participant
    talking before the research questions arrive. Marked via
    ``question_index = WARMUP_QUESTION_INDEX``; ``process_interview_turn``
    detects it and routes the next turn directly to guide question 0.

    Returns dict with: question_text, tts_audio_url, turn, is_warmup
    """
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    project = participant.project
    company_id = project.company_id
    proj_id = project.id

    use_warmup = bool(getattr(project, "warmup_enabled", True))

    # The participant's chosen language overrides the study default for the
    # opening turn (warm-up / first question) too.
    participant_lang = getattr(participant, "preferred_language", None)

    if use_warmup:
        question_text = _get_warmup_question(
            project, db=db, participant_id=participant_id, language_override=participant_lang
        )
        q_index = WARMUP_QUESTION_INDEX
    else:
        question_text, q_index = _get_first_question(
            project, db=db, participant_id=participant_id, language_override=participant_lang
        )

    # Generate TTS audio and upload (non-fatal — text-only fallback if TTS is down)
    tts_audio_url = None
    try:
        tts_key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
        tts_audio_url = upload_audio(generate_speech(question_text), tts_key)
        log_tts_usage(db, question_text, company_id=company_id, project_id=proj_id, participant_id=participant_id)
    except Exception:
        logger.warning("TTS failed for start_interview participant=%s; text-only fallback", participant_id)

    # Save the interviewer turn
    turn = InterviewTurn(
        participant_id=participant_id,
        turn_index=0,
        question_index=q_index,
        is_follow_up=False,
        follow_up_index=0,
        question_text=question_text,
        tts_audio_url=tts_audio_url,
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)

    return {
        "question_text": question_text,
        "tts_audio_url": tts_audio_url,
        "turn": turn,
        "is_warmup": use_warmup,
    }


def process_interview_turn(
    participant_id: str, audio_path: str, audio_url: str, db: Session
) -> dict:
    """Process a participant's audio response and generate the next question.

    Orchestrates: transcribe -> save transcript -> get context -> Claude decision -> TTS

    audio_path is the storage key (for STT download); audio_url is the public
    playback URL persisted on the turn so researchers can replay the recording.

    Returns dict with: question_text, tts_audio_url, is_complete
    """
    # 1. Transcribe the participant's audio
    audio_data = download_audio(audio_path)
    filename = os.path.basename(audio_path)
    transcript, audio_duration, segments = transcribe_audio(audio_data, filename)

    # 1a. Guard: Whisper sometimes returns an empty or whitespace-only string
    # for silent/inaudible clips. Saving that and passing it to Claude produces
    # garbage follow-ups. Signal the caller to prompt a re-record instead.
    if not transcript or not transcript.strip():
        raise EmptyTranscriptError(
            "No speech detected in the recording. Please try again in a quieter environment."
        )

    # 1b. Whisper hallucination guard — common phantom phrases on silent audio
    _HALLUCINATION_PHRASES = (
        "thank you for watching", "thanks for watching", "please subscribe",
        "like and subscribe", "see you in the next", "merci d'avoir regardé",
        "sous-titres réalisés", "sous-titrage",
    )
    _lower_transcript = transcript.strip().lower()
    if any(p in _lower_transcript for p in _HALLUCINATION_PHRASES):
        raise EmptyTranscriptError(
            "No speech detected in the recording. Please try again in a quieter environment."
        )

    # 2. Find the last interviewer turn to update with the participant's response
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    # The last turn should be the interviewer's question awaiting a response
    if turns:
        last_turn = turns[-1]
        last_turn.response_transcript = transcript
        last_turn.audio_recording_url = audio_url
        last_turn.response_segments = json.dumps(segments) if segments else None
        db.commit()

    # 3. Get context for Claude
    context = get_interview_context(participant_id, db)
    _proj = context["project"]
    _company_id = _proj.company_id
    _project_id = _proj.id

    # Log STT usage now that we have project/company context
    log_stt_usage(
        db, audio_duration,
        company_id=_company_id, project_id=_project_id, participant_id=participant_id,
    )

    # PF-3: warm-up handoff. If the turn the participant just answered was the
    # warm-up (question_index = -1), short-circuit Claude entirely and play
    # the first real guide question. The warm-up is a courtesy turn — we don't
    # want it consuming the AI's pacing budget or spawning follow-ups.
    last_was_warmup = bool(turns) and turns[-1].question_index == WARMUP_QUESTION_INDEX
    if last_was_warmup:
        first_q_text, _ = _get_first_question(
            _proj, db=db, participant_id=participant_id,
            language_override=context.get("language"),
        )
        first_tts_key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
        first_tts_url = upload_audio(generate_speech(first_q_text), first_tts_key)
        log_tts_usage(db, first_q_text, company_id=_company_id, project_id=_project_id, participant_id=participant_id)
        next_turn_idx = (turns[-1].turn_index + 1) if turns else 0
        new_turn = InterviewTurn(
            participant_id=participant_id,
            turn_index=next_turn_idx,
            question_index=0,
            is_follow_up=False,
            follow_up_index=0,
            question_text=first_q_text,
            tts_audio_url=first_tts_url,
        )
        db.add(new_turn)
        db.commit()
        db.refresh(new_turn)
        return {
            "question_text": first_q_text,
            "tts_audio_url": first_tts_url,
            "is_complete": False,
            "is_follow_up": False,
            "question_index": 0,
            "elapsed_seconds": int(context["elapsed_minutes"] * 60),
            "total_seconds": context["total_minutes"] * 60,
            "coaching_hint": None,
            "transcript": transcript,
        }

    # PF-3: short-answer detection for the AI prompt + participant coaching.
    # Walks the most recent participant responses and flags when the engagement
    # is dropping. Used both to nudge Claude (engine adapts) and to surface a
    # gentle hint to the participant (coaching tip).
    short_answer_state = _detect_short_answers(turns)

    # 4. Ask Claude for the next action
    decision = decide_next_action(
        system_prompt=context["system_prompt"],
        interview_guide_str=context["interview_guide"],
        conversation_history=context["conversation_history"],
        current_question_index=context["current_question_index"],
        elapsed_minutes=context["elapsed_minutes"],
        total_minutes=context["total_minutes"],
        all_questions_done=context["all_questions_done"],
        total_questions=context["total_questions"],
        research_objective=_proj.research_objective,
        language=context["language"],
        short_answer_state=short_answer_state,
        participant_profile=context.get("participant_profile"),
        db=db,
        company_id=_company_id,
        project_id=_project_id,
        participant_id=participant_id,
    )

    # Server-side safety guard: override a premature "close" decision.
    # Claude can only close if 80% of the time has elapsed OR all questions are done.
    if decision["action"] == "close":
        elapsed = context["elapsed_minutes"]
        total = context["total_minutes"]
        time_used_pct = (elapsed / total * 100) if total > 0 else 100
        if not context["all_questions_done"] and time_used_pct < 80.0:
            # Force a next_question instead
            decision["action"] = "next_question"

    # Server-side pace guard: if significantly behind, override follow_up to next_question
    if decision["action"] == "follow_up":
        elapsed = context["elapsed_minutes"]
        total = context["total_minutes"]
        total_q = context["total_questions"]
        cur_q = context["current_question_index"]
        if total_q > 0 and total > 0:
            minutes_per_q = total / total_q
            expected_q = elapsed / minutes_per_q
            if (cur_q - expected_q) < -1.5:
                decision["action"] = "next_question"

    action = decision["action"]
    question_text = decision["question"]
    is_complete = action == "close"

    # 5. Generate TTS for the next question / closing and upload
    tts_key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
    tts_audio_url = upload_audio(generate_speech(question_text), tts_key)
    log_tts_usage(db, question_text, company_id=_company_id, project_id=_project_id, participant_id=participant_id)

    # 6. Determine the new turn metadata
    next_turn_index = (turns[-1].turn_index + 1) if turns else 0

    if action == "next_question":
        new_q_index = context["current_question_index"] + 1
        is_follow_up = False
        follow_up_idx = 0
    elif action == "follow_up":
        new_q_index = context["current_question_index"]
        is_follow_up = True
        # Count existing follow-ups for this question
        follow_up_idx = sum(
            1 for t in turns
            if t.question_index == new_q_index and t.is_follow_up
        ) + 1
    else:  # close
        new_q_index = context["current_question_index"]
        is_follow_up = False
        follow_up_idx = 0

    # 7. Save the new interviewer turn
    new_turn = InterviewTurn(
        participant_id=participant_id,
        turn_index=next_turn_index,
        question_index=new_q_index,
        is_follow_up=is_follow_up,
        follow_up_index=follow_up_idx,
        question_text=question_text,
        tts_audio_url=tts_audio_url,
    )
    db.add(new_turn)

    # 8. Update participant status if complete
    if is_complete:
        participant.status = "completed"
        participant.completed_at = datetime.utcnow()

        # Consume one credit for the workspace that owns this project. No-op
        # for legacy plans (defer to old participant-limit gate) and
        # idempotent per participant — concurrent or replayed completions
        # never double-charge.
        try:
            from app.services.billing_service import consume_interview_credit
            consume_interview_credit(
                db,
                workspace_id=participant.project.company_id,
                participant_id=participant.id,
                project_id=participant.project_id,
                metadata={
                    "duration_seconds": int((participant.completed_at - participant.started_at).total_seconds()) if participant.started_at else None,
                    "language": participant.project.language if participant.project else None,
                },
            )
        except Exception:  # pragma: no cover — never fail an interview on billing
            logger.exception(
                "Credit consumption failed for participant %s; interview still completed",
                participant.id,
            )

        # Activation funnel event — fire-and-forget, never raises.
        try:
            from app.services.analytics import emit_event
            duration = None
            if participant.started_at and participant.completed_at:
                duration = int((participant.completed_at - participant.started_at).total_seconds())
            emit_event(
                "participant_completed",
                company=participant.project.company if participant.project else None,
                project_id=str(participant.project_id),
                participant_id=str(participant.id),
                duration_seconds=duration,
            )
        except Exception:
            pass

        # W3.2 — "your first response is in" lifecycle email. Fires the
        # FIRST time any participant ever completes for this workspace.
        # Idempotent via Company.first_response_email_sent_at: a second
        # response (or a replay) never re-triggers. Always best-effort.
        try:
            company_for_email = (
                participant.project.company if participant.project else None
            )
            if (
                company_for_email is not None
                and company_for_email.email
                and company_for_email.first_response_email_sent_at is None
            ):
                from app.config import settings
                from app.services.email import send_first_response_in

                project = participant.project
                project_url = (
                    f"{settings.APP_BASE_URL}/projects/{project.id}?tab=responses"
                    if project
                    else settings.APP_BASE_URL
                )
                send_first_response_in(
                    to=company_for_email.email,
                    project_name=(project.name if project else "your study"),
                    project_url=project_url,
                    lang=(company_for_email.preferred_language or "en"),
                )
                company_for_email.first_response_email_sent_at = datetime.utcnow()
                db.commit()
        except Exception:
            logger.exception(
                "First-response email failed for participant %s; interview still completed",
                participant.id,
            )

        # V4 paywall milestone — when the 3rd participant completes
        # for a workspace, fire the "free preview full, unlock the
        # rest" email. Fires at most once per workspace (idempotent).
        # Skip for paid / ever-paid workspaces — they don't see the
        # paywall, so the email would confuse them.
        try:
            from app.models.project import Project
            from app.models.interview import Participant as _Participant
            from app.services.paywall import FREE_PREVIEW_COUNT

            cefe = participant.project.company if participant.project else None
            paid_or_ever_paid = bool(
                cefe
                and (
                    cefe.has_ever_paid
                    or (cefe.subscription_status or "")
                    in ("active", "past_due")
                )
            )
            if (
                cefe is not None
                and cefe.email
                and not paid_or_ever_paid
                and cefe.free_preview_full_email_sent_at is None
            ):
                completed_count = (
                    db.query(_Participant)
                    .join(Project, _Participant.project_id == Project.id)
                    .filter(
                        Project.company_id == cefe.id,
                        Project.is_demo.is_(False),
                        _Participant.status == "completed",
                    )
                    .count()
                )
                if completed_count >= FREE_PREVIEW_COUNT:
                    from app.config import settings
                    from app.services.email import send_free_preview_full

                    project = participant.project
                    project_url = (
                        f"{settings.APP_BASE_URL}/projects/{project.id}?tab=responses"
                        if project
                        else settings.APP_BASE_URL
                    )
                    send_free_preview_full(
                        to=cefe.email,
                        project_name=(project.name if project else "your study"),
                        project_url=project_url,
                        lang=(cefe.preferred_language or "en"),
                    )
                    cefe.free_preview_full_email_sent_at = datetime.utcnow()
                    db.commit()
        except Exception:
            logger.exception(
                "Free-preview-full email failed; interview still completed",
            )

        # Send completion email if participant provided one
        try:
            from app.services.email import send_email
            if participant.email:
                project_name = participant.project.name
                lang = (participant.project.language or "en").lower()[:2]
                greeting = f" {participant.display_name}" if participant.display_name else ""
                if lang == "fr":
                    subject = f"Merci pour votre entretien — {project_name}"
                    body_html = f"""
                    <p>Bonjour{greeting},</p>
                    <p>Merci d'avoir complété l'entretien <strong>{project_name}</strong>. Vos réponses ont bien ét�� enregistrées et contribueront à enrichir la recherche.</p>
                    <p>Vous pouvez fermer cet e-mail — aucune action supplémentaire n'est requise.</p>
                    """
                else:
                    subject = f"Thank you for your interview — {project_name}"
                    body_html = f"""
                    <p>Hi{greeting},</p>
                    <p>Thank you for completing the <strong>{project_name}</strong> interview. Your responses have been recorded and will help shape the research.</p>
                    <p>You can close this email — no further action is needed.</p>
                    """
                send_email(to=participant.email, subject=subject, body_html=body_html)
        except Exception:
            pass  # Never fail the interview flow due to email errors

        # Auto-run AI quality assessment in background thread
        try:
            import threading as _threading
            _pid = participant.id
            _proj_id = participant.project_id
            def _assess():
                try:
                    from app.database import session_scope
                    from app.services.quality import run_ai_quality_assessment
                    from app.models.project import Project
                    from app.models.company import Company
                    with session_scope() as assess_db:
                        proj = assess_db.query(Project).filter(Project.id == _proj_id).first()
                        lang = "en"
                        if proj:
                            company = assess_db.query(Company).filter(Company.id == proj.company_id).first()
                            if company and company.preferred_language:
                                lang = company.preferred_language
                        run_ai_quality_assessment(_pid, assess_db, language=lang)
                except Exception:
                    pass
            _threading.Thread(target=_assess, daemon=True).start()
        except Exception:
            pass

    db.commit()
    db.refresh(new_turn)

    return {
        "question_text": question_text,
        "tts_audio_url": tts_audio_url,
        "is_complete": is_complete,
        "is_follow_up": is_follow_up,
        "question_index": new_q_index,
        "elapsed_seconds": int(context["elapsed_minutes"] * 60),
        "total_seconds": context["total_minutes"] * 60,
        "coaching_hint": _coaching_hint_for(short_answer_state, context["language"]) if not is_complete else None,
        "transcript": transcript,
    }


def skip_question(participant_id: str, db) -> dict:
    """Advance past the current question without a response and return the next question."""
    from app.services.tts import generate_speech
    from app.services.storage import upload_audio as upload_audio_file

    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if not participant:
        raise ValueError("Participant not found")

    project = participant.project
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    context = get_interview_context(participant_id, db)

    # Mark last unanswered turn as skipped
    unanswered = [t for t in turns if not t.response_transcript]
    if unanswered:
        last = unanswered[-1]
        last.response_transcript = "[Skipped]"
        db.commit()

    # Decide next action — force next_question
    current_q_index = context["current_question_index"]
    guide_questions = sorted(
        [q for q in project.guide_questions if not q.deprecated_at],
        key=lambda q: q.question_index,
    )
    next_questions = [q for q in guide_questions if q.question_index > current_q_index]

    if not next_questions:
        # No more questions — close
        closing_text = _closing_message(getattr(project, "language", None))
        tts_url = None
        try:
            audio_data = generate_speech(closing_text)
            key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
            upload_audio_file(audio_data, key)
            tts_url = f"/audio/{key}"
        except Exception:
            pass
        participant.status = "completed"
        participant.completed_at = datetime.utcnow()
        db.commit()

        # Auto-run AI quality assessment in background thread
        try:
            import threading as _threading
            _pid = participant.id
            _proj_id = participant.project_id
            def _assess_skip():
                try:
                    from app.database import session_scope
                    from app.services.quality import run_ai_quality_assessment
                    from app.models.project import Project
                    from app.models.company import Company
                    with session_scope() as assess_db:
                        proj = assess_db.query(Project).filter(Project.id == _proj_id).first()
                        lang = "en"
                        if proj:
                            company = assess_db.query(Company).filter(Company.id == proj.company_id).first()
                            if company and company.preferred_language:
                                lang = company.preferred_language
                        run_ai_quality_assessment(_pid, assess_db, language=lang)
                except Exception:
                    pass
            _threading.Thread(target=_assess_skip, daemon=True).start()
        except Exception:
            pass

        return {"question_text": closing_text, "tts_audio_url": tts_url, "is_complete": True, "is_follow_up": False, "question_index": current_q_index, "elapsed_seconds": 0, "total_seconds": 0}

    next_q = next_questions[0]
    question_text = next_q.main_question
    new_turn = InterviewTurn(
        participant_id=participant_id,
        turn_index=len(turns),
        question_index=next_q.question_index,
        is_follow_up=False,
        follow_up_index=0,
        question_text=question_text,
    )
    db.add(new_turn)
    db.commit()

    tts_url = None
    try:
        audio_data = generate_speech(question_text)
        key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
        upload_audio_file(audio_data, key)
        new_turn.tts_audio_url = key
        db.commit()
        tts_url = f"/audio/{key}"
    except Exception:
        pass

    total_minutes = project.interview_duration_minutes or 30
    elapsed = context["elapsed_minutes"]

    return {
        "question_text": question_text,
        "tts_audio_url": tts_url,
        "is_complete": False,
        "is_follow_up": False,
        "question_index": next_q.question_index,
        "elapsed_seconds": int(elapsed * 60),
        "total_seconds": total_minutes * 60,
    }
