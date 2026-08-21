"""Core interview engine: orchestrates STT, Claude decision-making, and TTS."""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _log_isolated(fn_name: str, *args, **kwargs) -> None:
    """Write an AI usage row on its OWN session.

    The usage loggers commit. Called with the request session they would
    commit a half-built turn: the participant's answer would land in the
    database before the question that follows it exists, and a crash in
    between would strand the interview. Logging on a separate session keeps
    ``process_interview_turn`` a single atomic transaction (and matches the
    loggers' own warning about poisoning a shared session).
    """
    from app.database import session_scope
    from app.services import usage_logger as _ul

    try:
        with session_scope() as udb:
            getattr(_ul, fn_name)(udb, *args, **kwargs)
    except Exception:
        logger.warning("usage logging failed (%s)", fn_name, exc_info=True)


def log_claude_usage(db, *args, **kwargs) -> None:
    _log_isolated("log_claude_usage", *args, **kwargs)


def log_stt_usage(db, *args, **kwargs) -> None:
    _log_isolated("log_stt_usage", *args, **kwargs)


def log_tts_usage(db, *args, **kwargs) -> None:
    _log_isolated("log_tts_usage", *args, **kwargs)

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
from app.services import usage_logger
from app.services import ai_models


class _DeferTTS(Exception):
    """Internal signal: synthesis is deferred to the /turn-audio fetch."""


class EmptyTranscriptError(Exception):
    """Raised when Whisper returns no speech in the participant's recording."""


INTERVIEWER_SYSTEM_PROMPT = """\
You are a senior qualitative interviewer running a live voice interview. You speak like a \
warm, curious peer, not a survey script and not a therapist. You are time-bounded and the \
participant can hear silence; aim for one focused question at a time.

Voice & stance:
- Express genuine interest in what the participant just said. Be brief: they speak more when you speak less.
- Stay neutral. Never approve, disapprove, or evaluate an answer. Never suggest an answer inside the question.
- Use the participant's own words and terminology. Mirror their language register.
- Avoid "why" questions, they invite rationalisation. Prefer "walk me through", "tell me about \
the last time", "what was happening when".
- Avoid yes/no questions. If the natural question is closed, reshape it into an open one.
- Single concept per question. No double-barrelled questions, no preambles longer than one sentence.
- Never use em dashes, en dashes, or double hyphens in anything you say. Use a comma or a colon instead.

Probing toolkit (pick the ONE that fits, vary across turns, never stack two):
- specific_moment: "Tell me about the last time that happened." Turns opinions into episodes.
- walk_through: "Walk me through what you did, step by step." Surfaces behaviour and workarounds.
- laddering: "What did that make possible for you?" / "What mattered about that?" Climbs from feature to consequence to value.
- contrast: "How is that different from how you did it before / elsewhere?" Sharpens what is distinctive.
- reflect_back: Restate their claim in their words and invite correction: "So if I heard you right, X. Is that fair?" Use sparingly, it validates and often unlocks nuance.
- counter_example: "Was there a time it did not go that way?" Tests how general a claim is.
- unpack_term: When they use a loaded word ("fine", "painful", "clunky"), ask what it looked like concretely.

Learning goals:
- Each guide question may carry a "Desired learning". That is your exit criterion for the topic, not a \
count of follow-ups. Stay on the topic while a learning goal is still unmet and the participant has more to give; \
move on when the learning goals are met, or when the participant clearly has nothing further.
- Connect back across the conversation when relevant ("earlier you mentioned X"), it shows you listened.

Handling people, not just answers:
- If the participant asks YOU a question, answer it in one honest sentence (you are an AI interviewer working for \
the research team; you do not know the study results; their answers are reviewed by the team), then gently return to the topic.
- If they say "I don't know" or go quiet, lower the stakes: offer a concrete, easier angle (a recent moment, a typical day). Never push twice.
- If they drift off-topic, acknowledge briefly and steer back with a bridge to the guide topic.
- If they ask to stop, say they are done with the SESSION, seem distressed, or signal discomfort, you MUST choose \
end_early: thank them warmly in one or two sentences, never argue or negotiate for "one more question". Fill \
stop_quote with their exact words. Be careful: "I'm done" / "that's all" about the CURRENT TOPIC is not a request to \
end the interview, it means move on to the next question.
- If they switch language, continue in the interview language unless they explicitly ask to switch.

Continuity (critical, the participant hears every turn):
- The greeting belongs to the OPENING question only. You have already greeted them. NEVER open a later \
turn with a fresh welcome ("thanks for being here", "merci d'être là", "to start / pour commencer"). \
You are mid-conversation, continue it.
- NEVER ask a question that has already been asked. Read the conversation so far and the coverage list: \
any guide topic already covered is done. Do not re-ask it, even reworded.
- When you move to the next guide question, move to the SPECIFIC next uncovered one named in the coverage \
block, never loop back to an earlier topic.
- When a new guide question opens a new section, mark the shift in a few words ("Let's talk about something a bit different now").

Decision rules (you MUST output exactly one action):

1. follow_up: ask a probing question that stays on the current topic. Choose this when ANY of:
   - A learning goal for the current topic is still unmet and the participant has more to give.
   - The participant introduced a concrete claim, story, or emotion that needs unpacking ("it was frustrating", \
"we just stopped using it", "the team pushed back").
   - You heard a generic answer ("it's fine", "it works") that hasn't surfaced behaviour or an example.
   - They asked you something or went off-topic: answer / acknowledge, then re-ask within the same turn.

2. next_question: move to the next guide question. Choose this when ANY of:
   - The learning goals for the current topic are met, or the topic has yielded a concrete example and you have nothing sharper to ask.
   - Pacing is behind (the host system will tell you).
   - You have already asked 2 follow-ups on this topic without new information.
   When transitioning, OPEN with a one-sentence callback to something specific the participant \
just said (use their exact words where natural), THEN introduce the new topic. This makes them feel heard.

3. close: wrap up warmly. ONLY available when the host system tells you the close gate is open. If the host says close is \
NOT available, you MUST NOT return "close" no matter how exhausted the conversation feels. When you close, thank them \
for something specific they shared and say what happens next in one sentence (the team reviews the conversation).

4. end_early: the participant asked to stop the interview, or is uncomfortable. Always available, but only ever on \
their explicit signal, which you MUST quote verbatim in stop_quote. One or two warm sentences, no new question.

The host system enforces the close gate and follow-up caps; when it tells you an action is forced, obey it and write \
the best possible wording for that action.
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
    "en": "That wraps up our interview. Thank you so much for your time and thoughtful responses. It's been really helpful!",
    "fr": "Voilà qui conclut notre entretien. Merci beaucoup pour votre temps et vos réponses, cela nous a été précieux !",
    "es": "Con esto cerramos la entrevista. Muchas gracias por su tiempo y sus respuestas, ha sido muy útil.",
    "de": "Damit beenden wir unser Interview. Vielen Dank für Ihre Zeit und Ihre durchdachten Antworten, das war sehr hilfreich!",
    "it": "Con questo concludiamo la nostra intervista. Grazie mille per il suo tempo e le sue risposte, è stato davvero utile!",
    "pt": "Com isto encerramos a entrevista. Muito obrigado pelo seu tempo e pelas suas respostas, foi muito útil!",
    "nl": "Daarmee sluiten we dit interview af. Heel erg bedankt voor uw tijd en doordachte antwoorden, het was enorm behulpzaam!",
    "ja": "以上でインタビューは終了です。お時間を割いて丁寧にお答えいただき、本当にありがとうございました。",
    "ko": "이것으로 인터뷰를 마치겠습니다. 시간을 내어 성의 있게 답해 주셔서 정말 감사합니다.",
    "zh": "我们的访谈到此结束。非常感谢您抽出宝贵时间并认真回答，这对我们非常有帮助！",
}

# Hard ceiling on consecutive follow-ups per guide question. The AI prompt
# advises moving on after ~2 follow-ups without new information; this is the
# server-enforced backstop so one topic can never eat the whole interview.
MAX_FOLLOWUPS_PER_QUESTION = 3


# Participant thank-you email, in every supported interview language.
# Keyed off the participant's effective language (their own choice first,
# then the project language) — same rule the spoken interview follows.
COMPLETION_EMAILS: dict[str, dict[str, str]] = {
    "en": {
        "subject": "Thank you for your interview: {project_name}",
        "body": (
            "<p>Hi{greeting},</p>"
            "<p>Thank you for taking part in the <strong>{project_name}</strong> interview. "
            "Your responses have been recorded and will help shape the research.</p>"
            "<p>You can close this email, no further action is needed.</p>"
        ),
    },
    "fr": {
        "subject": "Merci pour votre entretien : {project_name}",
        "body": (
            "<p>Bonjour{greeting},</p>"
            "<p>Merci d'avoir participé à l'entretien <strong>{project_name}</strong>. "
            "Vos réponses ont bien été enregistrées et contribueront à la recherche.</p>"
            "<p>Vous pouvez fermer cet e-mail, aucune action n'est requise de votre part.</p>"
        ),
    },
    "es": {
        "subject": "Gracias por su entrevista: {project_name}",
        "body": (
            "<p>Hola{greeting},</p>"
            "<p>Gracias por participar en la entrevista <strong>{project_name}</strong>. "
            "Sus respuestas han quedado registradas y contribuirán a la investigación.</p>"
            "<p>Puede cerrar este correo, no se requiere ninguna otra acción.</p>"
        ),
    },
    "de": {
        "subject": "Vielen Dank für Ihr Interview: {project_name}",
        "body": (
            "<p>Hallo{greeting},</p>"
            "<p>vielen Dank für Ihre Teilnahme am Interview <strong>{project_name}</strong>. "
            "Ihre Antworten wurden gespeichert und fließen in die Forschung ein.</p>"
            "<p>Sie können diese E-Mail schließen, es ist nichts weiter zu tun.</p>"
        ),
    },
    "it": {
        "subject": "Grazie per la sua intervista: {project_name}",
        "body": (
            "<p>Salve{greeting},</p>"
            "<p>grazie per aver partecipato all'intervista <strong>{project_name}</strong>. "
            "Le sue risposte sono state registrate e contribuiranno alla ricerca.</p>"
            "<p>Può chiudere questa email, non è richiesta alcuna ulteriore azione.</p>"
        ),
    },
    "pt": {
        "subject": "Obrigado pela sua entrevista: {project_name}",
        "body": (
            "<p>Olá{greeting},</p>"
            "<p>obrigado por participar na entrevista <strong>{project_name}</strong>. "
            "As suas respostas foram registadas e vão contribuir para a investigação.</p>"
            "<p>Pode fechar este email, não é necessária mais nenhuma ação.</p>"
        ),
    },
    "nl": {
        "subject": "Bedankt voor uw interview: {project_name}",
        "body": (
            "<p>Hallo{greeting},</p>"
            "<p>Bedankt voor uw deelname aan het interview <strong>{project_name}</strong>. "
            "Uw antwoorden zijn opgeslagen en dragen bij aan het onderzoek.</p>"
            "<p>U kunt deze e-mail sluiten, er is verder niets nodig.</p>"
        ),
    },
    "ja": {
        "subject": "インタビューへのご協力ありがとうございました：{project_name}",
        "body": (
            "<p>こんにちは{greeting}。</p>"
            "<p><strong>{project_name}</strong>のインタビューにご協力いただき、誠にありがとうございました。"
            "ご回答は記録され、調査に活用されます。</p>"
            "<p>このメールへの返信は不要です。</p>"
        ),
    },
    "ko": {
        "subject": "인터뷰에 참여해 주셔서 감사합니다: {project_name}",
        "body": (
            "<p>안녕하세요{greeting},</p>"
            "<p><strong>{project_name}</strong> 인터뷰에 참여해 주셔서 감사합니다. "
            "답변이 잘 기록되었으며 연구에 소중히 활용될 예정입니다.</p>"
            "<p>이 메일은 확인만 하시면 됩니다. 추가 조치는 필요하지 않습니다.</p>"
        ),
    },
    "zh": {
        "subject": "感谢您参与访谈：{project_name}",
        "body": (
            "<p>您好{greeting}，</p>"
            "<p>感谢您参与<strong>{project_name}</strong>访谈。"
            "您的回答已成功记录，将为这项研究提供帮助。</p>"
            "<p>您可以直接关闭这封邮件，无需任何后续操作。</p>"
        ),
    },
}


FALLBACK_FOLLOW_UPS: dict[str, str] = {
    "en": "Could you tell me more about that?",
    "fr": "Pouvez-vous m'en dire un peu plus ?",
    "es": "¿Podría contarme un poco más sobre eso?",
    "de": "Können Sie mir dazu etwas mehr erzählen?",
    "it": "Può dirmi qualcosa di più al riguardo?",
    "pt": "Pode contar-me um pouco mais sobre isso?",
    "nl": "Kunt u daar iets meer over vertellen?",
    "ja": "その点について、もう少し詳しく教えていただけますか？",
    "ko": "그 부분에 대해 조금 더 자세히 말씀해 주시겠어요?",
    "zh": "您能再多说一点吗？",
}


def _fallback_follow_up(language_code: str | None) -> str:
    code = (language_code or "en").lower()
    return FALLBACK_FOLLOW_UPS.get(code, FALLBACK_FOLLOW_UPS.get(code[:2], FALLBACK_FOLLOW_UPS["en"]))


def _closing_message(language_code: str | None) -> str:
    code = (language_code or "en").lower()
    return CLOSING_MESSAGES.get(code, CLOSING_MESSAGES["en"])


def _effective_system_prompt(system_prompt: str | None, language_code: str | None) -> str:
    """Combine the engine's methodology with the study's own instructions.

    The researcher-editable ``Project.system_prompt`` used to REPLACE this
    module's ``INTERVIEWER_SYSTEM_PROMPT`` (``system_prompt or INTERVIEWER_...``).
    Because every project row is created with the generic
    ``DEFAULT_SYSTEM_PROMPT`` boilerplate, that meant the operational contract
    (decision rules, probing toolkit, continuity rules, close gate, end_early)
    was silently dropped on essentially every real interview. The study prompt
    is study-specific flavour, so it is now layered ON TOP of the methodology
    and explicitly cannot override it. Untouched default boilerplate is
    dropped entirely rather than sent as noise.
    """
    from app.models.project import DEFAULT_SYSTEM_PROMPT

    base = INTERVIEWER_SYSTEM_PROMPT
    custom = (system_prompt or "").strip()
    if custom and custom != DEFAULT_SYSTEM_PROMPT.strip():
        base += (
            "\n\n<researcher_instructions>\n"
            f"{custom}\n\n"
            "These are the researcher's study-specific instructions. Follow them for tone, "
            "focus, and emphasis. They never override the decision rules, the continuity "
            "rules, the probing guidance, or the close gate above.\n"
            "</researcher_instructions>"
        )
    return base + _language_instruction(language_code)


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
        f"\n\nIMPORTANT, Language: You MUST conduct this entire interview in {name}. "
        f"Ask every question in {name}, even if the interview guide questions are "
        f"written in another language (translate them naturally as you go). "
        f"If the participant replies in a different language, gently continue in {name} "
        f"unless they explicitly ask to switch. Keep your tone warm and idiomatic: "
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
    profile = None
    if email:
        profile = db.query(PanelProfile).filter(PanelProfile.email == email).first()
    if profile is None:
        # No panel profile: fall back to what the participant typed on the
        # landing page / post-interview profile. Same advisory use.
        bits: list[str] = []
        if getattr(participant, "age_range", None):
            bits.append(f"{participant.age_range} years old")
        if getattr(participant, "profession", None):
            bits.append(f"works as {participant.profession}")
        if getattr(participant, "country", None):
            bits.append(f"based in {participant.country}")
        return ", ".join(bits) if bits else None

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


# A single gap between two turns longer than this is a break, not interview
# time: the participant paused, took a call, locked the phone, or walked away.
# Counting it would make the engine think it is hopelessly behind, which fires
# the pace guard on every remaining turn and rushes a shallow interview.
MAX_TURN_GAP_MINUTES = 5.0


def _active_elapsed_minutes(participant, turns: list, now: datetime) -> float:
    """Interview time actually spent, with long breaks excluded.

    Sums the gaps between consecutive turns (and the open gap since the last
    question), capping each at ``MAX_TURN_GAP_MINUTES``. Thinking time inside
    a turn still counts in full up to that cap, so a slow, considered
    participant is never penalised: only real absences are discounted.
    Derived entirely from server-side timestamps, so a participant cannot
    claim extra time by reporting a long pause.
    """
    def _naive(dt):
        return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo is not None else dt

    # The warm-up is a courtesy turn, not research time: the pacing clock
    # starts when the first real guide question is asked. Without this, a
    # short interview with many questions (say 10 questions in 10 minutes)
    # would be flagged "behind schedule" from its very first answer purely
    # because the icebreaker took a minute.
    real_turns = [t for t in turns if (t.question_index or 0) >= 0 and t.created_at is not None]
    started = _naive(participant.started_at) or now
    if real_turns:
        started = _naive(real_turns[0].created_at) or started
    elif turns:
        # Still in the warm-up: no research time has been spent yet.
        return 0.0

    marks = [started]
    marks.extend(
        _naive(t.created_at) for t in turns
        if t.created_at is not None and _naive(t.created_at) > started
    )
    marks.append(now)

    total = 0.0
    previous = marks[0]
    for mark in marks[1:]:
        gap = (mark - previous).total_seconds() / 60.0
        if gap > 0:
            total += min(gap, MAX_TURN_GAP_MINUTES)
            previous = mark
        elif mark > previous:
            previous = mark
    return total


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

    # Coverage map — turns store the GLOBAL ordinal (position in the flattened
    # guide) in question_index, but the guide the model reads is numbered
    # per-section, so the model can't tell where it is. Spell it out: which
    # guide questions are already covered (never re-ask) and the single next
    # uncovered one to advance to. This prevents the model re-greeting +
    # re-asking the opening question.
    covered_global = sorted(
        i for i in asked_indices if i is not None and 0 <= i < total_questions
    )
    covered_lines = [
        f"  ✓ Guide question {i + 1}: {guide_questions[i].main_question}"
        for i in covered_global
    ]
    next_global = current_question_index + 1
    if next_global < total_questions:
        next_line = (
            f"  → Guide question {next_global + 1}: "
            f"{guide_questions[next_global].main_question}"
        )
    else:
        next_line = "  (all guide questions have been asked, no next question remains)"
    current_learning_goal = None
    section_change_hint = None
    next_question_text = None
    if 0 <= current_question_index < total_questions:
        cur_q = guide_questions[current_question_index]
        current_learning_goal = (cur_q.desired_learning or "").strip() or None
        if next_global < total_questions:
            nxt = guide_questions[next_global]
            next_question_text = nxt.main_question
            if nxt.section_index != cur_q.section_index and nxt.section_title:
                section_change_hint = (
                    f"The next guide question opens a NEW section ({nxt.section_title}): "
                    "mark the shift in a few words when you get there."
                )
    elif total_questions and current_question_index < 0:
        next_question_text = guide_questions[0].main_question
    final_check_asked = any(t.question_index == FINAL_CHECK_QUESTION_INDEX for t in turns)
    coverage_block = (
        "<coverage>\n"
        "Already asked. NEVER ask any of these again (not even reworded), and "
        "do NOT re-open with a greeting:\n"
        + ("\n".join(covered_lines) if covered_lines else "  (none yet)")
        + "\n\nWhen you choose next_question, the ONLY topic to move to is:\n"
        + next_line
        + "\n</coverage>"
    )

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
    elapsed = _active_elapsed_minutes(participant, turns, now)

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
        "coverage_block": coverage_block,
        "elapsed_minutes": elapsed,
        "current_question_index": current_question_index,
        "total_minutes": project.interview_duration_minutes,
        "all_questions_done": all_questions_done,
        "system_prompt": project.system_prompt,
        "language": language,
        "participant_profile": _build_participant_profile_context(participant, db),
        "current_learning_goal": current_learning_goal,
        "section_change_hint": section_change_hint,
        "next_question_text": next_question_text,
        "final_check_asked": final_check_asked,
        "project": project,
        "participant": participant,
        "turns": turns,
        "total_questions": total_questions,
    }


VALID_ACTIONS = ("follow_up", "next_question", "close", "end_early")

# Structured-output tool: the model must call this instead of emitting free
# text, which removes the JSON-parsing fragility (preambles, fences, unknown
# keys) that used to let a stray sentence reach the participant's ears.
DECISION_TOOL = {
    "name": "interview_decision",
    "description": "Choose the next interviewer action and the exact words the participant will hear.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(VALID_ACTIONS)},
            "probe": {
                "type": "string",
                "description": "Which probing technique the question uses (follow_up only), e.g. specific_moment, laddering, contrast, reflect_back, counter_example, unpack_term, walk_through, none.",
            },
            "stop_quote": {
                "type": "string",
                "description": "REQUIRED for end_early: the participant's own words, copied verbatim from their latest answer, that ask to stop the interview. Never paraphrase or invent. If they only finished a topic rather than the session, do not use end_early.",
            },
            "learning_goals_met": {
                "type": "boolean",
                "description": "Whether the current guide question's desired learning is now covered by the conversation.",
            },
            "question": {
                "type": "string",
                "description": "The spoken text the participant will hear. One question, conversational, no dashes.",
            },
            "coaching": {
                "type": "string",
                "description": "Optional: one short warm tip for the participant (only when the host asks for it).",
            },
        },
        "required": ["action", "question"],
    },
}


class InterviewAIUnavailable(RuntimeError):
    """Raised when Claude could not be reached after retries."""


def _decision_fallback(
    *,
    has_next_question: bool,
    can_close: bool,
    language: str | None,
    next_question_text: str | None = None,
) -> dict:
    """Deterministic decision when the model is unreachable or misbehaves.

    Keeps the interview moving instead of surfacing a 500 to the participant:
    advance to the next guide question (verbatim, with a spoken bridge), close
    if the gate is open, otherwise ask a neutral follow-up.
    """
    if has_next_question and next_question_text:
        return {
            "action": "next_question",
            "question": f"{_bridge_to_next(language)} {next_question_text}",
            "coaching": None,
            "fallback": True,
        }
    if can_close:
        return {"action": "close", "question": _closing_message(language), "coaching": None, "fallback": True}
    return {"action": "follow_up", "question": _fallback_follow_up(language), "coaching": None, "fallback": True}


def decide_next_action(
    system_prompt: str,
    interview_guide_str: str,
    conversation_history: str,
    current_question_index: int,
    elapsed_minutes: float,
    total_minutes: int,
    all_questions_done: bool,
    total_questions: int = 0,
    coverage_block: str = "",
    research_objective: str | None = None,
    language: str | None = None,
    short_answer_state: dict | None = None,
    participant_profile: str | None = None,
    db=None,
    company_id=None,
    project_id=None,
    participant_id=None,
    forced_action: str | None = None,
    after_final_check: bool = False,
    current_learning_goal: str | None = None,
    section_change_hint: str | None = None,
) -> dict:
    """Call Claude to decide the next interview action.

    Returns a dict with keys: action (one of VALID_ACTIONS), question (str),
    coaching (str | None), probe (str | None), learning_goals_met (bool | None).

    ``forced_action`` is set by the host guards (pace / follow-up cap / close
    gate) when the model's previous choice was overridden: the model is asked
    to write the best wording for that action rather than us speaking a
    follow-up while silently advancing the guide. ``after_final_check`` tells
    the model the closing check question has been asked and answered, so it
    may close now (or ask one follow-up if the participant raised something
    new). Raises ``InterviewAIUnavailable`` after exhausting retries.
    """
    client = get_anthropic_client(60.0)

    pacing_known = total_minutes > 0
    time_used_pct = (elapsed_minutes / total_minutes * 100) if pacing_known else 0.0
    questions_answered = current_question_index + 1
    remaining_minutes = max(0.0, total_minutes - elapsed_minutes)

    if total_questions > 0 and total_minutes > 0:
        baseline_minutes_per_question = total_minutes / total_questions
        expected_q_index = elapsed_minutes / baseline_minutes_per_question
        pace_delta = current_question_index - expected_q_index  # positive = ahead
        questions_remaining = max(0, total_questions - current_question_index - 1)
        adaptive_minutes_per_question = remaining_minutes / (questions_remaining + 1)
        pace_ratio = adaptive_minutes_per_question / baseline_minutes_per_question
        slack_minutes = remaining_minutes - (questions_remaining * baseline_minutes_per_question)
    else:
        pace_delta = 0.0
        pace_ratio = 1.0
        slack_minutes = remaining_minutes

    if pace_delta < -1.5:
        pacing_instruction = (
            "PACING ALERT: You are significantly behind schedule. "
            "Move to the NEXT main guide question now, with a one-sentence callback so the shift feels natural. "
            "Do NOT ask a follow-up."
        )
    elif pace_delta < -0.5:
        pacing_instruction = (
            "PACING: You are slightly behind schedule. "
            "Only ask a follow-up if the participant's answer was genuinely too brief or unclear. "
            "Otherwise move to the next main question now."
        )
    elif pace_ratio >= 1.25:
        pacing_instruction = (
            "PACING: You are ahead of schedule, each remaining question has extra time. "
            "PREFER to stay on the current question and probe deeper (a concrete example, "
            "the story behind the answer, the emotion underneath) rather than advancing. "
            "Only move to the next main question once this topic is genuinely exhausted."
        )
    else:
        fu_word = "may" if slack_minutes > 0 else "should not"
        pacing_instruction = (
            f"PACING: You are on schedule. "
            f"You {fu_word} ask one follow-up if it genuinely adds value, then move to the next question."
        )

    if pacing_known:
        can_close = all_questions_done or time_used_pct >= 95.0
        can_close = can_close and (time_used_pct >= 80.0)
    else:
        can_close = all_questions_done

    if after_final_check:
        close_instruction = (
            '3. "close": OPEN. You already asked the closing check ("anything we haven\'t covered?") and the '
            "participant answered. If they raised something genuinely new and worth one question, you may ask ONE "
            "follow_up; otherwise close now, thanking them for something specific they shared."
        )
        can_close = True
    elif can_close:
        close_instruction = '3. "close": the interview is complete (all questions covered and/or time is up); wrap up warmly'
    else:
        close_instruction = (
            '3. "close": NOT available yet. '
            f'Only {elapsed_minutes:.1f} of {total_minutes} minutes have elapsed '
            f'({questions_answered} of {total_questions} questions reached). '
            'Keep the conversation going.'
        )

    objective_block = ""
    if research_objective:
        objective_block = (
            f"<objective>\n{research_objective}\n\n"
            "Keep this objective top of mind: probe for the job-to-be-done behind behaviours, "
            "amplify emotional language, and steer toward concrete examples, without breaking "
            "the conversational flow.\n</objective>\n\n"
        )

    examples_block = """<examples>
PARTICIPANT: "It was kind of frustrating when the import didn't work."
DECISION: follow_up (probe: specific_moment)
QUESTION: "Can you tell me what was happening right before you tried that import?"
WHY: emotional language + concrete claim, no story yet: unpack before moving on.

PARTICIPANT: "Yeah, I use it every Monday morning. I open the dashboard, scan for anything red, then ping the team in Slack. Takes about ten minutes."
DECISION: next_question
QUESTION: "That ten-minute Monday scan is really useful to hear. Shifting gears: could you walk me through the last time you onboarded a new teammate?"
WHY: concrete behaviour with detail; learning goal met; open with a callback ("ten-minute Monday scan") then transition.

PARTICIPANT: "It's fine."
DECISION: follow_up (probe: unpack_term)
QUESTION: "What does 'fine' look like for you on a typical day with it?"
WHY: generic answer with no behaviour or example.

PARTICIPANT: "Sorry, is this being recorded by a real person or a bot?"
DECISION: follow_up (probe: none)
QUESTION: "Fair question: I'm an AI interviewer, and the research team reads every conversation afterwards. Going back to your Monday routine, what usually happens after you ping the team?"
WHY: answer honestly in one sentence, then return to the topic.

PARTICIPANT: "Honestly I need to go, can we stop here?"
DECISION: end_early
QUESTION: "Of course, thank you so much for the time you gave us today, what you shared about the Monday scan is genuinely useful. Take care."
WHY: they asked to stop; never negotiate.
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

    # Volatile, per-turn user message. Everything stable (system prompt,
    # examples, objective, participant, guide) lives in cached system blocks.
    user_message = (
        f"{coverage_block + chr(10) + chr(10) if coverage_block else ''}"
        f"<conversation>\n{conversation_history}\n</conversation>\n\n"
        f"<state>\n"
        f"- Questions reached: {questions_answered} of {total_questions}\n"
        f"- Elapsed: {elapsed_minutes:.1f} / {total_minutes} min ({time_used_pct:.0f}% used, {remaining_minutes:.1f} min left)\n"
        f"- All main questions covered: {all_questions_done}\n"
        + (f"- Learning goal for the CURRENT question: {current_learning_goal}\n" if current_learning_goal else "")
        + (f"- {section_change_hint}\n" if section_change_hint else "")
        + f"- {pacing_instruction}\n"
        f"- Close gate: {'OPEN, you may close' if (can_close and not after_final_check) else close_instruction}\n"
        f"</state>\n\n"
    )

    if short_answer_state and short_answer_state.get("is_short_run") and pace_delta >= -0.5 and not forced_action:
        run = short_answer_state.get("run_length", 0)
        last_w = short_answer_state.get("last_words")
        user_message += (
            f"<engagement>\n"
            f"The participant's last {run} answer(s) were short "
            f"(most recent: ~{last_w} words). "
            f"Prefer a more open, specific follow-up that invites a story or example "
            f"(e.g. 'Walk me through the last time…', 'Tell me about a moment when…') "
            f"instead of moving to the next question.\n"
            f"ALSO fill the \"coaching\" field: one short, warm sentence "
            f"(max ~25 words, in the interview language) shown to the participant as a tip, "
            f"gently inviting a concrete story or example about the current topic. "
            f"Never mention answer length, evaluation, or that they are doing anything wrong.\n"
            f"</engagement>\n\n"
        )

    if forced_action:
        user_message += (
            f"<host_override>\n"
            f"The host system requires action = {forced_action} for this turn. Do not choose anything else. "
            f"Write the most natural wording for it: "
            + (
                "a one-sentence callback to what they just said, then the next uncovered guide question."
                if forced_action == "next_question"
                else "a warm, specific wrap-up."
                if forced_action == "close"
                else "one probing question on the current topic."
            )
            + "\n</host_override>\n\n"
        )

    user_message += "Decide the next action and write the words the participant will hear, via the interview_decision tool."

    base_system = _effective_system_prompt(system_prompt, language)
    stable_context = (
        f"{examples_block}\n\n{objective_block}{participant_block}<guide>\n{interview_guide_str}\n</guide>"
    )
    system_blocks = [
        {"type": "text", "text": base_system, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": stable_context, "cache_control": {"type": "ephemeral"}},
    ]

    import time as _time

    _max_retries = 2
    response = None
    for _attempt in range(_max_retries + 1):
        try:
            response = client.messages.create(
                model=ai_models.sonnet(),
                max_tokens=512,
                **ai_models.temperature_kwargs(ai_models.sonnet(), 0.4),
                system=system_blocks,
                tools=[DECISION_TOOL],
                tool_choice={"type": "tool", "name": "interview_decision"},
                messages=[{"role": "user", "content": user_message}],
            )
            break
        except (
            anthropic.APIStatusError,
            anthropic.APIConnectionError,
            httpx.TimeoutException,
        ) as exc:
            if _attempt < _max_retries:
                _time.sleep(1.5 ** _attempt)
                continue
            raise InterviewAIUnavailable(
                "Interview AI temporarily unavailable, please retry."
            ) from exc

    if db is not None:
        log_claude_usage(
            db, response, "interview_turn",
            company_id=company_id, project_id=project_id, participant_id=participant_id,
        )

    result = _parse_decision_response(response, language)

    if forced_action and result["action"] != forced_action:
        # The model disobeyed the host override: keep its wording only if it
        # is compatible, otherwise the caller falls back deterministically.
        result["action"] = forced_action
        result["disobeyed_override"] = True
    return result


def _parse_decision_response(response, language: str | None) -> dict:
    """Extract the decision from a tool_use block, with a text fallback."""
    result: dict | None = None
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and isinstance(getattr(block, "input", None), dict):
            result = dict(block.input)
            break

    if result is None:
        raw_text = ""
        for block in getattr(response, "content", None) or []:
            if getattr(block, "type", None) == "text":
                raw_text += getattr(block, "text", "") or ""
        text_to_parse = raw_text.strip()
        if text_to_parse.startswith("```"):
            lines = [l for l in text_to_parse.split("\n") if not l.strip().startswith("```")]
            text_to_parse = "\n".join(lines).strip()
        try:
            parsed = json.loads(text_to_parse)
            result = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            # Never speak unparsed model output: fall back to a neutral probe.
            result = {}

    action = result.get("action")
    if action not in VALID_ACTIONS:
        action = "follow_up"
    question = result.get("question")
    if not isinstance(question, str) or not question.strip():
        question = _fallback_follow_up(language)
    out = {
        "action": action,
        "question": _strip_banned_dashes(question.strip()),
        "stop_quote": result.get("stop_quote") if isinstance(result.get("stop_quote"), str) else None,
        "coaching": _sanitize_coaching(result.get("coaching")),
        "probe": result.get("probe") if isinstance(result.get("probe"), str) else None,
        "learning_goals_met": result.get("learning_goals_met") if isinstance(result.get("learning_goals_met"), bool) else None,
    }
    return out


_BANNED_DASH_RE = re.compile(r"\s*(?:—|–|--)\s*")


def _strip_banned_dashes(text: str) -> str:
    """Em/en dashes and double hyphens are banned from user-facing copy (see
    CLAUDE.md Copy Conventions). The prompts instruct the model; this
    guarantees it on everything the participant hears or reads."""
    if not text or not _BANNED_DASH_RE.search(text):
        return text
    # After sentence punctuation the dash is redundant: drop it.
    text = re.sub(r"([,;:.!?…])\s*(?:—|–|--)\s*", r"\1 ", text)
    # Between words it reads as a comma.
    return _BANNED_DASH_RE.sub(", ", text)


def _sanitize_coaching(value) -> str | None:
    """Whitelist a model-produced coaching line for direct participant display."""
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    if not value or len(value) > 240:
        return None
    return _strip_banned_dashes(value)


# Sentinel used in InterviewTurn.question_index to mark the warm-up turn
# (which isn't part of the guide). The next turn after a warm-up always
# advances to guide question 0 — the AI's decide-next-action step is
# skipped because the warm-up isn't a research probe.
WARMUP_QUESTION_INDEX = -1
# Sentinel question_index for the closing check ("anything we haven't
# covered?") asked once before the interview closes. Like the warm-up it is
# a non-counting turn: the frontend hides the progress counter for any
# negative question_index.
FINAL_CHECK_QUESTION_INDEX = -2

FINAL_CHECK_QUESTIONS: dict[str, str] = {
    "en": "Before we wrap up: is there anything we haven't covered that you expected to talk about, or anything you'd like to add?",
    "fr": "Avant de conclure : y a-t-il un sujet que nous n'avons pas abordé et dont vous pensiez parler, ou quelque chose que vous aimeriez ajouter ?",
    "es": "Antes de terminar: ¿hay algo que no hayamos tratado y que esperaba comentar, o algo que le gustaría añadir?",
    "de": "Bevor wir zum Ende kommen: Gibt es etwas, das wir nicht besprochen haben und das Sie erwartet hätten, oder möchten Sie noch etwas ergänzen?",
    "it": "Prima di concludere: c'è qualcosa che non abbiamo trattato e di cui pensava di parlare, o qualcosa che vorrebbe aggiungere?",
    "pt": "Antes de terminarmos: há algo que não abordámos e que esperava discutir, ou algo que gostaria de acrescentar?",
    "nl": "Voordat we afronden: is er iets dat we niet hebben besproken en dat u had verwacht, of wilt u nog iets toevoegen?",
    "ja": "最後に、まだ触れていないけれど話したいと思っていたことや、付け加えたいことはありますか？",
    "ko": "마무리하기 전에, 다루지 않았지만 이야기하고 싶었던 주제나 덧붙이고 싶은 말씀이 있으신가요?",
    "zh": "在结束之前：有没有我们还没谈到、但您原本想聊的内容，或者您想补充的？",
}

# Spoken bridges used when the host system overrides the model's action and a
# regeneration call is unavailable. Deterministic, short, localized.
BRIDGE_TO_NEXT: dict[str, str] = {
    "en": "Thank you, that's helpful. Let's move to the next topic.",
    "fr": "Merci, c'est très utile. Passons au sujet suivant.",
    "es": "Gracias, es muy útil. Pasemos al siguiente tema.",
    "de": "Danke, das hilft sehr. Kommen wir zum nächsten Thema.",
    "it": "Grazie, è molto utile. Passiamo al prossimo argomento.",
    "pt": "Obrigado, é muito útil. Passemos ao próximo tema.",
    "nl": "Dank u, dat helpt. Laten we naar het volgende onderwerp gaan.",
    "ja": "ありがとうございます。次のテーマに移りましょう。",
    "ko": "감사합니다. 다음 주제로 넘어가겠습니다.",
    "zh": "谢谢，这很有帮助。我们进入下一个话题。",
}


def _final_check_question(language_code: str | None) -> str:
    code = (language_code or "en").lower()
    return FINAL_CHECK_QUESTIONS.get(code, FINAL_CHECK_QUESTIONS.get(code[:2], FINAL_CHECK_QUESTIONS["en"]))


def _bridge_to_next(language_code: str | None) -> str:
    code = (language_code or "en").lower()
    return BRIDGE_TO_NEXT.get(code, BRIDGE_TO_NEXT.get(code[:2], BRIDGE_TO_NEXT["en"]))

# PF-3 thresholds. Tuned for typical interview pacing — anything tighter
# fires on legitimate short answers ("yes", "every day"), anything looser
# misses the actual signal of a disengaging participant.
SHORT_ANSWER_WORDS = 15
SHORT_ANSWER_RUN = 2  # need this many short answers in a row to flag
# Participant-facing hints are shown only when a short run *starts* (not on
# every turn the run continues) and at most this many times per interview —
# a tip repeated more often reads as nagging and gets banner-blindness.
MAX_COACHING_HINTS = 2


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
        return {"is_short_run": False, "last_words": None, "run_length": 0, "is_run_start": False, "run_starts": 0}

    def _wc(t):
        return len((t.response_transcript or "").split())

    last_words = _wc(answered[-1])
    run = 0
    for t in reversed(answered):
        if _wc(t) <= SHORT_ANSWER_WORDS:
            run += 1
        else:
            break

    # Count how many distinct short runs have *started* across the whole
    # interview (a streak hitting exactly SHORT_ANSWER_RUN). This is what
    # gates the participant-facing hint: show it when a run starts, skip it
    # while the run merely continues, and cap total hints per interview.
    run_starts = 0
    streak = 0
    for t in answered:
        if _wc(t) <= SHORT_ANSWER_WORDS:
            streak += 1
            if streak == SHORT_ANSWER_RUN:
                run_starts += 1
        else:
            streak = 0

    return {
        "is_short_run": run >= SHORT_ANSWER_RUN,
        "last_words": last_words,
        "run_length": run,
        "is_run_start": run == SHORT_ANSWER_RUN,
        "run_starts": run_starts,
    }


def _should_show_coaching(state: dict) -> bool:
    """Participant hint gate: only at the turn a short run starts, capped."""
    return (
        bool(state.get("is_short_run"))
        and bool(state.get("is_run_start"))
        and state.get("run_starts", 0) <= MAX_COACHING_HINTS
    )


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
        "es": "Los investigadores aprenden más de momentos específicos. Si le viene a la mente un ejemplo, tómese su tiempo para contarlo.",
        "de": "Forscher lernen am meisten aus konkreten Momenten. Wenn Ihnen eine Geschichte oder ein Beispiel einfällt, nehmen Sie sich Zeit, es zu erzählen.",
        "it": "I ricercatori imparano soprattutto dai momenti concreti. Se le viene in mente un esempio o un aneddoto, si prenda pure il tempo di raccontarlo.",
        "pt": "Os investigadores aprendem sobretudo com momentos concretos. Se lhe ocorrer um exemplo ou uma história, tome o seu tempo para a contar.",
        "nl": "Onderzoekers leren het meest van concrete momenten. Als u een voorbeeld of verhaal te binnen schiet, neem gerust de tijd om het te delen.",
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
        "en": "Welcome! Before we dive into the questions, could you tell me a bit about your typical week, just so we ease in?",
        "fr": "Bienvenue ! Avant d'entrer dans les questions, pourriez-vous me parler un peu de votre semaine type, juste pour démarrer en douceur ?",
        "es": "¡Bienvenido! Antes de entrar en las preguntas, ¿podría contarme un poco de su semana típica para empezar con calma?",
        "de": "Willkommen! Bevor wir zu den Fragen kommen, könnten Sie mir kurz von Ihrer typischen Woche erzählen, einfach zum Einstieg?",
        "it": "Benvenuto! Prima di entrare nelle domande, può raccontarmi un po' della sua settimana tipo, giusto per iniziare?",
        "pt": "Bem-vindo! Antes de entrar nas perguntas, poderia me contar um pouco sobre sua semana típica, só para começar?",
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

    # The first guide question follows immediately after the warm-up. The
    # warm-up MUST NOT overlap with it, or the participant hears the same
    # question twice in a row (classic case: warm-up "what do you do
    # day-to-day?" followed by guide Q1 "tell me about your role").
    guide_questions = sorted(
        [q for q in project.guide_questions if not getattr(q, "deprecated_at", None)],
        key=lambda q: (q.section_index, q.question_index),
    )
    first_guide_q = guide_questions[0].main_question if guide_questions else ""

    try:
        client = get_anthropic_client(60.0)
        effective_system_prompt = _effective_system_prompt(
        getattr(project, "system_prompt", None), language_code
    )
        avoid_block = (
            f"\n\nThe FIRST real interview question, asked right after your warm-up, will be:\n"
            f'"{first_guide_q[:300]}"\n'
            f"Your warm-up must NOT overlap with it in any way. If that question already asks "
            f"about their role, work, or daily routine, pick a different low-stakes angle "
            f"(e.g. how they came across this topic, or the setting they are in). The "
            f"participant must never feel asked the same thing twice."
            if first_guide_q
            else ""
        )
        response = client.messages.create(
            model=ai_models.sonnet(),
            max_tokens=180,
            **ai_models.temperature_kwargs(ai_models.sonnet(), 0.6),
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
                        f"topic, something they can answer without thinking hard. Avoid 'why'. "
                        f"Avoid asking for opinions or evaluations. Under 28 words. "
                        f"Return ONLY the spoken text, no JSON, no quotes, no preamble."
                        f"{avoid_block}"
                    ),
                }
            ],
        )
        text = _strip_banned_dashes(response.content[0].text.strip())
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
    warmup_exchange: tuple[str, str] | None = None,
) -> tuple[str, int]:
    """Get the first non-deprecated question from the interview guide, rephrased as an opener.

    When ``warmup_exchange`` is provided (the warm-up question and the
    participant's answer), the conversation has already started: the rephrase
    must NOT re-greet, and must acknowledge the answer instead of re-asking
    anything it already covered.
    """
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

    effective_system_prompt = _effective_system_prompt(
        getattr(project, "system_prompt", None), language_code
    )

    if warmup_exchange:
        warmup_q, warmup_a = warmup_exchange
        user_prompt = (
            f"You are mid-interview. You already welcomed the participant with this warm-up:\n"
            f'"{warmup_q[:300]}"\n'
            f"and they answered:\n"
            f'"{(warmup_a or "")[:600]}"\n\n'
            f"The first question from the guide is:\n"
            f'"{first_q.main_question}"\n\n'
            f"Continue the conversation in {language_name}. Do NOT greet again (no welcome, "
            f'no "to start with"): open with a few words acknowledging something specific '
            f"they just said, then ask the guide question conversationally. If their answer "
            f"already covered part of the guide question, do not re-ask that part: go one "
            f"level deeper on what they said instead. Avoid 'why'. Single concept. "
            f"Under 35 words. Return ONLY the spoken text, no JSON, no quotes, no preamble."
        )
    else:
        user_prompt = (
            f"You are starting an interview. The first question from the guide is:\n"
            f'"{first_q.main_question}"\n\n'
            f"Rephrase as a warm, natural OPENER in {language_name}. One short sentence "
            f"of welcome (no name needed), then the question, phrased conversationally. "
            f"Avoid 'why'. Single concept. Under 30 words. "
            f"Return ONLY the spoken text, no JSON, no quotes, no preamble."
        )

    response = client.messages.create(
        model=ai_models.sonnet(),
        max_tokens=256,
        **ai_models.temperature_kwargs(ai_models.sonnet(), 0.5),
        system=effective_system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    question_text = _strip_banned_dashes(response.content[0].text.strip())

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
        if settings.INTERVIEW_DEFER_TTS:
            raise _DeferTTS()
        tts_key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
        tts_audio_url = upload_audio(
            generate_speech(question_text, language=participant_lang or getattr(project, "language", None)),
            tts_key,
        )
        log_tts_usage(db, question_text, company_id=company_id, project_id=proj_id, participant_id=participant_id)
    except _DeferTTS:
        pass
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
        "turn_index": turn.turn_index,
        "is_warmup": use_warmup,
    }


def _lock_participant(db: Session, participant_id: str):
    """Fetch the participant, serialising concurrent turns for that person.

    Two overlapping /respond calls (an HTTP retry, a second tab, a proxy
    replay) would otherwise both see the same unanswered pending turn, both
    transcribe, and both append a turn at ``turns[-1].turn_index + 1``,
    producing two turns sharing an index. This used to be masked by the
    handler being ``async def`` with a blocking body, which accidentally
    serialised every request on the event loop; moving the work to a
    threadpool removed that side effect, so take the lock explicitly.

    SQLite has no row locks (and is single-writer anyway), so the clause is
    only emitted on Postgres.
    """
    query = db.query(Participant).filter(Participant.id == participant_id)
    try:
        if db.get_bind().dialect.name == "postgresql":
            query = query.with_for_update()
    except Exception:  # pragma: no cover - defensive, bind always resolves
        pass
    return query.first()


def _stt_glossary(project) -> str:
    """Whisper decoding hint: the study's proper nouns and domain terms.

    Whisper's ``prompt`` biases decoding toward the spellings it contains,
    so "Air France" is heard as "Air France" rather than "la France". We
    feed the study name, audience, and context (not the guide: a long
    prompt dilutes the effect and the window is ~224 tokens).
    """
    parts = [
        getattr(project, "name", None),
        getattr(project, "target_customer_description", None),
        getattr(project, "research_context", None),
    ]
    text = ". ".join(p.strip() for p in parts if p and p.strip())
    return text[:800]


def _cached_tts(text: str, language: str | None) -> str | None:
    """TTS for static lines (closings, checks): rendered once per text+voice.

    Returns the playback URL, or None when TTS/storage are unavailable.
    """
    import hashlib
    from app.services.storage import audio_exists, public_url_for

    digest = hashlib.sha256(
        f"{settings.TTS_MODEL}|{settings.TTS_VOICE}|{language or ''}|{text}".encode("utf-8")
    ).hexdigest()
    key = f"tts/shared/{digest}.mp3"
    try:
        if audio_exists(key):
            return public_url_for(key)
        return upload_audio(generate_speech(text, language=language), key)
    except Exception:
        logger.exception("Cached TTS failed for shared line; continuing text-only")
        return None


def _spawn_completion_side_effects(participant_id: str) -> None:
    """Everything that used to run inline on the completion turn and only
    slowed the participant's last response down: lifecycle emails, the
    participant's completion email, the AI quality pass, tag suggestions.
    Daemon thread, fresh session, every step best-effort."""
    import threading as _threading

    def _run():
        try:
            from app.database import session_scope
            from app.models.coding import ManualCode
            from app.models.company import Company
            from app.models.project import Project
            from app.models.interview import Participant as _Participant

            with session_scope() as sdb:
                participant = sdb.query(_Participant).filter(_Participant.id == participant_id).first()
                if participant is None:
                    return
                project = participant.project
                company = project.company if project else None

                # "Your first response is in" (once per workspace).
                try:
                    if company is not None and company.email and company.first_response_email_sent_at is None:
                        from app.services.email import send_first_response_in
                        lang = company.preferred_language or "en"
                        send_first_response_in(
                            to=company.email,
                            project_name=project.name if project else ("votre étude" if lang.startswith("fr") else "your study"),
                            project_url=f"{settings.APP_BASE_URL}/projects/{project.id}?tab=responses" if project else settings.APP_BASE_URL,
                            lang=lang,
                        )
                        company.first_response_email_sent_at = datetime.utcnow()
                        sdb.commit()
                except Exception:
                    logger.exception("First-response email failed for participant %s", participant_id)

                # Free-preview-full paywall milestone (once per workspace).
                try:
                    from app.services.paywall import FREE_PREVIEW_COUNT
                    paid = bool(company and (company.has_ever_paid or (company.subscription_status or "") in ("active", "past_due")))
                    if company is not None and company.email and not paid and company.free_preview_full_email_sent_at is None:
                        completed_count = (
                            sdb.query(_Participant)
                            .join(Project, _Participant.project_id == Project.id)
                            .filter(Project.company_id == company.id, Project.is_demo.is_(False), _Participant.status == "completed")
                            .count()
                        )
                        if completed_count >= FREE_PREVIEW_COUNT:
                            from app.services.email import send_free_preview_full
                            lang = company.preferred_language or "en"
                            send_free_preview_full(
                                to=company.email,
                                project_name=project.name if project else ("votre étude" if lang.startswith("fr") else "your study"),
                                project_url=f"{settings.APP_BASE_URL}/projects/{project.id}?tab=responses" if project else settings.APP_BASE_URL,
                                lang=lang,
                            )
                            company.free_preview_full_email_sent_at = datetime.utcnow()
                            sdb.commit()
                except Exception:
                    logger.exception("Free-preview-full email failed for participant %s", participant_id)

                # Participant completion email.
                try:
                    if participant.email and project is not None:
                        from app.services.email import send_email
                        lang = (getattr(participant, "preferred_language", None) or project.language or "en").lower()[:2]
                        greeting = f" {participant.display_name}" if participant.display_name else ""
                        copy = COMPLETION_EMAILS.get(lang, COMPLETION_EMAILS["en"])
                        send_email(
                            to=participant.email,
                            subject=copy["subject"].format(project_name=project.name),
                            body_html=copy["body"].format(project_name=project.name, greeting=greeting),
                        )
                except Exception:
                    logger.exception("Participant completion email failed for %s", participant_id)

                # AI quality assessment + tag suggestions.
                try:
                    from app.services.quality import run_ai_quality_assessment
                    from app.services.tag_suggestions import suggest_tags_for_participant
                    lang = "en"
                    if company is not None and company.preferred_language:
                        lang = company.preferred_language
                    run_ai_quality_assessment(participant_id, sdb, language=lang)
                    has_codes = (
                        sdb.query(ManualCode).filter(ManualCode.project_id == participant.project_id).first() is not None
                    )
                    if has_codes:
                        suggest_tags_for_participant(participant_id, sdb, language=lang)
                except Exception:
                    logger.exception("Post-completion quality pass failed for %s", participant_id)
        except Exception:
            logger.exception("Completion side effects crashed for %s", participant_id)

    try:
        _threading.Thread(target=_run, daemon=True, name=f"completion-{participant_id[:8]}").start()
    except Exception:
        logger.exception("Could not spawn completion side effects for %s", participant_id)


def _stop_request_is_grounded(stop_quote: str | None, transcript: str | None) -> bool:
    """True when the claimed stop request really appears in what was said.

    The model must copy the participant's own words. We normalise
    punctuation and whitespace, then require either a substring match or a
    strong word overlap (Whisper punctuation and the model's copy can differ
    slightly). A missing or invented quote fails closed: the interview keeps
    going with an ordinary follow-up rather than ending on a misread.
    """
    if not stop_quote or not transcript:
        return False

    def _norm(text: str) -> str:
        return re.sub(r"[^\w\s]", " ", text.lower()).strip()

    quote = re.sub(r"\s+", " ", _norm(stop_quote))
    said = re.sub(r"\s+", " ", _norm(transcript))
    if len(quote) < 3:
        return False
    if quote in said:
        return True

    quote_words = [w for w in quote.split() if len(w) > 2]
    if not quote_words:
        return False
    said_words = set(said.split())
    overlap = sum(1 for w in quote_words if w in said_words)
    return overlap / len(quote_words) >= 0.8


def _answered_main_questions(turns: list) -> int:
    """Distinct guide questions (index >= 0) that received a real answer."""
    return len({
        t.question_index for t in turns
        if t.question_index is not None and t.question_index >= 0
        and t.response_transcript and t.response_transcript.strip() not in ("", "[Skipped]")
    })


def _consume_credit_isolated(billing: dict | None) -> None:
    """Charge one interview credit on its own session, after the turn commits."""
    if not billing:
        return
    try:
        from app.database import session_scope
        from app.services.billing_service import consume_interview_credit

        with session_scope() as bdb:
            consume_interview_credit(
                bdb,
                workspace_id=billing["workspace_id"],
                participant_id=billing["participant_id"],
                project_id=billing["project_id"],
                metadata=billing["metadata"],
            )
    except Exception:  # pragma: no cover - never fail an interview on billing
        logger.exception(
            "Credit consumption failed for participant %s; interview still completed",
            billing.get("participant_id"),
        )


def _mark_completed(participant, db: Session, *, reason: str, bill: bool, completed_via: str) -> dict | None:
    """Flip status, stamp the reason, emit the funnel event, and return the
    billing payload for the caller to charge after the commit (or None).
    Never raises on analytics."""
    participant.status = "completed"
    participant.completed_at = datetime.utcnow()
    participant.completion_reason = reason

    # Billing is deferred to the caller, AFTER the turn commits:
    # consume_interview_credit commits (and on a duplicate rolls back) the
    # session it is handed, which on the request session would discard the
    # just-flushed answer and the pending closing turn. It also sends the
    # usage-warning email inline, which has no business running inside the
    # participant's final turn.
    billing = None
    if bill:
        billing = {
            "participant_id": participant.id,
            "workspace_id": participant.project.company_id,
            "project_id": participant.project_id,
            "metadata": {
                "duration_seconds": int((participant.completed_at - participant.started_at).total_seconds()) if participant.started_at else None,
                "language": participant.project.language if participant.project else None,
                "completed_via": completed_via,
            },
        }

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
            completion_reason=reason,
        )
    except Exception:
        pass

    return billing


def process_interview_turn(
    participant_id: str,
    audio_path: str | None,
    audio_url: str | None,
    db: Session,
    transcript_override: str | None = None,
    audio_bytes: bytes | None = None,
    audio_url_future=None,
) -> dict:
    """Process a participant's answer and generate the next question.

    Orchestrates: transcribe -> save transcript -> context -> Claude decision
    -> host guards -> TTS. ``audio_bytes`` (preferred) avoids re-downloading
    the recording we just uploaded; ``audio_path`` is the storage key used
    only when bytes are not supplied. ``audio_url_future`` is an optional
    object with ``.result()`` resolving to the recording's playback URL (the
    router uploads the recording concurrently with transcription).

    ``transcript_override`` is the accessibility text fallback.

    Returns dict with: question_text, tts_audio_url, is_complete,
    is_follow_up, question_index, turn_index, elapsed_seconds,
    total_seconds, coaching_hint, transcript.
    """
    participant = _lock_participant(db, participant_id)
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    if transcript_override is not None:
        transcript = transcript_override
        audio_duration = 0.0
        segments = None
    else:
        stt_language = (
            getattr(participant, "preferred_language", None)
            or getattr(participant.project, "language", None)
        )
        data = audio_bytes if audio_bytes is not None else download_audio(audio_path)
        filename = os.path.basename(audio_path or "recording.mp3")
        transcript, audio_duration, segments = transcribe_audio(
            data, filename, language=stt_language, prompt=_stt_glossary(participant.project)
        )

    if not transcript or not transcript.strip():
        raise EmptyTranscriptError(
            "No speech detected in the recording. Please try again in a quieter environment."
        )

    _HALLUCINATION_PHRASES = (
        "thank you for watching", "thanks for watching", "please subscribe",
        "like and subscribe", "see you in the next",
        "merci d'avoir regardé", "sous-titres réalisés", "sous-titrage",
        "untertitel der amara", "untertitelung des zdf", "vielen dank fürs zuschauen",
        "gracias por ver el vídeo", "gracias por ver el video", "subtítulos realizados por",
        "sottotitoli e revisione a cura di", "sottotitoli creati dalla comunità",
        "grazie per aver guardato",
        "obrigado por assistir", "legendas pela comunidade",
        "amara.org",
    )
    _lower_transcript = transcript.strip().lower()
    # Only treat the phrase as a hallucination when it IS the answer (short
    # clip), not when a real, longer answer happens to contain the words.
    if (
        transcript_override is None
        and len(_lower_transcript.split()) <= 12
        and any(p in _lower_transcript for p in _HALLUCINATION_PHRASES)
    ):
        raise EmptyTranscriptError(
            "No speech detected in the recording. Please try again in a quieter environment."
        )

    if audio_url_future is not None:
        try:
            audio_url = audio_url_future.result()
        except Exception:
            # One inline retry before giving up: losing the recording costs
            # the researcher the audio permanently, but failing the turn
            # would make the participant re-record an answer we already
            # transcribed. Retry, then keep the transcript either way.
            logger.warning("Recording upload failed for participant %s; retrying once", participant_id)
            audio_url = None
            if audio_path and audio_bytes:
                try:
                    audio_url = upload_audio(audio_bytes, audio_path)
                except Exception:
                    logger.exception(
                        "Recording upload retry failed for participant %s; transcript kept, audio lost",
                        participant_id,
                    )

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    if turns:
        last_turn = turns[-1]
        last_turn.response_transcript = transcript
        last_turn.audio_recording_url = audio_url
        last_turn.response_segments = json.dumps(segments) if segments else None
        # Flushed, not committed: the answer and the next question land in
        # one transaction so a crash mid-turn can't strand an answered turn
        # with no follow-on question.
        db.flush()

    context = get_interview_context(participant_id, db)
    _proj = context["project"]
    _company_id = _proj.company_id
    _project_id = _proj.id
    language = context["language"]

    if transcript_override is None:
        log_stt_usage(
            db, audio_duration,
            company_id=_company_id, project_id=_project_id, participant_id=participant_id,
        )

    def _tts(text: str) -> str | None:
        """Voice for a fresh question.

        With INTERVIEW_DEFER_TTS the synthesis is skipped here and the client
        fetches it from /turn-audio right after rendering the question text,
        so the participant is reading ~2s earlier. Returns None in that case,
        which every caller already treats as "text-only for now".
        """
        if settings.INTERVIEW_DEFER_TTS:
            return None
        key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
        try:
            url = upload_audio(generate_speech(text, language=language), key)
            log_tts_usage(db, text, company_id=_company_id, project_id=_project_id, participant_id=participant_id)
            return url
        except Exception:
            logger.exception("TTS failed for participant %s; continuing text-only", participant_id)
            return None

    def _persist_turn(*, question_text, tts_url, question_index, is_follow_up, follow_up_index=0):
        new_turn = InterviewTurn(
            participant_id=participant_id,
            turn_index=(turns[-1].turn_index + 1) if turns else 0,
            question_index=question_index,
            is_follow_up=is_follow_up,
            follow_up_index=follow_up_index,
            question_text=question_text,
            tts_audio_url=tts_url,
        )
        db.add(new_turn)
        return new_turn

    def _result(new_turn, *, is_complete, coaching_hint=None):
        return {
            "question_text": new_turn.question_text,
            "tts_audio_url": new_turn.tts_audio_url,
            "is_complete": is_complete,
            "is_follow_up": bool(new_turn.is_follow_up),
            "question_index": new_turn.question_index,
            "turn_index": new_turn.turn_index,
            "elapsed_seconds": int(context["elapsed_minutes"] * 60),
            "total_seconds": (context["total_minutes"] or 0) * 60,
            "coaching_hint": coaching_hint,
            "transcript": transcript,
        }

    # Warm-up handoff: play the first real guide question, no Claude decision.
    last_was_warmup = bool(turns) and turns[-1].question_index == WARMUP_QUESTION_INDEX
    if last_was_warmup:
        first_q_text, _ = _get_first_question(
            _proj, db=db, participant_id=participant_id,
            language_override=language,
            warmup_exchange=(turns[-1].question_text or "", transcript or ""),
        )
        new_turn = _persist_turn(question_text=first_q_text, tts_url=_tts(first_q_text), question_index=0, is_follow_up=False)
        db.commit()
        db.refresh(new_turn)
        return _result(new_turn, is_complete=False)

    short_answer_state = _detect_short_answers(turns)
    after_final_check = bool(turns) and turns[-1].question_index == FINAL_CHECK_QUESTION_INDEX

    cur_q = context["current_question_index"]
    total_q = context["total_questions"]
    has_next_question = cur_q < (total_q - 1)
    elapsed = context["elapsed_minutes"]
    total = context["total_minutes"] or 0
    time_used_pct = (elapsed / total * 100) if total > 0 else 0.0
    # Server-side close gate (the backstop). Deliberately laxer than the gate
    # advertised to the model: once the whole guide is genuinely covered we
    # let the interview end rather than forcing filler follow-ups to burn the
    # clock. Time alone can also open it near the end of the budget.
    can_close = (
        context["all_questions_done"]
        or (total > 0 and time_used_pct >= 80.0)
        or after_final_check
    )

    decide_kwargs = dict(
        system_prompt=context["system_prompt"],
        interview_guide_str=context["interview_guide"],
        conversation_history=context["conversation_history"],
        current_question_index=cur_q,
        elapsed_minutes=elapsed,
        total_minutes=context["total_minutes"],
        all_questions_done=context["all_questions_done"],
        total_questions=total_q,
        coverage_block=context.get("coverage_block", ""),
        research_objective=_proj.research_objective,
        language=language,
        short_answer_state=short_answer_state,
        participant_profile=context.get("participant_profile"),
        db=db,
        company_id=_company_id,
        project_id=_project_id,
        participant_id=participant_id,
        after_final_check=after_final_check,
        current_learning_goal=context.get("current_learning_goal"),
        section_change_hint=context.get("section_change_hint"),
    )

    def _fallback():
        return _decision_fallback(
            has_next_question=has_next_question,
            can_close=can_close,
            language=language,
            next_question_text=context.get("next_question_text"),
        )

    try:
        decision = decide_next_action(**decide_kwargs)
    except InterviewAIUnavailable:
        logger.exception("Claude unavailable for participant %s; deterministic fallback", participant_id)
        decision = _fallback()

    # ── Host guards ──────────────────────────────────────────────────────
    # Ending the session is irreversible, so end_early must be grounded in
    # something the participant actually said. Requiring a verbatim quote
    # stops the model from reading "I'm done with this topic" (or an
    # imagined signal) as "I want to stop the interview".
    if decision["action"] == "end_early" and not _stop_request_is_grounded(
        decision.get("stop_quote"), transcript
    ):
        logger.info(
            "end_early rejected for participant %s: stop request not grounded in the answer",
            participant_id,
        )
        decision["action"] = "follow_up"
        decision["question"] = _fallback_follow_up(language)


    # Each guard may change the action. When it does, the wording Claude
    # produced no longer fits (a follow-up spoken while the guide advances
    # silently skips a topic), so we regenerate for the forced action and
    # fall back to deterministic wording if that fails.
    forced: str | None = None
    action = decision["action"]

    if action == "close" and not can_close:
        forced = "next_question" if has_next_question else "follow_up"

    if action == "follow_up" and forced is None and total_q > 0 and total > 0:
        minutes_per_q = total / total_q
        expected_q = elapsed / minutes_per_q
        if (cur_q - expected_q) < -1.5 and has_next_question:
            forced = "next_question"

    if action == "follow_up" and forced is None:
        existing_followups = sum(1 for t in turns if t.question_index == cur_q and t.is_follow_up)
        if existing_followups >= MAX_FOLLOWUPS_PER_QUESTION and has_next_question:
            forced = "next_question"
        elif (
            not has_next_question
            and can_close
            and total > 0
            and time_used_pct >= 100.0
        ):
            # On the last question the follow-up cap is deliberately waived so
            # a rich final topic can breathe, but with the budget fully spent
            # and nowhere left to advance, the model could probe forever.
            forced = "close"

    if forced is not None and forced != action:
        regenerated = None
        if not decision.get("fallback"):
            try:
                regenerated = decide_next_action(**{**decide_kwargs, "forced_action": forced, "short_answer_state": None})
            except InterviewAIUnavailable:
                regenerated = None
        if regenerated is not None and not regenerated.get("disobeyed_override"):
            decision = regenerated
        elif forced == "next_question":
            decision = {
                "action": "next_question",
                "question": f"{_bridge_to_next(language)} {context.get('next_question_text') or ''}".strip(),
                "coaching": None,
            }
        else:
            decision = {"action": forced, "question": _fallback_follow_up(language), "coaching": None}
        action = decision["action"]

    # Closing check: before the first "close", ask once whether anything was
    # missed. The answer is treated like any other turn; on the next turn the
    # model may close (or ask one follow-up if something new came up).
    if action == "close" and not context.get("final_check_asked") and not after_final_check:
        check_text = _final_check_question(language)
        new_turn = _persist_turn(
            question_text=check_text,
            tts_url=_cached_tts(check_text, language),
            question_index=FINAL_CHECK_QUESTION_INDEX,
            is_follow_up=False,
        )
        db.commit()
        db.refresh(new_turn)
        return _result(new_turn, is_complete=False)

    question_text = decision["question"]

    if action == "end_early":
        new_turn = _persist_turn(question_text=question_text, tts_url=_tts(question_text), question_index=cur_q, is_follow_up=False)
        answered = _answered_main_questions(turns)
        billing = _mark_completed(
            participant, db,
            reason="participant_requested",
            # Only bill when at least half of the guide was actually answered:
            # a participant who stops at question one is not a usable interview.
            bill=total_q > 0 and answered * 2 >= total_q,
            completed_via="participant_requested",
        )
        db.commit()
        db.refresh(new_turn)
        _consume_credit_isolated(billing)
        _spawn_completion_side_effects(participant_id)
        return _result(new_turn, is_complete=True)

    billing = None
    if action == "next_question":
        new_turn = _persist_turn(question_text=question_text, tts_url=_tts(question_text), question_index=cur_q + 1, is_follow_up=False)
        is_complete = False
    elif action == "follow_up":
        fu_idx = sum(1 for t in turns if t.question_index == cur_q and t.is_follow_up) + 1
        new_turn = _persist_turn(question_text=question_text, tts_url=_tts(question_text), question_index=cur_q, is_follow_up=True, follow_up_index=fu_idx)
        is_complete = False
    else:  # close
        new_turn = _persist_turn(question_text=question_text, tts_url=_tts(question_text), question_index=cur_q, is_follow_up=False)
        is_complete = True
        billing = _mark_completed(participant, db, reason="natural", bill=True, completed_via="respond")

    db.commit()
    db.refresh(new_turn)

    if is_complete:
        _consume_credit_isolated(billing)
        _spawn_completion_side_effects(participant_id)

    coaching_hint = None
    if not is_complete and _should_show_coaching(short_answer_state):
        coaching_hint = decision.get("coaching") or _coaching_hint_for(short_answer_state, language)

    return _result(new_turn, is_complete=is_complete, coaching_hint=coaching_hint)


def ensure_turn_audio(participant_id: str, turn_index: int, db: Session) -> str | None:
    """Return (generating if needed) the spoken audio URL for one turn.

    Idempotent: once a turn has a ``tts_audio_url`` the stored URL is
    returned without a second synthesis. Returns None when TTS or storage
    are unavailable; the participant keeps the on-screen question text.
    """
    turn = (
        db.query(InterviewTurn)
        .filter(
            InterviewTurn.participant_id == participant_id,
            InterviewTurn.turn_index == turn_index,
        )
        .first()
    )
    if turn is None:
        return None
    if turn.tts_audio_url:
        return turn.tts_audio_url
    if not (turn.question_text or "").strip():
        return None

    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    project = participant.project if participant else None
    language = (
        getattr(participant, "preferred_language", None)
        or getattr(project, "language", None)
        or "en"
    )
    try:
        key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
        url = upload_audio(generate_speech(turn.question_text, language=language), key)
        turn.tts_audio_url = url
        if project is not None:
            log_tts_usage(
                db, turn.question_text,
                company_id=project.company_id, project_id=project.id,
                participant_id=participant_id,
            )
        db.commit()
        return url
    except Exception:
        logger.exception("Deferred TTS failed for participant %s turn %s", participant_id, turn_index)
        db.rollback()
        return None


def finish_interview(participant_id: str, db: Session) -> dict:
    """Participant-initiated "Finish here": close gracefully right now.

    Idempotent: a second call returns the stored closing turn. Billed only
    when at least half of the guide questions were answered (see
    ``end_early`` in ``process_interview_turn``).
    """
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    language = (
        getattr(participant, "preferred_language", None)
        or getattr(participant.project, "language", None)
        or "en"
    )

    if participant.status == "completed" and turns:
        last = turns[-1]
        return {
            "question_text": last.question_text,
            "tts_audio_url": last.tts_audio_url,
            "is_complete": True,
            "is_follow_up": False,
            "question_index": last.question_index or 0,
            "turn_index": last.turn_index,
            "elapsed_seconds": 0,
            "total_seconds": 0,
        }

    # The pending question (if any) is marked as left unanswered.
    if turns and not turns[-1].response_transcript:
        turns[-1].response_transcript = "[Skipped]"

    closing_text = _closing_message(language)
    tts_url = _cached_tts(closing_text, language)
    current_q = max((t.question_index for t in turns if t.question_index is not None), default=0)
    new_turn = InterviewTurn(
        participant_id=participant_id,
        turn_index=(turns[-1].turn_index + 1) if turns else 0,
        question_index=max(current_q, 0),
        is_follow_up=False,
        follow_up_index=0,
        question_text=closing_text,
        tts_audio_url=tts_url,
    )
    db.add(new_turn)

    total_q = len([q for q in participant.project.guide_questions if not getattr(q, "deprecated_at", None)])
    answered = _answered_main_questions(turns)
    billing = _mark_completed(
        participant, db,
        reason="participant_finished",
        bill=total_q > 0 and answered * 2 >= total_q,
        completed_via="finish",
    )
    db.commit()
    db.refresh(new_turn)
    _consume_credit_isolated(billing)
    _spawn_completion_side_effects(participant_id)

    return {
        "question_text": closing_text,
        "tts_audio_url": tts_url,
        "is_complete": True,
        "is_follow_up": False,
        "question_index": new_turn.question_index,
        "turn_index": new_turn.turn_index,
        "elapsed_seconds": 0,
        "total_seconds": 0,
    }


def skip_question(participant_id: str, db) -> dict:
    """Advance past the current question without a response."""
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if not participant:
        raise ValueError("Participant not found")

    project = participant.project
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    context = get_interview_context(participant_id, db)
    language = context.get("language")

    unanswered = [t for t in turns if not t.response_transcript]
    if unanswered:
        unanswered[-1].response_transcript = "[Skipped]"
        db.flush()

    # The engine tracks a GLOBAL question ordinal on each turn; a guide
    # question's own question_index restarts per section, so flatten first.
    current_q_index = context["current_question_index"]
    ordered_questions = sorted(
        [q for q in project.guide_questions if not q.deprecated_at],
        key=lambda q: (q.section_index, q.question_index),
    )
    next_pos = current_q_index + 1
    next_questions = ordered_questions[next_pos:]

    if not next_questions:
        closing_text = _closing_message(language)
        tts_url = _cached_tts(closing_text, language)
        new_turn = InterviewTurn(
            participant_id=participant_id,
            turn_index=(turns[-1].turn_index + 1) if turns else 0,
            question_index=max(current_q_index, 0),
            is_follow_up=False,
            follow_up_index=0,
            question_text=closing_text,
            tts_audio_url=tts_url,
        )
        db.add(new_turn)
        # Same rule as end_early / finish: a transcript that is entirely
        # "[Skipped]" is not a usable interview and must not burn a credit.
        total_q = len(ordered_questions)
        answered = _answered_main_questions(turns)
        billing = _mark_completed(
            participant, db,
            reason="skipped_to_end",
            bill=total_q > 0 and answered * 2 >= total_q,
            completed_via="skip",
        )
        db.commit()
        db.refresh(new_turn)
        _consume_credit_isolated(billing)
        _spawn_completion_side_effects(participant_id)
        return {
            "question_text": closing_text,
            "tts_audio_url": tts_url,
            "is_complete": True,
            "is_follow_up": False,
            "question_index": new_turn.question_index,
            "turn_index": new_turn.turn_index,
            "elapsed_seconds": int(context["elapsed_minutes"] * 60),
            "total_seconds": (context["total_minutes"] or 0) * 60,
        }

    question_text = next_questions[0].main_question
    new_turn = InterviewTurn(
        participant_id=participant_id,
        turn_index=(turns[-1].turn_index + 1) if turns else 0,
        # Global ordinal, NOT the per-section question_index.
        question_index=next_pos,
        is_follow_up=False,
        follow_up_index=0,
        question_text=question_text,
    )
    db.add(new_turn)
    db.flush()

    tts_url = None
    try:
        key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
        tts_url = upload_audio(generate_speech(question_text, language=language), key)
        new_turn.tts_audio_url = tts_url
        log_tts_usage(db, question_text, company_id=project.company_id, project_id=project.id, participant_id=participant_id)
    except Exception:
        logger.exception("Skip-path TTS failed for participant %s; continuing text-only", participant_id)
    db.commit()
    db.refresh(new_turn)

    return {
        "question_text": question_text,
        "tts_audio_url": tts_url,
        "is_complete": False,
        "is_follow_up": False,
        "question_index": new_turn.question_index,
        "turn_index": new_turn.turn_index,
        "elapsed_seconds": int(context["elapsed_minutes"] * 60),
        "total_seconds": (context["total_minutes"] or 0) * 60,
    }
