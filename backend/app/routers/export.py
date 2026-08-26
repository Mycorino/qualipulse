import csv
import io
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import (
    get_accessible_project_or_404 as _get_project_or_404,
    get_editable_project_or_404 as _get_editable_project_or_404,
    get_current_company,
    get_db,
)
from app.models.company import Company
from app.models.interview import REVIEW_REJECTED, InterviewTurn, Participant
from app.models.project import Project
from app.schemas.interview import (
    ParticipantResponse,
    TranscriptResponse,
    TranscriptTurnResponse,
)

router = APIRouter(prefix="/projects", tags=["export"])


def _require_csv_export(db: Session, company: Company) -> None:
    """Dual-track CSV-export gate.

    Legacy tiers read the ``export_csv`` TierLimits flag; credits-based
    plans read the ``csv_export`` plan entitlement (the two tracks use
    different key names, so ``workspace_has_feature`` can't cover both).
    """
    from app.services import billing_service
    from app.services.feature_gates import require_feature

    sub = billing_service.get_current_subscription(db, company.id)
    plan = billing_service.get_plan(db, sub.plan_id) if sub else None
    if plan is None or plan.is_legacy:
        require_feature(company, "export_csv")
    elif not billing_service.get_entitlements(db, company.id).get("csv_export", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "csv_export_not_included",
                "message": "CSV export is not included in your current plan.",
            },
        )


# Filler words/phrases that indicate disengaged or low-quality responses
_FILLERS = {
    "yes", "no", "maybe", "ok", "okay", "sure", "fine", "idk",
    "i don't know", "i don't care", "i dunno", "not sure", "no idea",
    "don't know", "can't say", "cant say", "nothing", "nope", "yep", "yeah",
    "i guess", "i suppose", "not really", "kind of", "sort of",
}

# How long a completed interview may sit without a quality summary before the
# assessment is presumed dead. The pass is one or two Claude calls with a 60s
# client timeout, so a live run is always well inside this. Anything older
# either crashed before it could stamp itself, or never got the chance: a
# Cloud Run instance recycled mid-flight kills the daemon thread outright, so
# the except branch that writes quality_status="failed" never runs.
_QUALITY_ASSESSMENT_GRACE = timedelta(minutes=10)


def _effective_quality_status(p: Participant) -> str | None:
    """What the client should show, not merely what got recorded.

    Returns "ok" when an assessment exists, "failed" when one is owed and is
    not plausibly still running, and None while it may still be in flight.
    """
    if p.quality_summary:
        return p.quality_status or "ok"
    if p.quality_status:
        return p.quality_status
    if p.status != "completed" or p.completed_at is None:
        return None
    if datetime.utcnow() - p.completed_at > _QUALITY_ASSESSMENT_GRACE:
        return "failed"
    return None


def _compute_quality(turns) -> tuple[float | None, str | None]:
    """Return (score 0.0-1.0, label) from participant turns. Returns (None, None) if no data."""
    responses = [
        t.response_transcript
        for t in turns
        if t.response_transcript and t.response_transcript.strip()
    ]
    if not responses:
        return None, None

    total = 0.0
    for text in responses:
        words = text.lower().split()
        wc = len(words)
        normalized = text.lower().strip().rstrip(".!?")

        is_filler = (
            normalized in _FILLERS
            or (wc <= 3 and any(f in normalized for f in _FILLERS))
        )

        if is_filler or wc <= 2:
            score = 0.0
        elif wc <= 8:
            score = 0.2
        elif wc <= 20:
            score = 0.5
        elif wc <= 50:
            score = 0.8
        else:
            score = 1.0

        total += score

    avg = total / len(responses)

    if avg < 0.25:
        label = "low"
    elif avg < 0.5:
        label = "fair"
    elif avg < 0.75:
        label = "good"
    else:
        label = "strong"

    return round(avg, 2), label


@router.get("/{project_id}/participants", response_model=list[ParticipantResponse])
def list_participants(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[ParticipantResponse]:
    project = _get_project_or_404(project_id, company.id, db)

    participants = (
        db.query(Participant)
        .filter(Participant.project_id == project.id)
        .order_by(Participant.started_at.desc())
        .all()
    )

    # V4 paywall — bulk-compute visibility once for the whole list
    # rather than per-row, to avoid N+1 queries. We do this by
    # gathering the first FREE_PREVIEW_COUNT completed participant IDs
    # across the workspace and treating everything else as locked
    # (unless the workspace has paid).
    from app.services.paywall import (
        FREE_PREVIEW_COUNT,
        _PAID_STATUSES,
    )
    fully_unlocked = (
        company.has_ever_paid
        or (company.subscription_status or "") in _PAID_STATUSES
    )
    visible_ids: set[str] = set()
    if not fully_unlocked:
        first_completed_ids = (
            db.query(Participant.id)
            .join(Project, Participant.project_id == Project.id)
            .filter(
                Project.company_id == company.id,
                Project.is_demo.is_(False),
                Participant.status == "completed",
            )
            .order_by(Participant.completed_at.asc())
            .limit(FREE_PREVIEW_COUNT)
            .all()
        )
        visible_ids = {row[0] for row in first_completed_ids}

    result = []
    for p in participants:
        # Use persisted quality score if available, otherwise compute heuristic
        if p.quality_score is not None and p.quality_label is not None:
            q_score, q_label = p.quality_score, p.quality_label
        else:
            q_score, q_label = _compute_quality(p.turns)
        # Locked iff completed AND not fully unlocked AND not in the
        # first-3 visible set. In-progress participants are always
        # visible (no body to gate).
        is_locked = (
            not fully_unlocked
            and p.status == "completed"
            and p.id not in visible_ids
        )
        result.append(
            ParticipantResponse(
                id=p.id,
                display_name=p.display_name,
                status=p.status,
                completion_reason=p.completion_reason,
                started_at=p.started_at,
                completed_at=p.completed_at,
                turn_count=len(p.turns),
                age_range=p.age_range,
                profession=p.profession,
                country=p.country,
                # Contact email stays behind the paywall alongside the
                # transcript body — a locked row shows consent status only.
                email=None if is_locked else p.email,
                email_verified=p.email_verified,
                panel_consent=p.panel_consent,
                screening_answers=p.screening_answers_list or None,
                quality_score=q_score,
                quality_label=q_label,
                quality_summary=p.quality_summary,
                quality_strengths=json.loads(p.quality_strengths) if p.quality_strengths else None,
                quality_issues=json.loads(p.quality_issues) if p.quality_issues else None,
                quality_status=_effective_quality_status(p),
                key_takeaways=json.loads(p.key_takeaways) if p.key_takeaways else None,
                notable_quotes=json.loads(p.notable_quotes) if p.notable_quotes else None,
                avg_response_words=p.avg_response_words,
                short_answer_pct=p.short_answer_pct,
                review_status=p.review_status,
                review_note=p.review_note,
                reviewed_at=p.reviewed_at,
                reward_sent_at=p.reward_sent_at,
                is_locked=is_locked,
            )
        )
    return result


@router.get(
    "/{project_id}/participants/{participant_id}/transcript",
    response_model=TranscriptResponse,
)
def get_transcript(
    project_id: str,
    participant_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> TranscriptResponse:
    project = _get_project_or_404(project_id, company.id, db)

    participant = (
        db.query(Participant)
        .filter(
            Participant.id == participant_id,
            Participant.project_id == project.id,
        )
        .first()
    )
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found"
        )

    # V4 paywall — gate transcript body for free workspaces past
    # the first FREE_PREVIEW_COUNT completed participants. The
    # frontend renders a paywall card from the 402 response.
    from app.services.paywall import (
        is_participant_visible,
        paywall_payload,
        get_visibility_state,
    )

    if not is_participant_visible(db, company, participant):
        state = get_visibility_state(db, company)
        # Approximate "how many transcripts are locked" — total
        # completed minus the free preview count.
        from sqlalchemy import and_
        total_completed = (
            db.query(Participant)
            .join(Project, Participant.project_id == Project.id)
            .filter(
                and_(
                    Project.company_id == company.id,
                    Project.is_demo.is_(False),
                    Participant.status == "completed",
                )
            )
            .count()
        )
        locked = max(0, total_completed - (state.free_used or 0))
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=paywall_payload(company, locked),
        )

    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    if participant.quality_score is not None and participant.quality_label is not None:
        q_score, q_label = participant.quality_score, participant.quality_label
    else:
        q_score, q_label = _compute_quality(turns)
    return TranscriptResponse(
        participant=ParticipantResponse(
            id=participant.id,
            display_name=participant.display_name,
            status=participant.status,
            completion_reason=participant.completion_reason,
            started_at=participant.started_at,
            completed_at=participant.completed_at,
            turn_count=len(turns),
            age_range=participant.age_range,
            profession=participant.profession,
            country=participant.country,
            quality_score=q_score,
            quality_label=q_label,
            quality_summary=participant.quality_summary,
            quality_strengths=json.loads(participant.quality_strengths) if participant.quality_strengths else None,
            quality_issues=json.loads(participant.quality_issues) if participant.quality_issues else None,
            quality_status=_effective_quality_status(participant),
            key_takeaways=json.loads(participant.key_takeaways) if participant.key_takeaways else None,
            notable_quotes=json.loads(participant.notable_quotes) if participant.notable_quotes else None,
            avg_response_words=participant.avg_response_words,
            short_answer_pct=participant.short_answer_pct,
            review_status=participant.review_status,
            review_note=participant.review_note,
            reviewed_at=participant.reviewed_at,
            reward_sent_at=participant.reward_sent_at,
            session_recording_url=getattr(participant, "session_recording_url", None),
        ),
        turns=[
            TranscriptTurnResponse(
                id=t.id,
                turn_index=t.turn_index,
                question_text=t.question_text,
                response_transcript=t.response_transcript,
                response_segments=json.loads(t.response_segments) if t.response_segments else None,
                is_follow_up=t.is_follow_up,
                manually_edited=t.manually_edited,
                edited_at=t.edited_at,
                created_at=t.created_at,
                audio_recording_url=t.audio_recording_url,
                tts_audio_url=t.tts_audio_url,
                translated_response=t.translated_response,
                translated_question=t.translated_question,
                translation_language=t.translation_language,
            )
            for t in turns
        ],
        translation_language=next(
            (t.translation_language for t in turns if t.translation_language), None
        ),
    )


@router.get("/{project_id}/export")
def export_transcripts_csv(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Export all interview transcripts for a project as a CSV download."""
    project = _get_project_or_404(project_id, company.id, db)
    _require_csv_export(db, company)

    # Rejected interviews are not research data: they never reach the CSV.
    participants = (
        db.query(Participant)
        .filter(
            Participant.project_id == project.id,
            Participant.review_status != REVIEW_REJECTED,
        )
        .order_by(Participant.started_at)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "participant_id",
        "display_name",
        "email",
        "follow_up_consent",
        "screening_answers",
        "status",
        "started_at",
        "completed_at",
        "turn_index",
        "question_index",
        "is_follow_up",
        "question_text",
        "response_transcript",
        "created_at",
    ])

    def _consent_cell(p: Participant) -> str:
        if p.panel_consent is True:
            return "yes"
        if p.panel_consent is False:
            return "no"
        return ""

    def _screening_cell(p: Participant) -> str:
        return " | ".join(
            f"{a.get('question', '')} = {a.get('answer', '')}"
            for a in p.screening_answers_list
            if a.get("question") and a.get("answer")
        )

    for p in participants:
        turns = sorted(p.turns, key=lambda t: t.turn_index)
        if not turns:
            # Write a row for the participant even with no turns
            writer.writerow([
                p.id,
                _csv_safe(p.display_name or ""),
                _csv_safe(p.email or ""),
                _consent_cell(p),
                _csv_safe(_screening_cell(p)),
                p.status,
                _fmt_dt(p.started_at),
                _fmt_dt(p.completed_at),
                "", "", "", "", "", "",
            ])
        else:
            for t in turns:
                writer.writerow([
                    p.id,
                    _csv_safe(p.display_name or ""),
                    _csv_safe(p.email or ""),
                    _consent_cell(p),
                    _csv_safe(_screening_cell(p)),
                    p.status,
                    _fmt_dt(p.started_at),
                    _fmt_dt(p.completed_at),
                    t.turn_index,
                    t.question_index if t.question_index is not None else "",
                    t.is_follow_up,
                    _csv_safe(t.question_text),
                    _csv_safe(t.response_transcript or ""),
                    _fmt_dt(t.created_at),
                ])

    output.seek(0)
    filename = f"{project.name.replace(' ', '_')}_transcripts.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{project_id}/participants/{participant_id}/quality")
def ai_quality_assessment(
    project_id: str,
    participant_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Use Claude to produce a structured quality assessment of an interview transcript.

    Delegates to the shared ``run_ai_quality_assessment`` service which persists
    all results to the Participant row.  Returns the persisted fields as JSON.
    """
    from app.services.quality import run_ai_quality_assessment

    project = _get_editable_project_or_404(project_id, company.id, db)

    participant = (
        db.query(Participant)
        .filter(Participant.id == participant_id, Participant.project_id == project_id)
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    responses = [t for t in turns if t.response_transcript]
    if not responses:
        raise HTTPException(status_code=400, detail="No responses to assess")

    # Clear any existing assessment so the service re-runs
    participant.quality_summary = None
    participant.quality_status = None
    db.flush()

    lang = company.preferred_language or "en"
    run_ai_quality_assessment(participant_id, db, language=lang)

    # Re-read to pick up persisted values
    db.refresh(participant)

    if participant.quality_summary is None:
        raise HTTPException(status_code=500, detail="Failed to produce quality assessment")

    return {
        "quality_score": participant.quality_score,
        "quality_label": participant.quality_label,
        "quality_status": participant.quality_status,
        "summary": participant.quality_summary,
        "strengths": json.loads(participant.quality_strengths) if participant.quality_strengths else [],
        "issues": json.loads(participant.quality_issues) if participant.quality_issues else [],
        "key_takeaways": json.loads(participant.key_takeaways) if participant.key_takeaways else [],
        "notable_quotes": json.loads(participant.notable_quotes) if participant.notable_quotes else [],
        "avg_response_words": participant.avg_response_words,
        "short_answer_pct": participant.short_answer_pct,
    }


@router.delete(
    "/{project_id}/participants/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_participant(
    project_id: str,
    participant_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> None:
    """Permanently delete one participant's interview data (GDPR erasure).

    Removes the transcript turns, quote tags, and stored audio files, then
    the participant row itself. Billing ledger rows keep only the
    pseudonymous participant id (financial audit trail, retained on purpose).
    """
    import logging

    from app.services.deletion import delete_participant_data

    project = _get_editable_project_or_404(project_id, company.id, db)

    participant = (
        db.query(Participant)
        .filter(Participant.id == participant_id, Participant.project_id == project.id)
        .first()
    )
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")

    logging.getLogger(__name__).warning(
        "PARTICIPANT_DELETION: participant_id=%s project_id=%s company_id=%s",
        participant.id, project.id, company.id,
    )
    delete_participant_data(db, participant, delete_files=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _fmt_dt(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def _csv_safe(value) -> str:
    """Neutralise CSV formula injection in participant/researcher free text.

    A cell whose value starts with =, +, -, @ (or a leading tab/CR) is executed
    as a formula by Excel/Sheets/LibreOffice on open. A malicious participant
    could set their display name to `=HYPERLINK(...)` and have it fire in a
    researcher's spreadsheet. Prefix any such cell with a single quote — the
    OWASP-recommended mitigation — so it's rendered as literal text.
    """
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text
