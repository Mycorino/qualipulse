import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File, status
from starlette.concurrency import run_in_threadpool
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.limiter import limiter, participant_rate_key
from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.panel import PanelProfile, PanelTag, ParticipantMagicToken
from app.schemas.interview import (
    StartInterviewRequest,
    StartInterviewResponse,
    TurnResponse,
    ResumeCheckResponse,
    ResumeSummaryResponse,
)
from app.services.feature_gates import require_participant_limit
from app.services.interview_engine import (
    _active_elapsed_minutes as engine_active_elapsed_minutes,
    ensure_turn_audio as engine_ensure_turn_audio,
    finish_interview as engine_finish_interview,
    process_interview_turn,
    start_interview,
    skip_question as engine_skip_question,
    EmptyTranscriptError,
)
from app.services.storage import upload_audio
from app.services.transcode import needs_transcode, transcode_to_mp3
from app.services.verification import generate_magic_token, verify_magic_token

logger = logging.getLogger("auto_interview")

# Operations that make up the participant interview loop's AI spend.
_INTERVIEW_COST_OPERATIONS = ("interview_turn", "interview_warmup", "stt", "tts")

# How long an in-progress interview stays resumable (measured from the last
# answered turn). Must cover the reminder-email schedule in
# routers/scheduled_emails.py: the second reminder lands around day 3.
RESUME_MAX_IDLE_DAYS = 7
# Idle gap beyond which we rebase the pacing clock on resume (see
# check_resume_by_email). Short same-sitting reloads keep the true clock.
RESUME_REBASE_IDLE_SECONDS = 30 * 60


def _check_interview_budget(
    db: Session, company_id: str, *, in_flight: bool = False
) -> None:
    """Per-workspace daily AI-spend ceiling for the public interview loop.

    /respond chains Whisper + Claude + TTS on an unauthenticated endpoint;
    the 30/min rate limit alone still permits hundreds of dollars a day
    from one leaked link. Mirrors the copilot budget gate. In-flight turns
    get a 2x grace ceiling so a real participant mid-session isn't cut
    off the moment the workspace crosses the line.
    """
    limit = settings.INTERVIEW_DAILY_COST_LIMIT_USD
    if limit <= 0:
        return
    ceiling = limit * 2 if in_flight else limit
    from app.models.usage import AIUsageLog

    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    spent = (
        db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0))
        .filter(
            AIUsageLog.company_id == company_id,
            AIUsageLog.operation.in_(_INTERVIEW_COST_OPERATIONS),
            AIUsageLog.created_at >= day_start,
        )
        .scalar()
        or 0.0
    )
    if spent >= ceiling:
        logger.warning(
            "Interview daily budget reached (company=%s spent=$%.2f ceiling=$%.2f in_flight=%s)",
            company_id, spent, ceiling, in_flight,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "interview_daily_limit_reached",
                "message": (
                    "This study has reached its daily interview capacity. "
                    "Please come back tomorrow, or contact the researcher "
                    "who shared this link."
                ),
            },
        )


def _sync_panel_consent_to_participant(participant: Participant, db: Session) -> None:
    """Copy PanelProfile.panel_consent onto the participant (matched by email).

    The panel profile is saved before the Participant row exists (the
    questionnaire runs pre-screening), so the two are only linkable by email.
    Denormalising the flag here lets researchers filter/export "OK to
    recontact" participants without a join. Best-effort — never raises.
    """
    try:
        if not participant.email:
            return
        profile = (
            db.query(PanelProfile)
            .filter(func.lower(PanelProfile.email) == participant.email.strip().lower())
            .first()
        )
        if profile is not None and participant.panel_consent != bool(profile.panel_consent):
            participant.panel_consent = bool(profile.panel_consent)
            db.commit()
    except Exception:
        logger.exception("panel-consent sync failed for participant %s", participant.id)


def _spawn_transcript_cleanup(participant_id: str) -> None:
    """Fire the ASR sense-check pass in a daemon thread with its own session."""
    import threading

    from app.database import session_scope
    from app.services.transcript_cleanup import cleanup_participant

    def _run():
        try:
            with session_scope() as bg_db:
                cleanup_participant(participant_id, bg_db)
        except Exception:  # pragma: no cover — never surface to the interview
            logger.exception("transcript cleanup thread failed for %s", participant_id)

    threading.Thread(target=_run, daemon=True).start()

router = APIRouter(prefix="/interview", tags=["interview"])

ALGORITHM = "HS256"
SESSION_TOKEN_EXPIRE_HOURS = 2

# Languages the participant UI + AI interviewer + TTS support.
SUPPORTED_INTERVIEW_LANGS = {"en", "fr", "de", "es", "it", "pt"}


def _effective_interview_language(participant: Participant) -> str:
    """The authoritative language the AI is conducting this interview in.

    Participant's explicit choice wins; otherwise the study's configured
    language; otherwise English. Normalised to a supported 2-letter code so
    the frontend can lock its UI chrome to exactly what the AI is speaking.
    """
    project = participant.project
    candidate = (
        getattr(participant, "preferred_language", None)
        or getattr(project, "language", None)
        or "en"
    )
    code = (candidate or "en").lower()[:2]
    return code if code in SUPPORTED_INTERVIEW_LANGS else "en"


class ScreenRequest(BaseModel):
    answers: dict[str, str]  # question_id → selected option


class ResumeCheckRequest(BaseModel):
    email: str
    # Magic-link session JWT proving the caller actually controls this
    # email. Required — without it, knowing someone's email + the public
    # link token would be enough to hijack their in-progress interview.
    session_token: str | None = None


class VerificationRequest(BaseModel):
    email: str
    # Participant-chosen UI/interview language for the magic-link email copy.
    # Falls back to the project language when omitted.
    lang: str | None = None


# Recording uploads run concurrently with transcription. Small pool: the work
# is network-bound and one slot per in-flight turn is plenty at Cloud Run's
# concurrency of 16.
_UPLOAD_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="rec-upload")


class SkipRequest(BaseModel):
    """Optional body for /skip. ``turn_index`` lets the server verify the
    client is skipping the question it is actually showing."""
    turn_index: int | None = None


class ParticipantProfileRequest(BaseModel):
    display_name: str | None = None
    age_range: str | None = None
    country: str | None = None
    profession: str | None = None
    email: str | None = None


class PanelProfileRequest(BaseModel):
    email: str
    session_token: str
    first_name: str | None = None
    age_range: str | None = None
    gender: str | None = None
    country: str | None = None
    city: str | None = None
    education: str | None = None
    employment_status: str | None = None
    job_function: str | None = None
    seniority: str | None = None
    industry: str | None = None
    company_size: str | None = None
    preferred_language: str | None = None
    panel_consent: bool = False
    tag_ids: list[int] = []


def _create_session_token(email: str, link_token: str) -> str:
    """Create a short-lived JWT for a verified participant session."""
    expire = datetime.now(timezone.utc) + timedelta(hours=SESSION_TOKEN_EXPIRE_HOURS)
    payload = {
        "email": email,
        "link_token": link_token,
        "verified": True,
        "exp": expire,
        "type": "participant_session",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def _is_profile_complete(profile: "PanelProfile | None") -> bool:
    """A returning participant counts as 'known' once the core demographics
    are on file. We deliberately key off the always-asked fields (name,
    country, age, education, employment) — the work-specific fields are
    conditional, so requiring them would re-prompt retirees/students forever.
    """
    if profile is None:
        return False
    required = (
        profile.first_name,
        profile.country,
        profile.age_range,
        profile.education,
        profile.employment_status,
    )
    return all(bool(v) for v in required)


def _decode_session_token(token: str) -> dict | None:
    """Decode and validate a participant session JWT. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "participant_session" or not payload.get("verified"):
            return None
        return payload
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# New endpoints
# ---------------------------------------------------------------------------

@router.get("/panel-tags")
def get_panel_tags(db: Session = Depends(get_db)):
    """Return all available panel tags for profile collection."""
    tags = db.query(PanelTag).all()
    return [{"id": t.id, "name": t.name, "category": t.category} for t in tags]


@router.post("/{token}/request-verification")
@limiter.limit("5/minute")
def request_verification(
    request: Request,
    token: str,
    body: VerificationRequest,
    db: Session = Depends(get_db),
):
    """Send a magic link to the participant's email to verify and start the interview.

    The frontend already enforces a 60-second resend cooldown, so we don't
    dedup on the server side — if the first send silently failed (SendGrid
    reject, network blip, etc.) the participant can retry immediately and
    actually get an email. We still surface a 502 when SendGrid refuses so
    the UI can show a real error instead of pretending success.
    """
    link = _get_active_link_or_404(token, db)

    # Prefer the participant's chosen language for the email body so the copy
    # matches the language they'll do the interview in; fall back to the
    # project's configured language.
    _SUPPORTED_LANGS = {"en", "fr", "de", "es", "it", "pt"}
    chosen = (body.lang or "").lower()[:2]
    if chosen in _SUPPORTED_LANGS:
        email_lang = chosen
    else:
        email_lang = getattr(link.project, "language", "en") or "en"

    _, delivered = generate_magic_token(
        db, body.email, token, lang=email_lang
    )
    if not delivered:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "We couldn't send the verification email. Please try again in a "
                "moment — if the problem persists, contact the researcher who "
                "shared this link."
            ),
        )
    return {"message": "Magic link sent", "email": body.email}


@router.get("/verify/{magic_token}")
def verify_participant_token(
    magic_token: str,
    db: Session = Depends(get_db),
):
    """Validate a magic token and return a session JWT for the participant."""
    record = verify_magic_token(db, magic_token)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has expired or has already been used. Please request a new one.",
        )

    session_token = _create_session_token(record.email, record.interview_link_token)

    # Recognize a returning participant: if a panel profile with the core
    # demographics already exists, the frontend skips the profiling
    # questionnaire entirely (the magic link behaves like a login).
    profile = (
        db.query(PanelProfile)
        .filter(PanelProfile.email == record.email)
        .first()
    )
    return {
        "session_token": session_token,
        "link_token": record.interview_link_token,
        "email": record.email,
        "profile_complete": _is_profile_complete(profile),
        "first_name": profile.first_name if profile else None,
        "preferred_language": profile.preferred_language if profile else None,
    }


@router.post("/{token}/panel-profile")
@limiter.limit("10/minute")
def save_panel_profile(
    request: Request,
    token: str,
    body: PanelProfileRequest,
    db: Session = Depends(get_db),
):
    """Upsert a panel profile for a participant who consented.

    Requires a valid participant session_token (issued by /verify/{magic})
    matching both the body email and the link token. Without this, anyone
    with the public link could overwrite the panel profile of any email.
    """
    _get_active_link_or_404(token, db)

    session_payload = _decode_session_token(body.session_token)
    if (
        session_payload is None
        or session_payload.get("email", "").lower() != body.email.lower()
        or session_payload.get("link_token") != token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session for panel profile update.",
        )

    email_norm = body.email.strip().lower()
    profile = (
        db.query(PanelProfile)
        .filter(func.lower(PanelProfile.email) == email_norm)
        .first()
    )
    newly_consented = False
    if profile is None:
        profile = PanelProfile(email=email_norm)
        db.add(profile)

    was_consented = bool(profile.panel_consent)

    # Update fields
    if body.first_name is not None:
        profile.first_name = body.first_name
    if body.age_range is not None:
        profile.age_range = body.age_range
    if body.gender is not None:
        profile.gender = body.gender
    if body.country is not None:
        profile.country = body.country
    if body.city is not None:
        profile.city = body.city
    if body.education is not None:
        profile.education = body.education
    if body.employment_status is not None:
        profile.employment_status = body.employment_status
    if body.job_function is not None:
        profile.job_function = body.job_function
    if body.seniority is not None:
        profile.seniority = body.seniority
    if body.industry is not None:
        profile.industry = body.industry
    if body.company_size is not None:
        profile.company_size = body.company_size
    if body.preferred_language is not None:
        profile.preferred_language = body.preferred_language

    if body.panel_consent:
        profile.panel_consent = True
        profile.consent_at = datetime.utcnow()
        profile.consent_interview_token = token
        newly_consented = not was_consented

    # Replace tags
    if body.tag_ids:
        tags = db.query(PanelTag).filter(PanelTag.id.in_(body.tag_ids)).all()
        profile.tags = tags

    profile.last_active = datetime.utcnow()
    db.commit()

    # Reflect the consent onto any participant rows this person already has on
    # this link — covers the post-interview re-prompt, where the Participant
    # row exists before the opt-in lands.
    consent_val = bool(profile.panel_consent)
    link_participants = (
        db.query(Participant)
        .join(InterviewLink, Participant.link_id == InterviewLink.id)
        .filter(
            InterviewLink.token == token,
            func.lower(Participant.email) == email_norm,
        )
        .all()
    )
    if any(p.panel_consent != consent_val for p in link_participants):
        for p in link_participants:
            p.panel_consent = consent_val
        db.commit()

    # On the first opt-in, email the durable "manage your panel" link so the
    # panelist can keep enriching their profile over time (more profile =
    # more study invites). Best-effort — never blocks the save.
    if newly_consented:
        try:
            from app.services.panel_service import create_panel_session
            from app.services.email import send_panel_access_link
            lang = (profile.preferred_language or "en")[:2]
            send_panel_access_link(
                email=profile.email,
                token=create_panel_session(profile.email),
                lang=lang,
            )
        except Exception:
            logger.exception("panel access link send failed for %s", body.email)

    return {"saved": True}


# ---------------------------------------------------------------------------
# Demo redirect endpoint — must be defined before /{token} catch-all
# ---------------------------------------------------------------------------

@router.get("/demo")
@limiter.limit("60/minute")
def get_demo_link(request: Request, db: Session = Depends(get_db)):
    """Return the active interview link token for the public demo company.

    The frontend navigates to /i/{redirect_token} so participants always land
    on a real, active interview link rather than the literal /i/demo URL.
    """
    company = db.query(Company).filter(Company.email == "demo@autointerview.com").first()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo not available")
    link = (
        db.query(InterviewLink)
        .join(InterviewLink.project)
        .filter(
            InterviewLink.is_active.is_(True),
            InterviewLink.project.has(company_id=company.id),
        )
        .first()
    )
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo not available")
    return {"redirect_token": link.token}


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------

@router.get("/{token}/screening-questions")
@limiter.limit("60/minute")
def get_screening_questions(
    request: Request, token: str, lang: str = "", db: Session = Depends(get_db)
):
    """Return screening questions localized to ``lang`` (no auth required).

    Each option is ``{value, label}`` — ``value`` is the canonical option (the
    disqualification gate's stable identity, which the client submits back),
    ``label`` is the localized display text. Missing translations are generated
    on demand and cached (hybrid fallback), falling back to canonical text.
    """
    link = _get_active_link_or_404(token, db)
    project = link.project
    if lang:
        from app.services.screening_translation import ensure_screening_language
        ensure_screening_language(project, lang, db)
    out = []
    for q in sorted(project.screening_questions, key=lambda q: q.sort_order):
        question, options = q.localized(lang)
        out.append({
            "id": q.id,
            "question": question,
            "options": options,
            "sort_order": q.sort_order,
        })
    return out


@router.post("/{token}/screen")
@limiter.limit("30/minute")
def screen_participant(request: Request, token: str, body: ScreenRequest, db: Session = Depends(get_db)):
    """Check answers against disqualifying options. Returns qualified status."""
    link = _get_active_link_or_404(token, db)
    for q in sorted(link.project.screening_questions, key=lambda q: q.sort_order):
        answer = body.answers.get(q.id)
        if answer and answer in q.disqualifying_options_list:
            return {"qualified": False, "disqualified_on": q.question}
    return {"qualified": True}


@router.get("/{token}")
@limiter.limit("60/minute")
def validate_link(
    request: Request,
    token: str,
    lang: str = "",
    db: Session = Depends(get_db),
):
    """Validate an interview link and return project info. No auth required.

    When ``lang`` is supplied the participant-facing study name is localized
    (translated on demand + cached); the canonical ``project.name`` stays the
    researcher's source of truth.
    """
    link = _get_active_link_or_404(token, db)
    project = link.project
    if lang:
        from app.services.screening_translation import (
            ensure_study_name_language,
            ensure_research_context_language,
        )
        ensure_study_name_language(project, lang, db)
        ensure_research_context_language(project, lang, db)

    branding_mode = getattr(project, "branding_mode", "standard") or "standard"
    anonymous = branding_mode == "anonymous"

    return {
        "project_name": project.localized_name(lang) if lang else project.name,
        # Company name powers the participant-facing identity avatar when
        # the project has no explicit researcher_name / logo. Falling back
        # to project_name produced nonsense initials (study title → "PN").
        # Anonymous studies strip ALL identity fields server-side — the
        # participant payload never contains who is running the research.
        "company_name": None if anonymous else (project.company.name if project.company else None),
        "welcome_message": project.welcome_message,
        "language": project.language,
        "interview_duration_minutes": project.interview_duration_minutes,
        "question_count": len([q for q in project.guide_questions if not q.deprecated_at]),
        "researcher_name": None if anonymous else project.researcher_name,
        "researcher_logo_url": None if anonymous else project.researcher_logo_url,
        "research_context": project.localized_research_context(lang) if lang else project.research_context,
        "privacy_policy_url": project.privacy_policy_url,
        "panel_collection_enabled": getattr(project, "panel_collection_enabled", True),
        "branding": {
            "mode": branding_mode,
            "primary_color": getattr(project, "brand_primary_color", None) if branding_mode == "branded" else None,
            "font": getattr(project, "brand_font", None) if branding_mode == "branded" else None,
        },
    }


@router.post("/{token}/resume", response_model=ResumeCheckResponse)
@limiter.limit("60/minute")
def check_resume_by_email(
    request: Request,
    token: str,
    body: ResumeCheckRequest,
    db: Session = Depends(get_db),
):
    """Check if an in-progress interview exists for this email address.

    Requires a magic-link session token proving possession of the email:
    the participant_id this endpoint returns grants access to the live
    interview session (/respond, /resume-summary), so handing it out on a
    bare email match would let anyone who knows a participant's email
    hijack their in-progress interview and read prior answers.
    """
    link = _get_active_link_or_404(token, db)

    session_payload = (
        _decode_session_token(body.session_token) if body.session_token else None
    )
    if (
        session_payload is None
        or session_payload.get("link_token") != token
        or (session_payload.get("email") or "").strip().lower()
        != (body.email or "").strip().lower()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email verification is required to resume an interview.",
        )
    email = body.email
    participant = (
        db.query(Participant)
        .filter(
            Participant.link_id == link.id,
            Participant.email == email,
            Participant.status == "in_progress",
        )
        .order_by(Participant.started_at.desc())
        .first()
    )
    if not participant:
        return ResumeCheckResponse(found=False)

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    last_turn = turns[-1] if turns else None

    # Resume window: reject sessions idle for more than RESUME_MAX_IDLE_DAYS
    # (measured from the last answered turn, not the start) — beyond that the
    # participant is better off starting fresh.
    def _naive(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

    now = datetime.utcnow()
    started = _naive(participant.started_at) if participant.started_at else now
    last_activity = (
        _naive(last_turn.created_at)
        if last_turn is not None and last_turn.created_at
        else started
    )
    if (now - last_activity).total_seconds() > RESUME_MAX_IDLE_DAYS * 86400:
        return ResumeCheckResponse(found=False)

    # Rebase the pacing clock after a long break. The engine paces the
    # interview on wall-clock elapsed time from started_at, so a participant
    # coming back a day later (e.g. from a reminder email) would instantly
    # trip the "time's up" close gate. Shift started_at so elapsed reflects
    # the time actually spent interviewing, not the days spent away.
    idle_seconds = (now - last_activity).total_seconds()
    if idle_seconds > RESUME_REBASE_IDLE_SECONDS:
        active_seconds = max(0.0, (last_activity - started).total_seconds())
        participant.started_at = now - timedelta(seconds=active_seconds)
        db.commit()
    return ResumeCheckResponse(
        found=True,
        participant_id=participant.id,
        last_question=last_turn.question_text if last_turn else None,
        turn_count=len(turns),
        question_index=last_turn.question_index or 0 if last_turn else 0,
    )


@router.get("/{token}/{participant_id}/resume-summary", response_model=ResumeSummaryResponse)
def get_resume_summary(
    token: str,
    participant_id: str,
    db: Session = Depends(get_db),
):
    """Return a summary of what has been covered so far for a resume flow."""
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)

    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    covered: list[str] = []
    seen_q: set[int] = set()
    for t in turns:
        if (
            not t.is_follow_up
            and t.question_index is not None
            and t.question_index not in seen_q
            and t.response_transcript
        ):
            seen_q.add(t.question_index)
            covered.append(t.question_text)

    # Same active-time clock the engine paces on, so the summary can never
    # tell a returning participant they have been interviewing for hours.
    elapsed_minutes = engine_active_elapsed_minutes(
        participant, turns, datetime.utcnow()
    )

    last_turn = turns[-1] if turns else None
    return ResumeSummaryResponse(
        questions_covered=covered,
        last_question=last_turn.question_text if last_turn else None,
        turn_count=len(turns),
        elapsed_minutes=round(elapsed_minutes, 1),
        language=_effective_interview_language(participant),
    )


@router.post("/{token}/start", response_model=StartInterviewResponse)
@limiter.limit("30/minute")
def start_interview_session(
    request: Request,
    token: str,
    body: StartInterviewRequest | None = None,
    db: Session = Depends(get_db),
):
    """Create a new participant and generate the first interview question.

    Email verification is **optional**. If the request carries a valid
    ``session_token`` from the magic-link flow we record the verified
    email on the participant; otherwise we accept an anonymous start so
    participants whose mail providers silently drop our magic link (hi
    iCloud, hi Outlook Safe Senders) aren't locked out of the study.
    """
    link = _get_active_link_or_404(token, db)

    # Validate session token if one was supplied. A missing token is a
    # valid "skip email" path — not an error.
    session_payload = None
    if body and body.session_token:
        session_payload = _decode_session_token(body.session_token)
        if session_payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This verification link has expired. Please request a new one or continue without email.",
            )
        # Ensure the session is for this link
        if session_payload.get("link_token") != token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session token does not match this interview link",
            )

    # Use email from session token if we have one. Otherwise fall back to
    # whatever the participant typed in the landing form (or nothing).
    verified_email: str | None = None
    email_was_verified = False
    if session_payload is not None:
        verified_email = session_payload.get("email")
        email_was_verified = True
    elif body and getattr(body, "email", None):
        verified_email = body.email
    # Normalise so the same person matches across projects and against their
    # PanelProfile row (whose lookups are also case-insensitive).
    verified_email = verified_email.strip().lower() if verified_email else None

    # Duplicate guard — one interview per email per link. The client checks
    # /resume before starting, but that check is skippable (direct API call,
    # a second browser, a race between two tabs), and every duplicate that
    # reaches completion burns a credit and pollutes the analysis with the
    # same voice twice. Enforce it server-side too.
    if verified_email:
        existing = (
            db.query(Participant)
            .filter(
                Participant.link_id == link.id,
                func.lower(Participant.email) == verified_email,
            )
            .order_by(Participant.started_at.desc())
            .first()
        )
        if existing is not None and existing.status == "completed":
                raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "already_completed",
                    "message": "This email has already completed the interview.",
                },
            )
        if existing is not None:
            # An in-progress interview already exists: hand it back instead of
            # creating a second one. The frontend resumes into it rather than
            # showing an error, so a participant who reopened the link in a new
            # browser simply continues where they left off.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "resume_available",
                    "participant_id": existing.id,
                    "message": "An interview is already in progress for this email.",
                },
            )

    # Per-link participant cap. Distinct from the workspace credit gate below:
    # this bounds a single link's exposure so a leaked or over-shared link
    # can't drain the whole balance. In-progress participants count, so a
    # burst of simultaneous starts can't overshoot the cap.
    if link.max_participants is not None:
        admitted = (
            db.query(Participant)
            .filter(Participant.link_id == link.id)
            .count()
        )
        if admitted >= link.max_participants:
            logger.info(
                "interview start blocked: link=%s at participant cap %s",
                link.id, link.max_participants,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "link_full",
                    "message": "This interview link has reached its participant limit.",
                },
            )

    # Enforce participant limit for this project. The new BillingService
    # handles legacy plans by deferring back to the existing
    # ``require_participant_limit`` gate (``is_legacy=True``); for credits-
    # based plans it checks the current credit balance.
    from app.models.project import Project as ProjectModel
    from app.services.billing_service import can_start_interview
    project = db.query(ProjectModel).filter(ProjectModel.id == link.project_id).first()
    if project and project.company:
        _check_interview_budget(db, project.company_id)
        decision = can_start_interview(db, project.company_id)
        if not decision.allowed:
            # Log the real reason so blocked studies are diagnosable — the
            # most common is the researcher never verifying their own email
            # (fraud floor), which otherwise looks like a generic failure to
            # both the participant and the researcher.
            logger.warning(
                "interview start blocked: company=%s project=%s reason=%s",
                project.company_id, project.id, decision.reason,
            )
            # Translate to the participant-facing message — never reveal
            # credit-balance details on the public endpoint.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "study_unavailable",
                    "message": "This study is not accepting new responses right now. Please reach out to the researcher.",
                },
            )
        if decision.is_legacy:
            current_count = db.query(Participant).filter(
                Participant.project_id == link.project_id,
                Participant.status == "completed",
            ).count()
            require_participant_limit(project.company, project, current_count)

    # Validate the participant's chosen interview language against the
    # supported set; ignore anything else so a junk value can't reach the
    # AI prompt / TTS.
    chosen_lang = (getattr(body, "preferred_language", None) or "").lower()[:2] if body else ""
    preferred_language = chosen_lang if chosen_lang in SUPPORTED_INTERVIEW_LANGS else None

    # Snapshot the screening answers the participant clicked through, keyed
    # by canonical option values (the gate's stable identity). Sanitized
    # against the project's screener: unknown question ids and options that
    # aren't in the canonical list are dropped, so a crafted request can't
    # inject text into researcher-facing surfaces or the analysis prompt.
    # Question text is frozen at answer time.
    screening_snapshot = None
    raw_answers = getattr(body, "screening_answers", None) if body else None
    if raw_answers:
        snapshot = []
        for q in sorted(link.project.screening_questions, key=lambda q: q.sort_order):
            answer = raw_answers.get(q.id)
            if answer and answer in q.options_list:
                snapshot.append({"question_id": q.id, "question": q.question, "answer": answer})
        if snapshot:
            screening_snapshot = json.dumps(snapshot)

    participant = Participant(
        link_id=link.id,
        project_id=link.project_id,
        display_name=body.display_name if body else None,
        profession=body.profession if body else None,
        age_range=body.age_range if body else None,
        country=body.country if body else None,
        email=verified_email,
        email_verified=email_was_verified,
        preferred_language=preferred_language,
        screening_answers=screening_snapshot,
        status="in_progress",
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)

    result = start_interview(participant.id, db)

    return StartInterviewResponse(
        participant_id=participant.id,
        first_question=result["question_text"],
        tts_audio_url=result["tts_audio_url"],
        turn_index=int(result.get("turn_index", 0)),
        is_warmup=bool(result.get("is_warmup", False)),
        language=_effective_interview_language(participant),
    )


# Accessibility text fallback: max length for a typed answer. Generous enough
# for a long verbal-style response, tight enough to keep Claude prompts sane.
MAX_TEXT_ANSWER_CHARS = 5000


@router.post("/{token}/{participant_id}/respond", response_model=TurnResponse)
@limiter.limit("30/minute", key_func=participant_rate_key)
async def respond_to_question(
    request: Request,
    token: str,
    participant_id: str,
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    turn_index: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Accept a participant response, process it, and return the next question.

    Exactly one of `audio` (recorded answer, the default path) or `text`
    (typed answer, the accessibility fallback for participants without a
    working microphone) must be provided.
    """
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)

    if (audio is None) == (text is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "audio_or_text_required",
                "message": "Provide exactly one of audio or text.",
            },
        )

    # Spend ceiling (2x grace for in-flight sessions) — checked before any
    # STT/Claude/TTS work is done.
    _check_interview_budget(db, link.project.company_id, in_flight=True)

    if participant.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is already completed",
        )

    # Turn reconciliation. The client echoes the turn_index it believes it is
    # answering; without it, a retry sent after the client's timeout (but
    # after the server finished) was accepted as the answer to a question the
    # participant never heard.
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    pending = turns[-1] if turns else None

    def _turn_response(turn, *, transcript=None) -> TurnResponse:
        return TurnResponse(
            question_text=turn.question_text,
            tts_audio_url=turn.tts_audio_url or "",
            is_complete=participant.status == "completed",
            is_follow_up=turn.is_follow_up or False,
            question_index=turn.question_index or 0,
            turn_index=turn.turn_index,
            elapsed_seconds=0,
            total_seconds=0,
            transcript=transcript,
        )

    if pending is not None and turn_index is not None and turn_index != pending.turn_index:
        answered = next((t for t in turns if t.turn_index == turn_index), None)
        following = next((t for t in turns if t.turn_index == turn_index + 1), None)
        if answered is not None and answered.response_transcript and following is not None:
            # The server already processed this answer (the client timed out
            # and retried): replay the question that followed it instead of
            # accepting the blob against a question they never heard.
            return _turn_response(following, transcript=answered.response_transcript)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "turn_mismatch",
                "message": "This answer is for an earlier question.",
                "current": _turn_response(pending).model_dump(),
            },
        )

    # Deduplication: the pending turn already has a response (double submit).
    if pending is not None and pending.response_transcript:
        return _turn_response(pending, transcript=pending.response_transcript)

    if text is not None:
        # Accessibility text fallback — no STT, no transcode, no audio upload.
        # The typed answer flows into the engine exactly like a Whisper
        # transcript; the turn's audio_recording_url stays NULL.
        typed = text.strip()
        if not typed:
            # Mirror the EmptyTranscriptError response shape so the frontend
            # handles a blank typed answer identically to silent audio.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "empty_transcript",
                    "message": "Your answer is empty. Please write a response and try again.",
                },
            )
        if len(typed) > MAX_TEXT_ANSWER_CHARS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "text_too_long",
                    "message": f"Answers are limited to {MAX_TEXT_ANSWER_CHARS} characters.",
                },
            )
        try:
            result = await run_in_threadpool(
                process_interview_turn,
                participant_id, None, None, db, transcript_override=typed,
            )
        except EmptyTranscriptError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "empty_transcript", "message": str(e)},
            )
    else:
        audio_data = await audio.read()
        ext = os.path.splitext(audio.filename or "recording.webm")[1] or ".webm"

        # Normalise to MP3 for cross-browser playback. Participant browsers record
        # webm/opus (Chrome/Firefox/Android), which Safari/iOS cannot decode, so a
        # researcher reviewing on a Mac would see "Audio unavailable". MP3 plays
        # everywhere and Whisper transcribes it fine. On any transcode failure
        # (e.g. ffmpeg missing in local dev) we fall back to the original bytes.
        # ffmpeg is blocking and CPU-bound: keep it off the event loop.
        if needs_transcode(ext):
            mp3_data = await run_in_threadpool(transcode_to_mp3, audio_data, ext)
            if mp3_data:
                audio_data = mp3_data
                ext = ".mp3"

        audio_key = f"recordings/{participant_id}/{uuid.uuid4().hex}{ext}"
        # Upload the recording concurrently with transcription instead of
        # serialising put -> get -> Whisper. The engine resolves the future
        # once it needs the playback URL, and tolerates an upload failure.
        upload_future = _UPLOAD_POOL.submit(upload_audio, audio_data, audio_key)

        try:
            result = await run_in_threadpool(
                process_interview_turn,
                participant_id, audio_key, None, db,
                None, audio_data, upload_future,
            )
        except EmptyTranscriptError as e:
            # 422 so the frontend can distinguish "bad audio, please retry" from
            # 5xx transport failures. The frontend preserves the blob for re-submit.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "empty_transcript", "message": str(e)},
            )

    # On completion, kick off an async ASR sense-check pass (Haiku) that fixes
    # obvious STT errors (proper nouns, domain terms) using study context. The
    # original transcript is preserved; this only fills cleaned_response. Daemon
    # thread with a fresh session — never blocks or fails the interview.
    if result["is_complete"]:
        _spawn_transcript_cleanup(participant_id)
        _sync_panel_consent_to_participant(participant, db)

    return TurnResponse(
        question_text=result["question_text"],
        tts_audio_url=result["tts_audio_url"],
        is_complete=result["is_complete"],
        is_follow_up=result.get("is_follow_up", False),
        question_index=result.get("question_index", 0),
        turn_index=result.get("turn_index", 0),
        elapsed_seconds=result.get("elapsed_seconds", 0),
        total_seconds=result.get("total_seconds", 0),
        coaching_hint=result.get("coaching_hint"),
        transcript=result.get("transcript"),
        is_warmup=False,
    )


@router.post("/{token}/{participant_id}/skip")
@limiter.limit("30/minute", key_func=participant_rate_key)
async def skip_question(
    request: Request,
    token: str,
    participant_id: str,
    body: SkipRequest | None = None,
    db: Session = Depends(get_db),
):
    """Skip the current question and advance to the next one."""
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)

    if participant.status == "completed":
        raise HTTPException(status_code=400, detail="Interview already completed")

    # Same reconciliation as /respond: never skip a question other than the
    # one the participant is actually looking at.
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    pending = turns[-1] if turns else None
    if (
        body is not None
        and body.turn_index is not None
        and pending is not None
        and body.turn_index != pending.turn_index
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "turn_mismatch",
                "message": "This skip is for an earlier question.",
                "current": TurnResponse(
                    question_text=pending.question_text,
                    tts_audio_url=pending.tts_audio_url or "",
                    is_complete=False,
                    is_follow_up=pending.is_follow_up or False,
                    question_index=pending.question_index or 0,
                    turn_index=pending.turn_index,
                ).model_dump(),
            },
        )

    result = await run_in_threadpool(engine_skip_question, participant_id, db)

    if result["is_complete"]:
        _sync_panel_consent_to_participant(participant, db)
        _spawn_transcript_cleanup(participant_id)

    return TurnResponse(
        question_text=result["question_text"],
        tts_audio_url=result["tts_audio_url"],
        is_complete=result["is_complete"],
        is_follow_up=result.get("is_follow_up", False),
        question_index=result.get("question_index", 0),
        turn_index=result.get("turn_index", 0),
        elapsed_seconds=result.get("elapsed_seconds", 0),
        total_seconds=result.get("total_seconds", 0),
    )


@router.post("/{token}/{participant_id}/finish", response_model=TurnResponse)
@limiter.limit("10/minute", key_func=participant_rate_key)
async def finish_interview_early(
    request: Request,
    token: str,
    participant_id: str,
    db: Session = Depends(get_db),
):
    """Participant-initiated "Finish here". Closes the interview gracefully.

    Idempotent: calling it on an already-completed interview replays the
    stored closing turn.
    """
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)
    already_complete = participant.status == "completed"

    result = await run_in_threadpool(engine_finish_interview, participant_id, db)

    if not already_complete:
        _sync_panel_consent_to_participant(participant, db)
        _spawn_transcript_cleanup(participant_id)

    return TurnResponse(
        question_text=result["question_text"],
        tts_audio_url=result["tts_audio_url"],
        is_complete=True,
        is_follow_up=False,
        question_index=result.get("question_index", 0),
        turn_index=result.get("turn_index", 0),
        elapsed_seconds=result.get("elapsed_seconds", 0),
        total_seconds=result.get("total_seconds", 0),
    )


@router.get("/{token}/{participant_id}/turn-audio")
@limiter.limit("60/minute", key_func=participant_rate_key)
async def get_turn_audio(
    request: Request,
    token: str,
    participant_id: str,
    turn_index: int,
    db: Session = Depends(get_db),
):
    """Voice for one interviewer turn, synthesised on first request.

    /respond returns the question text without waiting for TTS; the client
    renders it immediately and calls this to fetch the audio. Returns
    ``{"tts_audio_url": null}`` when synthesis is unavailable, which the
    client already handles by staying text-only.
    """
    link = _get_active_link_or_404(token, db)
    _get_participant_or_404(participant_id, link, db)
    url = await run_in_threadpool(engine_ensure_turn_audio, participant_id, turn_index, db)
    return {"tts_audio_url": url}


@router.patch("/{token}/{participant_id}/profile")
@limiter.limit("10/minute", key_func=participant_rate_key)
def update_participant_profile(
    request: Request,
    token: str,
    participant_id: str,
    body: ParticipantProfileRequest,
    db: Session = Depends(get_db),
):
    """Post-interview demographics for participants without a magic-link
    session. Cannot set panel consent (that needs a verified email, see
    POST /interview/{token}/panel-profile); email lands unverified.
    """
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)

    if body.display_name is not None:
        participant.display_name = body.display_name.strip()[:255] or None
    if body.age_range is not None:
        participant.age_range = body.age_range.strip()[:20] or None
    if body.country is not None:
        participant.country = body.country.strip()[:100] or None
    if body.profession is not None:
        participant.profession = body.profession.strip()[:100] or None
    if body.email is not None and not participant.email:
        email = body.email.strip().lower()[:255]
        if email:
            participant.email = email
            participant.email_verified = False
    db.commit()
    return {"saved": True}


@router.get("/{token}/{participant_id}/status")
def get_interview_status(
    token: str,
    participant_id: str,
    db: Session = Depends(get_db),
):
    """Get current interview status for a participant."""
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    last_question = turns[-1].question_text if turns else None

    return {
        "participant_id": participant.id,
        "status": participant.status,
        "turn_count": len(turns),
        "last_question": last_question,
        "language": _effective_interview_language(participant),
        "started_at": participant.started_at.isoformat() if participant.started_at else None,
        "completed_at": participant.completed_at.isoformat() if participant.completed_at else None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_active_link_or_404(token: str, db: Session) -> InterviewLink:
    link = (
        db.query(InterviewLink)
        .filter(InterviewLink.token == token, InterviewLink.is_active.is_(True))
        .first()
    )
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview link not found or inactive",
        )
    return link


def _get_participant_or_404(
    participant_id: str, link: InterviewLink, db: Session
) -> Participant:
    participant = (
        db.query(Participant)
        .filter(
            Participant.id == participant_id,
            Participant.link_id == link.id,
        )
        .first()
    )
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participant not found",
        )
    return participant
