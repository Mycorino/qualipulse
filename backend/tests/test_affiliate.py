"""
Affiliate program tests: apply/login, affiliate dashboard endpoints,
admin management (approve/reject, commission, payouts) and audit logging.
"""
import pytest

from app.config import settings
from app.models.admin_audit import AdminAuditLog
from app.models.affiliate import Affiliate

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


def _affiliate_login(client, email="jane@example.com", code="jane-doe"):
    resp = client.post("/affiliates/login", json={"email": email, "code": code})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestApplyAndLogin:

    def test_apply_then_login_requires_approval(self, client):
        _apply(client)
        resp = client.post("/affiliates/login", json={"email": "jane@example.com", "code": "jane-doe"})
        assert resp.status_code == 403

    def test_duplicate_email_rejected(self, client):
        _apply(client)
        resp = client.post("/affiliates/apply", json={
            "name": "Jane Doe", "email": "jane@example.com", "code": "other-code",
        })
        assert resp.status_code == 409

    def test_login_after_approval(self, client):
        aff_id = _apply(client)
        _approve(client, aff_id)
        headers = _affiliate_login(client)
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
        headers = _affiliate_login(client)
        mine = client.get("/affiliates/me/payouts", headers=headers)
        assert mine.status_code == 200
        assert mine.json()["total"] == 1

        # Audit trail
        audit = db_session.query(AdminAuditLog).filter(
            AdminAuditLog.action == "affiliate_payout"
        ).all()
        assert len(audit) == 1
