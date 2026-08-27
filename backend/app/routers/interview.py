import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File, status
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
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
from app.services.interview_preview import (
    normalise_lang as normalise_preview_lang,
    render_link_preview_html,
)
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
from app.services.verification import (
    CodeResult,
    generate_magic_token,
    verify_code,
    verify_magic_token,
)

logger = logging.getLogger("auto_interview")

# Operations that make up the participant interview loop's AI spend.
_INTERVIEW_COST_OPERATIONS = (
    "interview_turn", "interview_warmup", "stt", "tts", "realtime_interview",
)

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


class VerifyCodeRequest(BaseModel):
    email: str
    code: str


# Device-handoff tokens: short-lived so a QR code screenshot or a link pasted
# into the wrong chat doesn't stay live. Long enough to fetch a second device
# and scan without rushing.
HANDOFF_TOKEN_EXPIRE_MINUTES = 30


class HandoffCreateResponse(BaseModel):
    handoff_token: str
    expires_in_seconds: int


class HandoffClaimRequest(BaseModel):
    handoff_token: str


class HandoffClaimResponse(BaseModel):
    participant_id: str
    last_question: str | None = None
    turn_count: int = 0
    question_index: int = 0
    email: str | None = None
    # Minted when the participant has an email on file, so email-based
    # flows (later resume, reminders) keep working from the new device.
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


def _create_handoff_token(participant_id: str, link_token: str) -> str:
    """Signed continue-on-another-device token, bound to one in-progress
    interview. Possession-scoped: it is only ever displayed on the screen of
    the device already holding the interview session, so anyone who has it
    could already drive the interview via the participant_id it carries."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=HANDOFF_TOKEN_EXPIRE_MINUTES)
    payload = {
        "pid": participant_id,
        "link_token": link_token,
        "exp": expire,
        "type": "participant_handoff",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def _decode_handoff_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "participant_handoff":
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
        # Distinct from profile_complete on purpose: a returning panelist who
        # filled in their demographics but declined the panel is "known"
        # (skips the questionnaire) yet must still be offered the panel on
        # the completion screen, otherwise one refusal is permanent.
        "panel_consent": bool(profile.panel_consent) if profile else False,
        "first_name": profile.first_name if profile else None,
        "preferred_language": profile.preferred_language if profile else None,
    }


@router.post("/{token}/verify-code")
@limiter.limit("10/minute")
def verify_participant_code(
    request: Request,
    token: str,
    body: VerifyCodeRequest,
    db: Session = Depends(get_db),
):
    """Exchange the six-digit code from the verification email for a session.

    The OTP twin of GET /verify/{magic_token}, returning the identical shape
    so the frontend can treat the two routes interchangeably. This is the
    route that keeps a participant in the tab they started in: tapping the
    emailed link instead opens the study in the mail app's in-app browser,
    where MediaRecorder is frequently unavailable and the original tab's
    sessionStorage is gone, which for a voice interview ends the session.
    """
    _get_active_link_or_404(token, db)

    result, record = verify_code(db, body.email, token, body.code)

    if result == CodeResult.TOO_MANY_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "too_many_attempts",
                "message": "Too many incorrect codes. Request a new one to continue.",
            },
        )
    if result == CodeResult.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "code_expired",
                "message": "That code has expired or has already been used. Request a new one.",
            },
        )
    if result != CodeResult.OK or record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "code_invalid",
                "message": "That code is not right. Check the email and try again.",
            },
        )

    session_token = _create_session_token(record.email, record.interview_link_token)
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
        # Distinct from profile_complete on purpose: a returning panelist who
        # filled in their demographics but declined the panel is "known"
        # (skips the questionnaire) yet must still be offered the panel on
        # the completion screen, otherwise one refusal is permanent.
        "panel_consent": bool(profile.panel_consent) if profile else False,
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


@router.get("/{token}/preview", response_class=HTMLResponse)
@limiter.limit("60/minute")
def link_preview(request: Request, token: str, db: Session = Depends(get_db)):
    """Participant-facing link unfurl for `/i/{token}` and `/interview/{token}`.

    The frontend nginx sends link unfurlers (iMessage, WhatsApp, Slack,
    Facebook, LinkedIn, …) here; participants get the SPA untouched. See
    `services/interview_preview.py` for what the document contains and why.

    An unknown or deactivated token still renders a card (a "this link is no
    longer active" one) rather than a 404, so a stale link degrades to a
    useful message instead of a bare URL in the recipient's chat.
    """
    link = (
        db.query(InterviewLink)
        .filter(InterviewLink.token == token, InterviewLink.is_active.is_(True))
        .first()
    )
    project = link.project if link else None

    lang = normalise_preview_lang(getattr(project, "language", None))
    study_name = None
    inviter = None
    minutes = None
    if project is not None:
        anonymous = (getattr(project, "branding_mode", "standard") or "standard") == "anonymous"
        # Cache-only lookup: never trigger an on-demand AI translation for a
        # crawler. The study's own language is what the participant sees.
        study_name = project.localized_name(lang)
        minutes = project.interview_duration_minutes
        if not anonymous:
            inviter = project.researcher_name or (project.company.name if project.company else None)

    base = (settings.APP_BASE_URL or "").rstrip("/")
    html_doc = render_link_preview_html(
        lang=lang,
        study_name=study_name,
        inviter=inviter,
        minutes=minutes,
        canonical_url=f"{base}/i/{token}",
        image_url=f"{base}/og-interview-{lang}.png",
        active=link is not None,
    )
    return HTMLResponse(
        content=html_doc,
        headers={"Cache-Control": "public, max-age=300"},
    )


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
        # Shown verbatim on the landing screen, with a "subject to review"
        # qualifier added client-side. Researcher pays, never Qualipulse.
        "incentive_text": getattr(project, "incentive_text", None),
        "panel_collection_enabled": getattr(project, "panel_collection_enabled", True),
        # Drives whether the participant UI runs the socio-demographic
        # questionnaire before the interview or after it.
        "profile_before_interview": getattr(project, "profile_before_interview", False),
        # "realtime_beta" switches the participant UI to the live-voice flow
        # (WebRTC to the OpenAI Realtime API). Resolved server-side through
        # both gates, so a workspace that leaves (or never joins) the beta,
        # or a flipped-off kill switch, degrades every study to classic
        # without touching stored study settings.
        "interview_mode": _effective_interview_mode(project),
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


@router.post("/{token}/{participant_id}/handoff", response_model=HandoffCreateResponse)
@limiter.limit("10/minute")
def create_device_handoff(
    request: Request,
    token: str,
    participant_id: str,
    db: Session = Depends(get_db),
):
    """Mint a continue-on-another-device token for an in-progress interview.

    Shown as a QR code / copyable link on the current device (typically after
    a mic failure) so the participant can pick the interview up on a phone or
    another computer. Works for participants with no email on file, which the
    email-based resume flow cannot.
    """
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)
    if participant.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is already completed",
        )
    return HandoffCreateResponse(
        handoff_token=_create_handoff_token(participant.id, token),
        expires_in_seconds=HANDOFF_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/{token}/handoff/claim", response_model=HandoffClaimResponse)
@limiter.limit("30/minute")
def claim_device_handoff(
    request: Request,
    token: str,
    body: HandoffClaimRequest,
    db: Session = Depends(get_db),
):
    """Adopt an in-progress interview on a new device via a handoff token."""
    link = _get_active_link_or_404(token, db)
    payload = _decode_handoff_token(body.handoff_token)
    if payload is None or payload.get("link_token") != token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "handoff_invalid", "message": "This link has expired. Please create a new one on the original device."},
        )
    participant = (
        db.query(Participant)
        .filter(Participant.id == payload.get("pid"), Participant.link_id == link.id)
        .first()
    )
    if participant is None or participant.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "handoff_invalid", "message": "This interview is no longer in progress."},
        )
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    last_turn = turns[-1] if turns else None
    return HandoffClaimResponse(
        participant_id=participant.id,
        last_question=last_turn.question_text if last_turn else None,
        turn_count=len(turns),
        question_index=(last_turn.question_index or 0) if last_turn else 0,
        email=participant.email,
        session_token=(
            _create_session_token(participant.email, token) if participant.email else None
        ),
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

    # Turn reconciliation. The client echoes the turn_index it believes it is
    # answering; without it, a retry sent after the client's timeout (but
    # after the server finished) was accepted as the answer to a question the
    # participant never heard.
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    pending = turns[-1] if turns else None

    # Already finished: replay the stored closing turn so a lost 200 (mobile
    # drop, client timeout) cannot strand the participant on a retry loop.
    # Returning 400 here left them tapping Submit against an error forever,
    # never reaching the completion screen.
    if participant.status == "completed":
        if pending is not None:
            return _turn_response(participant, pending, transcript=pending.response_transcript)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview is already completed",
        )

    if pending is not None and turn_index is not None and turn_index != pending.turn_index:
        answered = next((t for t in turns if t.turn_index == turn_index), None)
        following = next((t for t in turns if t.turn_index == turn_index + 1), None)
        if answered is not None and answered.response_transcript and following is not None:
            # The server already processed this answer (the client timed out
            # and retried): replay the question that followed it instead of
            # accepting the blob against a question they never heard.
            return _turn_response(participant, following, transcript=answered.response_transcript)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "turn_mismatch",
                "message": "This answer is for an earlier question.",
                "current": _turn_response(participant, pending).model_dump(),
            },
        )

    # Deduplication: the pending turn already has a response (double submit).
    if pending is not None and pending.response_transcript:
        return _turn_response(participant, pending, transcript=pending.response_transcript)

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
        except IntegrityError:
            return _recover_from_turn_race(db, participant)
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
        except IntegrityError:
            return _recover_from_turn_race(db, participant)

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

    try:
        result = await run_in_threadpool(engine_skip_question, participant_id, db)
    except IntegrityError:
        return _recover_from_turn_race(db, participant)

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

    try:
        result = await run_in_threadpool(engine_finish_interview, participant_id, db)
    except IntegrityError:
        return _recover_from_turn_race(db, participant)

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
    last_turn = turns[-1] if turns else None

    return {
        "participant_id": participant.id,
        "status": participant.status,
        "turn_count": len(turns),
        "last_question": last_turn.question_text if last_turn else None,
        # Progress metadata for the realtime-beta client, which has no
        # per-turn HTTP response to read them from.
        "question_index": last_turn.question_index if last_turn else None,
        "is_follow_up": bool(last_turn.is_follow_up) if last_turn else False,
        "language": _effective_interview_language(participant),
        "started_at": participant.started_at.isoformat() if participant.started_at else None,
        "completed_at": participant.completed_at.isoformat() if participant.completed_at else None,
    }


# ---------------------------------------------------------------------------
# Realtime interview beta (projects.interview_mode == "realtime_beta")
# ---------------------------------------------------------------------------

def _effective_interview_mode(project) -> str:
    """The transport a participant actually gets for this study.

    Three gates, all of which must agree on realtime: the global kill
    switch, the owning workspace's beta opt-in
    (``Company.beta_features_enabled``), and the study's own setting.
    Anything else resolves to "classic", which always works.
    """
    if not settings.REALTIME_INTERVIEW_ENABLED:
        return "classic"
    if getattr(project, "interview_mode", "classic") != "realtime_beta":
        return "classic"
    owner = getattr(project, "company", None)
    if not getattr(owner, "beta_features_enabled", False):
        return "classic"
    return "realtime_beta"


def _get_realtime_project_or_404(link: InterviewLink):
    """The realtime endpoints exist only for studies opted into the beta."""
    project = link.project
    if _effective_interview_mode(project) != "realtime_beta":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Realtime interviews are not enabled for this study",
        )
    return project


@router.post("/{token}/{participant_id}/realtime/sdp")
@limiter.limit("30/minute")
async def create_realtime_session(
    request: Request,
    token: str,
    participant_id: str,
    db: Session = Depends(get_db),
):
    """WebRTC signaling for the realtime beta.

    The browser POSTs its SDP offer here; we forward it to the OpenAI
    Realtime API together with the session config (standard API key,
    server-side only), attach the sideband bridge to the returned call id,
    and hand the SDP answer back. Media then flows browser <-> OpenAI
    directly; every interview decision stays on this backend.
    """
    from fastapi.responses import Response as PlainResponse

    from app.services.realtime_interview import (
        RealtimeCallError,
        build_session_config,
        create_realtime_call,
        spawn_sideband,
    )

    link = _get_active_link_or_404(token, db)
    project = _get_realtime_project_or_404(link)
    participant = _get_participant_or_404(participant_id, link, db)
    if participant.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This interview is already completed",
        )
    _check_interview_budget(db, project.company_id, in_flight=True)

    # Do NOT strip the body: SDP requires a terminating newline after the
    # last attribute line, and OpenAI's parser rejects an offer without one
    # ("failed to unmarshal SDP: EOF").
    sdp_offer = (await request.body()).decode("utf-8", errors="replace")
    if not sdp_offer.lstrip().startswith("v="):
        raise HTTPException(status_code=422, detail="Body must be an SDP offer")
    if not sdp_offer.endswith("\n"):
        sdp_offer += "\r\n"

    language = _effective_interview_language(participant)
    session_config = build_session_config(project, participant, language)
    total_minutes = project.interview_duration_minutes
    try:
        answer_sdp, call_id = await run_in_threadpool(
            create_realtime_call, sdp_offer, session_config
        )
    except RealtimeCallError:
        logger.exception("realtime call creation failed for participant %s", participant_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "realtime_unavailable", "message": "Live voice is unavailable right now."},
        )
    spawn_sideband(call_id, participant.id, total_minutes)
    # The client needs the exact turn_detection config to restore VAD after
    # a mic pause (pause = session.update turn_detection null, the
    # documented push-to-talk pattern; resume = put this back).
    return PlainResponse(
        content=answer_sdp,
        media_type="application/sdp",
        headers={
            "X-Realtime-Turn-Detection": json.dumps(
                session_config["audio"]["input"]["turn_detection"]
            )
        },
    )


@router.post("/{token}/{participant_id}/realtime/recording")
@limiter.limit("30/minute")
async def upload_realtime_recording(
    request: Request,
    token: str,
    participant_id: str,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Store the browser's parallel full-session recording (realtime beta).

    The Realtime API never returns raw audio, so the client records the
    conversation itself (mic + interviewer voice mixed) and uploads it here,
    at completion or when the tab is closed. Re-uploads overwrite: the last,
    longest capture wins.
    """
    link = _get_active_link_or_404(token, db)
    participant = _get_participant_or_404(participant_id, link, db)
    # Deliberately looser than the SDP gate: gate flips (workspace leaving
    # the beta, the kill switch) must stop NEW sessions, never reject the
    # audio of one already running — that is how a deploy mid-interview
    # silently lost a session's recording once. The stored study setting
    # (or an existing recording being replaced) is proof enough that this
    # participant legitimately ran a realtime session.
    if (
        getattr(link.project, "interview_mode", "classic") != "realtime_beta"
        and not participant.session_recording_url
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Realtime interviews are not enabled for this study",
        )

    from app.services.realtime_interview import store_session_recording

    data = await audio.read()
    if not data or len(data) < 500:
        raise HTTPException(status_code=422, detail="Recording is empty")
    if len(data) > settings.MAX_AUDIO_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Recording too large. Max size is {settings.MAX_AUDIO_SIZE_MB}MB.",
        )
    ext = os.path.splitext(audio.filename or "")[1].lower() or ".webm"
    url = await run_in_threadpool(store_session_recording, participant, data, ext, db)
    return {"session_recording_url": url}


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


def _turn_response(participant: Participant, turn: InterviewTurn, *, transcript: str | None = None) -> TurnResponse:
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


def _recover_from_turn_race(db: Session, participant: Participant) -> TurnResponse:
    """Called after ``uq_turn_participant_index`` rejects a losing insert.

    Two /respond (or /skip, /finish) calls for the same participant can pass
    the router's own dedupe check and both reach the engine before either
    commits (an HTTP retry racing the original, a proxy replay, two tabs).
    The unique constraint on ``interview_turns(participant_id, turn_index)``
    makes the second one fail fast at INSERT time instead of, at any point,
    silently producing two turns at the same index. Recovery here mirrors
    the ordinary dedupe path: roll back the loser's half-built transaction,
    re-fetch what the winner actually committed, and hand the participant
    that turn, exactly as if their own request had landed second.
    """
    db.rollback()
    db.refresh(participant)
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    last = turns[-1]
    # The pending turn itself has no transcript yet (it's the next question);
    # what the participant actually said lives on the turn just before it,
    # committed by whichever request won the race.
    answered = turns[-2] if len(turns) > 1 else None
    transcript = answered.response_transcript if answered else None
    return _turn_response(participant, last, transcript=transcript)


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
