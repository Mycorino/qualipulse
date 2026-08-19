"""Recontact invitations: workspace pool scoping, eligibility guardrails,
send flow (claim-then-send), derived funnel, and the opt-out loop."""

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, Participant
from app.models.panel import PanelProfile, StudyInvite
from app.models.project import Project
from app.services import panel_service as ps


def _project(db, company_id, name="Study", with_link=True, is_demo=False):
    project = Project(company_id=company_id, name=name, language="en", is_demo=is_demo)
    db.add(project)
    db.flush()
    link = None
    if with_link:
        link = InterviewLink(project_id=project.id, token=uuid.uuid4().hex, is_active=True)
        db.add(link)
    db.commit()
    return project, link


def _participant(db, project, link, email, status="completed"):
    p = Participant(
        link_id=link.id, project_id=project.id, email=email, status=status,
        display_name=email.split("@")[0],
    )
    db.add(p)
    db.commit()
    return p


def _profile(db, email, consent=True, lang=None, **kw):
    prof = PanelProfile(
        email=email, panel_consent=consent,
        consent_at=datetime.utcnow() if consent else None,
        preferred_language=lang, **kw,
    )
    db.add(prof)
    db.commit()
    return prof


@pytest.fixture
def setup(client, db_session, registered_company):
    company = (
        db_session.query(Company)
        .filter(Company.email == registered_company["email"])
        .first()
    )
    source, source_link = _project(db_session, company.id, "Source study")
    target, target_link = _project(db_session, company.id, "Target study")

    # Three past participants of the workspace; two consented panelists.
    _participant(db_session, source, source_link, "alice@example.com")
    _participant(db_session, source, source_link, "ben@example.com")
    _participant(db_session, source, source_link, "carol@example.com")
    alice = _profile(db_session, "alice@example.com", lang="fr", country="FR")
    ben = _profile(db_session, "ben@example.com", lang="de")
    _profile(db_session, "carol@example.com", consent=False)

    # A consented panelist who only ever participated in ANOTHER workspace's
    # study — must never surface in this workspace's pool.
    other_co = Company(name="Other", email="other@example.com", password_hash="x")
    db_session.add(other_co)
    db_session.flush()
    other_proj, other_link = _project(db_session, other_co.id, "Foreign study")
    _participant(db_session, other_proj, other_link, "dora@example.com")
    _profile(db_session, "dora@example.com")

    return {
        "company": company, "source": source, "target": target,
        "target_link": target_link, "alice": alice, "ben": ben,
    }


class TestPoolAndCandidates:
    def test_pool_is_workspace_scoped_and_consent_gated(self, client, auth_headers, setup):
        resp = client.get(f"/projects/{setup['target'].id}/invite-candidates", headers=auth_headers)
        assert resp.status_code == 200
        emails = {c["email"] for c in resp.json()["candidates"]}
        assert emails == {"alice@example.com", "ben@example.com"}

    def test_blocked_reasons(self, client, auth_headers, db_session, setup):
        # alice already participated in the target study
        _participant(db_session, setup["target"], setup["target_link"], "alice@example.com")
        # ben was invited by ANOTHER workspace an hour ago -> platform cooldown
        db_session.add(StudyInvite(
            project_id=setup["source"].id, company_id="someone-else",
            email="ben@example.com", sent_at=datetime.utcnow() - timedelta(hours=1),
        ))
        db_session.commit()
        resp = client.get(f"/projects/{setup['target'].id}/invite-candidates", headers=auth_headers)
        by_email = {c["email"]: c["blocked_reason"] for c in resp.json()["candidates"]}
        assert by_email["alice@example.com"] == "already_participated"
        assert by_email["ben@example.com"] == "cooldown"

    def test_old_invites_do_not_cooldown(self, client, auth_headers, db_session, setup):
        db_session.add(StudyInvite(
            project_id=setup["source"].id, company_id=setup["company"].id,
            email="ben@example.com", sent_at=datetime.utcnow() - timedelta(days=30),
        ))
        db_session.commit()
        resp = client.get(f"/projects/{setup['target'].id}/invite-candidates", headers=auth_headers)
        by_email = {c["email"]: c["blocked_reason"] for c in resp.json()["candidates"]}
        assert by_email["ben@example.com"] is None


class TestSend:
    @pytest.fixture
    def sent_mails(self, monkeypatch):
        calls = []

        def fake_send(**kwargs):
            calls.append(kwargs)
            return True

        from app.routers import panel_recontact
        monkeypatch.setattr(panel_recontact, "send_interview_invite", fake_send)
        return calls

    def test_send_records_and_emails(self, client, auth_headers, db_session, setup, sent_mails):
        resp = client.post(
            f"/projects/{setup['target'].id}/invites",
            json={"profile_ids": [setup["alice"].id, setup["ben"].id]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["sent"] == 2
        assert len(sent_mails) == 2
        # language follows the panelist's preference, not the project's
        langs = {m["to"]: m["lang"] for m in sent_mails}
        assert langs["alice@example.com"] == "fr"
        assert langs["ben@example.com"] == "de"
        # every mail carries an opt-out link
        assert all("/panel/optout?token=" in m["optout_url"] for m in sent_mails)
        assert db_session.query(StudyInvite).filter_by(project_id=setup["target"].id).count() == 2

    def test_resend_is_blocked(self, client, auth_headers, setup, sent_mails):
        first = client.post(
            f"/projects/{setup['target'].id}/invites",
            json={"profile_ids": [setup["alice"].id]}, headers=auth_headers,
        )
        assert first.json()["sent"] == 1
        second = client.post(
            f"/projects/{setup['target'].id}/invites",
            json={"profile_ids": [setup["alice"].id]}, headers=auth_headers,
        )
        assert second.json()["sent"] == 0
        assert second.json()["skipped"][0]["reason"] == "already_invited"
        assert len(sent_mails) == 1

    def test_send_failure_releases_claim(self, client, auth_headers, db_session, setup, monkeypatch):
        from app.routers import panel_recontact
        monkeypatch.setattr(panel_recontact, "send_interview_invite", lambda **kw: False)
        resp = client.post(
            f"/projects/{setup['target'].id}/invites",
            json={"profile_ids": [setup["alice"].id]}, headers=auth_headers,
        )
        assert resp.json()["sent"] == 0
        assert resp.json()["skipped"][0]["reason"] == "send_failed"
        # claim released -> retry can succeed later
        assert db_session.query(StudyInvite).count() == 0

    def test_requires_active_link(self, client, auth_headers, db_session, setup, sent_mails):
        no_link, _ = _project(db_session, setup["company"].id, "Linkless", with_link=False)
        resp = client.post(
            f"/projects/{no_link.id}/invites",
            json={"profile_ids": [setup["alice"].id]}, headers=auth_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "no_active_link"

    def test_daily_limit(self, client, auth_headers, setup, sent_mails, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "INVITE_DAILY_LIMIT", 1)
        resp = client.post(
            f"/projects/{setup['target'].id}/invites",
            json={"profile_ids": [setup["alice"].id, setup["ben"].id]},
            headers=auth_headers,
        )
        body = resp.json()
        assert body["sent"] == 1
        assert body["skipped"][0]["reason"] == "daily_limit"

    def test_non_consented_profile_is_skipped(self, client, auth_headers, db_session, setup, sent_mails):
        carol = (
            db_session.query(PanelProfile)
            .filter(PanelProfile.email == "carol@example.com")
            .first()
        )
        resp = client.post(
            f"/projects/{setup['target'].id}/invites",
            json={"profile_ids": [carol.id]}, headers=auth_headers,
        )
        assert resp.json()["sent"] == 0
        assert resp.json()["skipped"][0]["reason"] == "not_eligible"

    def test_demo_project_refuses(self, client, auth_headers, db_session, setup, sent_mails):
        demo, _ = _project(db_session, setup["company"].id, "[Demo]", is_demo=True)
        resp = client.post(
            f"/projects/{demo.id}/invites",
            json={"profile_ids": [setup["alice"].id]}, headers=auth_headers,
        )
        assert resp.status_code == 400


class TestFunnel:
    def test_funnel_is_derived_from_participants(self, client, auth_headers, db_session, setup, monkeypatch):
        from app.routers import panel_recontact
        monkeypatch.setattr(panel_recontact, "send_interview_invite", lambda **kw: True)
        client.post(
            f"/projects/{setup['target'].id}/invites",
            json={"profile_ids": [setup["alice"].id, setup["ben"].id]},
            headers=auth_headers,
        )
        # alice started, then completed; ben never clicked
        _participant(db_session, setup["target"], setup["target_link"],
                     "alice@example.com", status="completed")
        resp = client.get(f"/projects/{setup['target'].id}/invites", headers=auth_headers)
        body = resp.json()
        assert body["summary"] == {"invited": 2, "started": 1, "completed": 1}
        statuses = {r["email"]: r["status"] for r in body["invites"]}
        assert statuses["alice@example.com"] == "completed"
        assert statuses["ben@example.com"] == "sent"


class TestWorkspacePanel:
    def test_pool_page_payload(self, client, auth_headers, db_session, setup, monkeypatch):
        from app.routers import panel_recontact
        monkeypatch.setattr(panel_recontact, "send_interview_invite", lambda **kw: True)
        client.post(
            f"/projects/{setup['target'].id}/invites",
            json={"profile_ids": [setup["alice"].id]}, headers=auth_headers,
        )
        resp = client.get("/workspace/panel", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["stats"]["pool_size"] == 2
        assert body["stats"]["invited_30d"] == 1
        alice = next(p for p in body["profiles"] if p["email"] == "alice@example.com")
        assert alice["studies_participated"] == 1
        assert alice["interviews_completed"] == 1
        assert alice["invites_sent"] == 1
        assert alice["last_invited_at"] is not None
        ben = next(p for p in body["profiles"] if p["email"] == "ben@example.com")
        assert ben["invites_sent"] == 0


class TestOptOut:
    def test_optout_flips_consent_everywhere(self, client, db_session, setup):
        token = ps.create_optout_token("alice@example.com")
        resp = client.post("/panel/opt-out", json={"token": token})
        assert resp.status_code == 200
        profile = (
            db_session.query(PanelProfile)
            .filter(PanelProfile.email == "alice@example.com")
            .first()
        )
        assert profile.panel_consent is False
        rows = (
            db_session.query(Participant)
            .filter(Participant.email == "alice@example.com")
            .all()
        )
        assert rows and all(p.panel_consent is False for p in rows)
        # idempotent
        assert client.post("/panel/opt-out", json={"token": token}).status_code == 200

    def test_opted_out_leaves_the_pool(self, client, auth_headers, db_session, setup):
        token = ps.create_optout_token("alice@example.com")
        client.post("/panel/opt-out", json={"token": token})
        resp = client.get(f"/projects/{setup['target'].id}/invite-candidates", headers=auth_headers)
        emails = {c["email"] for c in resp.json()["candidates"]}
        assert "alice@example.com" not in emails

    def test_bad_token_400(self, client):
        assert client.post("/panel/opt-out", json={"token": "junk"}).status_code == 400


class TestInviteEmailTemplate:
    def test_optout_footer_and_language_fallback(self, monkeypatch):
        from app.services import email as email_svc
        captured = {}

        def fake_send(to, subject, body_html, **kw):
            captured["subject"] = subject
            captured["html"] = body_html
            return True

        monkeypatch.setattr(email_svc, "send_email", fake_send)
        ok = email_svc.send_interview_invite(
            to="x@example.com", project_name="P", interview_url="https://x/i/t",
            sender_name="S", lang="de", optout_url="https://x/panel/optout?token=abc",
        )
        assert ok
        assert "Einladung" in captured["subject"]
        assert "https://x/panel/optout?token=abc" in captured["html"]
        assert "Keine Einladungen mehr erhalten" in captured["html"]
