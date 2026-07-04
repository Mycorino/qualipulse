"""Public panel recruitment (double opt-in) — /panel/join + /panel/join/confirm.

The join endpoint only sends a signed confirmation email; the profile and its
consent are created when the emailed token comes back via /join/confirm.
"""
from app.models.panel import PanelProfile
from app.services import panel_service as ps
from app.services.panel_catalog import ensure_attributes_seeded


def test_join_requires_consent(client):
    r = client.post("/panel/join", json={"email": "new@example.com", "consent": False})
    assert r.status_code == 400


def test_join_rejects_invalid_email(client):
    r = client.post("/panel/join", json={"email": "not-an-email", "consent": True})
    assert r.status_code == 422


def test_join_sends_confirmation_and_creates_nothing(client, db_session, monkeypatch):
    sent = {}

    def fake_send(email, token, lang="en"):
        sent.update(email=email, token=token, lang=lang)
        return True

    monkeypatch.setattr("app.services.email.send_panel_join_confirm", fake_send)

    r = client.post(
        "/panel/join",
        json={"email": "Newbie@Example.com", "first_name": "Ana", "lang": "fr", "consent": True},
    )
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert sent["email"] == "newbie@example.com"
    assert sent["lang"] == "fr"
    # Double opt-in: nothing stored until the link is clicked.
    assert db_session.query(PanelProfile).count() == 0
    # The emailed token carries the signup fields.
    payload = ps.resolve_join_token(sent["token"])
    assert payload == {"email": "newbie@example.com", "first_name": "Ana", "lang": "fr"}


def test_confirm_creates_consented_profile_and_opens_portal(client, db_session):
    ensure_attributes_seeded(db_session)
    token = ps.create_join_token("ana@example.com", "Ana", "fr")

    r = client.post("/panel/join/confirm", json={"token": token})
    assert r.status_code == 200
    session_token = r.json()["token"]

    db_session.expire_all()
    profile = db_session.query(PanelProfile).filter_by(email="ana@example.com").one()
    assert profile.panel_consent is True
    assert profile.consent_at is not None
    assert profile.first_name == "Ana"
    assert profile.preferred_language == "fr"

    # The returned durable session opens the portal immediately.
    me = client.get(f"/panel/me?token={session_token}")
    assert me.status_code == 200
    assert me.json()["email"] == "ana@example.com"

    # Idempotent: re-clicking the emailed link works, no duplicate row.
    r2 = client.post("/panel/join/confirm", json={"token": token})
    assert r2.status_code == 200
    db_session.expire_all()
    assert db_session.query(PanelProfile).count() == 1


def test_confirm_rejects_bad_tokens(client):
    assert client.post("/panel/join/confirm", json={"token": "garbage"}).status_code == 400
    # A panel_session token is not a join token.
    other = ps.create_panel_session("x@example.com")
    assert client.post("/panel/join/confirm", json={"token": other}).status_code == 400


def test_join_when_already_consented_sends_access_link(client, db_session, monkeypatch):
    db_session.add(PanelProfile(email="member@example.com", panel_consent=True))
    db_session.commit()
    calls = {"join": 0, "access": 0}
    monkeypatch.setattr(
        "app.services.email.send_panel_join_confirm",
        lambda **kw: calls.__setitem__("join", calls["join"] + 1) or True,
    )
    monkeypatch.setattr(
        "app.services.email.send_panel_access_link",
        lambda **kw: calls.__setitem__("access", calls["access"] + 1) or True,
    )
    r = client.post("/panel/join", json={"email": "member@example.com", "consent": True})
    assert r.status_code == 200
    assert calls == {"join": 0, "access": 1}
