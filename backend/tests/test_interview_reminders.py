"""Interview reminder emails for participants who went idle mid-interview.

Covers the reminder pass of /admin/scheduled-emails/run:
- reminder 1 after ~1 day idle, reminder 2 ~2 days after reminder 1
- idempotency via the participant_email_log unique constraint
- eligibility filters (verified email, active link, live project, no
  completed twin, catch-up caps)
- dry_run mode
and the resume-window changes in /interview/{token}/resume:
- multi-day resume with a rebased pacing clock
- hard rejection past RESUME_MAX_IDLE_DAYS
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.config import settings
from app.models.company import Company
from app.models.email_log import ParticipantEmailLog
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.panel import ParticipantMagicToken
from app.models.project import Project
from app.routers.interview import _create_session_token

ADMIN_KEY = "test-admin-secret"
EMAIL = "jane@example.com"
LINK_TOKEN = "tok-reminders"


@pytest.fixture(autouse=True)
def admin_secret_configured():
    prev = settings.ADMIN_SECRET_KEY
    settings.ADMIN_SECRET_KEY = ADMIN_KEY
    try:
        yield
    finally:
        settings.ADMIN_SECRET_KEY = prev


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {ADMIN_KEY}"}


def _seed(
    db,
    *,
    email: str | None = EMAIL,
    email_verified: bool = True,
    status: str = "in_progress",
    started_hours_ago: float = 25,
    last_turn_hours_ago: float | None = 24,
    link_active: bool = True,
    archived: bool = False,
    is_demo: bool = False,
    language: str = "en",
) -> Participant:
    now = datetime.utcnow()
    company = Company(
        name="Acme", email="owner@acme.com", password_hash="x", email_verified=True
    )
    db.add(company)
    db.flush()
    project = Project(company_id=company.id, name="Study", language=language)
    if archived:
        project.archived_at = now
    if is_demo:
        project.is_demo = True
    db.add(project)
    db.flush()
    link = InterviewLink(
        project_id=project.id, token=LINK_TOKEN, is_active=link_active
    )
    db.add(link)
    db.flush()
    participant = Participant(
        link_id=link.id,
        project_id=project.id,
        status=status,
        email=email,
        email_verified=email_verified,
        display_name="Jane",
    )
    participant.started_at = now - timedelta(hours=started_hours_ago)
    db.add(participant)
    db.flush()
    if last_turn_hours_ago is not None:
        turn = InterviewTurn(
            participant_id=participant.id,
            turn_index=0,
            question_index=0,
            question_text="Q1?",
            response_transcript="An answer.",
        )
        turn.created_at = now - timedelta(hours=last_turn_hours_ago)
        db.add(turn)
    db.commit()
    return participant


def _run(client, dry_run: bool = False):
    url = "/admin/scheduled-emails/run"
    if dry_run:
        url += "?dry_run=true"
    resp = client.post(url, headers=_admin_headers())
    assert resp.status_code == 200
    return resp.json()


def _logged_events(db, participant_id: str) -> list[str]:
    return [
        row.event
        for row in db.query(ParticipantEmailLog)
        .filter(ParticipantEmailLog.participant_id == participant_id)
        .all()
    ]


# ── Reminder 1 ───────────────────────────────────────────────────────────────


def test_reminder_1_sent_after_a_day_idle(client, db_session):
    participant = _seed(db_session)
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        body = _run(client)
    assert body["events"]["interview_reminders"]["sent"] == 1
    assert mock_send.call_count == 1
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to"] == EMAIL
    assert kwargs["final"] is False
    assert kwargs["lang"] == "en"
    assert "/interview/verify/" in kwargs["resume_url"]
    assert _logged_events(db_session, participant.id) == ["interview_reminder_1"]
    # A long-lived magic token was minted for the resume link.
    magic = (
        db_session.query(ParticipantMagicToken)
        .filter(ParticipantMagicToken.email == EMAIL)
        .one()
    )
    assert magic.expires_at > datetime.utcnow() + timedelta(days=6)


def test_reminder_1_is_idempotent(client, db_session):
    _seed(db_session)
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        _run(client)
        body = _run(client)
    assert mock_send.call_count == 1
    assert body["events"]["interview_reminders"]["sent"] == 0


def test_reminder_1_not_sent_too_early(client, db_session):
    _seed(db_session, started_hours_ago=13, last_turn_hours_ago=12)
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        _run(client)
    assert mock_send.call_count == 0


def test_reminder_1_window_missed_means_no_reminders(client, db_session):
    # Idle beyond the reminder-1 catch-up cap (e.g. feature shipped after
    # the abandon, or the cron was down): stay silent entirely.
    _seed(db_session, started_hours_ago=6 * 24, last_turn_hours_ago=5 * 24)
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        _run(client)
    assert mock_send.call_count == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"email": None},
        {"email_verified": False},
        {"status": "completed"},
        {"link_active": False},
        {"archived": True},
        {"is_demo": True},
    ],
)
def test_reminder_1_eligibility_filters(client, db_session, kwargs):
    _seed(db_session, **kwargs)
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        _run(client)
    assert mock_send.call_count == 0


def test_reminder_skipped_when_completed_under_another_row(client, db_session):
    participant = _seed(db_session)
    twin = Participant(
        link_id=participant.link_id,
        project_id=participant.project_id,
        status="completed",
        email=EMAIL.upper(),  # case-insensitive match
        email_verified=True,
    )
    db_session.add(twin)
    db_session.commit()
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        body = _run(client)
    assert mock_send.call_count == 0
    assert body["events"]["interview_reminders"]["skipped"] == 1


def test_dry_run_counts_but_does_not_send_or_record(client, db_session):
    participant = _seed(db_session)
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        body = _run(client, dry_run=True)
    assert body["events"]["interview_reminders"]["sent"] == 1
    assert mock_send.call_count == 0
    assert _logged_events(db_session, participant.id) == []


def test_reminder_uses_participant_language(client, db_session):
    _seed(db_session, language="fr")
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        _run(client)
    assert mock_send.call_args.kwargs["lang"] == "fr"


# ── Reminder 2 ───────────────────────────────────────────────────────────────


def _backdate_reminder_1(db, participant_id: str, hours: float) -> None:
    row = (
        db.query(ParticipantEmailLog)
        .filter(
            ParticipantEmailLog.participant_id == participant_id,
            ParticipantEmailLog.event == "interview_reminder_1",
        )
        .one()
    )
    row.sent_at = datetime.utcnow() - timedelta(hours=hours)
    db.commit()


def test_reminder_2_sent_two_days_after_reminder_1(client, db_session):
    participant = _seed(db_session, started_hours_ago=73, last_turn_hours_ago=72)
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        _run(client)  # sends reminder 1
        _backdate_reminder_1(db_session, participant.id, hours=48)
        _run(client)  # now sends reminder 2
        body = _run(client)  # and nothing more
    assert mock_send.call_count == 2
    assert mock_send.call_args_list[1].kwargs["final"] is True
    assert body["events"]["interview_reminders"]["sent"] == 0
    assert sorted(_logged_events(db_session, participant.id)) == [
        "interview_reminder_1",
        "interview_reminder_2",
    ]


def test_reminder_2_not_sent_before_gap(client, db_session):
    participant = _seed(db_session)
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        _run(client)
        _backdate_reminder_1(db_session, participant.id, hours=12)
        _run(client)
    assert mock_send.call_count == 1


def test_reminder_2_not_sent_after_completion(client, db_session):
    participant = _seed(db_session)
    with patch(
        "app.routers.scheduled_emails.send_interview_reminder"
    ) as mock_send:
        _run(client)
        _backdate_reminder_1(db_session, participant.id, hours=48)
        participant.status = "completed"
        db_session.commit()
        _run(client)
    assert mock_send.call_count == 1


# ── Resume window + pacing-clock rebase ──────────────────────────────────────


def _resume(client, session_email: str = EMAIL):
    return client.post(
        f"/interview/{LINK_TOKEN}/resume",
        json={
            "email": EMAIL,
            "session_token": _create_session_token(session_email, LINK_TOKEN),
        },
    )


def test_resume_after_two_days_rebases_pacing_clock(client, db_session):
    # Started 3 days ago, answered for ~10 minutes, then went idle. The old
    # behaviour rejected anything >24h; now it resumes with elapsed ≈ the
    # 10 minutes actually spent, so the engine's close gate doesn't fire.
    participant = _seed(
        db_session,
        started_hours_ago=72,
        last_turn_hours_ago=72 - (10 / 60.0),
    )
    resp = _resume(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["participant_id"] == participant.id
    db_session.refresh(participant)
    active_minutes = (
        datetime.utcnow() - participant.started_at
    ).total_seconds() / 60.0
    assert 9 <= active_minutes <= 12


def test_resume_rejected_after_max_idle_window(client, db_session):
    _seed(db_session, started_hours_ago=9 * 24, last_turn_hours_ago=8 * 24)
    resp = _resume(client)
    assert resp.status_code == 200
    assert resp.json()["found"] is False


def test_resume_within_same_sitting_keeps_true_clock(client, db_session):
    participant = _seed(db_session, started_hours_ago=1, last_turn_hours_ago=0.1)
    original = participant.started_at
    resp = _resume(client)
    assert resp.json()["found"] is True
    db_session.refresh(participant)
    assert participant.started_at == original
