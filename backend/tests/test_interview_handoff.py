"""Continue-on-another-device handoff.

A participant whose mic is failing can mint a short-lived signed token on
their current device (shown as a QR code / copyable link) and claim the
in-progress interview from another device. The claim adopts the participant
session; the new device then runs its own mic test before recording.
"""

import uuid

from jose import jwt

from app.config import settings
from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.routers.interview import _create_handoff_token


def _seed(db, token="tok-handoff", *, email=None, status="in_progress", turns=2):
    company = Company(
        name="Acme", email=f"{token}@acme.com", password_hash="x", email_verified=True
    )
    db.add(company)
    db.flush()
    project = Project(
        company_id=company.id, name="Study", language="en", interview_duration_minutes=20
    )
    db.add(project)
    db.flush()
    link = InterviewLink(project_id=project.id, token=token, is_active=True)
    db.add(link)
    db.flush()
    participant = Participant(
        link_id=link.id, project_id=project.id, status=status, email=email
    )
    db.add(participant)
    db.flush()
    for i in range(turns):
        db.add(
            InterviewTurn(
                participant_id=participant.id,
                turn_index=i,
                question_index=i,
                question_text=f"Question {i}?",
                response_transcript=f"answer {i}" if i < turns - 1 else None,
            )
        )
    db.commit()
    return link, participant


class TestCreateHandoff:
    def test_mints_a_token_for_an_in_progress_interview(self, client, db_session):
        link, participant = _seed(db_session, "tok-mint")

        res = client.post(f"/interview/{link.token}/{participant.id}/handoff")

        assert res.status_code == 200
        body = res.json()
        assert body["expires_in_seconds"] > 0
        payload = jwt.decode(
            body["handoff_token"], settings.SECRET_KEY, algorithms=["HS256"]
        )
        assert payload["type"] == "participant_handoff"
        assert payload["pid"] == participant.id
        assert payload["link_token"] == link.token

    def test_completed_interview_is_refused(self, client, db_session):
        link, participant = _seed(db_session, "tok-done", status="completed")

        res = client.post(f"/interview/{link.token}/{participant.id}/handoff")

        assert res.status_code == 400

    def test_unknown_participant_404s(self, client, db_session):
        link, _ = _seed(db_session, "tok-nopart")

        res = client.post(f"/interview/{link.token}/{uuid.uuid4().hex}/handoff")

        assert res.status_code == 404


class TestClaimHandoff:
    def test_round_trip_returns_the_interview_state(self, client, db_session):
        link, participant = _seed(db_session, "tok-claim", email="p@example.com")
        minted = client.post(f"/interview/{link.token}/{participant.id}/handoff").json()

        res = client.post(
            f"/interview/{link.token}/handoff/claim",
            json={"handoff_token": minted["handoff_token"]},
        )

        assert res.status_code == 200
        body = res.json()
        assert body["participant_id"] == participant.id
        assert body["last_question"] == "Question 1?"
        assert body["turn_count"] == 2
        assert body["question_index"] == 1
        assert body["email"] == "p@example.com"
        # A session token is minted so email-based flows keep working.
        session = jwt.decode(
            body["session_token"], settings.SECRET_KEY, algorithms=["HS256"]
        )
        assert session["type"] == "participant_session"
        assert session["email"] == "p@example.com"

    def test_participant_without_email_gets_no_session_token(self, client, db_session):
        link, participant = _seed(db_session, "tok-anon", email=None)
        minted = client.post(f"/interview/{link.token}/{participant.id}/handoff").json()

        res = client.post(
            f"/interview/{link.token}/handoff/claim",
            json={"handoff_token": minted["handoff_token"]},
        )

        assert res.status_code == 200
        assert res.json()["session_token"] is None

    def test_garbage_token_is_rejected(self, client, db_session):
        link, _ = _seed(db_session, "tok-garbage")

        res = client.post(
            f"/interview/{link.token}/handoff/claim",
            json={"handoff_token": "not-a-jwt"},
        )

        assert res.status_code == 400
        assert res.json()["detail"]["code"] == "handoff_invalid"

    def test_token_is_bound_to_its_link(self, client, db_session):
        """A handoff minted for one study must not open another study's
        interview, even when the participant id happens to be known."""
        link_a, participant_a = _seed(db_session, "tok-link-a")
        _seed(db_session, "tok-link-b")
        token_for_a = _create_handoff_token(participant_a.id, link_a.token)

        res = client.post(
            "/interview/tok-link-b/handoff/claim",
            json={"handoff_token": token_for_a},
        )

        assert res.status_code == 400
        assert res.json()["detail"]["code"] == "handoff_invalid"

    def test_session_token_type_is_rejected(self, client, db_session):
        """A participant_session JWT (same signing key) must not pass as a
        handoff token."""
        from app.routers.interview import _create_session_token

        link, participant = _seed(db_session, "tok-typeconf", email="p@example.com")
        session_jwt = _create_session_token("p@example.com", link.token)

        res = client.post(
            f"/interview/{link.token}/handoff/claim",
            json={"handoff_token": session_jwt},
        )

        assert res.status_code == 400

    def test_completed_interview_cannot_be_claimed(self, client, db_session):
        link, participant = _seed(db_session, "tok-claimdone")
        minted = client.post(f"/interview/{link.token}/{participant.id}/handoff").json()
        participant.status = "completed"
        db_session.commit()

        res = client.post(
            f"/interview/{link.token}/handoff/claim",
            json={"handoff_token": minted["handoff_token"]},
        )

        assert res.status_code == 400
