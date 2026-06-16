"""Participant onboarding redesign — magic-link verify recognises a returning
participant and the panel-profile upsert round-trips every demographic field
(including the new preferred_language).
"""
from datetime import datetime, timedelta

import pytest

from app.models.company import Company
from app.models.project import Project
from app.models.interview import InterviewLink
from app.models.panel import PanelProfile, ParticipantMagicToken


@pytest.fixture
def link(db_session):
    """A company + project + active interview link, committed to the test db."""
    company = Company(name="Acme", email="owner@acme.com", password_hash="x")
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
    """Insert a fresh, valid magic token for `email` against `link`."""
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


def test_verify_reports_incomplete_then_complete(client, db_session, link):
    email = "flyer@example.com"

    # First verify: no profile yet → not complete, no name.
    magic1 = _mint_magic(db_session, link, email)
    r1 = client.get(f"/interview/verify/{magic1}")
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["profile_complete"] is False
    assert body1["first_name"] is None
    session_token = body1["session_token"]

    # Save a full panel profile (the questionnaire submission).
    profile_payload = {
        "email": email,
        "session_token": session_token,
        "first_name": "Camille",
        "age_range": "35-44",
        "gender": "female",
        "country": "France",
        "education": "master",
        "employment_status": "full_time",
        "job_function": "product",
        "seniority": "senior",
        "industry": "technology",
        "company_size": "51-200",
        "preferred_language": "fr",
        "panel_consent": True,
        "tag_ids": [],
    }
    r2 = client.post(f"/interview/{link.token}/panel-profile", json=profile_payload)
    assert r2.status_code == 200, r2.text
    assert r2.json()["saved"] is True

    # Every field (incl. the new preferred_language) round-trips to the DB.
    saved = db_session.query(PanelProfile).filter(PanelProfile.email == email).first()
    assert saved is not None
    assert saved.first_name == "Camille"
    assert saved.country == "France"
    assert saved.education == "master"
    assert saved.employment_status == "full_time"
    assert saved.preferred_language == "fr"
    assert saved.panel_consent is True

    # Second verify (returning participant): now recognised as complete, with
    # the stored name + language echoed back for the frontend to skip ahead.
    magic2 = _mint_magic(db_session, link, email)
    r3 = client.get(f"/interview/verify/{magic2}")
    assert r3.status_code == 200, r3.text
    body3 = r3.json()
    assert body3["profile_complete"] is True
    assert body3["first_name"] == "Camille"
    assert body3["preferred_language"] == "fr"


def test_panel_profile_rejects_mismatched_session(client, db_session, link):
    """The session token must match the email — otherwise anyone with the public
    link could overwrite someone else's profile."""
    magic = _mint_magic(db_session, link, "real@example.com")
    session_token = client.get(f"/interview/verify/{magic}").json()["session_token"]

    r = client.post(
        f"/interview/{link.token}/panel-profile",
        json={
            "email": "attacker@example.com",  # different from the session email
            "session_token": session_token,
            "first_name": "Mallory",
            "panel_consent": False,
            "tag_ids": [],
        },
    )
    assert r.status_code == 401
