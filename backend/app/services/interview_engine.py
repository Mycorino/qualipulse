"""Core interview engine: orchestrates STT, Claude decision-making, and TTS.

Engine v2 (Apr 2026) introduces:
- Pre-flight interview plan (per-question talk-time budgets) — generated once at
  start_interview and persisted on Participant.interview_plan.
- Talk-time pacing — pacing math runs on Whisper-reported audio_duration, not
  wall clock. Wall clock is a hard cap only (1.5x total → force close).
- Extended decision schema — actions: follow_up | next_question | skip_to |
  reframe | clarification | close.
- Hard server-side caps — max follow-ups (per plan), max 1 reframe / clarification
  per question, premature close override, wall-clock overshoot override.
- Dead-air detection — short non-answers ("yeah", <3s) trigger a hardcoded
  clarification re-prompt without burning a Claude call.
- Rolling fatigue score — early-vs-late answer length ratio. High fatigue opens
  the close gate at 70%/70% instead of 80%/100%.
- Turn classification — InterviewTurn.turn_kind tags each row's role.
"""

import json
import os
from datetime import datetime, timezone

import anthropic
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.interview import InterviewTurn, Participant
from app.models.project import InterviewGuideQuestion, Project
from app.services.stt import transcribe_audio
from app.services.storage import download_audio
from app.services.usage_logger import log_claude_usage, log_stt_usage


class EmptyTranscriptError(Exception):
    """Raised when Whisper returns no speech in the participant's recording."""


CLAUDE_MODEL = "claude-sonnet-4-20250514"


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

Decision rules — you MUST output exactly one of these actions:

1. follow_up — probe deeper on the current topic. Choose when:
   - Answer was <40 words AND topic isn't exhausted, OR
   - Participant introduced a concrete claim/story/emotion that needs unpacking, OR
   - Generic answer ("it's fine", "it works") with no behaviour or example.
   - Pacing is on-track or ahead.
   The host caps follow-ups per question; if you're at the cap, the host will force next_question.

2. next_question — move to the next guide question. Choose when:
   - Current topic has yielded a concrete example or behaviour, OR
   - Pacing is behind, OR
   - You've already asked the planned follow-ups for this topic.
   When transitioning, OPEN with a one-sentence callback to something specific the participant \
just said (use their exact words where natural), THEN introduce the new topic.

3. skip_to — jump past one or more guide questions because the participant has \
already answered them. Choose ONLY when:
   - The most recent answer clearly and substantively covers a LATER guide \
     question (not just adjacent topics).
   Provide skip_to_question_index pointing at the question you want to ask next \
(must be > current_question_index). Phrase your question with a callback acknowledging \
that they already touched on the skipped material.

4. reframe — re-ask the SAME question with new wording because the participant \
misunderstood or went off-topic. Choose ONLY when:
   - The answer is on-topic-adjacent but misses what the question is actually \
     asking for (e.g. asked for a story, got a generalisation about the industry).
   - Do NOT use reframe just because the answer was short — that's follow_up.
   Host caps reframes at 1 per question.

5. clarification — gently re-prompt because the participant gave a non-answer \
("yeah", "I dunno", silence). The host detects most of these automatically; you \
should rarely need to choose this manually. Host caps at 1 per question.

6. close — wrap up warmly. ONLY available when the host says the close gate is \
open. If the host says close is NOT available, you MUST NOT return "close" no \
matter how exhausted the conversation feels.

Output: ONE JSON object, nothing else:
{"action": "<one of the 6 above>", "question": "<text the participant will hear>", \
"skip_to_question_index": <int or null>, "reason": "<≤12 words, optional>"}
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


# Hardcoded clarification re-prompts (used by dead-air detection so we don't
# burn a Claude call on a 2-second "yeah").
CLARIFICATION_PROMPTS: dict[str, str] = {
    "en": "Take your time — what comes to mind?",
    "fr": "Prends ton temps — qu'est-ce qui te vient à l'esprit ?",
    "es": "Tómate tu tiempo — ¿qué se te ocurre?",
    "de": "Lass dir Zeit — was fällt dir dazu ein?",
    "it": "Prendi il tuo tempo — cosa ti viene in mente?",
    "pt": "Sem pressa — o que lhe vem à cabeça?",
    "nl": "Neem rustig de tijd — wat komt er bij je op?",
    "ja": "ゆっくりで大丈夫です — どんなことが思い浮かびますか？",
    "ko": "천천히 생각하셔도 괜찮습니다 — 어떤 것이 떠오르세요?",
    "zh": "不用急——您能想到什么？",
}


# Tokens that signal a non-answer (case-insensitive, with optional trailing
# punctuation). We require both <3s of audio AND ≤3 word transcript AND a
# match in this set to trigger dead-air handling.
DEAD_AIR_TOKENS = {
    "yeah", "yes", "no", "nope", "yep", "sure", "ok", "okay",
    "hmm", "uh", "um",
    "i don't know", "i dunno", "dunno", "idk",
    "ouais", "non", "oui", "bof", "je sais pas", "je ne sais pas",
}


def _closing_message(language_code: str | None) -> str:
    code = (language_code or "en").lower()
    return CLOSING_MESSAGES.get(code, CLOSING_MESSAGES["en"])


def _clarification_prompt(language_code: str | None) -> str:
    code = (language_code or "en").lower()
    return CLARIFICATION_PROMPTS.get(code, CLARIFICATION_PROMPTS["en"])


def _is_dead_air(transcript: str, audio_duration: float) -> bool:
    """Return True if the response is a near-empty non-answer."""
    if audio_duration >= 3.0:
        return False
    text = (transcript or "").strip().lower()
    # Strip simple trailing punctuation
    text = text.rstrip(".!?, ").strip()
    if not text:
        return True  # whitespace-only counts
    words = text.split()
    if len(words) > 3:
        return False
    return text in DEAD_AIR_TOKENS or words[0] in DEAD_AIR_TOKENS


def _language_instruction(language_code: str | None) -> str:
    """Build a short system-prompt suffix telling Claude what language to use."""
    code = (language_code or "en").lower()
    name = LANGUAGE_NAMES.get(code, "English")
    if code == "en":
        return ""
    return (
        f"\n\nIMPORTANT — Language: You MUST conduct this entire interview in {name}. "
        f"Ask every question in {name}, even if the interview guide questions are "
        f"written in another language (translate them naturally as you go). "
        f"If the participant replies in a different language, gently continue in {name} "
        f"unless they explicitly ask to switch. Keep your tone warm and idiomatic — "
        f"use natural {name} phrasing, not literal translations."
    )


def _sorted_active_questions(project: Project) -> list[InterviewGuideQuestion]:
    return sorted(
        [q for q in project.guide_questions if not getattr(q, "deprecated_at", None)],
        key=lambda q: (q.section_index, q.question_index),
    )


def _build_interview_guide_str(project: Project) -> str:
    guide_questions = _sorted_active_questions(project)
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
    lines: list[str] = []
    for turn in sorted(turns, key=lambda t: t.turn_index):
        lines.append(f"Interviewer: {turn.question_text}")
        if turn.response_transcript:
            lines.append(f"Participant: {turn.response_transcript}")
    return "\n".join(lines)


# ─── Pre-flight planner ───────────────────────────────────────────────────────


def _uniform_plan(guide_questions: list[InterviewGuideQuestion], total_minutes: int) -> dict:
    """Fallback plan: even split, 2 follow-ups each, depth=standard."""
    n = max(1, len(guide_questions))
    per = max(1.0, total_minutes / n)
    return {
        "questions": [
            {
                "index": q.question_index,
                "budget_minutes": round(per, 1),
                "max_follow_ups": 2,
                "depth": "standard",
            }
            for q in guide_questions
        ],
        "total_budget_minutes": total_minutes,
        "model": "uniform-fallback",
        "generated_at": datetime.utcnow().isoformat(),
    }


def _generate_interview_plan(
    project: Project,
    total_minutes: int,
    language: str,
    db: Session | None = None,
    participant_id: str | None = None,
) -> dict:
    """One-shot pre-flight plan: per-question budgets + follow-up caps.

    Returns a JSON-serialisable dict. Falls back to a uniform plan on any error
    (network, parse failure, no API key, etc.) so we never block the interview
    from starting.
    """
    guide_questions = _sorted_active_questions(project)
    if not guide_questions:
        return {
            "questions": [],
            "total_budget_minutes": total_minutes,
            "model": "empty-guide",
            "generated_at": datetime.utcnow().isoformat(),
        }

    # If no API key is configured (e.g. in tests) skip the call.
    if not settings.ANTHROPIC_API_KEY:
        return _uniform_plan(guide_questions, total_minutes)

    guide_block = "\n".join(
        f"Q{q.question_index} (depth-hint: {q.desired_learning or 'unspecified'}): {q.main_question}"
        for q in guide_questions
    )

    user_msg = (
        f"Total budget: {total_minutes} minutes of TALK TIME (participant + interviewer combined).\n\n"
        f"Interview guide ({len(guide_questions)} questions):\n{guide_block}\n\n"
        "Allocate a talk-time budget (in minutes, can be fractional) to each question. "
        "Budgets must SUM to the total. Also assign each question:\n"
        "- depth: \"deep\" (rich-story question, 2 follow-ups) | \"standard\" (1-2 follow-ups) | \"light\" (0-1 follow-ups)\n"
        "- max_follow_ups: integer 0-3.\n\n"
        "Bias deep budget toward questions with substantive desired-learning hints "
        "and toward open-ended exploratory questions; trim from light/factual questions.\n\n"
        "Output ONLY this JSON, no prose:\n"
        '{"questions": [{"index": 0, "budget_minutes": 8.0, "max_follow_ups": 2, "depth": "deep"}, ...]}'
    )

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=httpx.Timeout(30.0))
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            temperature=0.2,
            system=(
                "You are an expert qualitative-research interview planner. "
                "Output strict JSON only — no markdown, no commentary."
                + _language_instruction(language)
            ),
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            response = stream.get_final_message()
        if db is not None:
            log_claude_usage(
                db, response, "interview_plan",
                company_id=getattr(project, "company_id", None),
                project_id=getattr(project, "id", None),
                participant_id=participant_id,
            )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```")).strip()
        parsed = json.loads(raw)
        questions = parsed.get("questions", [])
        # Sanity check: must contain every active question_index.
        active_indices = {q.question_index for q in guide_questions}
        plan_indices = {q.get("index") for q in questions}
        if not active_indices.issubset(plan_indices):
            return _uniform_plan(guide_questions, total_minutes)
        # Normalise + clamp.
        normalised: list[dict] = []
        for entry in questions:
            normalised.append({
                "index": int(entry["index"]),
                "budget_minutes": float(entry.get("budget_minutes", total_minutes / len(guide_questions))),
                "max_follow_ups": max(0, min(3, int(entry.get("max_follow_ups", 2)))),
                "depth": entry.get("depth", "standard"),
            })
        return {
            "questions": sorted(normalised, key=lambda x: x["index"]),
            "total_budget_minutes": total_minutes,
            "model": CLAUDE_MODEL,
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception:
        return _uniform_plan(guide_questions, total_minutes)


def _plan_for_question(plan: dict | None, question_index: int) -> dict:
    """Look up the plan entry for a question_index; return defaults if missing."""
    default = {"index": question_index, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"}
    if not plan:
        return default
    for entry in plan.get("questions", []):
        if entry.get("index") == question_index:
            return entry
    return default


# ─── Talk-time + fatigue helpers ──────────────────────────────────────────────


def _talk_seconds_for_question(turns: list[InterviewTurn], question_index: int) -> float:
    """Sum recorded audio seconds across all turns belonging to a question.

    We don't have per-turn duration stored, so we estimate from transcript word
    count (≈150 wpm conversational → 0.4s/word). This is an approximation used
    only for the per-question pacing signal; total talk time uses real Whisper
    durations summed onto Participant.talk_seconds.
    """
    total = 0.0
    for t in turns:
        if t.question_index != question_index or not t.response_transcript:
            continue
        words = len(t.response_transcript.split())
        total += words * 0.4
    return total


def _compute_fatigue_state(turns: list[InterviewTurn]) -> str | None:
    """Rolling fatigue: late 2-turn avg word-count vs early 2-turn avg.

    Returns "high" | "medium" | "low" | None (when not enough data).
    Excludes clarification turns and skip_skip turns.
    """
    answer_turns = [
        t for t in sorted(turns, key=lambda x: x.turn_index)
        if t.response_transcript
        and getattr(t, "turn_kind", "main") not in ("clarification", "skip_skip")
        and t.response_transcript.strip() not in ("[Skipped]", "[Implicitly answered in prior response]")
    ]
    if len(answer_turns) < 4:
        return None
    early = answer_turns[:2]
    late = answer_turns[-2:]
    early_avg = sum(len((t.response_transcript or "").split()) for t in early) / 2
    late_avg = sum(len((t.response_transcript or "").split()) for t in late) / 2
    if early_avg <= 0:
        return None
    ratio = late_avg / early_avg
    if ratio < 0.5:
        return "high"
    if ratio < 0.7:
        return "medium"
    return "low"


# ─── Context assembly ────────────────────────────────────────────────────────


def get_interview_context(participant_id: str, db: Session) -> dict:
    """Return conversation history, interview guide, and metadata for a participant."""
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    project = participant.project
    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    guide_questions = _sorted_active_questions(project)
    total_questions = len(guide_questions)

    asked_indices = {t.question_index for t in turns if t.question_index is not None}
    current_question_index = max(asked_indices) if asked_indices else 0

    last_index = total_questions - 1
    if total_questions == 0:
        all_questions_done = True
    elif current_question_index < last_index:
        all_questions_done = False
    else:
        last_q_turns = [t for t in turns if t.question_index == last_index]
        all_questions_done = any(t.response_transcript for t in last_q_turns)

    now = datetime.utcnow()
    started = participant.started_at.replace(tzinfo=None) if participant.started_at.tzinfo else participant.started_at
    elapsed = (now - started).total_seconds() / 60.0

    plan = None
    if getattr(participant, "interview_plan", None):
        try:
            plan = json.loads(participant.interview_plan)
        except (json.JSONDecodeError, TypeError):
            plan = None

    talk_minutes = (getattr(participant, "talk_seconds", 0.0) or 0.0) / 60.0

    return {
        "conversation_history": _build_conversation_history(turns),
        "interview_guide": _build_interview_guide_str(project),
        "elapsed_minutes": elapsed,
        "talk_minutes": talk_minutes,
        "current_question_index": current_question_index,
        "total_minutes": project.interview_duration_minutes,
        "all_questions_done": all_questions_done,
        "system_prompt": project.system_prompt,
        "language": project.language or "en",
        "project": project,
        "participant": participant,
        "turns": turns,
        "total_questions": total_questions,
        "interview_plan": plan,
        "fatigue_state": getattr(participant, "fatigue_state", None),
    }


# ─── Pacing math ──────────────────────────────────────────────────────────────


def _compute_pacing(
    plan: dict | None,
    turns: list[InterviewTurn],
    current_question_index: int,
    talk_minutes: float,
    elapsed_minutes: float,
    total_minutes: int,
    total_questions: int,
) -> dict:
    """Compute the pacing block passed to Claude.

    Returns dict with:
      current_q_pace, overall_pace, wall_clock_overshoot, instruction (str),
      current_q_budget, current_q_talk_minutes
    """
    # Per-question
    plan_entry = _plan_for_question(plan, current_question_index)
    current_q_budget = float(plan_entry["budget_minutes"])
    q_talk_seconds = _talk_seconds_for_question(turns, current_question_index)
    q_talk_minutes = q_talk_seconds / 60.0
    q_pct = (q_talk_minutes / current_q_budget * 100.0) if current_q_budget > 0 else 100.0
    if q_pct > 130:
        current_q_pace = "behind"  # over the per-q budget
    elif q_pct < 50:
        current_q_pace = "ahead"
    else:
        current_q_pace = "on_track"

    # Overall (talk-time vs total budget — talk_minutes is participant+interviewer
    # talk only; total_minutes is the configured budget — this is the canonical
    # pacing signal under v2)
    if total_minutes > 0:
        overall_pct = talk_minutes / total_minutes * 100.0
        # Expected progress through the questions, given talk-time consumed.
        if total_questions > 0:
            expected_q = (talk_minutes / total_minutes) * total_questions
            delta = current_question_index - expected_q
            if delta < -1.5:
                overall_pace = "behind"
            elif delta > 1.0:
                overall_pace = "ahead"
            else:
                overall_pace = "on_track"
        else:
            overall_pace = "on_track"
    else:
        overall_pct = 0.0
        overall_pace = "on_track"

    wall_clock_overshoot = total_minutes > 0 and elapsed_minutes > (1.5 * total_minutes)

    if wall_clock_overshoot:
        instruction = (
            "⚠️ HARD CAP: wall-clock has exceeded 150% of the budget. The host will close "
            "the interview. Do NOT ask another question."
        )
    elif overall_pace == "behind":
        instruction = (
            "⚠️ PACING: significantly behind on overall talk-time vs questions remaining. "
            "Move to the NEXT main guide question now. Do not ask a follow-up."
        )
    elif overall_pace == "ahead" and current_q_pace != "behind":
        instruction = (
            "PACING: ahead of schedule — there is room to probe. A follow-up is welcome "
            "if it would surface deeper insight."
        )
    elif current_q_pace == "behind":
        instruction = (
            f"PACING: this question has consumed {q_pct:.0f}% of its planned "
            f"{current_q_budget:.1f}-min budget. Wrap it and move on."
        )
    else:
        instruction = (
            "PACING: on schedule. Ask a follow-up only if it genuinely adds value, "
            "otherwise move on."
        )

    return {
        "current_q_pace": current_q_pace,
        "overall_pace": overall_pace,
        "wall_clock_overshoot": wall_clock_overshoot,
        "instruction": instruction,
        "current_q_budget": current_q_budget,
        "current_q_talk_minutes": q_talk_minutes,
        "talk_minutes": talk_minutes,
        "overall_pct": overall_pct,
    }


# ─── Decision (Claude call) ──────────────────────────────────────────────────


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
    talk_minutes: float | None = None,
    interview_plan: dict | None = None,
    fatigue_state: str | None = None,
    turns: list[InterviewTurn] | None = None,
) -> dict:
    """Call Claude for the next action under the v2 schema.

    Returns dict: {action, question, skip_to_question_index?, reason?}.
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=httpx.Timeout(60.0))

    # Talk-time pacing math.
    talk_minutes = talk_minutes if talk_minutes is not None else elapsed_minutes
    pacing = _compute_pacing(
        interview_plan,
        turns or [],
        current_question_index,
        talk_minutes,
        elapsed_minutes,
        total_minutes,
        total_questions,
    )

    questions_answered = current_question_index + 1
    talk_pct = pacing["overall_pct"]
    plan_entry = _plan_for_question(interview_plan, current_question_index)

    # Close gate (fatigue-aware).
    if fatigue_state == "high":
        # Earlier gate: 70% talk time + ≥70% questions covered.
        questions_pct = (questions_answered / total_questions) if total_questions else 1
        can_close = (
            (talk_pct >= 70.0 and questions_pct >= 0.7)
            or talk_pct >= 95.0
            or all_questions_done and talk_pct >= 70.0
        )
    else:
        can_close = (all_questions_done and talk_pct >= 80.0) or talk_pct >= 95.0

    if can_close:
        close_instruction = '6. "close" — gate is OPEN. Wrap up warmly when the topic feels exhausted.'
    else:
        close_instruction = (
            f'6. "close" — NOT available. Talk-time used: {talk_pct:.0f}%; '
            f'questions reached: {questions_answered}/{total_questions}. Keep going.'
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
DECISION: {"action":"follow_up","question":"Can you walk me through what was happening right before you tried that import?","skip_to_question_index":null,"reason":"emotion + concrete claim, no story yet"}

PARTICIPANT: "Yeah, I use it every Monday morning. I open the dashboard, scan for anything red, then ping the team in Slack. Takes about ten minutes."
DECISION: {"action":"next_question","question":"That ten-minute Monday scan is really useful. Shifting gears — could you walk me through the last time you onboarded a new teammate?","skip_to_question_index":null,"reason":"concrete behaviour, topic exhausted"}

PARTICIPANT: "It's fine."
DECISION: {"action":"follow_up","question":"What does 'fine' look like for you on a typical day with it?","skip_to_question_index":null,"reason":"generic, no behaviour"}

[After Q1 'how do you currently handle X', participant explains they use Tool Y AND mentions price made them switch from Z]
DECISION: {"action":"skip_to","question":"You mentioned price was the trigger to switch from Z. Can you walk me through that decision?","skip_to_question_index":3,"reason":"already covered Q2-Q3 implicitly"}

PARTICIPANT: "I think the industry generally has issues with this."
DECISION: {"action":"reframe","question":"That makes sense at a high level — and I'd love to ground it in your own experience. Could you tell me about the last time YOU ran into this?","skip_to_question_index":null,"reason":"generalisation; need a personal story"}
</examples>"""

    pacing_block = pacing["instruction"]
    fatigue_line = (
        f"- Fatigue: {fatigue_state} (close gate opens earlier)"
        if fatigue_state
        else "- Fatigue: not yet measurable"
    )

    user_message = (
        f"{examples_block}\n\n"
        f"{objective_block}"
        f"<guide>\n{interview_guide_str}\n</guide>\n\n"
        f"<conversation>\n{conversation_history}\n</conversation>\n\n"
        f"<state>\n"
        f"- Questions reached: {questions_answered} of {total_questions}\n"
        f"- Talk-time: {talk_minutes:.1f} / {total_minutes} min ({talk_pct:.0f}% used)\n"
        f"- Wall-clock elapsed: {elapsed_minutes:.1f} min\n"
        f"- Current question budget: {plan_entry['budget_minutes']:.1f} min, depth={plan_entry['depth']}, "
        f"used {pacing['current_q_talk_minutes']:.1f} min so far ({pacing['current_q_pace']})\n"
        f"- Max follow-ups for this question: {plan_entry['max_follow_ups']}\n"
        f"- All main questions covered: {all_questions_done}\n"
        f"{fatigue_line}\n"
        f"- {pacing_block}\n"
        f"- Close gate: {'OPEN' if can_close else close_instruction}\n"
        f"</state>\n\n"
        "Decide the next action. Return ONLY the JSON object specified by the system prompt."
    )

    effective_system_prompt = (system_prompt or INTERVIEWER_SYSTEM_PROMPT) + _language_instruction(language)

    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=512,
        temperature=0.4,
        system=effective_system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        response = stream.get_final_message()

    if db is not None:
        log_claude_usage(
            db, response, "interview_turn",
            company_id=company_id, project_id=project_id, participant_id=participant_id,
        )

    raw_text = response.content[0].text.strip()
    text_to_parse = raw_text
    if text_to_parse.startswith("```"):
        text_to_parse = "\n".join(
            l for l in text_to_parse.split("\n") if not l.strip().startswith("```")
        ).strip()

    try:
        result = json.loads(text_to_parse)
    except json.JSONDecodeError:
        result = {"action": "follow_up", "question": raw_text}

    if "action" not in result:
        result["action"] = "follow_up"
    if "question" not in result:
        result["question"] = raw_text
    result.setdefault("skip_to_question_index", None)
    result.setdefault("reason", None)

    return result


# ─── First-question opener ───────────────────────────────────────────────────


def _get_first_question(
    project: Project,
    db=None,
    participant_id=None,
) -> tuple[str, int]:
    """Get the first non-deprecated question, rephrased as a warm opener."""
    guide_questions = _sorted_active_questions(project)
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

    if not settings.ANTHROPIC_API_KEY:
        return first_q.main_question, first_q.question_index

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=httpx.Timeout(60.0))
    effective_system_prompt = INTERVIEWER_SYSTEM_PROMPT + _language_instruction(language_code)

    with client.messages.stream(
        model=CLAUDE_MODEL,
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
    ) as stream:
        response = stream.get_final_message()

    question_text = response.content[0].text.strip()

    if db is not None:
        log_claude_usage(
            db, response, "interview_turn",
            company_id=getattr(project, "company_id", None),
            project_id=getattr(project, "id", None),
            participant_id=participant_id,
        )

    return question_text, first_q.question_index


# ─── start_interview / process_interview_turn ────────────────────────────────


def start_interview(participant_id: str, db: Session) -> dict:
    """Generate the first question + TTS for a new interview, and persist a plan."""
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    project = participant.project
    company_id = project.company_id
    proj_id = project.id

    # Pre-flight: generate the interview plan.
    if not getattr(participant, "interview_plan", None):
        plan = _generate_interview_plan(
            project,
            project.interview_duration_minutes or 20,
            project.language or "en",
            db=db,
            participant_id=participant_id,
        )
        participant.interview_plan = json.dumps(plan)
        db.commit()

    question_text, q_index = _get_first_question(project, db=db, participant_id=participant_id)

    # Persist the turn first; TTS is served on demand from /audio/stream/{turn_id}.
    turn = InterviewTurn(
        participant_id=participant_id,
        turn_index=0,
        question_index=q_index,
        is_follow_up=False,
        follow_up_index=0,
        turn_kind="main",
        question_text=question_text,
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)

    tts_audio_url = f"/audio/stream/{turn.id}"
    turn.tts_audio_url = tts_audio_url
    db.commit()

    return {
        "question_text": question_text,
        "tts_audio_url": tts_audio_url,
        "turn": turn,
    }


def _count_kind(turns: list[InterviewTurn], question_index: int, kind: str) -> int:
    return sum(
        1 for t in turns
        if t.question_index == question_index and getattr(t, "turn_kind", "main") == kind
    )


def _save_clarification_turn(
    participant_id: str,
    db: Session,
    last_turn: InterviewTurn | None,
    turns: list[InterviewTurn],
    current_question_index: int,
    language: str,
    project_company_id,
    project_id,
) -> dict:
    """Hard-coded re-prompt path for dead-air responses. No Claude call."""
    question_text = _clarification_prompt(language)
    next_turn_index = (turns[-1].turn_index + 1) if turns else 0

    new_turn = InterviewTurn(
        participant_id=participant_id,
        turn_index=next_turn_index,
        question_index=current_question_index,
        is_follow_up=False,
        follow_up_index=0,
        turn_kind="clarification",
        question_text=question_text,
    )
    db.add(new_turn)
    db.commit()
    db.refresh(new_turn)

    tts_audio_url = f"/audio/stream/{new_turn.id}"
    new_turn.tts_audio_url = tts_audio_url
    db.commit()

    return {
        "question_text": question_text,
        "tts_audio_url": tts_audio_url,
        "is_complete": False,
        "is_follow_up": False,
        "question_index": current_question_index,
        "elapsed_seconds": 0,
        "total_seconds": 0,
    }


def process_interview_turn(
    participant_id: str, audio_path: str, db: Session
) -> dict:
    """Process a participant's audio response and generate the next interviewer turn."""
    # 1. Transcribe.
    audio_data = download_audio(audio_path)
    filename = os.path.basename(audio_path)
    transcript, audio_duration = transcribe_audio(audio_data, filename)

    if not transcript or not transcript.strip():
        raise EmptyTranscriptError(
            "No speech detected in the recording. Please try again in a quieter environment."
        )

    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        raise ValueError(f"Participant {participant_id} not found")

    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    # 2. Save participant transcript on the last (open) interviewer turn.
    if turns:
        last_turn = turns[-1]
        last_turn.response_transcript = transcript
        last_turn.audio_recording_url = audio_path
        # Accumulate talk-time on the participant.
        participant.talk_seconds = (participant.talk_seconds or 0.0) + float(audio_duration or 0.0)
        db.commit()
        # Re-read turns ordering after commit
        turns = sorted(participant.turns, key=lambda t: t.turn_index)
    else:
        last_turn = None

    project = participant.project
    company_id = project.company_id
    proj_id = project.id
    language = (project.language or "en").lower()

    log_stt_usage(
        db, audio_duration,
        company_id=company_id, project_id=proj_id, participant_id=participant_id,
    )

    # Determine the active question_index from existing turns BEFORE deciding.
    asked_indices = {t.question_index for t in turns if t.question_index is not None}
    current_question_index = max(asked_indices) if asked_indices else 0

    # 3. Dead-air detection — no Claude call needed.
    if _is_dead_air(transcript, audio_duration):
        clarification_count = _count_kind(turns, current_question_index, "clarification")
        if clarification_count < 1:
            return _save_clarification_turn(
                participant_id, db, last_turn, turns,
                current_question_index, language, company_id, proj_id,
            )
        # Already used the 1-clarification budget on this question — fall
        # through to a forced next_question.
        decision = {"action": "next_question", "question": None, "skip_to_question_index": None}
    else:
        # 4. Claude decision call.
        context = get_interview_context(participant_id, db)
        # Recompute and persist fatigue.
        fatigue = _compute_fatigue_state(context["turns"])
        if fatigue != participant.fatigue_state:
            participant.fatigue_state = fatigue
            db.commit()

        decision = decide_next_action(
            system_prompt=context["system_prompt"],
            interview_guide_str=context["interview_guide"],
            conversation_history=context["conversation_history"],
            current_question_index=context["current_question_index"],
            elapsed_minutes=context["elapsed_minutes"],
            total_minutes=context["total_minutes"],
            all_questions_done=context["all_questions_done"],
            total_questions=context["total_questions"],
            research_objective=project.research_objective,
            language=context["language"],
            db=db,
            company_id=company_id,
            project_id=proj_id,
            participant_id=participant_id,
            talk_minutes=context["talk_minutes"],
            interview_plan=context["interview_plan"],
            fatigue_state=fatigue,
            turns=context["turns"],
        )

    # 5. Server-side overrides on the model decision.
    context = get_interview_context(participant_id, db)
    plan = context["interview_plan"]
    elapsed = context["elapsed_minutes"]
    talk_minutes = context["talk_minutes"]
    total_minutes = context["total_minutes"]
    total_questions = context["total_questions"]
    all_questions_done = context["all_questions_done"]
    cur_q = context["current_question_index"]
    plan_entry = _plan_for_question(plan, cur_q)
    max_follow_ups = int(plan_entry.get("max_follow_ups", 2))

    action = decision.get("action") or "follow_up"

    # Wall-clock overshoot → force close (hard cap, bypasses close gate).
    wall_clock_hard_cap = total_minutes > 0 and elapsed > 1.5 * total_minutes

    # Premature close override (preserved from v1) — but skip when the wall-clock
    # hard cap is in effect.
    if action == "close" and not wall_clock_hard_cap:
        talk_pct = (talk_minutes / total_minutes * 100.0) if total_minutes > 0 else 100.0
        gate_open = (all_questions_done and talk_pct >= 80.0) or talk_pct >= 95.0
        if context["fatigue_state"] == "high":
            qpct = (cur_q + 1) / total_questions if total_questions else 1
            gate_open = gate_open or (talk_pct >= 70.0 and qpct >= 0.7)
        if not gate_open:
            action = "next_question"

    if wall_clock_hard_cap:
        action = "close"

    # Hard cap on follow-ups.
    if action == "follow_up":
        existing_fu = _count_kind(context["turns"], cur_q, "follow_up")
        if existing_fu >= max_follow_ups:
            action = "next_question"

    # Hard cap on reframes.
    if action == "reframe":
        if _count_kind(context["turns"], cur_q, "reframe") >= 1:
            action = "next_question"

    # Hard cap on clarifications (only path here is when Claude itself asked
    # for a clarification — dead-air path already gated above).
    if action == "clarification":
        if _count_kind(context["turns"], cur_q, "clarification") >= 1:
            action = "next_question"

    # Validate skip_to.
    skip_to_idx = decision.get("skip_to_question_index")
    if action == "skip_to":
        if (
            skip_to_idx is None
            or not isinstance(skip_to_idx, int)
            or skip_to_idx <= cur_q
            or skip_to_idx >= total_questions
        ):
            action = "next_question"

    # Behind-pace override on follow_up (kept from v1, but now talk-time based).
    if action == "follow_up" and total_minutes > 0 and total_questions > 0:
        expected_q = (talk_minutes / total_minutes) * total_questions
        if (cur_q - expected_q) < -1.5:
            action = "next_question"

    is_complete = action == "close"

    # 6. Build the question text we'll actually speak.
    if is_complete:
        # If Claude returned its own closing line, use it; else fall back.
        question_text = decision.get("question") or _closing_message(language)
    elif action == "next_question":
        # If Claude provided text, prefer it; otherwise fall back to the next
        # main guide question.
        if decision.get("question"):
            question_text = decision["question"]
        else:
            guide = _sorted_active_questions(project)
            nexts = [q for q in guide if q.question_index > cur_q]
            question_text = nexts[0].main_question if nexts else _closing_message(language)
    else:
        question_text = decision.get("question") or "Could you tell me a bit more?"

    # 7. TTS — deferred. We persist the turn first, then return a streaming URL
    # that the participant's browser will GET and that spawns the OpenAI TTS
    # call as bytes flow through. tts_audio_url is filled in below after we
    # have the new turn's ID.

    # 8. Compute new turn metadata + handle skip_to synthetic skip turns.
    next_turn_index = (turns[-1].turn_index + 1) if turns else 0

    if action == "next_question":
        new_q_index = cur_q + 1
        is_follow_up = False
        follow_up_idx = 0
        turn_kind = "main"
    elif action == "follow_up":
        new_q_index = cur_q
        is_follow_up = True
        follow_up_idx = _count_kind(context["turns"], cur_q, "follow_up") + 1
        turn_kind = "follow_up"
    elif action == "reframe":
        new_q_index = cur_q
        is_follow_up = False
        follow_up_idx = 0
        turn_kind = "reframe"
    elif action == "clarification":
        new_q_index = cur_q
        is_follow_up = False
        follow_up_idx = 0
        turn_kind = "clarification"
    elif action == "skip_to":
        # Insert synthetic skip_skip rows for every intermediate question, then
        # land on skip_to_question_index as a "main" ask-turn.
        for skipped_idx in range(cur_q + 1, skip_to_idx):
            db.add(
                InterviewTurn(
                    participant_id=participant_id,
                    turn_index=next_turn_index,
                    question_index=skipped_idx,
                    is_follow_up=False,
                    follow_up_index=0,
                    turn_kind="skip_skip",
                    question_text="[Skipped — implicitly answered earlier]",
                    response_transcript="[Implicitly answered in prior response]",
                )
            )
            next_turn_index += 1
        new_q_index = skip_to_idx
        is_follow_up = False
        follow_up_idx = 0
        turn_kind = "main"
    else:  # close
        new_q_index = cur_q
        is_follow_up = False
        follow_up_idx = 0
        turn_kind = "closing"

    new_turn = InterviewTurn(
        participant_id=participant_id,
        turn_index=next_turn_index,
        question_index=new_q_index,
        is_follow_up=is_follow_up,
        follow_up_index=follow_up_idx,
        turn_kind=turn_kind,
        question_text=question_text,
    )
    db.add(new_turn)
    db.flush()  # need new_turn.id before committing the streaming URL
    tts_audio_url = f"/audio/stream/{new_turn.id}"
    new_turn.tts_audio_url = tts_audio_url

    # 9. Wrap up bookkeeping.
    if is_complete:
        participant.status = "completed"
        participant.completed_at = datetime.utcnow()
        try:
            from app.services.email import send_email
            if participant.email:
                project_name = project.name
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
            pass

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
        "elapsed_seconds": int(elapsed * 60),
        "total_seconds": total_minutes * 60,
    }


def skip_question(participant_id: str, db) -> dict:
    """Advance past the current question without a response, return the next question."""
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if not participant:
        raise ValueError("Participant not found")

    project = participant.project
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    context = get_interview_context(participant_id, db)

    unanswered = [t for t in turns if not t.response_transcript]
    if unanswered:
        last = unanswered[-1]
        last.response_transcript = "[Skipped]"
        db.commit()

    current_q_index = context["current_question_index"]
    guide_questions = _sorted_active_questions(project)
    next_questions = [q for q in guide_questions if q.question_index > current_q_index]

    if not next_questions:
        closing_text = _closing_message(getattr(project, "language", None))
        # Persist a closing turn so the streaming endpoint can serve TTS.
        closing_turn = InterviewTurn(
            participant_id=participant_id,
            turn_index=len(turns),
            question_index=current_q_index,
            is_follow_up=False,
            follow_up_index=0,
            turn_kind="closing",
            question_text=closing_text,
        )
        db.add(closing_turn)
        db.flush()
        tts_url = f"/audio/stream/{closing_turn.id}"
        closing_turn.tts_audio_url = tts_url
        participant.status = "completed"
        participant.completed_at = datetime.utcnow()
        db.commit()

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

        return {
            "question_text": closing_text, "tts_audio_url": tts_url, "is_complete": True,
            "is_follow_up": False, "question_index": current_q_index,
            "elapsed_seconds": 0, "total_seconds": 0,
        }

    next_q = next_questions[0]
    question_text = next_q.main_question
    new_turn = InterviewTurn(
        participant_id=participant_id,
        turn_index=len(turns),
        question_index=next_q.question_index,
        is_follow_up=False,
        follow_up_index=0,
        turn_kind="main",
        question_text=question_text,
    )
    db.add(new_turn)
    db.flush()
    tts_url = f"/audio/stream/{new_turn.id}"
    new_turn.tts_audio_url = tts_url
    db.commit()

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
