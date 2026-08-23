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
        assert data["impersonation_admin"] == f"shared-key:{ADMIN_IDENTITY}"

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
        assert suspend_entries[0]["admin_identity"] == f"shared-key:{ADMIN_IDENTITY}"
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
        assert entries[0]["admin_identity"] == "shared-key:corin"

    def test_audit_log_without_identity_header(self, client):
        tokens = _signup(client)
        cid = tokens["company_id"]

        headers = {"Authorization": f"Bearer {ADMIN_KEY}"}
        client.post(f"/admin/users/{cid}/suspend", json={"reason": "test"}, headers=headers)

        resp = client.get("/admin/audit-log", headers=headers)
        entries = resp.json()
        assert entries[0]["admin_identity"] == "shared-key:unknown"


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
        assert body["all_time_cost_usd"] > 0
        assert body["window_cost_usd"] > 0
        assert len(body["by_company"]) == 1
        assert body["by_company"][0]["company_id"] == tokens["company_id"]
        assert body["by_operation"][0]["operation"] == "interview_turn"
        assert body["interview_economics"]["interviews_with_cost"] == 1

    def test_costs_all_time_and_company_drilldown(self, client, db_session):
        from app.models.usage import AIUsageLog

        tokens = _signup(client)
        db_session.add(AIUsageLog(
            company_id=tokens["company_id"], operation="stt", model="whisper-1",
            audio_seconds=30.0, cost_usd=0.003, participant_id="p-1",
        ))
        db_session.commit()

        resp = client.get("/admin/costs", params={"days": 0}, headers=_admin_headers())
        assert resp.status_code == 200, resp.text
        assert resp.json()["days"] is None
        assert resp.json()["daily"] == []

        resp = client.get(f"/admin/costs/company/{tokens['company_id']}", headers=_admin_headers())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_cost_usd"] > 0
        assert body["interview_economics"]["breakdown"]["stt"] > 0
        assert isinstance(body["interviews"], list)

        resp = client.get("/admin/costs/company/nope", headers=_admin_headers())
        assert resp.status_code == 404

    def test_overview_shape(self, client, db_session):
        _signup(client)
        resp = client.get("/admin/overview", params={"days": 7}, headers=_admin_headers())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["kpis"]["signups"]["value"] == 1
        assert body["kpis"]["signups"]["previous"] == 0
        assert body["totals"]["users"] == 1
        assert len(body["daily"]) == 8
        assert [f["step"] for f in body["funnel"]] == [
            "signed_up", "onboarded", "created_study", "first_interview",
        ]


class TestInterviewEconomics:
    """Per-interview cost math: fully-loaded cost, demo exclusion, drilldown."""

    def _seed(self, db_session, company_id):
        import uuid
        from datetime import timedelta
        from app.models.interview import InterviewLink, InterviewTurn, Participant
        from app.models.project import Project
        from app.models.usage import AIUsageLog

        now = datetime.utcnow()
        real = Project(id=str(uuid.uuid4()), company_id=company_id, name="Real study")
        demo = Project(id=str(uuid.uuid4()), company_id=company_id, name="Demo", is_demo=True)
        db_session.add_all([real, demo])
        db_session.flush()
        link = InterviewLink(id=str(uuid.uuid4()), project_id=real.id, token="tok-econ")
        db_session.add(link)
        db_session.flush()
        pids = []
        for i, cost in enumerate((0.10, 0.30)):
            p = Participant(
                id=str(uuid.uuid4()), link_id=link.id, project_id=real.id,
                display_name=f"P{i}", status="completed",
                started_at=now - timedelta(minutes=12), completed_at=now - timedelta(minutes=2),
            )
            db_session.add(p)
            db_session.flush()
            pids.append(p.id)
            for t in range(3):
                db_session.add(InterviewTurn(
                    id=str(uuid.uuid4()), participant_id=p.id, turn_index=t,
                    question_index=t, question_text="q", response_transcript="a",
                ))
            db_session.add(AIUsageLog(company_id=company_id, project_id=real.id, participant_id=p.id,
                                      operation="interview_turn", model="claude-sonnet-4-6", cost_usd=cost))
            db_session.add(AIUsageLog(company_id=company_id, project_id=real.id, participant_id=p.id,
                                      operation="stt", model="whisper-1", audio_seconds=120, cost_usd=0.012))
            db_session.add(AIUsageLog(company_id=company_id, project_id=real.id, participant_id=p.id,
                                      operation="tts", model="tts-1", characters=1000, cost_usd=0.015))
        # Demo participant: completed, no spend -- must not dilute averages.
        db_session.add(Participant(id=str(uuid.uuid4()), link_id=link.id, project_id=demo.id,
                                   display_name="Demo", status="completed", completed_at=now))
        # Study-level overhead: not part of per-interview cost.
        db_session.add(AIUsageLog(company_id=company_id, project_id=real.id,
                                  operation="analysis", model="claude-sonnet-4-6", cost_usd=1.0))
        db_session.commit()
        return real.id, pids

    def test_platform_economics(self, client, db_session):
        tokens = _signup(client)
        self._seed(db_session, tokens["company_id"])

        body = client.get("/admin/costs", params={"days": 30}, headers=_admin_headers()).json()
        econ = body["interview_economics"]
        assert econ["completed_interviews"] == 2
        assert econ["interviews_with_cost"] == 2
        assert econ["total_cost_usd"] == pytest.approx(0.454, abs=1e-4)
        assert econ["cost_per_completed_usd"] == pytest.approx(0.227, abs=1e-4)
        assert econ["per_interview"]["median"] == pytest.approx(0.227, abs=1e-4)
        assert econ["per_interview"]["max"] == pytest.approx(0.327, abs=1e-4)
        assert econ["breakdown"]["stt"] == pytest.approx(0.024, abs=1e-4)
        assert econ["avg_turns"] == 3.0
        assert econ["avg_audio_minutes"] == 2.0
        assert body["window_cost_usd"] == pytest.approx(1.454, abs=1e-4)
        areas = {r["area"]: r["cost_usd"] for r in body["by_area"]}
        assert areas["analysis"] == pytest.approx(1.0)
        assert areas["interviews"] == pytest.approx(0.454, abs=1e-4)
        row = body["by_company"][0]
        assert row["window_interviews"] == 2 and row["total_interviews"] == 2
        assert row["window_cost_per_interview_usd"] == pytest.approx(0.227, abs=1e-4)

    def test_company_drilldown(self, client, db_session):
        tokens = _signup(client)
        real_id, pids = self._seed(db_session, tokens["company_id"])

        body = client.get(f"/admin/costs/company/{tokens['company_id']}", headers=_admin_headers()).json()
        projects = {p["project_id"]: p for p in body["by_project"]}
        assert projects[real_id]["completed_interviews"] == 2
        assert projects[real_id]["cost_per_interview_usd"] == pytest.approx(0.727, abs=1e-4)
        demo = next(p for p in body["by_project"] if p["is_demo"])
        assert demo["cost_per_interview_usd"] is None
        assert len(body["interviews"]) == 2  # demo participant excluded
        top = max(body["interviews"], key=lambda r: r["cost_usd"])
        assert top["cost_usd"] == pytest.approx(0.327, abs=1e-4)
        assert top["llm_usd"] == pytest.approx(0.30)
        assert top["turns"] == 3 and top["duration_minutes"] == 10.0

    def test_overview_counts_real_interviews_only(self, client, db_session):
        tokens = _signup(client)
        self._seed(db_session, tokens["company_id"])
        body = client.get("/admin/overview", params={"days": 7}, headers=_admin_headers()).json()
        assert body["kpis"]["interviews_completed"]["value"] == 2
        assert body["kpis"]["active_workspaces"]["value"] == 1
        assert body["kpis"]["cost_per_interview_usd"]["value"] == pytest.approx(0.227, abs=1e-4)
        assert body["kpis"]["studies_created"]["value"] == 1
        assert body["top_workspaces"][0]["interviews"] == 2
        assert body["funnel"][-1]["count"] == 1


# ── Named admin accounts + TOTP ───────────────────────────────────────────────


def _enable_2fa(client, db_session, tokens):
    """Enrol the account in TOTP the way the UI does and return the secret."""
    import pyotp

    auth = {"Authorization": f"Bearer {tokens['access_token']}"}
    setup = client.post("/auth/2fa/setup", headers=auth)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enable = client.post("/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=auth)
    assert enable.status_code == 200, enable.text
    return secret


def _grant_admin(db_session, company_id: str) -> None:
    company = db_session.query(Company).filter(Company.id == company_id).first()
    company.is_admin = True
    db_session.commit()


def _open_admin_session(client, tokens, secret) -> str:
    import pyotp

    resp = client.post(
        "/admin/session",
        json={"code": pyotp.TOTP(secret).now()},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["admin_token"]


class TestAdminAccounts:

    def test_non_admin_cannot_open_session(self, client, db_session):
        import pyotp

        tokens = _signup(client)
        secret = _enable_2fa(client, db_session, tokens)
        resp = client.post(
            "/admin/session",
            json={"code": pyotp.TOTP(secret).now()},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not an admin"

    def test_admin_without_2fa_is_refused(self, client, db_session):
        tokens = _signup(client)
        _grant_admin(db_session, tokens["company_id"])
        resp = client.post(
            "/admin/session",
            json={"code": "000000"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "admin_2fa_required"

    def test_wrong_code_is_refused_and_audited(self, client, db_session):
        tokens = _signup(client)
        _enable_2fa(client, db_session, tokens)
        _grant_admin(db_session, tokens["company_id"])
        resp = client.post(
            "/admin/session",
            json={"code": "000000"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 401
        from app.models.admin_audit import AdminAuditLog
        actions = [r.action for r in db_session.query(AdminAuditLog).all()]
        assert "admin_session_denied" in actions

    def test_admin_token_opens_panel_with_verified_identity(self, client, db_session):
        tokens = _signup(client, email="staff@qualipulse.com")
        secret = _enable_2fa(client, db_session, tokens)
        _grant_admin(db_session, tokens["company_id"])
        admin_token = _open_admin_session(client, tokens, secret)

        # Works without any X-Admin-Identity header...
        headers = {"Authorization": f"Bearer {admin_token}"}
        assert client.get("/admin/stats", headers=headers).status_code == 200

        # ...and a self-declared identity header is ignored: the audit log
        # gets the verified email.
        victim = _signup(client, email="victim@example.com", name="Victim")
        resp = client.patch(
            f"/admin/users/{victim['company_id']}/tier", json={"tier": "team"},
            headers={**headers, "X-Admin-Identity": "someone-else"},
        )
        assert resp.status_code == 200, resp.text
        audit = client.get("/admin/audit-log", headers=headers).json()
        assert audit[0]["admin_identity"] == "staff@qualipulse.com"

    def test_app_session_token_is_not_an_admin_token(self, client, db_session):
        tokens = _signup(client)
        _enable_2fa(client, db_session, tokens)
        _grant_admin(db_session, tokens["company_id"])
        # A plain 24h app access token must never open /admin, even for an admin.
        resp = client.get("/admin/stats", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 401

    def test_destructive_action_needs_fresh_step_up(self, client, db_session):
        import pyotp

        tokens = _signup(client, email="staff@qualipulse.com")
        secret = _enable_2fa(client, db_session, tokens)
        _grant_admin(db_session, tokens["company_id"])
        admin_token = _open_admin_session(client, tokens, secret)
        headers = {"Authorization": f"Bearer {admin_token}"}
        victim = _signup(client, email="victim@example.com", name="Victim")

        resp = client.post(f"/admin/users/{victim['company_id']}/suspend", json={"reason": "x"}, headers=headers)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "admin_step_up_required"

        resp = client.post(
            f"/admin/users/{victim['company_id']}/suspend", json={"reason": "x"},
            headers={**headers, "X-Admin-Step-Up": "000000"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "admin_step_up_invalid"

        resp = client.post(
            f"/admin/users/{victim['company_id']}/suspend", json={"reason": "x"},
            headers={**headers, "X-Admin-Step-Up": pyotp.TOTP(secret).now()},
        )
        assert resp.status_code == 200, resp.text

    def test_revoking_admin_flag_kills_live_session(self, client, db_session):
        tokens = _signup(client)
        secret = _enable_2fa(client, db_session, tokens)
        _grant_admin(db_session, tokens["company_id"])
        admin_token = _open_admin_session(client, tokens, secret)
        headers = {"Authorization": f"Bearer {admin_token}"}
        assert client.get("/admin/stats", headers=headers).status_code == 200

        company = db_session.query(Company).filter(Company.id == tokens["company_id"]).first()
        company.is_admin = False
        db_session.commit()
        assert client.get("/admin/stats", headers=headers).status_code == 403

    def test_logout_everywhere_revokes_admin_token(self, client, db_session):
        tokens = _signup(client)
        secret = _enable_2fa(client, db_session, tokens)
        _grant_admin(db_session, tokens["company_id"])
        admin_token = _open_admin_session(client, tokens, secret)
        headers = {"Authorization": f"Bearer {admin_token}"}
        assert client.get("/admin/stats", headers=headers).status_code == 200

        client.post("/auth/logout-all", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert client.get("/admin/stats", headers=headers).status_code == 401

    def test_shared_key_refused_once_rollout_flag_is_off(self, client):
        prev = settings.ADMIN_ALLOW_SHARED_KEY
        settings.ADMIN_ALLOW_SHARED_KEY = False
        try:
            assert client.get("/admin/stats", headers=_admin_headers()).status_code == 401
            # ...but the cron endpoints still take it as a service key.
            resp = client.post("/admin/retention/run", params={"dry_run": "true"}, headers=_admin_headers())
            assert resp.status_code == 200, resp.text
        finally:
            settings.ADMIN_ALLOW_SHARED_KEY = prev

    def test_auth_config_reflects_rollout_flag(self, client):
        assert client.get("/admin/auth-config").json()["shared_key_login"] is True
        prev = settings.ADMIN_ALLOW_SHARED_KEY
        settings.ADMIN_ALLOW_SHARED_KEY = False
        try:
            assert client.get("/admin/auth-config").json()["shared_key_login"] is False
        finally:
            settings.ADMIN_ALLOW_SHARED_KEY = prev
