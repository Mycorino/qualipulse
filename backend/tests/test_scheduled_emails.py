"""Wave 3B — scheduled lifecycle email runner.

Covers the /admin/scheduled-emails/run endpoint end to end:
- the three event windows (Day-1, Day-7, Day-12)
- idempotency via the email_send_log unique constraint
- dry_run mode
- X-Admin-Key required
- unverified emails are skipped (won't pester pre-verification)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.config import settings
from app.models.company import Company
from app.models.email_log import EmailSendLog
from app.models.project import Project


ADMIN_KEY = "test-admin-secret"


@pytest.fixture(autouse=True)
def admin_secret_configured():
    """The runner is gated behind ADMIN_SECRET_KEY; tests need it set."""
    prev = settings.ADMIN_SECRET_KEY
    settings.ADMIN_SECRET_KEY = ADMIN_KEY
    try:
        yield
    finally:
        settings.ADMIN_SECRET_KEY = prev


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {ADMIN_KEY}"}


def _make_company(
    db,
    *,
    email: str,
    created_days_ago: float = 0,
    trial_days_left: float | None = None,
    onboarding_completed: bool = True,
    email_verified: bool = True,
    company_size: str | None = "11–50",
    with_project: bool = True,
    # Default to "trialing" — what a real new signup looks like. The
    # model's column default is "active" which would silently filter
    # the row out of the trial-email runs.
    subscription_status: str = "trialing",
) -> Company:
    """Build a Company + first non-demo project + trial bounds, like a
    real signup would. Each test is isolated by the in-memory DB."""
    now = datetime.utcnow()
    company = Company(
        name="Test Co",
        email=email,
        password_hash="x",
        first_name="Alice",
        onboarding_completed=onboarding_completed,
        email_verified=email_verified,
        company_size=company_size,
        preferred_language="en",
        subscription_status=subscription_status,
    )
    company.created_at = now - timedelta(days=created_days_ago)
    if trial_days_left is not None:
        company.trial_ends_at = now + timedelta(days=trial_days_left)
    db.add(company)
    db.flush()  # need company.id for the FK
    if with_project:
        project = Project(
            company_id=company.id,
            name="My first study",
            language="en",
            interview_duration_minutes=20,
        )
        db.add(project)
    db.commit()
    db.refresh(company)
    return company


# ── Auth ─────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_requires_admin_key(self, client):
        resp = client.post("/admin/scheduled-emails/run")
        assert resp.status_code == 403

    def test_rejects_wrong_admin_key(self, client):
        resp = client.post(
            "/admin/scheduled-emails/run",
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 403


# ── Day-1 follow-up ──────────────────────────────────────────────────────────

class TestDay1Followup:
    def test_sends_for_eligible_company(self, client, db_session):
        _make_company(db_session, email="alice@ex.com", created_days_ago=1)
        with patch("app.routers.scheduled_emails.send_day_1_followup") as mock:
            resp = client.post(
                "/admin/scheduled-emails/run", headers=_admin_headers()
            )
        assert resp.status_code == 200
        assert resp.json()["events"]["day_1_followup"]["sent"] == 1
        assert mock.called
        # send-log row is now in place — second run must NOT re-send.
        logs = db_session.query(EmailSendLog).filter(
            EmailSendLog.event == "day_1_followup"
        ).all()
        assert len(logs) == 1

    def test_skips_too_recent(self, client, db_session):
        # Signed up < 18h ago — too soon to fire.
        _make_company(db_session, email="b@ex.com", created_days_ago=0.5)
        with patch("app.routers.scheduled_emails.send_day_1_followup") as mock:
            resp = client.post(
                "/admin/scheduled-emails/run", headers=_admin_headers()
            )
        assert resp.json()["events"]["day_1_followup"]["sent"] == 0
        assert not mock.called

    def test_skips_unverified_email(self, client, db_session):
        _make_company(
            db_session, email="c@ex.com", created_days_ago=1, email_verified=False
        )
        with patch("app.routers.scheduled_emails.send_day_1_followup") as mock:
            resp = client.post(
                "/admin/scheduled-emails/run", headers=_admin_headers()
            )
        assert resp.json()["events"]["day_1_followup"]["sent"] == 0
        assert not mock.called

    def test_skips_when_no_real_project(self, client, db_session):
        _make_company(
            db_session,
            email="d@ex.com",
            created_days_ago=1,
            with_project=False,
        )
        with patch("app.routers.scheduled_emails.send_day_1_followup") as mock:
            resp = client.post(
                "/admin/scheduled-emails/run", headers=_admin_headers()
            )
        assert resp.json()["events"]["day_1_followup"]["sent"] == 0
        assert resp.json()["events"]["day_1_followup"]["skipped"] == 1
        assert not mock.called

    def test_idempotent_on_rerun(self, client, db_session):
        _make_company(db_session, email="e@ex.com", created_days_ago=1)
        with patch("app.routers.scheduled_emails.send_day_1_followup") as mock:
            client.post(
                "/admin/scheduled-emails/run", headers=_admin_headers()
            )
            assert mock.call_count == 1
            # Run a second time — must not send again.
            client.post(
                "/admin/scheduled-emails/run", headers=_admin_headers()
            )
            assert mock.call_count == 1


# ── Dry run ──────────────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_reports_but_does_not_send_or_log(self, client, db_session):
        _make_company(db_session, email="dry@ex.com", created_days_ago=1)
        with patch("app.routers.scheduled_emails.send_day_1_followup") as mock:
            resp = client.post(
                "/admin/scheduled-emails/run?dry_run=true",
                headers=_admin_headers(),
            )
        body = resp.json()
        assert body["dry_run"] is True
        assert body["events"]["day_1_followup"]["sent"] == 1
        # No send and no log row.
        assert not mock.called
        assert (
            db_session.query(EmailSendLog).count() == 0
        ), "dry-run must not persist"


# Calendar-trial emails (Day-7 / Day-12) were retired alongside the
# credits-native billing model — credits gate usage, not days. The
# endpoint no longer reports `trial_half_over` or `trial_ending` in
# its events dict, so the old test classes for those have been removed.


class TestRetiredTrialEmails:
    def test_endpoint_no_longer_reports_calendar_trial_events(
        self, client, db_session
    ):
        _make_company(
            db_session,
            email="h@ex.com",
            created_days_ago=8,
            trial_days_left=6,
        )
        resp = client.post(
            "/admin/scheduled-emails/run", headers=_admin_headers()
        )
        body = resp.json()
        assert "trial_half_over" not in body["events"]
        assert "trial_ending" not in body["events"]
