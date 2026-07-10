"""
Affiliate program tests: apply/magic-link login, affiliate dashboard endpoints,
admin management (approve/reject/suspend, commission, payouts), signup referral
attribution, Stripe conversion tracking, and audit logging.
"""
import pytest

from app.config import settings
from app.models.admin_audit import AdminAuditLog
from app.models.affiliate import Affiliate, AffiliateReferral
from app.models.company import Company

ADMIN_KEY = "test-admin-secret-key"
ADMIN_IDENTITY = "test-admin"


@pytest.fixture(autouse=True)
def admin_secret_configured():
    prev = settings.ADMIN_SECRET_KEY
    settings.ADMIN_SECRET_KEY = ADMIN_KEY
    try:
        yield
    finally:
        settings.ADMIN_SECRET_KEY = prev


def _bearer_admin_headers() -> dict:
    return {
        "Authorization": f"Bearer {ADMIN_KEY}",
        "X-Admin-Identity": ADMIN_IDENTITY,
    }


def _legacy_admin_headers() -> dict:
    return {"X-Admin-Key": ADMIN_KEY}


def _apply(client, email="jane@example.com", code="jane-doe"):
    resp = client.post("/affiliates/apply", json={
        "name": "Jane Doe",
        "email": email,
        "code": code,
        "website": "https://jane.example.com",
        "how_they_found_us": "Twitter",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["affiliate_id"]


def _approve(client, affiliate_id):
    resp = client.patch(
        f"/affiliates/admin/{affiliate_id}",
        json={"status": "active"},
        headers=_bearer_admin_headers(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _affiliate_login(client, affiliate_id):
    """Session via the magic-link verify step (the email leg is side-effect only)."""
    from app.routers.affiliate import _create_magic_token
    resp = client.post(
        "/affiliates/login/verify", json={"token": _create_magic_token(affiliate_id)}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _signup_with_ref(client, ref_code, email="startup@example.com"):
    resp = client.post("/auth/signup", json={
        "name": "Startup Co",
        "email": email,
        "password": "Password1",
        "ref_code": ref_code,
    })
    assert resp.status_code == 201, resp.text


class TestApplyAndLogin:

    def test_login_request_is_generic_200(self, client):
        """Anti-enumeration: pending, active and unknown emails all get the
        same 200 — the response must not reveal whether an account exists."""
        _apply(client)
        known = client.post("/affiliates/login", json={"email": "jane@example.com"})
        unknown = client.post("/affiliates/login", json={"email": "nobody@example.com"})
        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json()

    def test_magic_verify_rejects_pending_affiliate(self, client):
        from app.routers.affiliate import _create_magic_token
        aff_id = _apply(client)
        resp = client.post(
            "/affiliates/login/verify", json={"token": _create_magic_token(aff_id)}
        )
        assert resp.status_code == 403

    def test_magic_verify_rejects_garbage_token(self, client):
        resp = client.post("/affiliates/login/verify", json={"token": "not-a-jwt"})
        assert resp.status_code == 401

    def test_session_token_rejected_as_magic_token(self, client):
        """A 24h session token must not be exchangeable for a fresh session."""
        aff_id = _apply(client)
        _approve(client, aff_id)
        headers = _affiliate_login(client, aff_id)
        session_token = headers["Authorization"].split(" ", 1)[1]
        resp = client.post("/affiliates/login/verify", json={"token": session_token})
        assert resp.status_code == 401

    def test_magic_token_rejected_as_session_token(self, client):
        from app.routers.affiliate import _create_magic_token
        aff_id = _apply(client)
        _approve(client, aff_id)
        resp = client.get(
            "/affiliates/me",
            headers={"Authorization": f"Bearer {_create_magic_token(aff_id)}"},
        )
        assert resp.status_code == 401

    def test_duplicate_email_rejected(self, client):
        _apply(client)
        resp = client.post("/affiliates/apply", json={
            "name": "Jane Doe", "email": "jane@example.com", "code": "other-code",
        })
        assert resp.status_code == 409

    def test_login_after_approval(self, client):
        aff_id = _apply(client)
        _approve(client, aff_id)
        headers = _affiliate_login(client, aff_id)
        me = client.get("/affiliates/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["status"] == "active"


class TestAdminAuth:

    def test_admin_list_accepts_bearer(self, client):
        resp = client.get("/affiliates/admin/list", headers=_bearer_admin_headers())
        assert resp.status_code == 200

    def test_admin_list_accepts_legacy_x_admin_key(self, client):
        resp = client.get("/affiliates/admin/list", headers=_legacy_admin_headers())
        assert resp.status_code == 200

    def test_admin_list_rejects_missing_key(self, client):
        resp = client.get("/affiliates/admin/list")
        assert resp.status_code == 401

    def test_admin_list_rejects_wrong_key(self, client):
        resp = client.get("/affiliates/admin/list", headers={"X-Admin-Key": "nope"})
        assert resp.status_code == 401

    def test_guard_rejects_non_ascii_key(self):
        # Must be a clean 401, not a TypeError-driven 500 — compare_digest
        # raises TypeError on non-ASCII str input. (Direct call: the test
        # client refuses to encode non-ASCII header values, real clients don't.)
        from fastapi import HTTPException
        from app.routers.affiliate import _get_admin_identity
        with pytest.raises(HTTPException) as exc:
            _get_admin_identity(authorization=None, x_admin_key="café-clé", x_admin_identity=None)
        assert exc.value.status_code == 401


class TestAdminManagement:

    def test_list_includes_enriched_fields(self, client):
        _apply(client)
        resp = client.get("/affiliates/admin/list", headers=_bearer_admin_headers())
        affs = resp.json()["affiliates"]
        assert len(affs) == 1
        aff = affs[0]
        assert aff["pending_earnings"] == 0.0
        assert aff["payout_threshold"] == 50.0
        assert aff["website"] == "https://jane.example.com"
        assert aff["how_they_found_us"] == "Twitter"
        assert aff["approved_at"] is None

    def test_approve_sets_approved_at_and_audits(self, client, db_session):
        aff_id = _apply(client)
        body = _approve(client, aff_id)
        assert body["affiliate"]["status"] == "active"
        assert body["affiliate"]["approved_at"] is not None

        audit = db_session.query(AdminAuditLog).filter(
            AdminAuditLog.action == "affiliate_status_change"
        ).all()
        assert len(audit) == 1
        assert audit[0].admin_identity == ADMIN_IDENTITY
        assert audit[0].target_company_email == "jane@example.com"

    def test_cannot_reject_active(self, client):
        aff_id = _apply(client)
        _approve(client, aff_id)
        resp = client.patch(
            f"/affiliates/admin/{aff_id}",
            json={"status": "rejected"},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 400

    def test_suspend_and_reactivate(self, client, db_session):
        aff_id = _apply(client)
        _approve(client, aff_id)
        headers = _affiliate_login(client, aff_id)

        resp = client.patch(
            f"/affiliates/admin/{aff_id}",
            json={"status": "suspended"},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["affiliate"]["status"] == "suspended"

        # Suspension bites immediately: outstanding session tokens stop working
        assert client.get("/affiliates/me", headers=headers).status_code == 403
        # ... and new signups through the code no longer attribute
        _signup_with_ref(client, "jane-doe", email="during-suspension@example.com")
        assert db_session.query(AffiliateReferral).count() == 0

        resp = client.patch(
            f"/affiliates/admin/{aff_id}",
            json={"status": "active"},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 200
        assert client.get("/affiliates/me", headers=headers).status_code == 200

    def test_cannot_suspend_pending(self, client):
        aff_id = _apply(client)
        resp = client.patch(
            f"/affiliates/admin/{aff_id}",
            json={"status": "suspended"},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 400

    def test_commission_update_audited(self, client, db_session):
        aff_id = _apply(client)
        resp = client.patch(
            f"/affiliates/admin/{aff_id}",
            json={"commission_pct": 25.0},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["affiliate"]["commission_pct"] == 25.0
        audit = db_session.query(AdminAuditLog).filter(
            AdminAuditLog.action == "affiliate_commission_change"
        ).all()
        assert len(audit) == 1

    def test_commission_out_of_range_rejected(self, client):
        aff_id = _apply(client)
        resp = client.patch(
            f"/affiliates/admin/{aff_id}",
            json={"commission_pct": 150.0},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 422


class TestReferralAttribution:

    def test_signup_with_ref_code_creates_referral(self, client, db_session):
        aff_id = _apply(client)
        _approve(client, aff_id)
        _signup_with_ref(client, "jane-doe")
        referral = db_session.query(AffiliateReferral).one()
        assert referral.affiliate_id == aff_id
        assert referral.status == "signed_up"

    def test_ref_code_is_normalised(self, client, db_session):
        aff_id = _apply(client)
        _approve(client, aff_id)
        _signup_with_ref(client, "  JANE-DOE  ")
        assert db_session.query(AffiliateReferral).count() == 1

    def test_pending_affiliate_code_does_not_attribute(self, client, db_session):
        _apply(client)  # never approved
        _signup_with_ref(client, "jane-doe")
        assert db_session.query(AffiliateReferral).count() == 0

    def test_self_referral_ignored(self, client, db_session):
        aff_id = _apply(client)
        _approve(client, aff_id)
        _signup_with_ref(client, "jane-doe", email="jane@example.com")
        assert db_session.query(AffiliateReferral).count() == 0


class TestConversionTracking:

    def _converted_setup(self, client, db_session):
        aff_id = _apply(client)
        _approve(client, aff_id)
        _signup_with_ref(client, "jane-doe")
        company = db_session.query(Company).filter(
            Company.email == "startup@example.com"
        ).one()
        return aff_id, company.id

    @staticmethod
    def _stripe_sub(status="active", unit_amount="9900"):
        return {
            "status": status,
            "items": {"data": [{"price": {"unit_amount_decimal": unit_amount}}]},
        }

    def test_conversion_credits_commission_once(self, client, db_session):
        from app.routers.billing import _track_affiliate_conversion
        aff_id, company_id = self._converted_setup(client, db_session)

        _track_affiliate_conversion(db_session, company_id, self._stripe_sub())
        referral = db_session.query(AffiliateReferral).one()
        affiliate = db_session.query(Affiliate).filter(Affiliate.id == aff_id).one()
        assert referral.status == "converted"
        assert referral.commission_amount == pytest.approx(19.80)  # 20% of €99
        assert affiliate.total_earned == pytest.approx(19.80)

        # Stripe delivers at-least-once — a replay must not double-pay.
        _track_affiliate_conversion(db_session, company_id, self._stripe_sub())
        db_session.refresh(affiliate)
        assert affiliate.total_earned == pytest.approx(19.80)

    def test_unpaid_subscription_does_not_convert(self, client, db_session):
        from app.routers.billing import _track_affiliate_conversion
        _, company_id = self._converted_setup(client, db_session)

        _track_affiliate_conversion(
            db_session, company_id, self._stripe_sub(status="incomplete")
        )
        referral = db_session.query(AffiliateReferral).one()
        assert referral.status == "signed_up"

        # ...but converts once the subscription later activates (the
        # subscription.updated handler re-fires this).
        _track_affiliate_conversion(db_session, company_id, self._stripe_sub())
        db_session.refresh(referral)
        assert referral.status == "converted"


class TestPayouts:

    def _seed_earnings(self, db_session, aff_id, earned=100.0):
        aff = db_session.query(Affiliate).filter(Affiliate.id == aff_id).first()
        aff.total_earned = earned
        db_session.commit()

    def test_payout_exceeding_pending_rejected(self, client, db_session):
        aff_id = _apply(client)
        _approve(client, aff_id)
        self._seed_earnings(db_session, aff_id, earned=40.0)
        resp = client.post(
            f"/affiliates/admin/{aff_id}/payout",
            json={"amount": 60.0},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 400
        assert "exceeds pending earnings" in resp.json()["detail"]

    def test_payout_nonpositive_rejected(self, client):
        aff_id = _apply(client)
        resp = client.post(
            f"/affiliates/admin/{aff_id}/payout",
            json={"amount": 0},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 422

    def test_payout_recorded_and_visible_everywhere(self, client, db_session):
        aff_id = _apply(client)
        _approve(client, aff_id)
        self._seed_earnings(db_session, aff_id, earned=100.0)

        resp = client.post(
            f"/affiliates/admin/{aff_id}/payout",
            json={"amount": 60.0, "notes": "PayPal ref 1"},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_paid"] == 60.0
        assert body["pending_earnings"] == 40.0

        # Admin payout history
        history = client.get(
            f"/affiliates/admin/{aff_id}/payouts", headers=_bearer_admin_headers()
        )
        assert history.status_code == 200
        assert history.json()["total"] == 1
        assert history.json()["payouts"][0]["amount"] == 60.0
        assert history.json()["payouts"][0]["notes"] == "PayPal ref 1"

        # Affiliate-facing payout history
        headers = _affiliate_login(client, aff_id)
        mine = client.get("/affiliates/me/payouts", headers=headers)
        assert mine.status_code == 200
        assert mine.json()["total"] == 1

        # Audit trail
        audit = db_session.query(AdminAuditLog).filter(
            AdminAuditLog.action == "affiliate_payout"
        ).all()
        assert len(audit) == 1

    def test_payout_marks_converted_referrals_paid(self, client, db_session):
        from app.routers.billing import _track_affiliate_conversion
        aff_id = _apply(client)
        _approve(client, aff_id)
        _signup_with_ref(client, "jane-doe")
        company = db_session.query(Company).filter(
            Company.email == "startup@example.com"
        ).one()
        _track_affiliate_conversion(db_session, company.id, {
            "status": "active",
            "items": {"data": [{"price": {"unit_amount_decimal": "9900"}}]},
        })

        resp = client.post(
            f"/affiliates/admin/{aff_id}/payout",
            json={"amount": 19.80},
            headers=_bearer_admin_headers(),
        )
        assert resp.status_code == 200, resp.text
        referral = db_session.query(AffiliateReferral).one()
        db_session.refresh(referral)
        assert referral.status == "paid"
