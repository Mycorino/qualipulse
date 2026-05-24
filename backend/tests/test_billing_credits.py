"""Tests for the credits-based billing system (PR 1: foundation).

Covers:
- Plan + entitlement seeding (idempotent, updates on re-run).
- Existing-Company backfill onto legacy plans.
- ``can_start_interview`` for legacy plans (delegates), trial (with credits),
  trial (expired), past_due, quota exceeded, overage path.
- ``consume_interview_credit`` idempotency: second call for the same
  participant returns None and never double-debits the balance.
- Screened-out participant doesn't consume credits (the engine never calls
  consume for them — verified by absence of a ledger row).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.billing import (
    CreditBalance,
    CreditLedger,
    Plan,
    PlanEntitlement,
    WorkspaceSubscription,
)
from app.models.company import Company
from app.services.billing_service import (
    EVT_CONSUME_INTERVIEW,
    backfill_legacy_subscriptions,
    bootstrap_trial_subscription,
    can_start_interview,
    consume_interview_credit,
    ensure_plans_seeded,
    get_active_balance,
    get_current_subscription,
    get_entitlements,
)


def _make_company(db_session, *, tier: str = "starter", email: str | None = None) -> Company:
    company = Company(
        id=str(uuid.uuid4()),
        name="Test",
        email=email or f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        subscription_tier=tier,
        # V4 paywall — can_start_interview now gates on verified email.
        # These tests are about credit math, not the verification gate,
        # so we mark email_verified=True up front.
        email_verified=True,
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


class TestPlanSeeding:
    def test_seeds_all_plans_idempotently(self, db_session):
        ensure_plans_seeded(db_session)
        first = db_session.query(Plan).count()
        assert first == 8  # 3 legacy + trial + exploration + team + agency + enterprise

        # Re-running doesn't duplicate.
        ensure_plans_seeded(db_session)
        assert db_session.query(Plan).count() == first

    def test_legacy_flag_set_correctly(self, db_session):
        ensure_plans_seeded(db_session)
        legacy = db_session.query(Plan).filter(Plan.is_legacy == True).all()  # noqa: E712
        legacy_ids = {p.id for p in legacy}
        assert legacy_ids == {"legacy_starter", "legacy_team", "legacy_lab"}

    def test_entitlements_attach_to_plan(self, db_session):
        ensure_plans_seeded(db_session)
        team_ents = {
            e.key: e.value
            for e in db_session.query(PlanEntitlement).filter(PlanEntitlement.plan_id == "team").all()
        }
        assert team_ents["csv_export"] is True
        assert team_ents["custom_branding"] is False
        assert team_ents["team_workspace"] is True


class TestBackfill:
    def test_backfills_existing_companies_onto_legacy_plans(self, db_session):
        ensure_plans_seeded(db_session)
        starter = _make_company(db_session, tier="starter")
        team = _make_company(db_session, tier="team")
        lab = _make_company(db_session, tier="lab")
        free = _make_company(db_session, tier="free")  # legacy alias

        created = backfill_legacy_subscriptions(db_session)
        assert created == 4

        # Each company gets a subscription on the right legacy plan.
        sub_starter = get_current_subscription(db_session, starter.id)
        assert sub_starter is not None
        assert sub_starter.plan_id == "legacy_starter"

        sub_team = get_current_subscription(db_session, team.id)
        assert sub_team.plan_id == "legacy_team"

        sub_lab = get_current_subscription(db_session, lab.id)
        assert sub_lab.plan_id == "legacy_lab"

        # 'free' aliases to legacy_starter.
        sub_free = get_current_subscription(db_session, free.id)
        assert sub_free.plan_id == "legacy_starter"

    def test_backfill_is_idempotent(self, db_session):
        ensure_plans_seeded(db_session)
        _make_company(db_session)
        first = backfill_legacy_subscriptions(db_session)
        assert first == 1
        second = backfill_legacy_subscriptions(db_session)
        assert second == 0  # nothing new to do


class TestCanStartInterviewLegacy:
    def test_legacy_plan_returns_legacy_flag(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session, tier="starter")
        backfill_legacy_subscriptions(db_session)

        result = can_start_interview(db_session, c.id)
        assert result.allowed is True
        assert result.is_legacy is True
        assert result.plan_id == "legacy_starter"


class TestCanStartInterviewCredits:
    def test_trial_with_credits_allows_interview(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        bootstrap_trial_subscription(db_session, c)

        result = can_start_interview(db_session, c.id)
        assert result.allowed is True
        assert result.is_legacy is False
        assert result.available_credits == 10

    def test_expired_trial_still_allowed_if_credits_remain(self, db_session):
        # Credits-native model: trial expiry no longer gates. As long as
        # the company has credits left (or overage is on), they can
        # still run an interview. Calendar trials are vestigial.
        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        sub = bootstrap_trial_subscription(db_session, c)
        sub.trial_end = datetime.utcnow() - timedelta(days=1)
        db_session.commit()

        result = can_start_interview(db_session, c.id)
        assert result.allowed is True
        assert result.reason == "ok"
        assert result.available_credits == 10

    def test_no_credits_no_overage_blocks(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        bootstrap_trial_subscription(db_session, c)
        # Drain the balance.
        bal = get_active_balance(db_session, c.id)
        bal.used_credits = 10
        db_session.commit()

        result = can_start_interview(db_session, c.id)
        assert result.allowed is False
        assert result.reason == "quota_exceeded"

    def test_no_credits_with_overage_allows(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        sub = bootstrap_trial_subscription(db_session, c)
        # Pretend we're on the team plan with overage on; drain the balance.
        sub.plan_id = "team"
        sub.overage_enabled = True
        bal = get_active_balance(db_session, c.id)
        bal.used_credits = 10
        db_session.commit()

        result = can_start_interview(db_session, c.id)
        assert result.allowed is True
        assert result.overage_will_apply is True


class TestConsumeIdempotency:
    def test_first_consume_decrements_balance(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        sub = bootstrap_trial_subscription(db_session, c)
        # Move from 'trial' to 'team' so credits are credited via the
        # shared bootstrap path; the bootstrap creates a balance with
        # included_credits=10 for trial. Re-use it.
        participant_id = str(uuid.uuid4())

        ledger = consume_interview_credit(
            db_session, workspace_id=c.id, participant_id=participant_id
        )
        assert ledger is not None
        assert ledger.event_type == EVT_CONSUME_INTERVIEW
        assert ledger.credits_delta == -1

        bal = get_active_balance(db_session, c.id)
        assert bal.used_credits == 1
        assert bal.available == 9

    def test_second_consume_for_same_participant_is_noop(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        bootstrap_trial_subscription(db_session, c)
        participant_id = str(uuid.uuid4())

        first = consume_interview_credit(db_session, workspace_id=c.id, participant_id=participant_id)
        assert first is not None

        # Replay — should silently no-op.
        second = consume_interview_credit(db_session, workspace_id=c.id, participant_id=participant_id)
        assert second is None

        # Balance still only reduced by one.
        bal = get_active_balance(db_session, c.id)
        assert bal.used_credits == 1
        # Ledger has exactly one consume row for this participant.
        rows = (
            db_session.query(CreditLedger)
            .filter(CreditLedger.participant_id == participant_id)
            .all()
        )
        assert len(rows) == 1

    def test_legacy_plan_consume_is_noop(self, db_session):
        """Legacy plans rely on participant-limit gates, not credits."""
        ensure_plans_seeded(db_session)
        c = _make_company(db_session, tier="team")  # legacy team
        backfill_legacy_subscriptions(db_session)

        result = consume_interview_credit(
            db_session, workspace_id=c.id, participant_id=str(uuid.uuid4())
        )
        assert result is None
        assert db_session.query(CreditLedger).count() == 0


class TestEntitlements:
    def test_entitlements_pulled_from_plan(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session, tier="team")  # legacy team
        backfill_legacy_subscriptions(db_session)
        ents = get_entitlements(db_session, c.id)
        assert ents["csv_export"] is True
        assert ents["custom_branding"] is False
        assert ents["legacy_tier"] == "team"


# ── PR 2: trial bootstrap + Stripe lifecycle ───────────────────────────────


class TestTrialBootstrap:
    def test_bootstraps_fresh_company_to_trial(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session)

        sub = bootstrap_trial_subscription(db_session, c)
        assert sub is not None
        assert sub.plan_id == "trial"
        assert sub.status == "trialing"
        assert sub.trial_end is not None

        bal = get_active_balance(db_session, c.id)
        assert bal is not None
        assert bal.included_credits == 10
        assert bal.available == 10

    def test_replaces_legacy_starter_from_backfill(self, db_session):
        """Common path: company exists, startup created legacy_starter,
        onboarding upgrades it to trial in-place."""
        ensure_plans_seeded(db_session)
        c = _make_company(db_session, tier="starter")
        backfill_legacy_subscriptions(db_session)
        before = get_current_subscription(db_session, c.id)
        assert before.plan_id == "legacy_starter"

        sub = bootstrap_trial_subscription(db_session, c)
        assert sub is not None
        assert sub.id == before.id  # same row, replaced in place
        assert sub.plan_id == "trial"
        assert sub.status == "trialing"

    def test_idempotent_when_already_trialing(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        first = bootstrap_trial_subscription(db_session, c)
        second = bootstrap_trial_subscription(db_session, c)
        assert second is not None
        assert second.id == first.id

        from app.models.billing import CreditBalance
        assert db_session.query(CreditBalance).filter(CreditBalance.workspace_id == c.id).count() == 1

    def test_does_not_downgrade_paid_plan(self, db_session):
        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        sub = bootstrap_trial_subscription(db_session, c)
        sub.plan_id = "team"
        sub.status = "active"
        db_session.commit()

        result = bootstrap_trial_subscription(db_session, c)
        assert result is None
        cur = get_current_subscription(db_session, c.id)
        assert cur.plan_id == "team"


class TestStripeLifecycle:
    def test_upsert_subscription_inserts_then_updates(self, db_session):
        from datetime import datetime, timedelta
        from app.services.billing_service import upsert_subscription_from_stripe

        ensure_plans_seeded(db_session)
        c = _make_company(db_session)

        now = datetime.utcnow()
        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            stripe_price_id="price_test",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        assert sub.plan_id == "team"
        assert sub.status == "active"

        # Replay — same row, status updated.
        sub2 = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
            stripe_price_id="price_test",
            status="past_due",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        assert sub2.id == sub.id
        assert sub2.status == "past_due"

    def test_grant_period_credits_idempotent(self, db_session):
        from datetime import datetime, timedelta
        from app.services.billing_service import (
            EVT_GRANT_INCLUDED,
            grant_period_credits,
            upsert_subscription_from_stripe,
        )
        from app.models.billing import CreditBalance, CreditLedger

        ensure_plans_seeded(db_session)
        c = _make_company(db_session)

        now = datetime.utcnow()
        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id="cus_x",
            stripe_subscription_id="sub_x",
            stripe_price_id="price_x",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        bal1 = grant_period_credits(db_session, sub)
        assert bal1 is not None
        assert bal1.included_credits == 100  # team plan default

        # Replay → same balance, no double grant.
        bal2 = grant_period_credits(db_session, sub)
        assert bal2 is not None
        assert bal2.id == bal1.id

        assert db_session.query(CreditBalance).filter(CreditBalance.workspace_id == c.id).count() == 1
        assert (
            db_session.query(CreditLedger)
            .filter(
                CreditLedger.workspace_id == c.id,
                CreditLedger.event_type == EVT_GRANT_INCLUDED,
            )
            .count()
            == 1
        )

    def test_cancel_subscription_marks_canceled(self, db_session):
        from datetime import datetime, timedelta
        from app.services.billing_service import (
            cancel_subscription,
            upsert_subscription_from_stripe,
        )

        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        now = datetime.utcnow()
        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id="cus_z",
            stripe_subscription_id="sub_z",
            stripe_price_id="price_z",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        result = cancel_subscription(db_session, stripe_subscription_id="sub_z")
        assert result is not None
        assert result.id == sub.id
        assert result.status == "canceled"


# ── PR 3: credit packs + admin adjustment + usage warnings ──────────────────


class TestCreditPackGrant:
    def test_grant_purchased_credits_idempotent_per_session(self, db_session):
        from datetime import datetime, timedelta
        from app.services.billing_service import (
            grant_period_credits,
            grant_purchased_credits,
            upsert_subscription_from_stripe,
        )

        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        now = datetime.utcnow()
        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id="cus_pack",
            stripe_subscription_id="sub_pack",
            stripe_price_id="price_x",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        grant_period_credits(db_session, sub)

        bal = grant_purchased_credits(
            db_session, c.id, credits=50, stripe_session_id="cs_test_1", pack_id="pack_50"
        )
        assert bal is not None
        assert bal.purchased_credits == 50

        # Replay with same Stripe session id — no double grant.
        bal2 = grant_purchased_credits(
            db_session, c.id, credits=50, stripe_session_id="cs_test_1", pack_id="pack_50"
        )
        assert bal2 is not None
        assert bal2.purchased_credits == 50  # unchanged

        # Different session id → adds again.
        bal3 = grant_purchased_credits(
            db_session, c.id, credits=25, stripe_session_id="cs_test_2", pack_id="pack_25"
        )
        assert bal3 is not None
        assert bal3.purchased_credits == 75

    def test_grant_purchased_credits_no_balance_returns_none(self, db_session):
        from app.services.billing_service import grant_purchased_credits

        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        result = grant_purchased_credits(
            db_session, c.id, credits=25, stripe_session_id="cs_orphan", pack_id="pack_25"
        )
        assert result is None


class TestUsageWarningEmails:
    def test_no_warning_under_80_percent(self, db_session, monkeypatch):
        from app.services.billing_service import (
            _maybe_send_usage_warning,
            bootstrap_trial_subscription,
            get_active_balance,
        )

        sent: list[dict] = []
        def fake_send(**kwargs):
            sent.append(kwargs)
            return True
        from app.services import email as email_module
        monkeypatch.setattr(email_module, "send_usage_warning", fake_send)

        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        bootstrap_trial_subscription(db_session, c)
        bal = get_active_balance(db_session, c.id)
        bal.used_credits = 5  # 50%
        db_session.commit()

        _maybe_send_usage_warning(db_session, c.id, bal)
        assert sent == []

    def test_fires_at_80_percent_then_idempotent(self, db_session, monkeypatch):
        from app.services.billing_service import (
            _maybe_send_usage_warning,
            bootstrap_trial_subscription,
            get_active_balance,
        )
        from app.models.billing import UsageEvent

        sent: list[dict] = []
        def fake_send(**kwargs):
            sent.append(kwargs)
            return True
        from app.services import email as email_module
        monkeypatch.setattr(email_module, "send_usage_warning", fake_send)

        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        bootstrap_trial_subscription(db_session, c)
        bal = get_active_balance(db_session, c.id)
        bal.used_credits = 8  # 80%
        db_session.commit()

        _maybe_send_usage_warning(db_session, c.id, bal)
        assert len(sent) == 1
        assert sent[0]["percent"] == 80

        _maybe_send_usage_warning(db_session, c.id, bal)
        assert len(sent) == 1

        assert (
            db_session.query(UsageEvent)
            .filter(UsageEvent.workspace_id == c.id, UsageEvent.event_name == "usage_warning_80")
            .count()
            == 1
        )

    def test_fires_at_100_percent(self, db_session, monkeypatch):
        from app.services.billing_service import (
            _maybe_send_usage_warning,
            bootstrap_trial_subscription,
            get_active_balance,
        )

        sent: list[dict] = []
        def fake_send(**kwargs):
            sent.append(kwargs)
            return True
        from app.services import email as email_module
        monkeypatch.setattr(email_module, "send_usage_warning", fake_send)

        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        bootstrap_trial_subscription(db_session, c)
        bal = get_active_balance(db_session, c.id)
        bal.used_credits = 10  # 100%
        db_session.commit()

        _maybe_send_usage_warning(db_session, c.id, bal)
        assert len(sent) == 1
        assert sent[0]["percent"] == 100


# ── V2.2: rollover policy ────────────────────────────────────────────────────


class TestRolloverPolicy:
    """Period-transition rollover. Policy: purchased + prior-rollover credits
    roll forever; included credits expire at period end. Consumption is
    attributed to buckets in this order: included → rollover → purchased."""

    def _setup_subscription(self, db_session, *, period_start, period_end):
        from app.services.billing_service import upsert_subscription_from_stripe

        ensure_plans_seeded(db_session)
        c = _make_company(db_session)
        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
            stripe_subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
            stripe_price_id="price_x",
            status="active",
            billing_interval="monthly",
            current_period_start=period_start,
            current_period_end=period_end,
        )
        return c, sub

    def test_no_prior_balance_means_zero_rollover(self, db_session):
        from app.services.billing_service import grant_period_credits

        now = datetime.utcnow()
        _, sub = self._setup_subscription(
            db_session, period_start=now, period_end=now + timedelta(days=30)
        )
        bal = grant_period_credits(db_session, sub)
        assert bal.rollover_credits == 0
        assert bal.included_credits == 100  # team plan default

    def test_unused_purchased_rolls_forward_unused_included_expires(self, db_session):
        from app.services.billing_service import (
            EVT_EXPIRE_CREDITS,
            EVT_GRANT_ROLLOVER,
            grant_period_credits,
            upsert_subscription_from_stripe,
        )

        now = datetime.utcnow()
        c, sub = self._setup_subscription(
            db_session, period_start=now - timedelta(days=30), period_end=now
        )
        bal1 = grant_period_credits(db_session, sub)
        bal1.purchased_credits = 25
        bal1.used_credits = 30
        db_session.commit()

        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id=sub.stripe_customer_id,
            stripe_subscription_id=sub.stripe_subscription_id,
            stripe_price_id="price_x",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        bal2 = grant_period_credits(db_session, sub)
        assert bal2.id != bal1.id
        assert bal2.included_credits == 100
        assert bal2.rollover_credits == 25
        assert bal2.purchased_credits == 0

        rollover_events = (
            db_session.query(CreditLedger)
            .filter(
                CreditLedger.workspace_id == c.id,
                CreditLedger.event_type == EVT_GRANT_ROLLOVER,
            )
            .all()
        )
        assert len(rollover_events) == 1
        assert rollover_events[0].credits_delta == 25
        expire_events = (
            db_session.query(CreditLedger)
            .filter(
                CreditLedger.workspace_id == c.id,
                CreditLedger.event_type == EVT_EXPIRE_CREDITS,
            )
            .all()
        )
        assert len(expire_events) == 1
        assert expire_events[0].credits_delta == -70

    def test_consumption_drains_included_first_then_rollover_then_purchased(self, db_session):
        from app.services.billing_service import (
            grant_period_credits,
            upsert_subscription_from_stripe,
        )

        now = datetime.utcnow()
        c, sub = self._setup_subscription(
            db_session, period_start=now - timedelta(days=30), period_end=now
        )
        bal1 = grant_period_credits(db_session, sub)
        bal1.purchased_credits = 50
        bal1.used_credits = 130
        db_session.commit()

        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id=sub.stripe_customer_id,
            stripe_subscription_id=sub.stripe_subscription_id,
            stripe_price_id="price_x",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        bal2 = grant_period_credits(db_session, sub)
        assert bal2.rollover_credits == 20

    def test_rollover_of_rollover(self, db_session):
        from app.services.billing_service import (
            grant_period_credits,
            upsert_subscription_from_stripe,
        )

        now = datetime.utcnow()
        c, sub = self._setup_subscription(
            db_session, period_start=now - timedelta(days=30), period_end=now
        )
        bal1 = grant_period_credits(db_session, sub)
        bal1.rollover_credits = 40
        bal1.used_credits = 100
        db_session.commit()

        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id=sub.stripe_customer_id,
            stripe_subscription_id=sub.stripe_subscription_id,
            stripe_price_id="price_x",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        bal2 = grant_period_credits(db_session, sub)
        assert bal2.rollover_credits == 40

    def test_zero_rollover_when_everything_consumed(self, db_session):
        from app.services.billing_service import (
            grant_period_credits,
            upsert_subscription_from_stripe,
        )

        now = datetime.utcnow()
        c, sub = self._setup_subscription(
            db_session, period_start=now - timedelta(days=30), period_end=now
        )
        bal1 = grant_period_credits(db_session, sub)
        bal1.purchased_credits = 25
        bal1.used_credits = 125
        db_session.commit()

        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id=sub.stripe_customer_id,
            stripe_subscription_id=sub.stripe_subscription_id,
            stripe_price_id="price_x",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        bal2 = grant_period_credits(db_session, sub)
        assert bal2.rollover_credits == 0

    def test_idempotent_no_duplicate_rollover_on_replay(self, db_session):
        from app.services.billing_service import (
            EVT_GRANT_ROLLOVER,
            grant_period_credits,
            upsert_subscription_from_stripe,
        )

        now = datetime.utcnow()
        c, sub = self._setup_subscription(
            db_session, period_start=now - timedelta(days=30), period_end=now
        )
        bal1 = grant_period_credits(db_session, sub)
        bal1.purchased_credits = 25
        db_session.commit()

        sub = upsert_subscription_from_stripe(
            db_session,
            workspace_id=c.id,
            plan_id="team",
            stripe_customer_id=sub.stripe_customer_id,
            stripe_subscription_id=sub.stripe_subscription_id,
            stripe_price_id="price_x",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        grant_period_credits(db_session, sub)
        grant_period_credits(db_session, sub)
        rollover_events = (
            db_session.query(CreditLedger)
            .filter(
                CreditLedger.workspace_id == c.id,
                CreditLedger.event_type == EVT_GRANT_ROLLOVER,
            )
            .all()
        )
        assert len(rollover_events) == 1
