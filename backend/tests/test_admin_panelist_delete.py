"""Admin deletion of a consumer / panelist account (GDPR erasure + testing
reset): removes the panel profile, enrichment answers, and magic tokens."""
import json
from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.models.panel import PanelProfile, PanelAnswer, PanelAttribute, ParticipantMagicToken
from app.services.panel_catalog import ensure_attributes_seeded

ADMIN_KEY = "test-admin-secret-key"


@pytest.fixture(autouse=True)
def admin_secret(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_SECRET_KEY", ADMIN_KEY)


def _headers():
    return {"Authorization": f"Bearer {ADMIN_KEY}", "X-Admin-Identity": "tester"}


def test_delete_panelist_removes_profile_answers_tokens(client, db_session):
    ensure_attributes_seeded(db_session)
    p = PanelProfile(email="dupe@example.com", panel_consent=True, first_name="Dupe")
    db_session.add(p)
    db_session.flush()
    db_session.add(PanelAnswer(profile_id=p.id, attribute_id="has_pets", value=json.dumps(True)))
    db_session.add(ParticipantMagicToken(
        email="dupe@example.com", token="tok-x", interview_link_token="L",
        used=False, expires_at=datetime.utcnow() + timedelta(minutes=30),
    ))
    db_session.commit()

    r = client.delete("/admin/panel/dupe@example.com", headers=_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["panel_profile"] == 1
    assert body["panel_answers"] == 1
    assert body["magic_tokens"] == 1

    assert db_session.query(PanelProfile).filter_by(email="dupe@example.com").first() is None
    assert db_session.query(PanelAnswer).count() == 0
    assert db_session.query(ParticipantMagicToken).filter_by(email="dupe@example.com").first() is None


def test_delete_panelist_requires_admin(client):
    assert client.delete("/admin/panel/x@example.com").status_code == 403


def test_delete_missing_panelist_is_noop(client, db_session):
    r = client.delete("/admin/panel/nobody@example.com", headers=_headers())
    assert r.status_code == 200
    assert r.json()["panel_profile"] == 0
