"""
Tests for the three admin-ops features:
1. Account suspension — blocks login, refresh, and API access
2. Admin impersonation — generates scoped JWT, bypasses suspension
3. Admin audit log — records all admin mutations
"""
import pytest
from datetime import datetime

from app.config import settings
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


def _admin_headers(identity: str = ADMIN_IDENTITY) -> dict:
    return {
        "Authorization": f"Bearer {ADMIN_KEY}",
        "X-Admin-Identity": identity,
    }


def _signup(client, email="test@example.com", name="Test Co"):
    resp = client.post("/auth/signup", json={
        "name": name,
        "email": email,
        "password": "Password123!",
    })
    assert resp.status_code == 201, resp.text
    tokens = resp.json()
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    return {**tokens, "company_id": me.json()["id"]}


# ── Suspension ────────────────────────────────────────────────────────────────


class TestSuspension:

    def test_suspend_user(self, client):
        tokens = _signup(client)
        company_id = tokens["company_id"]

        resp = client.post(
            f"/admin/users/{company_id}/suspend",
            json={"reason": "ToS violation"},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["suspended_at"] is not None
        assert data["suspension_reason"] == "ToS violation"

    def test_suspend_blocks_login(self, client):
        tokens = _signup(client, email="suspend@example.com")
        cid = tokens["company_id"]

        client.post(
            f"/admin/users/{cid}/suspend",
            json={"reason": "test"},
            headers=_admin_headers(),
        )

        resp = client.post("/auth/login", json={
            "email": "suspend@example.com",
            "password": "Password123!",
        })
        assert resp.status_code == 403
        assert "suspended" in resp.json()["detail"].lower()

    def test_suspend_blocks_api(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]
        access = tokens["access_token"]

        client.post(
            f"/admin/users/{cid}/suspend",
            json={"reason": "test"},
            headers=_admin_headers(),
        )

        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert resp.status_code == 403

    def test_suspend_blocks_refresh(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]
        refresh = tokens["refresh_token"]

        client.post(
            f"/admin/users/{cid}/suspend",
            json={"reason": "test"},
            headers=_admin_headers(),
        )

        resp = client.post("/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 403
        assert "suspended" in resp.json()["detail"].lower()

    def test_unsuspend_restores_access(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]
        access = tokens["access_token"]

        client.post(
            f"/admin/users/{cid}/suspend",
            json={"reason": "test"},
            headers=_admin_headers(),
        )

        resp = client.post(
            f"/admin/users/{cid}/unsuspend",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["suspended_at"] is None

        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert resp.status_code == 200

    def test_suspend_already_suspended(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]
        client.post(f"/admin/users/{cid}/suspend", json={"reason": "x"}, headers=_admin_headers())

        resp = client.post(f"/admin/users/{cid}/suspend", json={"reason": "y"}, headers=_admin_headers())
        assert resp.status_code == 409

    def test_unsuspend_not_suspended(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]
        resp = client.post(f"/admin/users/{cid}/unsuspend", headers=_admin_headers())
        assert resp.status_code == 409


# ── Impersonation ─────────────────────────────────────────────────────────────


class TestImpersonation:

    def test_impersonate_returns_token(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        resp = client.post(
            f"/admin/users/{cid}/impersonate",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["company_name"] == "Test Co"
        assert data["company_email"] == "test@example.com"

    def test_impersonation_token_accesses_api(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        resp = client.post(f"/admin/users/{cid}/impersonate", headers=_admin_headers())
        imp_token = resp.json()["access_token"]

        me = client.get("/auth/me", headers={"Authorization": f"Bearer {imp_token}"})
        assert me.status_code == 200
        data = me.json()
        assert data["is_impersonation"] is True
        assert data["impersonation_admin"] == ADMIN_IDENTITY

    def test_impersonation_bypasses_suspension(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        client.post(f"/admin/users/{cid}/suspend", json={"reason": "test"}, headers=_admin_headers())

        resp = client.post(f"/admin/users/{cid}/impersonate", headers=_admin_headers())
        imp_token = resp.json()["access_token"]

        me = client.get("/auth/me", headers={"Authorization": f"Bearer {imp_token}"})
        assert me.status_code == 200
        assert me.json()["is_impersonation"] is True

    def test_impersonate_nonexistent_user(self, client):
        resp = client.post(
            "/admin/users/nonexistent-id/impersonate",
            headers=_admin_headers(),
        )
        assert resp.status_code == 404


# ── Audit log ─────────────────────────────────────────────────────────────────


class TestAuditLog:

    def test_suspend_creates_audit_entry(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        client.post(f"/admin/users/{cid}/suspend", json={"reason": "test"}, headers=_admin_headers())

        resp = client.get("/admin/audit-log", headers=_admin_headers())
        assert resp.status_code == 200
        entries = resp.json()
        suspend_entries = [e for e in entries if e["action"] == "suspend"]
        assert len(suspend_entries) >= 1
        assert suspend_entries[0]["admin_identity"] == ADMIN_IDENTITY
        assert suspend_entries[0]["target_company_email"] == "test@example.com"

    def test_impersonation_creates_audit_entry(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        client.post(f"/admin/users/{cid}/impersonate", headers=_admin_headers())

        resp = client.get("/admin/audit-log", headers=_admin_headers())
        entries = resp.json()
        imp_entries = [e for e in entries if e["action"] == "impersonation_start"]
        assert len(imp_entries) >= 1

    def test_tier_change_creates_audit_entry(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        client.patch(
            f"/admin/users/{cid}/tier",
            json={"tier": "lab"},
            headers=_admin_headers(),
        )

        resp = client.get("/admin/audit-log", headers=_admin_headers())
        entries = resp.json()
        tier_entries = [e for e in entries if e["action"] == "tier_change"]
        assert len(tier_entries) >= 1
        assert tier_entries[0]["details"]["new_tier"] == "lab"

    def test_delete_creates_audit_entry(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        client.delete(f"/admin/users/{cid}", headers=_admin_headers())

        resp = client.get("/admin/audit-log", headers=_admin_headers())
        entries = resp.json()
        del_entries = [e for e in entries if e["action"] == "user_delete"]
        assert len(del_entries) >= 1
        assert del_entries[0]["target_company_id"] is None
        assert del_entries[0]["target_company_email"] == "test@example.com"

    def test_audit_log_filter_by_action(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        client.post(f"/admin/users/{cid}/suspend", json={"reason": "x"}, headers=_admin_headers())
        client.post(f"/admin/users/{cid}/unsuspend", headers=_admin_headers())

        resp = client.get("/admin/audit-log", params={"action": "suspend"}, headers=_admin_headers())
        entries = resp.json()
        assert all(e["action"] == "suspend" for e in entries)

    def test_audit_log_filter_by_email(self, client):
        _signup(client, email="alice@example.com", name="Alice")
        _signup(client, email="bob@example.com", name="Bob")

        alice = client.get("/admin/users", params={"search": "alice"}, headers=_admin_headers())
        alice_id = alice.json()[0]["id"]
        client.post(f"/admin/users/{alice_id}/suspend", json={"reason": "x"}, headers=_admin_headers())

        resp = client.get("/admin/audit-log", params={"search": "alice"}, headers=_admin_headers())
        entries = resp.json()
        assert all("alice" in e["target_company_email"] for e in entries)

    def test_audit_log_identity_from_header(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        client.post(
            f"/admin/users/{cid}/suspend",
            json={"reason": "test"},
            headers=_admin_headers(identity="corin"),
        )

        resp = client.get("/admin/audit-log", headers=_admin_headers())
        entries = resp.json()
        assert entries[0]["admin_identity"] == "corin"

    def test_audit_log_without_identity_header(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        headers = {"Authorization": f"Bearer {ADMIN_KEY}"}
        client.post(f"/admin/users/{cid}/suspend", json={"reason": "test"}, headers=headers)

        resp = client.get("/admin/audit-log", headers=headers)
        entries = resp.json()
        assert entries[0]["admin_identity"] == "unknown"


# ── Costs report ──────────────────────────────────────────────────────────────


class TestCostsReport:

    def test_costs_endpoint_returns_report(self, client, db_session):
        """Regression: /admin/costs 500ed because the per-company aggregation
        used func.case() instead of the sqlalchemy case() construct."""
        from app.models.usage import AIUsageLog

        tokens = _signup(client)
        db_session.add(AIUsageLog(
            company_id=tokens["company_id"],
            operation="interview_turn",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0123,
            participant_id="p-1",
        ))
        db_session.commit()

        resp = client.get("/admin/costs", headers=_admin_headers())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_cost_usd"] > 0
        assert len(body["by_company"]) == 1
        assert body["by_company"][0]["company_id"] == tokens["company_id"]
