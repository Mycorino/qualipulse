"""Native-language study name: localized serving for participants, canonical
name stays the researcher's identity, on-demand no-op when already translated."""
import json

import pytest

from app.models.company import Company
from app.models.project import Project
from app.models.interview import InterviewLink


@pytest.fixture
def project_with_name(db_session, registered_company):
    company = db_session.query(Company).filter(Company.email == registered_company["email"]).first()
    project = Project(
        company_id=company.id,
        name="Customer Satisfaction Long Haul Flights",
        language="en",
        name_translations=json.dumps({"fr": "Satisfaction client — vols long-courriers"}),
    )
    db_session.add(project)
    db_session.flush()
    link = InterviewLink(project_id=project.id, token="name-token", is_active=True)
    db_session.add(link)
    db_session.commit()
    return {"project": project, "company_id": company.id}


def test_localized_name_unit():
    p = Project(
        name="Flights study",
        language="en",
        name_translations=json.dumps({"fr": "Étude vols"}),
    )
    assert p.localized_name("fr") == "Étude vols"
    # missing language → canonical name; no lang → canonical name
    assert p.localized_name("de") == "Flights study"
    assert p.localized_name(None) == "Flights study"


def test_info_returns_localized_name(client, project_with_name):
    r = client.get("/interview/name-token", params={"lang": "fr"})
    assert r.status_code == 200, r.text
    assert r.json()["project_name"] == "Satisfaction client — vols long-courriers"


def test_info_canonical_name_without_lang(client, project_with_name):
    r = client.get("/interview/name-token")
    assert r.status_code == 200
    assert r.json()["project_name"] == "Customer Satisfaction Long Haul Flights"


def test_missing_name_language_falls_back(client, project_with_name):
    # de isn't stored; with no API key on-demand translate fails gracefully →
    # canonical name served, no 500.
    r = client.get("/interview/name-token", params={"lang": "de"})
    assert r.status_code == 200
    assert r.json()["project_name"] == "Customer Satisfaction Long Haul Flights"


def test_ensure_name_language_noop_when_present(db_session, project_with_name, monkeypatch):
    from app.services import screening_translation as st
    project = project_with_name["project"]

    def _boom(*a, **k):
        raise AssertionError("get_anthropic_client must not be called when present")
    monkeypatch.setattr(st, "get_anthropic_client", _boom)

    st.ensure_study_name_language(project, "fr", db_session)  # already translated
    st.ensure_study_name_language(project, "en", db_session)  # source language
