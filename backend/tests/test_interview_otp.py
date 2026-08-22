"""Email OTP for participant verification.

The code exists because tapping the emailed link opens the study in the mail
app's in-app browser, where MediaRecorder is frequently unavailable and the
tab's sessionStorage is gone. For a voice interview that ends the session,
so the code (which keeps the participant where they are) is the primary
route and the link is the fallback, not the other way round.
"""

from datetime import datetime, timedelta

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink
from app.models.panel import ParticipantMagicToken
from app.models.project import Project
from app.services.verification import (
    MAX_CODE_ATTEMPTS,
    CodeResult,
    mint_magic_credentials,
    verify_code,
    verify_magic_token,
)


def _seed(db, token="tok-otp"):
    company = Company(name="Acme", email=f"{token}@acme.com", password_hash="x", email_verified=True)
    db.add(company)
    db.flush()
    project = Project(company_id=company.id, name="Study", language="en")
    db.add(project)
    db.flush()
    link = InterviewLink(project_id=project.id, token=token, is_active=True)
    db.add(link)
    db.commit()
    return link


class TestCodeVerification:
    def test_correct_code_returns_the_record(self, db_session):
        link = _seed(db_session, "tok-ok")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)

        result, record = verify_code(db_session, "a@example.com", link.token, code)

        assert result == CodeResult.OK
        assert record.email == "a@example.com"

    def test_code_is_six_digits_and_zero_padded(self, db_session):
        link = _seed(db_session, "tok-digits")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)
        assert len(code) == 6
        assert code.isdigit()

    def test_wrong_code_is_rejected_and_counted(self, db_session):
        link = _seed(db_session, "tok-wrong")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)
        wrong = "000000" if code != "000000" else "111111"

        result, record = verify_code(db_session, "a@example.com", link.token, wrong)

        assert result == CodeResult.INVALID
        assert record is None
        stored = db_session.query(ParticipantMagicToken).first()
        assert stored.code_attempts == 1

    def test_brute_force_is_capped(self, db_session):
        """Six digits is a million combinations: the per-IP rate limit alone
        would not protect it."""
        link = _seed(db_session, "tok-brute")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)
        wrong = "000000" if code != "000000" else "111111"

        for _ in range(MAX_CODE_ATTEMPTS):
            verify_code(db_session, "a@example.com", link.token, wrong)

        # Even the CORRECT code is dead once the cap is hit.
        result, record = verify_code(db_session, "a@example.com", link.token, code)
        assert result == CodeResult.TOO_MANY_ATTEMPTS
        assert record is None

    def test_code_is_single_use_like_the_link(self, db_session):
        link = _seed(db_session, "tok-single")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)

        assert verify_code(db_session, "a@example.com", link.token, code)[0] == CodeResult.OK
        assert verify_code(db_session, "a@example.com", link.token, code)[0] == CodeResult.EXPIRED

    def test_reusable_invite_code_survives_reuse(self, db_session):
        link = _seed(db_session, "tok-reuse")
        _, code = mint_magic_credentials(
            db_session, "a@example.com", link.token, reusable=True
        )

        assert verify_code(db_session, "a@example.com", link.token, code)[0] == CodeResult.OK
        assert verify_code(db_session, "a@example.com", link.token, code)[0] == CodeResult.OK

    def test_expired_code_is_rejected(self, db_session):
        link = _seed(db_session, "tok-exp")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)
        rec = db_session.query(ParticipantMagicToken).first()
        rec.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db_session.commit()

        assert verify_code(db_session, "a@example.com", link.token, code)[0] == CodeResult.EXPIRED

    def test_code_is_scoped_to_its_own_link(self, db_session):
        """A code for study A must not unlock study B."""
        link_a = _seed(db_session, "tok-a")
        link_b = _seed(db_session, "tok-b")
        _, code = mint_magic_credentials(db_session, "a@example.com", link_a.token)

        assert verify_code(db_session, "a@example.com", link_b.token, code)[0] == CodeResult.EXPIRED

    def test_code_is_scoped_to_its_own_email(self, db_session):
        link = _seed(db_session, "tok-email")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)

        assert verify_code(db_session, "b@example.com", link.token, code)[0] == CodeResult.EXPIRED

    def test_resend_invalidates_the_previous_code(self, db_session):
        """Only the newest live code works, so a resend is unambiguous."""
        link = _seed(db_session, "tok-resend")
        _, first = mint_magic_credentials(db_session, "a@example.com", link.token)
        _, second = mint_magic_credentials(db_session, "a@example.com", link.token)
        assert first != second

        assert verify_code(db_session, "a@example.com", link.token, first)[0] == CodeResult.INVALID
        assert verify_code(db_session, "a@example.com", link.token, second)[0] == CodeResult.OK

    def test_whitespace_and_separators_are_tolerated(self, db_session):
        """People paste '123 456' off a phone screen."""
        link = _seed(db_session, "tok-space")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)
        spaced = f" {code[:3]} {code[3:]} "

        assert verify_code(db_session, "a@example.com", link.token, spaced)[0] == CodeResult.OK

    def test_code_spent_by_the_link_route_cannot_be_replayed(self, db_session):
        link = _seed(db_session, "tok-mixed")
        token, code = mint_magic_credentials(db_session, "a@example.com", link.token)

        assert verify_magic_token(db_session, token) is not None
        assert verify_code(db_session, "a@example.com", link.token, code)[0] == CodeResult.EXPIRED


class TestCodeEndpoint:
    def test_endpoint_returns_a_session_token(self, client, db_session):
        link = _seed(db_session, "tok-ep")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)

        r = client.post(
            f"/interview/{link.token}/verify-code",
            json={"email": "a@example.com", "code": code},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["email"] == "a@example.com"
        assert body["session_token"]
        assert body["link_token"] == link.token

    def test_endpoint_rejects_a_wrong_code(self, client, db_session):
        link = _seed(db_session, "tok-ep-bad")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)
        wrong = "000000" if code != "000000" else "111111"

        r = client.post(
            f"/interview/{link.token}/verify-code",
            json={"email": "a@example.com", "code": wrong},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "code_invalid"

    def test_endpoint_reports_lockout_distinctly(self, client, db_session):
        """The participant needs to be told to request a NEW code, not to
        keep guessing at one that can no longer work."""
        link = _seed(db_session, "tok-ep-lock")
        _, code = mint_magic_credentials(db_session, "a@example.com", link.token)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(MAX_CODE_ATTEMPTS):
            client.post(
                f"/interview/{link.token}/verify-code",
                json={"email": "a@example.com", "code": wrong},
            )

        r = client.post(
            f"/interview/{link.token}/verify-code",
            json={"email": "a@example.com", "code": code},
        )
        assert r.status_code == 429
        assert r.json()["detail"]["code"] == "too_many_attempts"


class TestEmailCarriesBoth:
    def test_email_contains_the_code_and_the_link(self, db_session, monkeypatch):
        sent = {}

        from app.services import email as email_svc

        def fake_send(to, subject, body_html, **kw):
            sent["subject"] = subject
            sent["html"] = body_html
            return True

        monkeypatch.setattr(email_svc, "send_email", fake_send)
        email_svc.send_interview_magic_link(
            email="a@example.com",
            magic_url="https://app.example.com/interview/verify/abc?lang=en",
            expiry_minutes=30,
            lang="en",
            code="123456",
        )

        assert "123456" in sent["html"]
        assert "/interview/verify/abc" in sent["html"]
        # The code is in the subject so it is readable from the notification.
        assert "123456" in sent["subject"]
