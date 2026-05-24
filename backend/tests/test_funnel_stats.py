"""Tests for /admin/funnel/stats — derived signup → activation → paid
conversion stats from existing tables.

Seeded with a tiny fixture cohort (3 signups, different progression
points) so we can verify totals + rates + cohort grouping work
without needing a populated production DB.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.models.company import Company
from app.models.interview import InterviewLink, Participant
from app.models.project import Project


ADMIN_KEY = "test-admin-secret"


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


def _make_company(
    db,
    *,
    onboarding_completed: bool = False,
    email_verified: bool = False,
    has_ever_paid: bool = False,
    created_days_ago: float = 0,
) -> Company:
    company = Company(
        id=str(uuid.uuid4()),
        name="Test",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        onboarding_completed=onboarding_completed,
        email_verified=email_verified,
        has_ever_paid=has_ever_paid,
    )
    company.created_at = datetime.utcnow() - timedelta(days=created_days_ago)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _make_project(db, company_id: str, *, is_demo: bool = False) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        company_id=company_id,
        name="Test study",
        language="en",
        is_demo=is_demo,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_link(db, project_id: str) -> InterviewLink:
    link = InterviewLink(
        id=str(uuid.uuid4()),
        project_id=project_id,
        token=uuid.uuid4().hex,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _make_completed_participant(
    db,
    project_id: str,
    link_id: str,
    *,
    minutes_after_signup: float = 60,
    signup_at: datetime | None = None,
) -> Participant:
    if signup_at is None:
        signup_at = datetime.utcnow()
    completed_at = signup_at + timedelta(minutes=minutes_after_signup)
    p = Participant(
        id=str(uuid.uuid4()),
        link_id=link_id,
        project_id=project_id,
        status="completed",
        started_at=completed_at - timedelta(minutes=5),
        completed_at=completed_at,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


class TestAuth:
    def test_requires_admin_key(self, client):
        resp = client.get("/admin/funnel/stats")
        assert resp.status_code == 403

    def test_rejects_wrong_admin_key(self, client):
        resp = client.get(
            "/admin/funnel/stats",
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 403


class TestEmptyDb:
    def test_zero_signups_returns_zeros(self, client, db_session):
        resp = client.get("/admin/funnel/stats", headers=_admin_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["totals"]["signups"] == 0
        assert body["rates"]["signup_to_paid"] == 0.0
        assert body["time_medians_minutes"]["signup_to_first_participant"] is None
        assert body["cohorts_by_week"] == []


class TestFunnelTotals:
    def test_counts_signups_and_progression(self, client, db_session):
        # 3 signups at different funnel positions.
        # A: signed up, didn't onboard
        # B: onboarded + ran 2 interviews + has not paid
        # C: onboarded + ran 5 interviews + paid
        a = _make_company(db_session, email_verified=False)
        b = _make_company(
            db_session, onboarding_completed=True, email_verified=True
        )
        c = _make_company(
            db_session,
            onboarding_completed=True,
            email_verified=True,
            has_ever_paid=True,
        )

        proj_b = _make_project(db_session, b.id)
        link_b = _make_link(db_session, proj_b.id)
        for _ in range(2):
            _make_completed_participant(
                db_session, proj_b.id, link_b.id, signup_at=b.created_at
            )

        proj_c = _make_project(db_session, c.id)
        link_c = _make_link(db_session, proj_c.id)
        for _ in range(5):
            _make_completed_participant(
                db_session, proj_c.id, link_c.id, signup_at=c.created_at
            )

        resp = client.get("/admin/funnel/stats", headers=_admin_headers())
        body = resp.json()

        # Totals
        assert body["totals"]["signups"] == 3
        assert body["totals"]["onboarded"] == 2
        assert body["totals"]["email_verified"] == 2
        assert body["totals"]["has_ever_paid"] == 1
        assert body["totals"]["studies_created"] == 2
        assert body["totals"]["workspaces_with_link"] == 2
        assert body["totals"]["first_participant_workspaces"] == 2
        assert body["totals"]["participants_completed"] == 7
        assert body["totals"]["workspaces_3plus_completed"] == 1

    def test_demo_projects_excluded_from_counts(self, client, db_session):
        # Demo seeded projects shouldn't pollute the funnel.
        company = _make_company(db_session, onboarding_completed=True)
        demo = _make_project(db_session, company.id, is_demo=True)
        link = _make_link(db_session, demo.id)
        _make_completed_participant(
            db_session, demo.id, link.id, signup_at=company.created_at
        )

        resp = client.get("/admin/funnel/stats", headers=_admin_headers())
        body = resp.json()
        assert body["totals"]["signups"] == 1
        # Demo projects/participants are excluded.
        assert body["totals"]["studies_created"] == 0
        assert body["totals"]["participants_completed"] == 0
        assert body["totals"]["first_participant_workspaces"] == 0


class TestRates:
    def test_conversion_rates_computed(self, client, db_session):
        # 10 signups → 8 onboarded → 5 first-participant → 2 paid
        for i in range(10):
            company = _make_company(
                db_session,
                onboarding_completed=(i < 8),
                has_ever_paid=(i < 2),
            )
            if i < 5:
                proj = _make_project(db_session, company.id)
                link = _make_link(db_session, proj.id)
                _make_completed_participant(
                    db_session, proj.id, link.id, signup_at=company.created_at
                )

        resp = client.get("/admin/funnel/stats", headers=_admin_headers())
        body = resp.json()
        assert body["totals"]["signups"] == 10
        assert body["rates"]["signup_to_onboarded"] == 0.8
        assert body["rates"]["onboarded_to_first_participant"] == 0.625  # 5/8
        assert body["rates"]["signup_to_paid"] == 0.2


class TestTimeMedians:
    def test_signup_to_first_participant_median(self, client, db_session):
        # Three workspaces complete their first interview at 30, 60,
        # and 120 minutes after signup. Median should be 60.
        for minutes_after in (30, 60, 120):
            company = _make_company(db_session, onboarding_completed=True)
            proj = _make_project(db_session, company.id)
            link = _make_link(db_session, proj.id)
            _make_completed_participant(
                db_session,
                proj.id,
                link.id,
                signup_at=company.created_at,
                minutes_after_signup=minutes_after,
            )

        resp = client.get("/admin/funnel/stats", headers=_admin_headers())
        body = resp.json()
        assert body["time_medians_minutes"]["signup_to_first_participant"] == 60.0


class TestCohorts:
    def test_groups_by_signup_week(self, client, db_session):
        # 2 signups this week, 1 last week.
        _make_company(db_session, created_days_ago=0)
        _make_company(db_session, created_days_ago=1)
        _make_company(db_session, created_days_ago=10)

        resp = client.get("/admin/funnel/stats", headers=_admin_headers())
        body = resp.json()
        weeks = body["cohorts_by_week"]
        assert len(weeks) >= 1
        # Total signups across cohorts equals overall signups.
        assert sum(w["signups"] for w in weeks) == 3

    def test_window_filter(self, client, db_session):
        # Old company (200 days ago) shouldn't appear in a 30-day window.
        _make_company(db_session, created_days_ago=200)
        _make_company(db_session, created_days_ago=5)
        resp = client.get(
            "/admin/funnel/stats?days=30", headers=_admin_headers()
        )
        body = resp.json()
        assert body["totals"]["signups"] == 1
        assert body["window_days"] == 30
