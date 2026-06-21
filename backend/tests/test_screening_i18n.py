"""Native-language screening: localized serving, gate stays language-independent,
researcher edits, on-demand no-op when already translated."""
import json

import pytest

from app.models.company import Company
from app.models.project import Project, ScreeningQuestion
from app.models.interview import InterviewLink


@pytest.fixture
def project_with_screening(db_session, registered_company):
    company = db_session.query(Company).filter(Company.email == registered_company["email"]).first()
    project = Project(company_id=company.id, name="Flights", language="en")
    db_session.add(project)
    db_session.flush()
    sq = ScreeningQuestion(
        project_id=project.id, sort_order=0,
        question="What is your role?",
        options=json.dumps(["Manager", "Engineer", "Student"]),
        disqualifying_options=json.dumps(["Student"]),
        translations=json.dumps({"fr": {"question": "Quel est votre rôle ?",
                                         "options": ["Manager", "Ingénieur", "Étudiant"]}}),
    )
    db_session.add(sq)
    link = InterviewLink(project_id=project.id, token="scr-token", is_active=True)
    db_session.add(link)
    db_session.commit()
    return {"project": project, "sq": sq, "company_id": company.id}


def test_localized_unit():
    sq = ScreeningQuestion(
        question="What is your role?",
        options=json.dumps(["Manager", "Student"]),
        disqualifying_options=json.dumps(["Student"]),
        translations=json.dumps({"fr": {"question": "Quel rôle ?", "options": ["Manager", "Étudiant"]}}),
    )
    q, opts = sq.localized("fr")
    assert q == "Quel rôle ?"
    assert opts == [{"value": "Manager", "label": "Manager"}, {"value": "Student", "label": "Étudiant"}]
    # value is always canonical (gate identity); missing lang → canonical labels
    q2, opts2 = sq.localized("de")
    assert q2 == "What is your role?"
    assert opts2[1] == {"value": "Student", "label": "Student"}


def test_screening_questions_localized(client, project_with_screening):
    r = client.get("/interview/scr-token/screening-questions", params={"lang": "fr"})
    assert r.status_code == 200, r.text
    q = r.json()[0]
    assert q["question"] == "Quel est votre rôle ?"
    assert q["options"] == [
        {"value": "Manager", "label": "Manager"},
        {"value": "Engineer", "label": "Ingénieur"},
        {"value": "Student", "label": "Étudiant"},
    ]


def test_gate_is_language_independent(client, project_with_screening):
    """A FR participant submits the canonical value of the disqualifying option;
    the gate (exact-match on canonical) still disqualifies."""
    sq_id = project_with_screening["sq"].id
    r = client.post("/interview/scr-token/screen", json={"answers": {sq_id: "Student"}})
    assert r.status_code == 200
    assert r.json()["qualified"] is False
    # a non-disqualifying canonical value qualifies
    r2 = client.post("/interview/scr-token/screen", json={"answers": {sq_id: "Manager"}})
    assert r2.json()["qualified"] is True


def test_missing_language_falls_back_to_canonical(client, project_with_screening, monkeypatch):
    # de isn't stored; with no API key the on-demand translate fails gracefully
    # → canonical text served, no 500.
    r = client.get("/interview/scr-token/screening-questions", params={"lang": "de"})
    assert r.status_code == 200
    q = r.json()[0]
    assert q["question"] == "What is your role?"
    assert q["options"][0] == {"value": "Manager", "label": "Manager"}


def test_ensure_language_noop_when_present(db_session, project_with_screening, monkeypatch):
    """fr is already stored → no Claude call. (Source language en → no call.)"""
    from app.services import screening_translation as st
    project = project_with_screening["project"]

    def _boom(*a, **k):
        raise AssertionError("get_anthropic_client must not be called when present")
    monkeypatch.setattr(st, "get_anthropic_client", _boom)

    st.ensure_screening_language(project, "fr", db_session)  # already translated
    st.ensure_screening_language(project, "en", db_session)  # source language


def test_patch_translation(client, auth_headers, project_with_screening):
    pid = project_with_screening["project"].id
    sid = project_with_screening["sq"].id
    r = client.patch(
        f"/projects/{pid}/screening/{sid}/translations",
        headers=auth_headers,
        json={"lang": "de", "question": "Was ist Ihre Rolle?", "options": ["Manager", "Ingenieur", "Student"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["translations"]["de"]["question"] == "Was ist Ihre Rolle?"
    # serving in de now returns the edited text
    g = client.get("/interview/scr-token/screening-questions", params={"lang": "de"})
    assert g.json()[0]["question"] == "Was ist Ihre Rolle?"
