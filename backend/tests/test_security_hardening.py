"""Security hardening test suite: password policy, brute-force lockout,
TOTP 2FA, token revocation (token_version), and the Stripe refund /
payment-failed webhook handlers."""
from datetime import datetime, timedelta

import pyotp
import pytest

from app.models.company import Company


def _get_company(db_session, email="test@example.com"):
    return db_session.query(Company).filter(Company.email == email).first()


# ── Password policy ───────────────────────────────────────────────────


class TestPasswordPolicy:
    def test_signup_rejects_letters_only_password(self, client):
        resp = client.post("/auth/signup", json={
            "name": "Weak Co", "email": "weak@example.com", "password": "onlyletters",
        })
        assert resp.status_code == 400
        assert "letter and one number" in resp.json()["detail"]

    def test_signup_rejects_digits_only_password(self, client):
        resp = client.post("/auth/signup", json={
            "name": "Weak Co", "email": "weak2@example.com", "password": "12345678",
        })
        assert resp.status_code == 400

    def test_signup_accepts_letter_digit_password(self, client):
        resp = client.post("/auth/signup", json={
            "name": "OK Co", "email": "ok@example.com", "password": "goodpass1",
        })
        assert resp.status_code == 201

    def test_change_password_enforces_policy(self, client, auth_headers, registered_company):
        resp = client.post("/auth/change-password", headers=auth_headers, json={
            "current_password": registered_company["password"],
            "new_password": "weakpassword",
        })
        assert resp.status_code == 400

    def test_reset_confirm_enforces_policy(self, client, db_session, registered_company):
        from app.models.company import PasswordResetToken
        company = _get_company(db_session)
        token = PasswordResetToken(
            company_id=company.id,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db_session.add(token)
        db_session.commit()
        resp = client.post("/auth/password-reset/confirm", json={
            "token": token.token, "new_password": "lettersonly",
        })
        assert resp.status_code == 400


# ── Brute-force lockout ───────────────────────────────────────────────


class TestAccountLockout:
    def test_lockout_after_five_failures(self, client, registered_company):
        for _ in range(5):
            resp = client.post("/auth/login", json={
                "email": registered_company["email"], "password": "wrongpass1",
            })
            assert resp.status_code == 401
        # 6th attempt — even with the CORRECT password — is locked out.
        resp = client.post("/auth/login", json={
            "email": registered_company["email"],
            "password": registered_company["password"],
        })
        assert resp.status_code == 429
        assert "Too many" in resp.json()["detail"]

    def test_counter_resets_on_success(self, client, db_session, registered_company):
        for _ in range(3):
            client.post("/auth/login", json={
                "email": registered_company["email"], "password": "wrongpass1",
            })
        resp = client.post("/auth/login", json={
            "email": registered_company["email"],
            "password": registered_company["password"],
        })
        assert resp.status_code == 200
        company = _get_company(db_session)
        db_session.refresh(company)
        assert company.failed_login_attempts == 0

    def test_password_reset_clears_lockout(self, client, db_session, registered_company):
        from app.models.company import PasswordResetToken
        for _ in range(5):
            client.post("/auth/login", json={
                "email": registered_company["email"], "password": "wrongpass1",
            })
        company = _get_company(db_session)
        db_session.refresh(company)
        assert company.locked_until is not None
        token = PasswordResetToken(
            company_id=company.id,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db_session.add(token)
        db_session.commit()
        resp = client.post("/auth/password-reset/confirm", json={
            "token": token.token, "new_password": "freshpass1",
        })
        assert resp.status_code == 200
        db_session.refresh(company)
        assert company.locked_until is None
        resp = client.post("/auth/login", json={
            "email": registered_company["email"], "password": "freshpass1",
        })
        assert resp.status_code == 200

    def test_unknown_email_is_generic_401(self, client):
        resp = client.post("/auth/login", json={
            "email": "nobody@example.com", "password": "whatever1",
        })
        assert resp.status_code == 401


# ── TOTP 2FA ──────────────────────────────────────────────────────────


class TestTwoFactor:
    def _enroll(self, client, auth_headers):
        setup = client.post("/auth/2fa/setup", headers=auth_headers)
        assert setup.status_code == 200, setup.text
        secret = setup.json()["secret"]
        assert "otpauth://" in setup.json()["otpauth_url"]
        code = pyotp.TOTP(secret).now()
        enable = client.post("/auth/2fa/enable", headers=auth_headers, json={"code": code})
        assert enable.status_code == 200, enable.text
        return secret, enable.json()["backup_codes"]

    def test_full_enrolment_and_login_flow(self, client, auth_headers, registered_company):
        secret, backup_codes = self._enroll(client, auth_headers)
        assert len(backup_codes) == 10

        # Password-only login now returns a pending token, not sessions.
        resp = client.post("/auth/login", json={
            "email": registered_company["email"],
            "password": registered_company["password"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("requires_2fa") is True
        assert "access_token" not in body

        # Wrong code rejected.
        bad = client.post("/auth/login/2fa", json={
            "pending_token": body["pending_token"], "code": "000000",
        })
        assert bad.status_code == 401

        # Correct TOTP code completes login.
        good = client.post("/auth/login/2fa", json={
            "pending_token": body["pending_token"],
            "code": pyotp.TOTP(secret).now(),
        })
        assert good.status_code == 200
        assert good.json()["access_token"]

    def test_backup_code_is_single_use(self, client, auth_headers, registered_company):
        _, backup_codes = self._enroll(client, auth_headers)
        login = client.post("/auth/login", json={
            "email": registered_company["email"],
            "password": registered_company["password"],
        }).json()
        first = client.post("/auth/login/2fa", json={
            "pending_token": login["pending_token"], "code": backup_codes[0],
        })
        assert first.status_code == 200
        # Same code again fails.
        login2 = client.post("/auth/login", json={
            "email": registered_company["email"],
            "password": registered_company["password"],
        }).json()
        second = client.post("/auth/login/2fa", json={
            "pending_token": login2["pending_token"], "code": backup_codes[0],
        })
        assert second.status_code == 401

    def test_enable_requires_valid_code(self, client, auth_headers):
        setup = client.post("/auth/2fa/setup", headers=auth_headers)
        assert setup.status_code == 200
        enable = client.post("/auth/2fa/enable", headers=auth_headers, json={"code": "000000"})
        assert enable.status_code == 400

    def test_disable_restores_plain_login(self, client, auth_headers, registered_company):
        secret, _ = self._enroll(client, auth_headers)
        resp = client.post("/auth/2fa/disable", headers=auth_headers, json={
            "code": pyotp.TOTP(secret).now(),
            "password": registered_company["password"],
        })
        assert resp.status_code == 200, resp.text
        login = client.post("/auth/login", json={
            "email": registered_company["email"],
            "password": registered_company["password"],
        })
        assert login.status_code == 200
        assert login.json().get("access_token")

    def test_totp_enabled_exposed_in_me(self, client, auth_headers):
        self._enroll(client, auth_headers)
        me = client.get("/auth/me", headers=auth_headers)
        assert me.status_code == 200
        assert me.json()["totp_enabled"] is True


# ── Token revocation ──────────────────────────────────────────────────


class TestTokenRevocation:
    def test_logout_all_kills_existing_tokens(self, client, auth_headers):
        assert client.get("/auth/me", headers=auth_headers).status_code == 200
        resp = client.post("/auth/logout-all", headers=auth_headers)
        assert resp.status_code == 200
        assert client.get("/auth/me", headers=auth_headers).status_code == 401

    def test_logout_all_kills_refresh_token(self, client, auth_headers, registered_company):
        client.post("/auth/logout-all", headers=auth_headers)
        resp = client.post("/auth/refresh", json={
            "refresh_token": registered_company["tokens"]["refresh_token"],
        })
        assert resp.status_code == 401

    def test_change_password_revokes_other_sessions(self, client, auth_headers, registered_company):
        # A "second device" logs in.
        other = client.post("/auth/login", json={
            "email": registered_company["email"],
            "password": registered_company["password"],
        }).json()
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}
        assert client.get("/auth/me", headers=other_headers).status_code == 200

        resp = client.post("/auth/change-password", headers=auth_headers, json={
            "current_password": registered_company["password"],
            "new_password": "brandnew1",
        })
        assert resp.status_code == 200
        body = resp.json()
        # This session got fresh tokens; the other device is signed out.
        assert body["access_token"]
        fresh_headers = {"Authorization": f"Bearer {body['access_token']}"}
        assert client.get("/auth/me", headers=fresh_headers).status_code == 200
        assert client.get("/auth/me", headers=other_headers).status_code == 401

    def test_pre_migration_tokens_still_work(self, client, auth_headers):
        # Tokens minted while token_version == 0 with no "tv" claim must
        # keep working (back-compat for sessions from before this deploy).
        from app.services.auth import create_access_token
        from app.services.auth import decode_access_token  # noqa: F401
        me = client.get("/auth/me", headers=auth_headers)
        assert me.status_code == 200
        legacy_token = create_access_token({"sub": me.json()["id"]})  # no tv claim
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {legacy_token}"})
        assert resp.status_code == 200


# ── Stripe webhook handlers ───────────────────────────────────────────


@pytest.fixture
def credit_workspace(client, db_session, registered_company):
    """A workspace on the credits trial plan with an active balance."""
    from app.services.billing_service import (
        bootstrap_trial_subscription,
        ensure_plans_seeded,
    )
    ensure_plans_seeded(db_session)
    company = _get_company(db_session)
    sub = bootstrap_trial_subscription(db_session, company)
    return {"company": company, "subscription": sub}


class TestRefundWebhooks:
    def test_credit_pack_refund_claws_back_credits(self, db_session, credit_workspace):
        from app.services import billing_service
        company = credit_workspace["company"]
        balance = billing_service.grant_purchased_credits(
            db_session, company.id, credits=25, stripe_session_id="cs_test_1",
            pack_id="pack_25",
        )
        assert balance.purchased_credits == 25

        from app.routers.billing import _handle_charge_refunded
        charge = {
            "id": "ch_test_1",
            "metadata": {"workspace_id": company.id, "checkout_session_id": "cs_test_1"},
            "invoice": None,
            "payment_intent": "pi_test_1",
        }
        _handle_charge_refunded(db_session, charge)
        db_session.refresh(balance)
        assert balance.purchased_credits == 0

        # Replay is a no-op (idempotent per session).
        _handle_charge_refunded(db_session, charge)
        db_session.refresh(balance)
        assert balance.purchased_credits == 0

    def test_purchase_grant_idempotent_by_session_column(self, db_session, credit_workspace):
        from app.services import billing_service
        company = credit_workspace["company"]
        b1 = billing_service.grant_purchased_credits(
            db_session, company.id, credits=25, stripe_session_id="cs_dup", pack_id="pack_25",
        )
        b2 = billing_service.grant_purchased_credits(
            db_session, company.id, credits=25, stripe_session_id="cs_dup", pack_id="pack_25",
        )
        assert b1.id == b2.id
        db_session.refresh(b1)
        assert b1.purchased_credits == 25

    def test_partial_spend_refund_clamps_at_zero(self, db_session, credit_workspace):
        from app.services import billing_service
        company = credit_workspace["company"]
        balance = billing_service.grant_purchased_credits(
            db_session, company.id, credits=5, stripe_session_id="cs_partial", pack_id=None,
        )
        # Simulate the pack partially spent.
        balance.purchased_credits = 2
        db_session.commit()
        billing_service.revoke_purchased_credits(
            db_session, company.id, stripe_session_id="cs_partial", stripe_charge_id="ch_p",
        )
        db_session.refresh(balance)
        assert balance.purchased_credits == 0  # clamped, never negative

    def test_subscription_refund_records_usage_event(self, db_session, credit_workspace):
        from app.routers.billing import _handle_charge_refunded
        from app.models.billing import UsageEvent
        company = credit_workspace["company"]
        _handle_charge_refunded(db_session, {
            "id": "ch_sub_1",
            "metadata": {"workspace_id": company.id},
            "invoice": "in_test_1",
            "amount_refunded": 29900,
            "currency": "eur",
        })
        ev = (
            db_session.query(UsageEvent)
            .filter(UsageEvent.event_name == "stripe_subscription_refund")
            .first()
        )
        assert ev is not None
        assert ev.workspace_id == company.id


class TestPaymentFailedWebhook:
    def test_payment_failed_marks_past_due(self, db_session, credit_workspace):
        from app.routers.billing import _handle_invoice_payment_failed
        sub = credit_workspace["subscription"]
        sub.stripe_subscription_id = "sub_test_1"
        db_session.commit()

        _handle_invoice_payment_failed(db_session, {"subscription": "sub_test_1"})
        db_session.refresh(sub)
        assert sub.status == "past_due"
        company = credit_workspace["company"]
        db_session.refresh(company)
        assert company.subscription_status == "past_due"

    def test_unknown_subscription_is_noop(self, db_session, credit_workspace):
        from app.routers.billing import _handle_invoice_payment_failed
        _handle_invoice_payment_failed(db_session, {"subscription": "sub_unknown"})
        # No exception = pass.


class TestDisputeWebhook:
    def test_dispute_records_usage_event(self, db_session, credit_workspace):
        from app.routers.billing import _handle_charge_dispute
        from app.models.billing import UsageEvent
        company = credit_workspace["company"]
        _handle_charge_dispute(db_session, "charge.dispute.created", {
            "id": "dp_test_1",
            "charge": "ch_disputed",
            "metadata": {"workspace_id": company.id},
            "status": "needs_response",
            "reason": "fraudulent",
            "amount": 29900,
            "currency": "eur",
        })
        ev = (
            db_session.query(UsageEvent)
            .filter(UsageEvent.event_name == "stripe_dispute")
            .first()
        )
        assert ev is not None
        assert ev.event_metadata["stripe_dispute_id"] == "dp_test_1"
