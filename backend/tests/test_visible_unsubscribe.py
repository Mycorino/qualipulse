"""Bulk mail must carry a visible unsubscribe link, not just the header.

Gmail only requires the List-Unsubscribe header, but the native button it
renders is not shown by every client. A recipient who cannot find a way out
reaches for "report spam" instead, which is the worst signal a sending
domain can collect.
"""
import re

import pytest

from app.models.email_suppression import EmailSuppression
from app.services import email as email_mod
from app.services.email import send_interview_invite, send_verification_email


@pytest.fixture
def sent(monkeypatch):
    """Capture what the transport was handed, instead of sending."""
    captured = {}

    def _capture(to, subject, body_html, body_text=None, headers=None):
        captured.update(
            to=to,
            subject=subject,
            html=body_html,
            text=body_text,
            headers=headers or {},
        )
        return True

    monkeypatch.setattr(email_mod, "_send_console", _capture)
    return captured


def test_bulk_mail_carries_a_visible_link(sent, db_session):
    send_interview_invite(
        to="invitee@example.com",
        project_name="Grocery habits",
        interview_url="https://app.qualipulse.com/i/tok",
        sender_name="Acme Research",
        lang="en",
        db=db_session,
    )
    assert "Unsubscribe from research invitations" in sent["html"]
    assert "/api/email/unsubscribe?token=" in sent["html"]
    # The header stays too: the two are complementary, not alternatives.
    assert "List-Unsubscribe-Post" in sent["headers"]


def test_transactional_mail_has_no_link_and_no_leftover_marker(sent, db_session):
    send_verification_email(
        to="user@example.com",
        name="Marie",
        verify_url="https://app.qualipulse.com/verify?token=x",
        lang="en",
    )
    assert "email/unsubscribe" not in sent["html"]
    assert "Unsubscribe" not in sent["html"]
    # The slot must be consumed, never shipped as a raw comment.
    assert "QP_UNSUBSCRIBE_SLOT" not in sent["html"]


def test_link_is_localised_to_the_interview_language(sent, db_session):
    """Invites go out in the project's language, including the four beyond en/fr."""
    for lang, expected in [
        ("fr", "Se désabonner des invitations"),
        ("de", "Keine Studieneinladungen mehr erhalten"),
        ("pt", "Cancelar a subscrição de convites"),
    ]:
        send_interview_invite(
            to=f"{lang}@example.com",
            project_name="Etude",
            interview_url="https://app.qualipulse.com/i/tok",
            sender_name="Acme",
            lang=lang,
            db=db_session,
        )
        assert expected in sent["html"], lang


def test_plain_text_alternative_carries_the_url(sent, db_session):
    """Text-only clients must still get a working way out.

    The plain-text part is derived from the final HTML inside
    ``_send_sendgrid``, so this asserts on that derivation rather than on
    the console transport (which is handed ``None`` and never builds one).
    """
    send_interview_invite(
        to="text@example.com",
        project_name="Study",
        interview_url="https://app.qualipulse.com/i/tok",
        sender_name="Acme",
        lang="en",
        db=db_session,
    )
    text = email_mod._html_to_text(sent["html"])
    assert "email/unsubscribe?token=" in text
    assert "Unsubscribe from research invitations" in text


def test_the_emailed_link_actually_unsubscribes(sent, client, db_session):
    """End to end: pull the real token out of the sent body and use it."""
    send_interview_invite(
        to="realuser@example.com",
        project_name="Study",
        interview_url="https://app.qualipulse.com/i/tok",
        sender_name="Acme",
        lang="en",
        db=db_session,
    )
    token = re.search(r"email/unsubscribe\?token=([^\"'&]+)", sent["html"]).group(1)

    assert client.post(f"/email/unsubscribe?token={token}").status_code == 200
    row = (
        db_session.query(EmailSuppression)
        .filter_by(email="realuser@example.com")
        .first()
    )
    assert row is not None

    # And the next bulk send to them is actually dropped.
    sent.clear()
    ok = send_interview_invite(
        to="realuser@example.com",
        project_name="Study",
        interview_url="https://app.qualipulse.com/i/tok2",
        sender_name="Acme",
        lang="en",
        db=db_session,
    )
    assert ok is False
    assert sent == {}
