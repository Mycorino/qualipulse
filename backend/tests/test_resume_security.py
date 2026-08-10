"""Resume-by-email must require proof of email possession (magic-link JWT)."""

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.routers.interview import _create_session_token

EMAIL = "jane@example.com"
TOKEN = "tok-resume-sec"


def _seed(db):
    company = Company(name="Acme", email="o@acme.com", password_hash="x", email_verified=True)
    db.add(company)
    db.flush()
    project = Project(company_id=company.id, name="Study", language="en")
    db.add(project)
    db.flush()
    link = InterviewLink(project_id=project.id, token=TOKEN, is_active=True)
    db.add(link)
    db.flush()
    participant = Participant(
        link_id=link.id, project_id=project.id, status="in_progress", email=EMAIL
    )
    db.add(participant)
    db.flush()
    db.add(
        InterviewTurn(
            participant_id=participant.id,
            turn_index=0,
            question_index=0,
            question_text="Q1?",
        )
    )
    db.commit()
    return participant


def test_resume_without_token_is_rejected(client, db_session):
    _seed(db_session)
    resp = client.post(f"/interview/{TOKEN}/resume", json={"email": EMAIL})
    assert resp.status_code == 401
    assert "participant_id" not in (resp.json().get("detail") or "")


def test_resume_with_wrong_email_token_is_rejected(client, db_session):
    _seed(db_session)
    stolen = _create_session_token("attacker@evil.com", TOKEN)
    resp = client.post(
        f"/interview/{TOKEN}/resume",
        json={"email": EMAIL, "session_token": stolen},
    )
    assert resp.status_code == 401


def test_resume_with_token_for_other_link_is_rejected(client, db_session):
    _seed(db_session)
    other_link = _create_session_token(EMAIL, "some-other-link")
    resp = client.post(
        f"/interview/{TOKEN}/resume",
        json={"email": EMAIL, "session_token": other_link},
    )
    assert resp.status_code == 401


def test_resume_with_valid_token_returns_participant(client, db_session):
    participant = _seed(db_session)
    good = _create_session_token(EMAIL, TOKEN)
    resp = client.post(
        f"/interview/{TOKEN}/resume",
        json={"email": EMAIL, "session_token": good},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["participant_id"] == participant.id


def test_resume_email_match_is_case_insensitive(client, db_session):
    _seed(db_session)
    good = _create_session_token(EMAIL.upper(), TOKEN)
    resp = client.post(
        f"/interview/{TOKEN}/resume",
        json={"email": EMAIL, "session_token": good},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is True
