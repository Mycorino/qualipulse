"""Follow-up capture: email normalisation, panel-consent denormalisation onto
Participant, and researcher-side exposure (participant list + CSV export)."""
from datetime import datetime, timedelta

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, Participant
from app.models.panel import PanelProfile, ParticipantMagicToken
from app.models.project import Project


@pytest.fixture
def link(db_session):
    """A company + project + active interview link, committed to the test db."""
    company = Company(name="Acme", email="owner@acme.com", password_hash="x", email_verified=True)
    db_session.add(company)
    db_session.flush()
    project = Project(company_id=company.id, name="Long-haul flights", language="en")
    db_session.add(project)
    db_session.flush()
    link = InterviewLink(project_id=project.id, token="link-token-abc", is_active=True)
    db_session.add(link)
    db_session.commit()
    return link


def _mint_magic(db_session, link, email="flyer@example.com"):
    import uuid
    tok = ParticipantMagicToken(
        email=email,
        token=f"magic-{uuid.uuid4().hex}",
        interview_link_token=link.token,
        used=False,
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db_session.add(tok)
    db_session.commit()
    return tok.token


def _session_token(client, db_session, link, email="flyer@example.com"):
    magic = _mint_magic(db_session, link, email)
    r = client.get(f"/interview/verify/{magic}")
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _add_participant(db_session, link, email="flyer@example.com", status="completed", panel_consent=None):
    p = Participant(
        link_id=link.id,
        project_id=link.project_id,
        display_name="Camille",
        email=email,
        email_verified=True,
        status=status,
        panel_consent=panel_consent,
    )
    db_session.add(p)
    db_session.commit()
    return p


class TestPanelConsentSync:
    def test_panel_profile_normalises_email_and_syncs_consent(self, client, db_session, link):
        """Mixed-case email in the panel-profile payload lands lowercased on
        PanelProfile, and existing participant rows on the link get the
        consent flag (the post-interview re-prompt path)."""
        participant = _add_participant(db_session, link, email="flyer@example.com")
        session_token = _session_token(client, db_session, link)

        r = client.post(
            f"/interview/{link.token}/panel-profile",
            json={
                "email": "FLYER@Example.com",
                "session_token": session_token,
                "panel_consent": True,
                "tag_ids": [],
            },
        )
        assert r.status_code == 200, r.text

        profile = db_session.query(PanelProfile).first()
        assert profile is not None
        assert profile.email == "flyer@example.com"
        assert profile.panel_consent is True

        db_session.refresh(participant)
        assert participant.panel_consent is True

    def test_panel_profile_without_consent_marks_participant_declined(self, client, db_session, link):
        participant = _add_participant(db_session, link)
        session_token = _session_token(client, db_session, link)

        r = client.post(
            f"/interview/{link.token}/panel-profile",
            json={
                "email": "flyer@example.com",
                "session_token": session_token,
                "panel_consent": False,
                "tag_ids": [],
            },
        )
        assert r.status_code == 200, r.text
        db_session.refresh(participant)
        assert participant.panel_consent is False

    def test_sync_helper_matches_email_case_insensitively(self, db_session, link):
        from app.routers.interview import _sync_panel_consent_to_participant

        db_session.add(PanelProfile(email="flyer@example.com", panel_consent=True))
        db_session.commit()
        # Legacy participant row stored with mixed case (pre-normalisation).
        participant = _add_participant(db_session, link, email="Flyer@Example.com")

        _sync_panel_consent_to_participant(participant, db_session)
        db_session.refresh(participant)
        assert participant.panel_consent is True


class TestResearcherVisibility:
    def _project_and_link(self, client, db_session, auth_headers):
        resp = client.post(
            "/projects/",
            json={
                "name": "Follow-up study",
                "interview_duration_minutes": 20,
                "questions": [
                    {
                        "section_index": 0,
                        "section_title": "Intro",
                        "question_index": 0,
                        "main_question": "Tell me about your day?",
                    },
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        project_id = resp.json()["id"]
        link = InterviewLink(project_id=project_id, token="research-link-1", is_active=True)
        db_session.add(link)
        db_session.commit()
        return project_id, link

    def test_participant_list_exposes_email_and_consent(self, client, db_session, auth_headers):
        project_id, link = self._project_and_link(client, db_session, auth_headers)
        _add_participant(db_session, link, email="alice@example.com", panel_consent=True)

        r = client.get(f"/projects/{project_id}/participants", headers=auth_headers)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["email"] == "alice@example.com"
        assert rows[0]["panel_consent"] is True

    def test_csv_export_includes_email_and_consent_columns(self, client, db_session, auth_headers, registered_company):
        project_id, link = self._project_and_link(client, db_session, auth_headers)
        _add_participant(db_session, link, email="alice@example.com", panel_consent=True)

        # CSV export is feature-gated — lift the company to a tier that has it.
        company = db_session.query(Company).filter(
            Company.email == registered_company["email"]
        ).first()
        company.subscription_tier = "enterprise"
        db_session.commit()

        r = client.get(f"/projects/{project_id}/export", headers=auth_headers)
        assert r.status_code == 200, r.text
        lines = r.text.splitlines()
        header = lines[0].split(",")
        assert "email" in header
        assert "follow_up_consent" in header
        row = lines[1].split(",")
        assert row[header.index("email")] == "alice@example.com"
        assert row[header.index("follow_up_consent")] == "yes"
