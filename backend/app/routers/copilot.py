"""Research Copilot endpoints.

The copilot is the in-context AI assistant. It runs on two surfaces, each
with its own adapter (see ``services/copilot.py`` / ``copilot_interview.py``):

- ``/surveys/{id}/copilot``  — the survey builder
- ``/projects/{id}/copilot`` — the interview-guide builder

``POST .../copilot`` runs one agent turn (proposes changes). The
``.../copilot/conversation`` GET/PUT persist the panel's chat thread so
it resumes when the researcher navigates away and back.
"""

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.project import Project
from app.models.survey import Survey
from app.schemas.copilot import (
    ConversationState,
    CopilotRequest,
    CopilotResponse,
    OnboardingStudyCreate,
)
from app.services.copilot import (
    SURVEY_ADAPTER,
    get_conversation,
    get_memory,
    run_copilot_turn,
    run_copilot_turn_stream,
    save_conversation,
)
from app.services.copilot_interview import INTERVIEW_ADAPTER
from app.services.copilot_onboarding import ONBOARDING_ADAPTER


def _sse_event(event: dict) -> str:
    """Frame one event for an SSE stream. One JSON object per `data:` line."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# Buffering must be off through every proxy or the stream batches at the
# end and defeats the point. nginx in the frontend container respects
# X-Accel-Buffering; Cloud Run streams HTTP/1.1 natively.
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _stream_copilot_response(
    engine,
    company_id: str,
    instrument_kind: str,  # "project" | "survey" | "company"
    instrument_id: str,
    adapter,
    body: CopilotRequest,
) -> StreamingResponse:
    """Shared streaming response for every copilot surface.

    The generator opens its OWN Session bound to the request's engine —
    Depends(get_db) closes its session as soon as the route returns the
    StreamingResponse, but the body iterator runs after that. Binding to
    ``engine`` (captured from the request session, ``db.get_bind()``) means
    the test conftest's in-memory engine and the production engine both
    work without touching ``SessionLocal`` directly.
    """
    def stream():
        from sqlalchemy.orm import Session as _Session

        from app.models.company import Company as _Company
        from app.models.project import Project as _Project
        from app.models.survey import Survey as _Survey

        with _Session(engine) as gen_db:
            comp = gen_db.query(_Company).filter(_Company.id == company_id).one()
            if instrument_kind == "company":
                inst = comp
            elif instrument_kind == "project":
                inst = gen_db.query(_Project).filter(
                    _Project.id == instrument_id
                ).one()
            elif instrument_kind == "survey":
                inst = gen_db.query(_Survey).filter(
                    _Survey.id == instrument_id
                ).one()
            else:
                raise ValueError(f"Unknown instrument kind: {instrument_kind}")
            for event in run_copilot_turn_stream(
                gen_db, comp, inst, adapter, body.messages,
                body.active_section, body.mission,
            ):
                yield _sse_event(event)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers=_SSE_HEADERS,
    )

router = APIRouter(tags=["copilot"])


def _survey_or_404(db: Session, survey_id: str, company: Company) -> Survey:
    survey = (
        db.query(Survey)
        .filter(Survey.id == survey_id, Survey.company_id == company.id)
        .first()
    )
    if survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found"
        )
    return survey


def _project_or_404(db: Session, project_id: str, company: Company) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company.id)
        .first()
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


# ── Survey surface ───────────────────────────────────────────────────────────


@router.post("/surveys/{survey_id}/copilot")
def survey_copilot(
    survey_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StreamingResponse:
    """Run one Research Copilot turn against a survey — SSE stream.
    See project_copilot for the event schema and the session-lifetime
    workaround for Depends(get_db) under StreamingResponse."""
    _survey_or_404(db, survey_id, company)
    return _stream_copilot_response(
        engine=db.get_bind(),
        company_id=company.id,
        instrument_kind="survey",
        instrument_id=survey_id,
        adapter=SURVEY_ADAPTER,
        body=body,
    )


@router.get(
    "/surveys/{survey_id}/copilot/conversation", response_model=ConversationState
)
def get_survey_conversation(
    survey_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _survey_or_404(db, survey_id, company)
    thread, version = get_conversation(db, "survey", survey_id)
    return ConversationState(thread=thread, version=version)


@router.put(
    "/surveys/{survey_id}/copilot/conversation", response_model=ConversationState
)
def put_survey_conversation(
    survey_id: str,
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _survey_or_404(db, survey_id, company)
    new_version = save_conversation(
        db, company.id, "survey", survey_id, body.thread, body.version,
    )
    return ConversationState(thread=body.thread, version=new_version)


# ── Interview-guide surface ──────────────────────────────────────────────────


@router.post("/projects/{project_id}/copilot")
def project_copilot(
    project_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StreamingResponse:
    """Run one Research Copilot turn against an interview guide — streams
    progress + the reply text as SSE. The terminal `done` event carries
    the authoritative {reply, proposed_actions, memory_updated}."""
    _project_or_404(db, project_id, company)
    return _stream_copilot_response(
        engine=db.get_bind(),
        company_id=company.id,
        instrument_kind="project",
        instrument_id=project_id,
        adapter=INTERVIEW_ADAPTER,
        body=body,
    )


@router.get(
    "/projects/{project_id}/copilot/conversation", response_model=ConversationState
)
def get_project_conversation(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _project_or_404(db, project_id, company)
    thread, version = get_conversation(db, "project", project_id)
    return ConversationState(thread=thread, version=version)


@router.put(
    "/projects/{project_id}/copilot/conversation", response_model=ConversationState
)
def put_project_conversation(
    project_id: str,
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _project_or_404(db, project_id, company)
    new_version = save_conversation(
        db, company.id, "project", project_id, body.thread, body.version,
    )
    return ConversationState(thread=body.thread, version=new_version)


# ── Onboarding surface ───────────────────────────────────────────────────────


@router.post("/onboarding/copilot")
def onboarding_copilot(
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StreamingResponse:
    """Run one onboarding-copilot turn — the new researcher's first
    conversation. The 'instrument' is the Company itself. SSE stream."""
    return _stream_copilot_response(
        engine=db.get_bind(),
        company_id=company.id,
        instrument_kind="company",
        instrument_id=company.id,
        adapter=ONBOARDING_ADAPTER,
        body=body,
    )


@router.get("/onboarding/copilot/conversation", response_model=ConversationState)
def get_onboarding_conversation(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    thread, version = get_conversation(db, "company", company.id)
    return ConversationState(thread=thread, version=version)


@router.put("/onboarding/copilot/conversation", response_model=ConversationState)
def put_onboarding_conversation(
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    new_version = save_conversation(
        db, company.id, "company", company.id, body.thread, body.version,
    )
    return ConversationState(thread=body.thread, version=new_version)


@router.get("/onboarding/copilot/memory")
def get_onboarding_memory(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    """The workspace-scope memory the copilot wrote during onboarding —
    shown back to the researcher on the completion screen.

    Returns both the free-form memory the agent saved AND a deterministic
    ``profile_summary`` built from the captured Company fields plus the
    most recent non-demo Project's strategic context (decision /
    timeline / audience / success criteria). That mix is what makes the
    recap feel earned ("you're a PM at a 50-person SaaS company; your
    decision is in 2 weeks") instead of a generic placeholder.
    """
    row = get_memory(db, "company", company.id)
    # Most recent non-demo Project — created by acceptStudy moments
    # before the completion screen renders.
    from app.models.project import Project

    latest_project = (
        db.query(Project)
        .filter(Project.company_id == company.id, Project.is_demo.is_(False))
        .order_by(Project.created_at.desc())
        .first()
    )
    return {
        "memory": (row.content if row and row.content else ""),
        "profile_summary": _build_profile_summary(db, company, latest_project),
    }


@router.post("/onboarding/copilot/greeting-prep")
def prep_welcome_greeting(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
) -> dict:
    """Generate (or fetch cached) a personalised /welcome greeting from
    the wizard-captured profile. Cached for 24h on the Company row.
    Returns ``{"greeting": str | null}``. Null means we couldn't
    generate (sparse profile, API failure, missing key) and the
    frontend should fall back to the static i18n greeting."""
    from app.services.onboarding_personalisation import generate_welcome_greeting

    text = generate_welcome_greeting(company)
    if text and company.welcome_greeting_at:
        # Generation refreshed the cache — persist.
        db.commit()
    return {"greeting": text}


@router.get("/onboarding/demo-bundle")
def get_demo_bundle_endpoint(
    variant: str = "saas",
    company: Company = Depends(get_current_company),
) -> dict:
    """Return a structured demo bundle for the sample-study modal —
    themes + verbatims + interview guide, shaped like a real
    ProjectAnalysis + QuoteTag + GuideQuestion graph.

    Variant routing matches frontend `pickSampleVariant()`:
    `saas` (default), `b2b_specifier`, `consumer`. Locale derived from
    the company's `preferred_language`. Unknown variant/locale falls
    back to (saas, en)."""
    from app.services.demo_bundles import get_demo_bundle

    locale = (company.preferred_language or "en").lower()
    bundle = get_demo_bundle(variant=variant, locale=locale)
    return dict(bundle)


@router.get("/onboarding/copilot/starter-suggestions")
def get_starter_suggestions(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
) -> dict:
    """Return three personalised research starter chips based on the
    captured profile + business summary. Cached for 24h. Falls back to
    static i18n chips on the frontend when we return ``{"suggestions": null}``."""
    from app.services.onboarding_personalisation import generate_starter_suggestions

    arr = generate_starter_suggestions(company)
    if arr and company.starter_suggestions_at:
        db.commit()
    return {"suggestions": arr}


def _build_profile_summary(
    db: Session, company: Company, project=None
) -> str:
    """Two-sentence third-person memory recap of what we know about this
    researcher's project. Generated by Claude Haiku in the user's
    preferred language and cached on ``Company.onboarding_recap`` so
    subsequent visits to the completion screen are free.

    Returns empty string when we have nothing meaningful to say (no
    profile fields captured AND no project context), so the frontend
    can fall back to its localised placeholder gracefully.
    """
    # Cache hit — short-circuit. The recap is shown once on the
    # completion screen; regenerating it on every refresh would burn
    # tokens for zero value.
    cached = (company.onboarding_recap or "").strip()
    if cached:
        return cached

    role = (company.role or "").strip()
    size = (company.company_size or "").strip()
    industry = (company.industry or "").strip()
    use_case = (company.use_case or "").strip()
    business = (company.business_summary or "").strip()
    experience = (company.research_experience or "").strip()
    company_name = (company.name or "").strip()
    decision = ""
    timeline = ""
    success = ""
    audience = ""
    if project is not None:
        decision = (getattr(project, "decision_to_inform", "") or "").strip()
        timeline = (getattr(project, "timeline", "") or "").strip()
        success = (getattr(project, "success_criteria", "") or "").strip()
        audience = (
            getattr(project, "target_customer_description", "") or ""
        ).strip()

    # Nothing captured at all — let the frontend show its fallback copy.
    if not any([role, size, industry, use_case, business, decision, timeline]):
        return ""

    # Generate via Haiku in the user's preferred language. Fall back to
    # a minimal deterministic line if the API is unavailable (no key /
    # network blip / quota) so the completion screen never breaks.
    preferred_language = (company.preferred_language or "en").strip().lower()
    language_name = "French" if preferred_language.startswith("fr") else "English"

    recap = _generate_haiku_recap(
        db=db,
        company=company,
        language_name=language_name,
        role=role,
        size=size,
        industry=industry,
        use_case=use_case,
        business=business,
        experience=experience,
        company_name=company_name,
        decision=decision,
        timeline=timeline,
        success=success,
        audience=audience,
    )
    if not recap:
        recap = _fallback_recap(
            language_name=language_name,
            role=role,
            size=size,
            industry=industry,
            decision=decision,
            timeline=timeline,
        )
    if recap:
        company.onboarding_recap = recap
        try:
            db.commit()
        except Exception:  # noqa: BLE001 — never fail the response on cache write
            db.rollback()
    return recap


def _generate_haiku_recap(
    *,
    db: Session,
    company: Company,
    language_name: str,
    role: str,
    size: str,
    industry: str,
    use_case: str,
    business: str,
    experience: str,
    company_name: str,
    decision: str,
    timeline: str,
    success: str,
    audience: str,
) -> str:
    """Call Claude Haiku for the 2-sentence recap. Returns an empty
    string on any failure — the caller falls back to a deterministic
    line so the completion screen never breaks."""
    from app.config import settings  # local import — keeps router clean
    from app.logging_config import logger

    if not getattr(settings, "ANTHROPIC_API_KEY", None):
        return ""

    # SKIP role when the literal value is the chip escape-hatch — it
    # leaks "Other" / "Autre" into the recap otherwise.
    role_for_prompt = role
    if role.strip().lower() in {"other", "autre"}:
        role_for_prompt = ""

    # 5-8 word business hint — never paste the full summary.
    business_hint = ""
    if business:
        # The prompt instructs the model to compress; we still pass
        # the full text so it has signal to compress from.
        business_hint = business

    facts_lines = []
    if role_for_prompt:
        facts_lines.append(f"- role: {role_for_prompt}")
    if company_name:
        facts_lines.append(f"- company: {company_name}")
    if size:
        facts_lines.append(f"- team size: {size}")
    if industry:
        facts_lines.append(f"- industry: {industry}")
    if use_case:
        facts_lines.append(f"- research use case: {use_case}")
    if experience:
        facts_lines.append(f"- research experience: {experience}")
    if decision:
        facts_lines.append(f"- decision they need to make: {decision}")
    if timeline:
        facts_lines.append(f"- timeline: {timeline}")
    if success:
        facts_lines.append(f"- success criterion: {success}")
    if audience:
        facts_lines.append(f"- target audience: {audience}")
    if business_hint:
        facts_lines.append(f"- company business (raw, to compress to 5-8 words): {business_hint}")
    facts = "\n".join(facts_lines)

    system_prompt = (
        f"Write a 2-sentence third-person memory in {language_name} of what "
        "we know about this researcher's project. Use:\n"
        "- role + company + team size (SKIP role if it's the literal 'Other' "
        "or 'Autre')\n"
        "- the decision they need to make + timeline (1-month, 1-quarter, etc.)\n"
        "- the company's business in 5-8 words MAX — never paste the full summary\n"
        "Constraints: warm, factual, no jargon, no truncation, fully in the "
        "target locale. Output the 2 sentences only — no preamble, no markdown."
    )
    user_prompt = (
        f"Facts captured:\n{facts}\n\n"
        "Write the 2-sentence recap now."
    )

    try:
        import httpx  # noqa: F401 — anthropic SDK uses httpx under the hood
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=240,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        # Best-effort cost log — the recap is a tiny call but counts.
        try:
            from app.services.usage_logger import log_claude_usage

            log_claude_usage(db, resp, company_id=company.id, operation="onboarding_recap")
        except Exception:  # noqa: BLE001
            pass
        blocks = getattr(resp, "content", None) or []
        for block in blocks:
            text = getattr(block, "text", None)
            if text and text.strip():
                return text.strip()
    except Exception:  # noqa: BLE001
        logger.exception("onboarding recap haiku call failed")
    return ""


def _fallback_recap(
    *,
    language_name: str,
    role: str,
    size: str,
    industry: str,
    decision: str,
    timeline: str,
) -> str:
    """Deterministic last-resort recap when Haiku is unavailable. Tiny
    and factual — better than nothing on the completion screen.

    Role is skipped when it's the literal 'Other' / 'Autre' escape hatch.
    """
    role_clean = "" if role.strip().lower() in {"other", "autre"} else role
    if language_name == "French":
        parts: list[str] = []
        who = []
        if role_clean:
            who.append(role_clean)
        if size or industry:
            who.append(
                ("dans une équipe " if not who else "d'une équipe ")
                + (f"{size} ({industry})" if size and industry else (size or industry))
            )
        if who:
            parts.append("Chercheur·euse : " + ", ".join(who) + ".")
        if decision:
            tl = f" — {timeline}" if timeline else ""
            parts.append(f"Décision à éclairer : {decision}{tl}.")
        return " ".join(parts).strip()
    # English fallback
    parts = []
    who_en = []
    if role_clean:
        who_en.append(role_clean)
    if size or industry:
        who_en.append(
            "on a team " + (f"{size} ({industry})" if size and industry else (size or industry))
        )
    if who_en:
        parts.append("Researcher: " + ", ".join(who_en) + ".")
    if decision:
        tl = f" — {timeline}" if timeline else ""
        parts.append(f"Decision to inform: {decision}{tl}.")
    return " ".join(parts).strip()


# ── Atomic study creation (onboarding) ──────────────────────────────────────

_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


@router.post("/onboarding/study", status_code=status.HTTP_201_CREATED)
def create_onboarding_study(
    body: OnboardingStudyCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    """Create a project + guide questions + interview link in one
    transaction. Replaces the fragile multi-call sequence the frontend
    used to perform during onboarding acceptance."""
    from app.models.interview import InterviewLink
    from app.models.project import InterviewGuideQuestion, Project

    project = Project(
        company_id=company.id,
        name=body.study_name,
        language=body.language,
        research_objective=body.objective,
        decision_to_inform=body.decision_to_inform,
        timeline=body.timeline,
        success_criteria=body.success_criteria,
        target_customer_description=body.target_customer_description,
        interview_duration_minutes=20,
    )
    db.add(project)
    db.flush()

    sections: dict[str, int] = {}
    for i, q in enumerate(body.questions):
        if q.section_title not in sections:
            sections[q.section_title] = len(sections)
        db.add(InterviewGuideQuestion(
            project_id=project.id,
            section_index=sections[q.section_title],
            section_title=q.section_title,
            question_index=i,
            main_question=q.main_question,
            desired_learning=q.desired_learning or "",
            sort_order=i,
        ))

    token = "".join(secrets.choice(_BASE58) for _ in range(43))
    link = InterviewLink(project_id=project.id, token=token)
    db.add(link)
    db.commit()

    return {
        "project_id": project.id,
        "study_name": body.study_name,
        "interview_token": token,
    }
