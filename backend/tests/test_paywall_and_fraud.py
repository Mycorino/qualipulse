"""V4 paywall + fraud-floor tests.

Two surfaces:
- ``email_normalization`` — collapse +aliases and dots so multi-account
  abuse via gmail variants is detected at signup.
- ``paywall`` — visibility derivation across the workspace's paid
  state + completion order. The free preview is first 3 completed,
  paid OR ever-paid unlocks everything.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from app.models.company import Company
from app.models.interview import InterviewLink, Participant
from app.models.project import Project
from app.services.email_normalization import canonicalize_email
from app.services.paywall import (
    FREE_PREVIEW_COUNT,
    get_visibility_state,
    is_participant_visible,
)
from app.services.signup_prefetch import is_disposable_email_domain


# ── Email canonicalization ──────────────────────────────────────────────────


class TestCanonicalizeEmail:
    def test_strips_plus_alias_on_gmail(self):
        assert (
            canonicalize_email("alice+study1@gmail.com") == "alice@gmail.com"
        )
        assert (
            canonicalize_email("alice+abc.def@gmail.com") == "alice@gmail.com"
        )

    def test_strips_dots_on_gmail_only(self):
        assert canonicalize_email("a.lice@gmail.com") == "alice@gmail.com"
        # Stripe is NOT gmail — dot-stripping is gmail-specific.
        assert canonicalize_email("a.lice@stripe.com") == "a.lice@stripe.com"

    def test_googlemail_collapses_to_gmail(self):
        assert (
            canonicalize_email("alice@googlemail.com") == "alice@gmail.com"
        )

    def test_plus_alias_on_outlook_proton_yahoo(self):
        assert (
            canonicalize_email("bob+tag@outlook.com") == "bob@outlook.com"
        )
        assert (
            canonicalize_email("bob+tag@proton.me") == "bob@proton.me"
        )
        assert (
            canonicalize_email("bob+tag@yahoo.com") == "bob@yahoo.com"
        )

    def test_lowercases_everything(self):
        assert (
            canonicalize_email("Alice@Gmail.COM") == "alice@gmail.com"
        )

    def test_invalid_inputs_return_none(self):
        assert canonicalize_email(None) is None
        assert canonicalize_email("") is None
        assert canonicalize_email("not-an-email") is None
        assert canonicalize_email("a@b") is None  # no TLD
        assert canonicalize_email("@gmail.com") is None  # no local
        assert canonicalize_email("alice@") is None
        assert canonicalize_email("a@b@c.com") is None  # multiple @

    def test_preserves_dots_for_non_gmail(self):
        # Most providers DO distinguish dot variants.
        assert (
            canonicalize_email("alice.smith@fastmail.com")
            == "alice.smith@fastmail.com"
        )


class TestIsDisposable:
    def test_known_disposable_blocked(self):
        assert is_disposable_email_domain("mailinator.com") is True
        assert is_disposable_email_domain("10minutemail.com") is True
        assert is_disposable_email_domain("yopmail.com") is True
        assert is_disposable_email_domain("guerrillamail.com") is True

    def test_real_freemail_passes(self):
        assert is_disposable_email_domain("gmail.com") is False
        assert is_disposable_email_domain("outlook.com") is False

    def test_corporate_passes(self):
        assert is_disposable_email_domain("stripe.com") is False
        assert is_disposable_email_domain("anthropic.com") is False

    def test_none_passes(self):
        # Unknown / empty input is not disposable; signup will reject
        # via the canonical-email check separately.
        assert is_disposable_email_domain(None) is False
        assert is_disposable_email_domain("") is False


# ── Paywall visibility ──────────────────────────────────────────────────────


def _make_company(db, *, has_ever_paid: bool = False, status: str = "trialing"):
    company = Company(
        id=str(uuid.uuid4()),
        name="Test",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        subscription_status=status,
        has_ever_paid=has_ever_paid,
    )
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


def _make_participant(
    db,
    project_id: str,
    *,
    status: str = "completed",
    completed_at: datetime | None = None,
) -> Participant:
    # Participants need an InterviewLink — create one per call (cheap
    # in SQLite, decoupled across tests). The token must be unique.
    link = InterviewLink(
        id=str(uuid.uuid4()),
        project_id=project_id,
        token=uuid.uuid4().hex,
    )
    db.add(link)
    db.flush()
    p = Participant(
        id=str(uuid.uuid4()),
        link_id=link.id,
        project_id=project_id,
        status=status,
        started_at=datetime.utcnow(),
        completed_at=completed_at,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


class TestVisibilityState:
    def test_paid_subscription_fully_unlocked(self, db_session):
        company = _make_company(db_session, status="active")
        state = get_visibility_state(db_session, company)
        assert state.fully_unlocked is True
        assert state.free_remaining is None

    def test_has_ever_paid_fully_unlocked(self, db_session):
        company = _make_company(
            db_session, has_ever_paid=True, status="canceled"
        )
        state = get_visibility_state(db_session, company)
        assert state.fully_unlocked is True

    def test_free_with_no_completed_zero_used(self, db_session):
        company = _make_company(db_session)
        state = get_visibility_state(db_session, company)
        assert state.fully_unlocked is False
        assert state.free_used == 0
        assert state.free_remaining == FREE_PREVIEW_COUNT

    def test_free_with_2_completed_one_remaining(self, db_session):
        company = _make_company(db_session)
        project = _make_project(db_session, company.id)
        for i in range(2):
            _make_participant(
                db_session,
                project.id,
                completed_at=datetime.utcnow() + timedelta(seconds=i),
            )
        state = get_visibility_state(db_session, company)
        assert state.free_used == 2
        assert state.free_remaining == 1

    def test_free_with_more_than_preview_caps_at_preview_count(
        self, db_session
    ):
        company = _make_company(db_session)
        project = _make_project(db_session, company.id)
        for i in range(7):
            _make_participant(
                db_session,
                project.id,
                completed_at=datetime.utcnow() + timedelta(seconds=i),
            )
        state = get_visibility_state(db_session, company)
        assert state.free_used == FREE_PREVIEW_COUNT
        assert state.free_remaining == 0


class TestIsParticipantVisible:
    def test_paid_sees_everything(self, db_session):
        company = _make_company(db_session, status="active")
        project = _make_project(db_session, company.id)
        participants = [
            _make_participant(
                db_session,
                project.id,
                completed_at=datetime.utcnow() + timedelta(seconds=i),
            )
            for i in range(5)
        ]
        for p in participants:
            assert is_participant_visible(db_session, company, p) is True

    def test_free_sees_first_three_completed_only(self, db_session):
        company = _make_company(db_session)
        project = _make_project(db_session, company.id)
        base = datetime.utcnow()
        participants = [
            _make_participant(
                db_session,
                project.id,
                completed_at=base + timedelta(seconds=i),
            )
            for i in range(5)
        ]
        visible = [
            p for p in participants if is_participant_visible(db_session, company, p)
        ]
        assert len(visible) == FREE_PREVIEW_COUNT
        # The visible 3 are the EARLIEST completed (deterministic).
        assert visible == participants[:FREE_PREVIEW_COUNT]

    def test_in_progress_always_visible(self, db_session):
        company = _make_company(db_session)
        project = _make_project(db_session, company.id)
        # Fill the free preview budget first.
        for i in range(FREE_PREVIEW_COUNT):
            _make_participant(
                db_session,
                project.id,
                completed_at=datetime.utcnow() + timedelta(seconds=i),
            )
        # An in-progress participant after the budget — still visible
        # because there's no body to gate.
        in_progress = _make_participant(
            db_session,
            project.id,
            status="in_progress",
            completed_at=None,
        )
        assert (
            is_participant_visible(db_session, company, in_progress) is True
        )

    def test_demo_project_participants_dont_count(self, db_session):
        # Demo projects are excluded from the workspace's free-budget
        # counting — so seeded showcase data doesn't burn the real
        # preview slots.
        company = _make_company(db_session)
        demo = _make_project(db_session, company.id, is_demo=True)
        for i in range(5):
            _make_participant(
                db_session,
                demo.id,
                completed_at=datetime.utcnow() + timedelta(seconds=i),
            )
        state = get_visibility_state(db_session, company)
        assert state.free_used == 0  # demo doesn't count
        assert state.free_remaining == FREE_PREVIEW_COUNT
