"""
Affiliate program tests: apply, magic-link login, affiliate dashboard
endpoints, admin management (approve/reject, commission, payouts), audit
logging, referral attribution, and conversion idempotency.
"""
import pytest

from app.config import settings
from app.models.admin_audit import AdminAuditLog
from app.models.affiliate import Affiliate, AffiliateReferral
from app.services.auth import create_affiliate_magic_token

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


def _apply(client, email="jane@example.com", code="jane-doe", **extra):
    resp = client.post("/affiliates/apply", json={
        "name": "Jane Doe",
        "email": email,
        "code": code,
        "website": "https://jane.example.com",
        "how_they_found_us": "Twitter",
        **extra,
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
    """Sign in the way a real affiliate does: verify an emailed magic token."""
    magic = create_affiliate_magic_token(affiliate_id)
    resp = client.post("/affiliates/login/verify", json={"token": magic})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestApplyAndLogin:

    def test_apply_captures_language(self, client, db_session):
        _apply(client, preferred_language="fr")
        aff = db_session.query(Affiliate).first()
        assert aff.preferred_language == "fr"

    def test_apply_unknown_language_falls_back_to_en(self, client, db_session):
        _apply(client, preferred_language="zz")
        aff = db_session.query(Affiliate).first()
        assert aff.preferred_language == "en"

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


class TestMagicLinkLogin:

    def test_old_code_login_removed(self, client):
        # The referral code is public (it's in every shared link) so it must
        # never work as a credential.
        resp = client.post("/affiliates/login", json={"email": "jane@example.com", "code": "jane-doe"})
        assert resp.status_code in (404, 405)

    def test_login_request_always_200(self, client):
        aff_id = _apply(client)
        _approve(client, aff_id)
        # Unknown email leaks nothing: same 200 + same body as a real one
        unknown = client.post("/affiliates/login-request", json={"email": "nobody@example.com"})
        known = client.post("/affiliates/login-request", json={"email": "jane@example.com"})
        assert unknown.status_code == known.status_code == 200
        assert unknown.json() == known.json()

    def test_verify_garbage_token_401(self, client):
        resp = client.post("/affiliates/login/verify", json={"token": "not-a-token"})
        assert resp.status_code == 401

    def test_verify_pending_affiliate_401(self, client):
        aff_id = _apply(client)  # still pending
        magic = create_affiliate_magic_token(aff_id)
        resp = client.post("/affiliates/login/verify", json={"token": magic})
        assert resp.status_code == 401

    def test_magic_token_rejected_as_session_token(self, client):
        # The 30-min emailed token must not work as a dashboard bearer token.
        aff_id = _apply(client)
        _approve(client, aff_id)
        magic = create_affiliate_magic_token(aff_id)
        me = client.get("/affiliates/me", headers={"Authorization": f"Bearer {magic}"})
        assert me.status_code == 401


class TestReferralAttribution:

    def test_signup_with_ref_code_creates_referral(self, client, db_session):
        aff_id = _apply(client)
        _approve(client, aff_id)
        resp = client.post(
            "/auth/signup",
            json={"name": "Acme", "email": "buyer@example.com", "password": "Secure123!", "ref_code": "jane-doe"},
        )
        assert resp.status_code == 201
        referral = db_session.query(AffiliateReferral).first()
        assert referral is not None
        assert referral.affiliate_id == aff_id
        assert referral.status == "signed_up"

    def test_pending_affiliate_code_ignored(self, client, db_session):
        _apply(client)  # not approved
        client.post(
            "/auth/signup",
            json={"name": "Acme", "email": "buyer@example.com", "password": "Secure123!", "ref_code": "jane-doe"},
        )
        assert db_session.query(AffiliateReferral).count() == 0

    def test_self_referral_ignored(self, client, db_session):
        aff_id = _apply(client)
        _approve(client, aff_id)
        client.post(
            "/auth/signup",
            json={"name": "Jane Co", "email": "jane@example.com", "password": "Secure123!", "ref_code": "jane-doe"},
        )
        assert db_session.query(AffiliateReferral).count() == 0


class TestConversionTracking:
    STRIPE_SUB = {"items": {"data": [{"price": {"unit_amount_decimal": "8900"}}]}}

    def test_conversion_credits_commission_once(self, client, db_session):
        from app.models.company import Company
        from app.routers.billing import _track_affiliate_conversion

        aff_id = _apply(client)
        _approve(client, aff_id)
        client.post(
            "/auth/signup",
            json={"name": "Acme", "email": "buyer@example.com", "password": "Secure123!", "ref_code": "jane-doe"},
        )
        company = db_session.query(Company).filter(Company.email == "buyer@example.com").first()

        _track_affiliate_conversion(db_session, company.id, self.STRIPE_SUB)
        # Replay (cancel + resubscribe, or a replayed webhook) must not double-pay
        _track_affiliate_conversion(db_session, company.id, self.STRIPE_SUB)

        affiliate = db_session.query(Affiliate).filter(Affiliate.id == aff_id).first()
        referral = db_session.query(AffiliateReferral).first()
        assert referral.status == "converted"
        assert referral.commission_amount == pytest.approx(17.8)  # 20% of €89
        assert affiliate.total_earned == pytest.approx(17.8)


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

    def test_cannot_reapprove_active(self, client):
        aff_id = _apply(client)
        _approve(client, aff_id)
        resp = client.patch(
            f"/affiliates/admin/{aff_id}",
            json={"status": "rejected"},
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
        assert "€" in resp.json()["detail"]

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
