"""Suppression list: blocking rules, SendGrid webhook, one-click unsubscribe."""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.config import settings
from app.models.email_suppression import (
    REASON_BOUNCE,
    REASON_MANUAL,
    REASON_SPAM_REPORT,
    REASON_UNSUBSCRIBE,
    EmailSuppression,
)
from app.services.email import _unsubscribe_headers, send_email
from app.services.email_suppression import (
    is_suppressed,
    make_unsubscribe_token,
    read_unsubscribe_token,
    suppress,
)


# ── Blocking rules ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "reason,blocks_transactional",
    [
        (REASON_BOUNCE, True),      # dead mailbox — nothing is deliverable
        (REASON_MANUAL, True),      # support escalation — honour fully
        (REASON_UNSUBSCRIBE, False),  # opted out of bulk, still needs resets
        (REASON_SPAM_REPORT, False),  # ditto: never lock someone out of their account
    ],
)
def test_reason_decides_what_is_blocked(db_session, reason, blocks_transactional):
    suppress(db_session, "person@example.com", reason)
    db_session.commit()

    # Marketing is blocked by every reason, without exception.
    assert is_suppressed(db_session, "person@example.com", "marketing") is True
    assert (
        is_suppressed(db_session, "person@example.com", "transactional")
        is blocks_transactional
    )


def test_lookup_is_case_and_whitespace_insensitive(db_session):
    suppress(db_session, "Person@Example.com", REASON_BOUNCE)
    db_session.commit()
    assert is_suppressed(db_session, "  PERSON@EXAMPLE.COM  ", "transactional") is True


def test_unknown_address_is_not_suppressed(db_session):
    assert is_suppressed(db_session, "nobody@example.com", "marketing") is False


def test_suppress_is_idempotent_and_first_reason_wins(db_session):
    suppress(db_session, "dup@example.com", REASON_BOUNCE)
    suppress(db_session, "dup@example.com", REASON_UNSUBSCRIBE)
    db_session.commit()

    rows = db_session.query(EmailSuppression).filter_by(email="dup@example.com").all()
    assert len(rows) == 1
    # A later unsubscribe must not downgrade an earlier hard bounce, or
    # transactional mail would resume to a dead mailbox.
    assert rows[0].reason == REASON_BOUNCE


def test_unknown_reason_is_rejected(db_session):
    assert suppress(db_session, "x@example.com", "not-a-reason") is None
    assert db_session.query(EmailSuppression).count() == 0


# ── send_email integration ─────────────────────────────────────────────────


def test_send_email_skips_suppressed_marketing_but_allows_transactional(db_session):
    suppress(db_session, "opted@example.com", REASON_UNSUBSCRIBE)
    db_session.commit()

    assert (
        send_email(
            to="opted@example.com",
            subject="Invite",
            body_html="<p>hi</p>",
            email_type="marketing",
            db=db_session,
        )
        is False
    )
    assert (
        send_email(
            to="opted@example.com",
            subject="Password reset",
            body_html="<p>hi</p>",
            email_type="transactional",
            db=db_session,
        )
        is True
    )


def test_send_email_skips_bounced_address_entirely(db_session):
    suppress(db_session, "dead@example.com", REASON_BOUNCE)
    db_session.commit()
    assert (
        send_email(
            to="dead@example.com",
            subject="Anything",
            body_html="<p>hi</p>",
            email_type="transactional",
            db=db_session,
        )
        is False
    )


# ── List-Unsubscribe headers ───────────────────────────────────────────────


def test_marketing_advertises_one_click_transactional_does_not():
    marketing = _unsubscribe_headers("marketing", "someone@example.com")
    assert marketing["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    # HTTPS target must come first: providers prefer it over the mailto.
    assert marketing["List-Unsubscribe"].startswith("<http")
    assert "/api/email/unsubscribe?token=" in marketing["List-Unsubscribe"]
    assert "mailto:" in marketing["List-Unsubscribe"]

    assert _unsubscribe_headers("transactional", "someone@example.com") == {}


def test_unsubscribe_token_round_trip():
    token = make_unsubscribe_token("Round@Trip.com")
    assert read_unsubscribe_token(token) == "round@trip.com"


def test_garbage_and_foreign_tokens_are_rejected():
    assert read_unsubscribe_token("not-a-jwt") is None
    from jose import jwt

    # Correctly signed, but minted for a different purpose — must not unsubscribe.
    other = jwt.encode(
        {"sub": "a@b.com", "purpose": "password_reset"},
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    assert read_unsubscribe_token(other) is None


# ── Unsubscribe endpoints ──────────────────────────────────────────────────


def test_one_click_post_unsubscribes(client, db_session):
    token = make_unsubscribe_token("bulk@example.com")
    resp = client.post(f"/email/unsubscribe?token={token}")
    assert resp.status_code == 200

    row = db_session.query(EmailSuppression).filter_by(email="bulk@example.com").first()
    assert row is not None and row.reason == REASON_UNSUBSCRIBE


def test_one_click_post_rejects_bad_token(client, db_session):
    assert client.post("/email/unsubscribe?token=garbage").status_code == 400
    assert db_session.query(EmailSuppression).count() == 0


def test_get_unsubscribe_renders_confirmation(client):
    token = make_unsubscribe_token("browser@example.com")
    resp = client.get(f"/email/unsubscribe?token={token}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # Reassures the reader that account mail still works.
    assert "security emails are unaffected" in resp.text


def test_unsubscribe_withdraws_panel_consent(client, db_session):
    """Suppression alone would leave them in the recruit pool as a phantom."""
    from app.models.panel import PanelProfile

    db_session.add(PanelProfile(email="panelist@example.com", panel_consent=True))
    db_session.commit()

    token = make_unsubscribe_token("panelist@example.com")
    assert client.post(f"/email/unsubscribe?token={token}").status_code == 200

    profile = (
        db_session.query(PanelProfile).filter_by(email="panelist@example.com").first()
    )
    db_session.refresh(profile)
    assert profile.panel_consent is False


# ── SendGrid event webhook ─────────────────────────────────────────────────


def _post_events(client, events):
    return client.post("/email/events", json=events)


def test_hard_bounce_suppresses(client, db_session):
    _post_events(client, [{"email": "hard@example.com", "event": "bounce", "type": "bounce"}])
    row = db_session.query(EmailSuppression).filter_by(email="hard@example.com").first()
    assert row is not None and row.reason == REASON_BOUNCE


def test_blocked_bounce_does_not_suppress(client, db_session):
    """``blocked`` is a transient deferral — suppressing would be permanent."""
    _post_events(
        client, [{"email": "soft@example.com", "event": "bounce", "type": "blocked"}]
    )
    assert db_session.query(EmailSuppression).filter_by(email="soft@example.com").first() is None


def test_spamreport_and_unsubscribe_events_suppress(client, db_session):
    _post_events(
        client,
        [
            {"email": "complained@example.com", "event": "spamreport"},
            {"email": "gone@example.com", "event": "unsubscribe"},
            {"email": "dropped@example.com", "event": "dropped"},
        ],
    )
    reasons = {
        r.email: r.reason for r in db_session.query(EmailSuppression).all()
    }
    assert reasons["complained@example.com"] == REASON_SPAM_REPORT
    assert reasons["gone@example.com"] == REASON_UNSUBSCRIBE
    assert reasons["dropped@example.com"] == REASON_BOUNCE


def test_delivered_and_open_events_are_ignored(client, db_session):
    _post_events(
        client,
        [
            {"email": "fine@example.com", "event": "delivered"},
            {"email": "fine@example.com", "event": "open"},
        ],
    )
    assert db_session.query(EmailSuppression).count() == 0


def test_malformed_batch_does_not_error(client):
    assert client.post("/email/events", content=b"not json").status_code == 200


def test_unsigned_payload_rejected_when_key_configured(client, db_session, monkeypatch):
    """With a key set, an unsigned POST is a forgery attempt, not a dev call."""
    monkeypatch.setattr(settings, "SENDGRID_WEBHOOK_PUBLIC_KEY", "Zm9v", raising=False)
    resp = _post_events(client, [{"email": "x@example.com", "event": "bounce", "type": "bounce"}])
    assert resp.status_code == 403
    assert db_session.query(EmailSuppression).count() == 0


def test_valid_ecdsa_signature_is_accepted(client, db_session, monkeypatch):
    """End-to-end proof the real signature path works, not just the dev bypass."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_der = private_key.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )
    monkeypatch.setattr(
        settings,
        "SENDGRID_WEBHOOK_PUBLIC_KEY",
        base64.b64encode(public_der).decode(),
        raising=False,
    )

    payload = json.dumps(
        [{"email": "signed@example.com", "event": "bounce", "type": "bounce"}]
    ).encode()
    timestamp = str(int(time.time()))
    from cryptography.hazmat.primitives import hashes

    signature = private_key.sign(
        timestamp.encode() + payload, ec.ECDSA(hashes.SHA256())
    )

    resp = client.post(
        "/email/events",
        content=payload,
        headers={
            "X-Twilio-Email-Event-Webhook-Signature": base64.b64encode(signature).decode(),
            "X-Twilio-Email-Event-Webhook-Timestamp": timestamp,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    assert (
        db_session.query(EmailSuppression).filter_by(email="signed@example.com").first()
        is not None
    )


def test_stale_signature_is_rejected(client, db_session, monkeypatch):
    """A captured-and-replayed batch must not be accepted forever."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_der = private_key.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )
    monkeypatch.setattr(
        settings,
        "SENDGRID_WEBHOOK_PUBLIC_KEY",
        base64.b64encode(public_der).decode(),
        raising=False,
    )

    payload = json.dumps([{"email": "old@example.com", "event": "bounce", "type": "bounce"}]).encode()
    timestamp = str(int(time.time()) - 3600)  # an hour stale
    from cryptography.hazmat.primitives import hashes

    signature = private_key.sign(timestamp.encode() + payload, ec.ECDSA(hashes.SHA256()))

    resp = client.post(
        "/email/events",
        content=payload,
        headers={
            "X-Twilio-Email-Event-Webhook-Signature": base64.b64encode(signature).decode(),
            "X-Twilio-Email-Event-Webhook-Timestamp": timestamp,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 403
    assert db_session.query(EmailSuppression).count() == 0
