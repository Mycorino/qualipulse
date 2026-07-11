"""Tests for the survey-results HTML export (quantitative dashboard document).

GET /surveys/{id}/dashboard/report.html renders the survey's live dashboard
aggregates as a standalone, print-ready document with server-drawn charts.
Shares the same seeding path as test_surveys.py — no AI key needed.
"""

from app.models.company import Company


def _seed_survey(client, auth_headers, *, n: int = 40):
    """A survey with an NPS + MC + open-text question and `n` completed responses."""

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Pricing pulse"}
    ).json()
    nps = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={"type": "nps", "prompt": "How likely to recommend us?", "config": {}},
    ).json()
    mc = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "mc_single",
            "prompt": "Which plan fits you?",
            "config": {
                "choices": [
                    {"id": "starter", "label": "Starter"},
                    {"id": "team", "label": "Team"},
                ],
                "randomize": False,
                "has_other": False,
            },
        },
    ).json()
    txt = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={"type": "open_text", "prompt": "Anything else?", "config": {}},
    ).json()
    link = client.post(
        f"/surveys/{survey['id']}/links",
        headers=auth_headers,
        json={"is_anonymous": False},
    ).json()
    client.patch(f"/surveys/{survey['id']}", headers=auth_headers, json={"status": "live"})

    for i in range(n):
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "email": f"resp-{i}@example.com",
                "answers": [
                    {"question_id": nps["id"], "value_numeric": 9 if i % 2 else 4},
                    {"question_id": mc["id"], "value_choice_ids": ["starter" if i % 3 else "team"]},
                    {"question_id": txt["id"], "value_text": f"Feedback number {i}"},
                ],
                "is_complete": True,
            },
        )
    return survey


def _set_language(db_session, lang: str) -> None:
    company = db_session.query(Company).first()
    company.preferred_language = lang
    db_session.commit()


def test_survey_report_export_renders_full_document(client, auth_headers, db_session):
    survey = _seed_survey(client, auth_headers, n=40)
    _set_language(db_session, "en")

    resp = client.get(
        f"/surveys/{survey['id']}/dashboard/report.html", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text

    # Document chrome + sections.
    assert "QualiPulse" in body
    assert "Survey results report" in body
    assert "Results at a glance" in body
    assert "Results by question" in body
    assert "Methodology contract" in body
    # Cover + stat band reflect the real data (40 completed responses).
    assert ">40<" in body
    assert "Pricing pulse" in body
    # Server-drawn charts for each analysable question.
    assert "How likely to recommend us?" in body
    assert "Which plan fits you?" in body
    assert "<svg" in body
    # Open-text verbatims are sampled into the document.
    assert "Anything else?" in body
    assert "Feedback number" in body
    # Filename slug in the content-disposition header.
    assert "Pricing_pulse_results.html" in resp.headers["content-disposition"]


def test_survey_report_export_localised_french(client, auth_headers, db_session):
    survey = _seed_survey(client, auth_headers, n=32)
    _set_language(db_session, "fr")

    resp = client.get(
        f"/surveys/{survey['id']}/dashboard/report.html", headers=auth_headers
    )
    assert resp.status_code == 200
    assert "Rapport de résultats du sondage" in resp.text
    assert "Contrat méthodologique" in resp.text
    assert "Les résultats en un coup d'œil" in resp.text


def test_survey_report_export_suppresses_percentages_below_threshold(
    client, auth_headers, db_session
):
    """Below n=30 the document shows raw counts + the sub-threshold notice,
    never a computed percentage — mirroring the dashboard's contract."""

    survey = _seed_survey(client, auth_headers, n=5)
    _set_language(db_session, "en")

    resp = client.get(
        f"/surveys/{survey['id']}/dashboard/report.html", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.text
    assert "below the n=30 threshold" in body
    # The sub-threshold choice chart carries the raw-counts caption instead
    # of any computed percentage.
    assert "raw counts, no percentages" in body


def test_survey_report_export_escapes_html(client, auth_headers, db_session):
    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Safe survey"}
    ).json()
    client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "short_text",
            "prompt": '<script>alert("xss")</script>',
            "config": {},
        },
    )
    _set_language(db_session, "en")

    resp = client.get(
        f"/surveys/{survey['id']}/dashboard/report.html", headers=auth_headers
    )
    assert resp.status_code == 200
    assert '<script>alert("xss")</script>' not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_survey_report_export_404_for_unknown_survey(client, auth_headers):
    resp = client.get("/surveys/does-not-exist/dashboard/report.html", headers=auth_headers)
    assert resp.status_code == 404


def test_survey_report_export_requires_auth(client, auth_headers):
    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Auth survey"}
    ).json()
    resp = client.get(f"/surveys/{survey['id']}/dashboard/report.html")
    assert resp.status_code in (401, 403)
