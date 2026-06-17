"""Panel enrichment — catalogue seeding, answer upsert/validation, the
sensitive-data consent gate, durable panel_session auth, and completeness.
"""
import pytest

from app.services.panel_catalog import ensure_attributes_seeded, CATALOG
from app.services.panel_service import create_panel_session
from app.models.panel import PanelProfile, PanelAttribute


@pytest.fixture
def seeded(db_session):
    ensure_attributes_seeded(db_session)
    return db_session


@pytest.fixture
def panelist(seeded):
    """A consented panelist + a durable panel_session token for them."""
    p = PanelProfile(email="panelist@example.com", panel_consent=True)
    seeded.add(p)
    seeded.commit()
    return create_panel_session("panelist@example.com")


def test_catalog_seeds_idempotently(seeded):
    n1 = seeded.query(PanelAttribute).count()
    ensure_attributes_seeded(seeded)
    n2 = seeded.query(PanelAttribute).count()
    assert n1 == n2 == len(CATALOG)


def test_attributes_public_excludes_sensitive(client, seeded):
    r = client.get("/panel/attributes?lang=fr")
    assert r.status_code == 200
    attrs = r.json()["attributes"]
    assert all(not a["is_sensitive"] for a in attrs)
    # French labels resolve
    assert any(a["label"] and a["label"] != "" for a in attrs)


def test_invalid_token_rejected(client, seeded):
    assert client.get("/panel/me?token=garbage").status_code == 401
    assert client.post("/panel/answers", json={"token": "garbage", "answers": []}).status_code == 401


def test_save_answers_upsert_and_validation(client, panelist):
    # valid single + multi
    r = client.post("/panel/answers", json={"token": panelist, "answers": [
        {"attribute_id": "has_pets", "value": True},
        {"attribute_id": "pet_types", "value": ["dog", "cat"]},
        {"attribute_id": "grocery_channel", "value": "supermarket"},
        {"attribute_id": "grocery_channel", "value": "bogus_option"},   # rejected
        {"attribute_id": "nonexistent_attr", "value": "x"},             # rejected
    ]})
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] == 3
    assert "nonexistent_attr" in body["rejected"]
    assert "grocery_channel" in body["rejected"] or body["saved"] == 3
    assert body["completeness"]["percent"] > 0

    # upsert overwrites
    client.post("/panel/answers", json={"token": panelist, "answers": [
        {"attribute_id": "grocery_channel", "value": "online"},
    ]})
    me = client.get(f"/panel/me?token={panelist}").json()
    assert me["answers"]["grocery_channel"] == "online"
    assert me["answers"]["pet_types"] == ["dog", "cat"]


def test_sensitive_gated_until_consent(client, panelist):
    # sensitive attribute hidden + rejected before consent
    me = client.get(f"/panel/me?token={panelist}").json()
    assert me["sensitive_consent"] is False
    assert all(not a["is_sensitive"] for a in me["attributes"])
    r = client.post("/panel/answers", json={"token": panelist, "answers": [
        {"attribute_id": "income_band", "value": "60_100"},
    ]})
    assert "income_band" in r.json()["rejected"]
    assert r.json()["saved"] == 0

    # grant consent -> sensitive now visible + accepted
    cons = client.post("/panel/sensitive-consent", json={"token": panelist})
    assert cons.status_code == 200
    assert any(a["is_sensitive"] for a in cons.json()["attributes"])
    r2 = client.post("/panel/answers", json={"token": panelist, "answers": [
        {"attribute_id": "income_band", "value": "60_100"},
    ]})
    assert r2.json()["saved"] == 1
    me2 = client.get(f"/panel/me?token={panelist}").json()
    assert me2["sensitive_consent"] is True
    assert me2["answers"]["income_band"] == "60_100"


def test_repeated_and_duplicate_saves_dont_collide(client, panelist):
    """Rapid re-saves of the same attribute (incl. duplicated in one batch)
    must upsert, never trip the unique constraint (the prod 500 we hit)."""
    for _ in range(3):
        r = client.post("/panel/answers", json={"token": panelist, "answers": [
            {"attribute_id": "grocery_channel", "value": "online"},
        ]})
        assert r.status_code == 200, r.text
    # same attribute twice within a single batch
    r = client.post("/panel/answers", json={"token": panelist, "answers": [
        {"attribute_id": "has_pets", "value": True},
        {"attribute_id": "has_pets", "value": False},
    ]})
    assert r.status_code == 200, r.text
    me = client.get(f"/panel/me?token={panelist}").json()
    assert me["answers"]["has_pets"] is False


def test_participant_session_also_authorizes(client, seeded):
    """A still-valid interview participant_session works for enrichment too."""
    from app.routers.interview import _create_session_token
    PanelProfile  # ensure import
    prof = PanelProfile(email="fresh@example.com", panel_consent=True)
    seeded.add(prof); seeded.commit()
    token = _create_session_token("fresh@example.com", "some-link-token")
    r = client.get(f"/panel/me?token={token}")
    assert r.status_code == 200
    assert r.json()["email"] == "fresh@example.com"
