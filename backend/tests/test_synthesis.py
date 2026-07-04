"""Tests for cross-study synthesis (decision memos) + public shared report export."""
import json
from datetime import datetime

import pytest

from app.models.company import Company
from app.models.interview import ProjectAnalysis
from app.models.project import Project
from app.models.study import Study
from app.models.synthesis import CrossStudySynthesis
from app.services.study_synthesis import run_cross_synthesis


def _mini_report(theme="Trust drives retention"):
    return {
        "summary": "Trust matters more than price.",
        "themes": [
            {
                "title": theme,
                "summary": "P1 and P2 agree.",
                "quotes": [
                    {"text": "I stay where my history lives.", "participant_identifier": "P1",
                     "participant_display_name": "Alice", "turn_index": 1, "question_text": "Why stay?"},
                ],
                "frequency": "most",
                "disconfirming_evidence": "",
            }
        ],
        "jobs_to_be_done": [],
        "tensions": [],
        "recommendations": ["Do the thing. Would be wrong if churn is flat."],
        "confidence": "medium",
        "confidence_rationale": "N=4.",
        "participant_count": 4,
    }


_MEMO_JSON = {
    "decision": "Should we prioritise retention features over acquisition exclusives?",
    "verdict": "Prioritise retention. Strongest reason: switching cost is emotional across both studies. Biggest caveat: pricing evidence is single-market.",
    "summary": "Both studies converge on trust as the retention lever.",
    "key_findings": [
        {
            "finding": "Switching cost is emotional, not financial",
            "detail": "Both studies found history loss outweighs price.",
            "supporting_studies": ["Streaming choices", "Churn triggers"],
            "evidence": "\"I stay where my history lives.\" (Streaming choices — Alice)",
            "strength": "strong",
        }
    ],
    "conflicts": [
        {"topic": "Price sensitivity", "detail": "Streaming choices found low sensitivity; Churn triggers found spikes on increase emails."}
    ],
    "gaps": ["No evidence on enterprise buyers."],
    "recommendations": ["Ship history export. Would be wrong if reactivation is history-age-independent."],
    "confidence": "medium",
    "confidence_rationale": "Two studies, medium confidence each, overlapping scope.",
}


@pytest.fixture
def two_ready_studies(db_session, registered_company):
    company = (
        db_session.query(Company)
        .filter(Company.email == registered_company["email"])
        .first()
    )
    company.preferred_language = "en"  # memo language is deterministic in tests
    studies = []
    for name in ["Streaming choices", "Churn triggers"]:
        study = Study(company_id=company.id, name=name)
        db_session.add(study)
        db_session.flush()
        project = Project(
            company_id=company.id,
            study_id=study.id,
            name=f"{name} interviews",
            interview_duration_minutes=20,
            research_objective=f"Understand {name.lower()}",
        )
        db_session.add(project)
        db_session.flush()
        db_session.add(
            ProjectAnalysis(
                project_id=project.id,
                version=1,
                status="ready",
                participant_count=4,
                report=json.dumps(_mini_report(theme=f"Theme of {name}")),
                generated_at=datetime(2026, 6, 20, 10, 0),
            )
        )
        studies.append(study)
    db_session.commit()
    return studies


def test_create_synthesis_requires_ready_analyses(client, auth_headers, db_session, registered_company):
    company = (
        db_session.query(Company)
        .filter(Company.email == registered_company["email"])
        .first()
    )
    s1 = Study(company_id=company.id, name="Ready-less A")
    s2 = Study(company_id=company.id, name="Ready-less B")
    db_session.add_all([s1, s2])
    db_session.commit()

    resp = client.post(
        "/synthesis/",
        json={"study_ids": [s1.id, s2.id]},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "studies_not_ready"
    assert set(detail["studies"]) == {"Ready-less A", "Ready-less B"}


def test_create_synthesis_cross_company_404(client, auth_headers, db_session, two_ready_studies):
    other = Company(name="Other Co", email="other@example.com", password_hash="x")
    db_session.add(other)
    db_session.flush()
    foreign = Study(company_id=other.id, name="Foreign study")
    db_session.add(foreign)
    db_session.commit()

    resp = client.post(
        "/synthesis/",
        json={"study_ids": [two_ready_studies[0].id, foreign.id]},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_create_run_and_export_memo(client, auth_headers, db_session, two_ready_studies, monkeypatch):
    # Don't spawn the real background thread (it would open its own session
    # against the non-test engine) — we drive run_cross_synthesis ourselves.
    monkeypatch.setattr("app.routers.synthesis._spawn_synthesis_thread", lambda _id: None)
    monkeypatch.setattr(
        "app.services.study_synthesis._call_claude",
        lambda prompt, db, company_id: json.dumps(_MEMO_JSON),
    )

    resp = client.post(
        "/synthesis/",
        json={
            "study_ids": [s.id for s in two_ready_studies],
            "name": "Retention vs acquisition",
            "decision_question": "Retention features or acquisition exclusives?",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 202, resp.text
    synth_id = resp.json()["id"]

    run_cross_synthesis(synth_id, db_session)
    row = db_session.query(CrossStudySynthesis).filter_by(id=synth_id).first()
    assert row.status == "ready", row.error

    # Detail endpoint returns the parsed memo
    detail = client.get(f"/synthesis/{synth_id}", headers=auth_headers).json()
    assert detail["status"] == "ready"
    assert detail["report"]["verdict"].startswith("Prioritise retention")

    # List endpoint includes it with study names
    listing = client.get("/synthesis/", headers=auth_headers).json()
    assert listing[0]["id"] == synth_id
    assert set(listing[0]["study_names"]) == {"Streaming choices", "Churn triggers"}

    # Print-ready memo export
    html_resp = client.get(f"/synthesis/{synth_id}/report.html", headers=auth_headers)
    assert html_resp.status_code == 200
    assert html_resp.headers["content-type"].startswith("text/html")
    body = html_resp.text
    assert "Retention vs acquisition" in body
    assert "Prioritise retention" in body
    assert "Switching cost is emotional" in body
    assert "Streaming choices" in body
    assert "Decision memo" in body


def test_run_synthesis_marks_failed_on_error(client, auth_headers, db_session, two_ready_studies, monkeypatch):
    monkeypatch.setattr("app.routers.synthesis._spawn_synthesis_thread", lambda _id: None)

    def _boom(prompt, db, company_id):
        raise RuntimeError("api down")

    monkeypatch.setattr("app.services.study_synthesis._call_claude", _boom)

    resp = client.post(
        "/synthesis/",
        json={"study_ids": [s.id for s in two_ready_studies]},
        headers=auth_headers,
    )
    synth_id = resp.json()["id"]
    run_cross_synthesis(synth_id, db_session)

    row = db_session.query(CrossStudySynthesis).filter_by(id=synth_id).first()
    assert row.status == "failed"
    assert "api down" in row.error

    # Memo export refuses while not ready
    html_resp = client.get(f"/synthesis/{synth_id}/report.html", headers=auth_headers)
    assert html_resp.status_code == 404


def test_memo_escapes_html(client, auth_headers, db_session, two_ready_studies, monkeypatch):
    monkeypatch.setattr("app.routers.synthesis._spawn_synthesis_thread", lambda _id: None)
    evil = dict(_MEMO_JSON)
    evil["verdict"] = '<script>alert("memo")</script>'
    monkeypatch.setattr(
        "app.services.study_synthesis._call_claude",
        lambda prompt, db, company_id: json.dumps(evil),
    )
    resp = client.post(
        "/synthesis/",
        json={"study_ids": [s.id for s in two_ready_studies]},
        headers=auth_headers,
    )
    synth_id = resp.json()["id"]
    run_cross_synthesis(synth_id, db_session)

    body = client.get(f"/synthesis/{synth_id}/report.html", headers=auth_headers).text
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_shared_report_public_print_html(client, db_session, two_ready_studies):
    analysis = db_session.query(ProjectAnalysis).first()
    analysis.share_token = "public-print-token"
    db_session.commit()
    project = db_session.query(Project).filter_by(id=analysis.project_id).first()

    resp = client.get("/reports/public-print-token/report.html")
    assert resp.status_code == 200
    assert project.name in resp.text
    # Public variant strips the participant appendix
    assert "Appendix — participants" not in resp.text

    assert client.get("/reports/bad-token/report.html").status_code == 404
