"""Core interview engine: orchestrates STT, Claude decision-making, and TTS."""

import json
import os
import uuid
from datetime import datetime, timezone

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.models.interview import InterviewTurn, Participant
from app.models.project import InterviewGuideQuestion, Project
from app.services.stt import transcribe_audio
from app.services.storage import upload_audio, download_audio
from app.services.tts import generate_speech

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

You must respond in JSON format: {"action": "follow_up" or "next_question" or "close", "question": "your question text"}
"""


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
) -> dict:
    """Call Claude to decide the next interview action.

    Returns a dict with keys: action ("follow_up"|"next_question"|"close"), question (str)
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Compute how much of the allotted time has been used and questions answered
    time_used_pct = (elapsed_minutes / total_minutes * 100) if total_minutes > 0 else 100
    questions_answered = current_question_index + 1  # 1-based count of questions reached
    remaining_minutes = max(0.0, total_minutes - elapsed_minutes)

    # Decide whether "close" should even be allowed as an option.
    # Block it unless both conditions are met:
    #   (a) all guide questions have been covered, OR time is genuinely exhausted (>=95%)
    #   (b) at least 80% of the allotted time has elapsed
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

Based on the conversation so far and the interview guide, decide what to do next:
1. "follow_up" — the current topic needs more depth; ask a probing follow-up question
2. "next_question" — the current topic is well-explored; move to the next main guide question (rephrase naturally)
{close_instruction}

Return ONLY a JSON object: {{"action": "follow_up" or "next_question" or "close", "question": "your question text"}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
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


def _get_first_question(project: Project) -> tuple[str, int]:
    """Get the first non-deprecated question from the interview guide, rephrased as an opener."""
    guide_questions = sorted(
        [q for q in project.guide_questions if not getattr(q, "deprecated_at", None)],
        key=lambda q: (q.section_index, q.question_index),
    )
    if not guide_questions:
        return "Thank you for joining. Could you start by telling me a bit about yourself?", 0

    first_q = guide_questions[0]

    # Use Claude to rephrase the first question as a natural conversation opener
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        system=INTERVIEWER_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"You are starting an interview. The first question from the guide is:\n"
                    f'"{first_q.main_question}"\n\n'
                    f"Rephrase this as a warm, natural opening question. "
                    f"Return ONLY the question text, no JSON."
                ),
            }
        ],
    )

    question_text = response.content[0].text.strip()
    return question_text, 0


def start_interview(participant_id: str, db: Session) -> dict:
    """Generate the first question and TTS for a new interview.

    Returns dict with: question_text, tts_audio_url, turn
    """
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    project = participant.project

    question_text, q_index = _get_first_question(project)

    # Generate TTS audio and upload
    tts_key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
    tts_audio_url = upload_audio(generate_speech(question_text), tts_key)

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
    transcript = transcribe_audio(audio_data, filename)

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
        research_objective=context["project"].research_objective,
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

    action = decision["action"]
    question_text = decision["question"]
    is_complete = action == "close"

    # 5. Generate TTS for the next question / closing and upload
    tts_key = f"tts/{participant_id}/{uuid.uuid4().hex}.mp3"
    tts_audio_url = upload_audio(generate_speech(question_text), tts_key)

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

    db.commit()
    db.refresh(new_turn)

    return {
        "question_text": question_text,
        "tts_audio_url": tts_audio_url,
        "is_complete": is_complete,
    }
