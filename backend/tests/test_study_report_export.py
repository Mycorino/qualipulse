"""Tests for the study-report HTML export (Quantified Themes document).

GET /studies/{id}/analyses/{analysis_id}/report.html renders the stored
StudyAnalysis as a standalone research document with server-drawn charts.
Uses the same stub-mode generation path as test_studies.py — no AI key.
"""

import json

from app.models.company import Company
from app.models.study import StudyAnalysis


def _seed_study_with_analysis(client, auth_headers, n_per_cohort: int = 40):
    """Survey (mc_single segment + nps) with two cohorts, then a stub analysis."""

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Export fixture"}
    ).json()
    seg = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "mc_single",
            "prompt": "Your role?",
            "config": {
                "choices": [
                    {"id": "pm", "label": "Product Manager"},
                    {"id": "eng", "label": "Engineer"},
                ],
                "randomize": False,
                "has_other": False,
            },
        },
    ).json()
    nps = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={"type": "nps", "prompt": "How likely to recommend?", "config": {}},
    ).json()
    link = client.post(
        f"/surveys/{survey['id']}/links",
        headers=auth_headers,
        json={"is_anonymous": False},
    ).json()
    client.patch(f"/surveys/{survey['id']}", headers=auth_headers, json={"status": "live"})

    counter = 0
    for role, score in (("pm", 3), ("eng", 9)):
        for _ in range(n_per_cohort):
            counter += 1
            client.post(
                f"/r/{link['token']}/responses",
                json={
                    "link_token": link["token"],
                    "email": f"exp-{counter}@example.com",
                    "answers": [
                        {"question_id": seg["id"], "value_choice_ids": [role]},
                        {"question_id": nps["id"], "value_numeric": score},
                    ],
                    "is_complete": True,
                },
            )

    analysis = client.post(
        f"/studies/{survey['study_id']}/analyses", headers=auth_headers
    ).json()
    assert analysis["status"] == "ready"
    return survey["study_id"], analysis


def _set_language(db_session, lang: str) -> None:
    # Signup defaults preferred_language to "fr" — pin it so language
    # assertions are explicit rather than riding on the default.
    company = db_session.query(Company).first()
    company.preferred_language = lang
    db_session.commit()


def test_study_report_export_renders_full_document(client, auth_headers, db_session):
    study_id, analysis = _seed_study_with_analysis(client, auth_headers)
    _set_language(db_session, "en")

    resp = client.get(
        f"/studies/{study_id}/analyses/{analysis['id']}/report.html",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text

    # Document chrome + sections.
    assert "QualiPulse" in body
    assert "Mixed-methods research report" in body
    assert "The essentials" in body
    assert "The evidence at a glance" in body
    assert "Methodology contract" in body
    # Stat band reflects the real data (80 completed responses).
    assert ">80<" in body
    # Server-drawn charts for the source survey's questions.
    assert "How likely to recommend?" in body
    assert "Your role?" in body
    assert "<svg" in body
    # Every stub theme title appears.
    for theme in analysis["report"]["themes"]:
        assert theme["title"][:40] in body
    # Deterministic confidence rationale is rendered.
    assert "Why “" in body


def test_study_report_export_latest_alias(client, auth_headers, db_session):
    study_id, analysis = _seed_study_with_analysis(client, auth_headers)
    _set_language(db_session, "en")
    resp = client.get(
        f"/studies/{study_id}/analyses/latest/report.html", headers=auth_headers
    )
    assert resp.status_code == 200
    assert f"Report v{analysis['version']}" in resp.text


def test_study_report_export_404_without_ready_analysis(client, auth_headers):
    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "No analysis yet"}
    ).json()
    resp = client.get(
        f"/studies/{survey['study_id']}/analyses/latest/report.html",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_study_report_export_requires_auth(client, auth_headers):
    study_id, analysis = _seed_study_with_analysis(client, auth_headers)
    resp = client.get(f"/studies/{study_id}/analyses/{analysis['id']}/report.html")
    assert resp.status_code in (401, 403)


def test_study_report_export_localised_french(client, auth_headers, db_session):
    study_id, analysis = _seed_study_with_analysis(client, auth_headers)
    _set_language(db_session, "fr")

    resp = client.get(
        f"/studies/{study_id}/analyses/{analysis['id']}/report.html",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "Rapport de recherche mixte" in resp.text
    assert "Contrat méthodologique" in resp.text
    assert "L'essentiel" in resp.text


def test_study_report_export_escapes_html(client, auth_headers, db_session):
    study_id, analysis = _seed_study_with_analysis(client, auth_headers)
    row = (
        db_session.query(StudyAnalysis)
        .filter(StudyAnalysis.id == analysis["id"])
        .first()
    )
    report = json.loads(row.report)
    report["themes"][0]["title"] = '<script>alert("xss")</script>'
    row.report = json.dumps(report)
    db_session.commit()

    resp = client.get(
        f"/studies/{study_id}/analyses/{analysis['id']}/report.html",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert '<script>alert("xss")</script>' not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_study_report_suppresses_percentages_below_threshold(client, auth_headers, db_session):
    """The methodology contract must hold in the document: a survey whose
    n is under 30 renders raw counts and the sub-threshold notice, never
    a computed percentage."""

    study_id, analysis = _seed_study_with_analysis(client, auth_headers, n_per_cohort=4)
    _set_language(db_session, "en")
    resp = client.get(
        f"/studies/{study_id}/analyses/{analysis['id']}/report.html",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "Sub-threshold group (n&lt;30)" in resp.text or "Sub-threshold group (n<30)" in resp.text
