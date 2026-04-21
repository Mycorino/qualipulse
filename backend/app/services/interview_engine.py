"""Core interview engine: orchestrates STT, Claude decision-making, and TTS."""

import json
import os
import uuid
from datetime import datetime, timezone

import anthropic
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.interview import InterviewTurn, Participant
from app.models.project import InterviewGuideQuestion, Project
from app.services.stt import transcribe_audio
from app.services.storage import upload_audio, download_audio
from app.services.tts import generate_speech
from app.services.usage_logger import log_claude_usage, log_stt_usage, log_tts_usage


class EmptyTranscriptError(Exception):
    """Raised when Whisper returns no speech in the participant's recording."""


INTERVIEWER_SYSTEM_PROMPT = """\
You are an expert qualitative interviewer conducting a research interview on behalf of a company.

Your role:
- Listen carefully and express genuine interest in what the participant tells you
- Maintain a friendly, conversational tone — not a strict Q&A
- Remain neutral: don't approve or disapprove of responses
- Encourage the participant to expand and give details
- If answers are brief, use "describe," "tell me about" prompts
- Don't move to a new topic until you've explored the current one thoroughly
- Use the participant's own language and terminology
- Avoid "why" questions (they make people give socially acceptable answers instead of honest ones)
- Be time-conscious: cover all guide questions within the allotted time
- When transitioning to a new main guide question (action: "next_question"), open with a one-sentence callback to something specific the participant just said — using their exact words where natural — before introducing the new topic. This makes participants feel genuinely heard.

You must respond in JSON format: {"action": "follow_up" or "next_question" or "close", "question": "your question text"}
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

    return {
        "conversation_history": _build_conversation_history(turns),
        "interview_guide": _build_interview_guide_str(project),
        "elapsed_minutes": elapsed,
        "current_question_index": current_question_index,
        "total_minutes": project.interview_duration_minutes,
        "all_questions_done": all_questions_done,
        "system_prompt": project.system_prompt,
        "language": project.language or "en",
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
    db=None,
    company_id=None,
    project_id=None,
    participant_id=None,
) -> dict:
    """Call Claude to decide the next interview action.

    Returns a dict with keys: action ("follow_up"|"next_question"|"close"), question (str)
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=httpx.Timeout(60.0))

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
        objective_block = f"""
RESEARCH OBJECTIVE:
{research_objective}

As a skilled qualitative researcher, keep this objective top of mind. Use proven product marketing techniques:
- Surface unmet needs, frustrations, and workarounds the participant may not explicitly state
- Probe for the "job to be done" behind behaviours (why they do something, not just what)
- Listen for emotional language and amplify it ("you said X frustrates you — can you tell me more?")
- When an answer hints at insight relevant to the objective, follow up before moving on
- Gently steer the conversation so the guide questions naturally uncover data that serves the objective
"""

    user_message = f"""Here is the interview context:
{objective_block}
INTERVIEW GUIDE:
{interview_guide_str}

CONVERSATION SO FAR:
{conversation_history}

CURRENT STATE:
- Questions reached: {questions_answered} of {total_questions}
- Elapsed time: {elapsed_minutes:.1f} / {total_minutes} minutes ({time_used_pct:.0f}% used, {remaining_minutes:.1f} min remaining)
- All main questions covered: {all_questions_done}

{pacing_instruction}

Based on the conversation so far and the interview guide, decide what to do next:
1. "follow_up" — the current topic needs more depth; ask a probing follow-up question
2. "next_question" — the current topic is well-explored; move to the next main guide question (rephrase naturally)
{close_instruction}

Return ONLY a JSON object: {{"action": "follow_up" or "next_question" or "close", "question": "your question text"}}"""

    # Append language instruction to the system prompt if the project uses a
    # non-English interview language.
    effective_system_prompt = (system_prompt or INTERVIEWER_SYSTEM_PROMPT) + _language_instruction(language)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        temperature=0.7,
        system=effective_system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

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
        # Fallback: treat entire response as a follow-up question
        result = {"action": "follow_up", "question": raw_text}

    # Validate keys
    if "action" not in result:
        result["action"] = "follow_up"
    if "question" not in result:
        result["question"] = raw_text

    return result


def _get_first_question(
    project: Project,
    db=None,
    participant_id=None,
) -> tuple[str, int]:
    """Get the first non-deprecated question from the interview guide, rephrased as an opener."""
    guide_questions = sorted(
        [q for q in project.guide_questions if not getattr(q, "deprecated_at", None)],
        key=lambda q: (q.section_index, q.question_index),
    )
    language_code = (getattr(project, "language", None) or "en").lower()
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
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=httpx.Timeout(60.0))

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
                    f"Rephrase this as a warm, natural opening question in {language_name}. "
                    f"Return ONLY the question text, no JSON."
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

    Returns dict with: question_text, tts_audio_url, turn
    """
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    project = participant.project
    company_id = project.company_id
    proj_id = project.id

    question_text, q_index = _get_first_question(project, db=db, participant_id=participant_id)

    # Generate TTS audio and upload
    tts_key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
    tts_audio_url = upload_audio(generate_speech(question_text), tts_key)
    log_tts_usage(db, question_text, company_id=company_id, project_id=proj_id, participant_id=participant_id)

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
    }


def process_interview_turn(
    participant_id: str, audio_path: str, db: Session
) -> dict:
    """Process a participant's audio response and generate the next question.

    Orchestrates: transcribe -> save transcript -> get context -> Claude decision -> TTS

    Returns dict with: question_text, tts_audio_url, is_complete
    """
    # 1. Transcribe the participant's audio
    audio_data = download_audio(audio_path)
    filename = os.path.basename(audio_path)
    transcript, audio_duration = transcribe_audio(audio_data, filename)

    # 1a. Guard: Whisper sometimes returns an empty or whitespace-only string
    # for silent/inaudible clips. Saving that and passing it to Claude produces
    # garbage follow-ups. Signal the caller to prompt a re-record instead.
    if not transcript or not transcript.strip():
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
        last_turn.audio_recording_url = audio_path  # key; resolved to URL via storage layer
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
        # Send completion email if participant provided one
        try:
            from app.services.email import send_email
            if participant.email:
                project_name = participant.project.name
                send_email(
                    to=participant.email,
                    subject=f"Thank you for your interview — {project_name}",
                    body_html=f"""
                    <p>Hi{' ' + participant.display_name if participant.display_name else ''},</p>
                    <p>Thank you for completing the <strong>{project_name}</strong> interview. Your responses have been recorded and will help shape the research.</p>
                    <p>You can close this email — no further action is needed.</p>
                    """,
                )
        except Exception:
            pass  # Never fail the interview flow due to email errors

        # Auto-run AI quality assessment in background thread
        try:
            import threading as _threading
            _pid = participant.id
            _proj_id = participant.project_id
            def _assess():
                try:
                    from app.database import SessionLocal
                    from app.services.quality import run_ai_quality_assessment
                    from app.models.project import Project
                    from app.models.company import Company
                    assess_db = SessionLocal()
                    try:
                        proj = assess_db.query(Project).filter(Project.id == _proj_id).first()
                        lang = "en"
                        if proj:
                            company = assess_db.query(Company).filter(Company.id == proj.company_id).first()
                            if company and company.preferred_language:
                                lang = company.preferred_language
                        run_ai_quality_assessment(_pid, assess_db, language=lang)
                    finally:
                        assess_db.close()
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
                    from app.database import SessionLocal
                    from app.services.quality import run_ai_quality_assessment
                    from app.models.project import Project
                    from app.models.company import Company
                    assess_db = SessionLocal()
                    try:
                        proj = assess_db.query(Project).filter(Project.id == _proj_id).first()
                        lang = "en"
                        if proj:
                            company = assess_db.query(Company).filter(Company.id == proj.company_id).first()
                            if company and company.preferred_language:
                                lang = company.preferred_language
                        run_ai_quality_assessment(_pid, assess_db, language=lang)
                    finally:
                        assess_db.close()
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
