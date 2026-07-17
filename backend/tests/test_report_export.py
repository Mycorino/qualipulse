"""Tests for the HTML findings-report export (GET /projects/{id}/analysis/report.html)."""
import json
from datetime import datetime, timedelta

import pytest

from app.models.company import Company
from app.models.interview import (
    AnalysisThemeAnnotation,
    InterviewLink,
    Participant,
    ProjectAnalysis,
)
from app.models.project import Project


def _make_report(theme_title="Trust is earned at delivery", quote_text="I always check the tracking page twice a day"):
    return {
        "summary": "Participants trust brands that communicate proactively about delivery.",
        "themes": [
            {
                "title": theme_title,
                "summary": "P1 and P2 both described delivery updates as the moment trust forms.",
                "quotes": [
                    {
                        "text": quote_text,
                        "participant_identifier": "P1",
                        "participant_display_name": "Alice M.",
                        "turn_index": 3,
                        "question_text": "How do you decide whether to reorder?",
                    },
                    {
                        "text": "If the package is late and nobody tells me, I'm done.",
                        "participant_identifier": "P2",
                        "participant_display_name": "Ben K.",
                        "turn_index": 5,
                        "question_text": "Tell me about a bad experience.",
                    },
                ],
                "frequency": "most",
                "disconfirming_evidence": "P3 said she never reads delivery emails at all.",
            }
        ],
        "jobs_to_be_done": [
            {
                "job": "When I order online, I want proactive updates, so I can stop worrying.",
                "insight": "The anxiety is about uncertainty, not speed.",
                "frequency": "most",
            }
        ],
        "tensions": [
            {
                "tension": "Speed vs. certainty",
                "detail": "P1 wants faster delivery; P2 explicitly prefers slower but predictable.",
            }
        ],
        "recommendations": [
            "Ship a proactive delay notification. Would be wrong if open rates stay under 10%.",
        ],
        "confidence": "medium",
        "confidence_rationale": "N=3 with good response depth but limited diversity.",
        "participant_count": 3,
    }


@pytest.fixture
def project_with_analysis(db_session, registered_company):
    company = (
        db_session.query(Company)
        .filter(Company.email == registered_company["email"])
        .first()
    )
    # Report chrome follows the researcher's preferred_language (it must match
    # the analysis body, which is generated in that language) — pin it to EN so
    # the English assertions below hold regardless of the signup default.
    company.preferred_language = "en"
    project = Project(
        company_id=company.id,
        name="Customer Discovery Study",
        language="en",
        interview_duration_minutes=20,
        research_objective="Understand reorder decisions",
        decision_to_inform="Whether to build delivery notifications",
    )
    db_session.add(project)
    db_session.flush()

    link = InterviewLink(project_id=project.id, token="tok-report-export-test")
    db_session.add(link)
    db_session.flush()

    base = datetime(2026, 6, 1, 10, 0, 0)
    for i, (name, prof, country, quality) in enumerate(
        [
            ("Alice M.", "Product Manager", "UK", "strong"),
            ("Ben K.", "Engineer", "Germany", "good"),
            ("Sarah L.", "Designer", "France", "fair"),
        ]
    ):
        db_session.add(
            Participant(
                link_id=link.id,
                project_id=project.id,
                display_name=name,
                profession=prof,
                age_range="25-34",
                country=country,
                status="completed",
                started_at=base + timedelta(days=i),
                completed_at=base + timedelta(days=i, minutes=20),
                quality_label=quality,
                quality_score=0.8,
            )
        )

    analysis = ProjectAnalysis(
        project_id=project.id,
        version=1,
        status="ready",
        participant_count=3,
        report=json.dumps(_make_report()),
        generated_at=datetime(2026, 6, 5, 9, 0, 0),
    )
    db_session.add(analysis)
    db_session.flush()
    db_session.add(
        AnalysisThemeAnnotation(
            analysis_id=analysis.id,
            theme_title="Trust is earned at delivery",
            status="confirmed",
            researcher_note="Matches support-ticket data.",
        )
    )
    db_session.commit()
    return project, analysis


def test_report_export_renders_full_document(client, auth_headers, project_with_analysis):
    project, analysis = project_with_analysis
    resp = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    assert "findings_v1.html" in resp.headers.get("content-disposition", "")

    body = resp.text
    assert "Customer Discovery Study" in body
    assert "Trust is earned at delivery" in body
    assert "I always check the tracking page twice a day" in body
    assert "Alice M." in body
    assert "Ship a proactive delay notification" in body
    # Disconfirming evidence + annotation + JTBD + tension all present
    assert "P3 said she never reads delivery emails" in body
    assert "Confirmed by researcher" in body
    assert "proactive updates" in body
    assert "Speed vs. certainty" in body
    # Evidence map identifiers + appendix roster
    assert ">P1<" in body and ">P3<" in body
    assert "Product Manager" in body


def test_report_export_escapes_html(client, auth_headers, db_session, project_with_analysis):
    project, analysis = project_with_analysis
    report = _make_report(
        theme_title='<script>alert("x")</script>',
        quote_text='He said "use <b>bold</b> claims"',
    )
    analysis.report = json.dumps(report)
    db_session.commit()

    resp = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers)
    assert resp.status_code == 200
    assert "<script>alert" not in resp.text
    assert "&lt;script&gt;" in resp.text
    assert "use &lt;b&gt;bold&lt;/b&gt; claims" in resp.text


def test_report_export_404_without_ready_analysis(client, auth_headers, db_session, registered_company):
    company = (
        db_session.query(Company)
        .filter(Company.email == registered_company["email"])
        .first()
    )
    project = Project(company_id=company.id, name="Empty Study", interview_duration_minutes=15)
    db_session.add(project)
    db_session.commit()

    resp = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers)
    assert resp.status_code == 404


def test_report_export_specific_version(client, auth_headers, db_session, project_with_analysis):
    project, v1 = project_with_analysis
    v2_report = _make_report(theme_title="A refined v2 theme")
    db_session.add(
        ProjectAnalysis(
            project_id=project.id,
            version=2,
            status="ready",
            participant_count=3,
            report=json.dumps(v2_report),
            version_label="researcher_refined",
            parent_version_id=v1.id,
            generated_at=datetime(2026, 6, 6, 9, 0, 0),
        )
    )
    db_session.commit()

    latest = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers)
    assert "A refined v2 theme" in latest.text

    pinned = client.get(
        f"/projects/{project.id}/analysis/report.html?version=1", headers=auth_headers
    )
    assert "Trust is earned at delivery" in pinned.text
    assert "A refined v2 theme" not in pinned.text


def test_report_export_localised_french(client, auth_headers, db_session, project_with_analysis):
    project, _ = project_with_analysis
    # Chrome language = the researcher's preferred_language (matches the
    # analysis body), not the interview language.
    project.company.preferred_language = "fr"
    project.language = "fr"
    db_session.commit()

    resp = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers)
    assert resp.status_code == 200
    assert "Rapport de résultats de recherche" in resp.text
    assert "Recommandations" in resp.text


def test_report_export_requires_auth(client, project_with_analysis):
    project, _ = project_with_analysis
    resp = client.get(f"/projects/{project.id}/analysis/report.html")
    assert resp.status_code in (401, 403)


# ── Object recommendations + personas + journey (report v2 fields) ──────────

def _make_rich_report():
    """A report exercising object recommendations, personas and a journey."""
    rep = _make_report()
    rep["recommendations"] = [
        {
            "action": "Ship a proactive delay notification.",
            "rationale": "P1 and P2 lose trust on silent delays.",
            "owner_role": "Product", "horizon": "30d",
            "impact": "high", "effort": "low",
            "kpi": "Notification open rate above 40%.",
            "falsifier": "Open rates stay under 10%.",
        },
        {
            "action": "Redesign the tracking page.",
            "rationale": "Confusion at the tracking step.",
            "owner_role": "Design", "horizon": "60_90d",
            "impact": "high", "effort": "high",
            "kpi": "Support tickets about tracking fall.",
            "falsifier": "Tickets unchanged after launch.",
        },
        "Legacy string recommendation stays valid.",
    ]
    rep["personas"] = [
        {
            "name": "The Anxious Reorderer", "grounded_in": ["P1", "P2"],
            "segment": "Frequent online shoppers",
            "one_liner": "Checks tracking obsessively until the parcel lands.",
            "goals": ["Stop worrying about delivery"],
            "frustrations": ["Silent delays"],
            "behaviours": ["Refreshes the tracking page"],
            "primary_job": "Know where my order is.",
            "anchor_quote": {
                "text": "I always check the tracking page twice a day",
                "participant_identifier": "P1", "verified": True,
            },
        }
    ]
    rep["journey"] = {
        "applicable": True, "label": "Reordering online", "stages": [
            {"name": "Order", "goal": "Place the order", "emotion": 1,
             "quote": {"text": "I always check the tracking page twice a day",
                       "participant_identifier": "P1", "verified": True},
             "pain": "", "opportunity": "Set expectations early"},
            {"name": "Wait", "goal": "Track the parcel", "emotion": -2,
             "quote": {"text": "If the package is late and nobody tells me, I'm done.",
                       "participant_identifier": "P2", "verified": True},
             "pain": "Silence on delays", "opportunity": "Proactive comms"},
            {"name": "Receive", "goal": "Get the parcel", "emotion": 2,
             "quote": {"text": "", "participant_identifier": ""}, "pain": "", "opportunity": ""},
        ]
    }
    return rep


def test_report_export_object_recommendations(client, auth_headers, db_session, project_with_analysis):
    project, analysis = project_with_analysis
    analysis.report = json.dumps(_make_rich_report())
    db_session.commit()
    body = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers).text

    # Rich fields rendered
    assert "Ship a proactive delay notification." in body
    assert "Owner" in body and "Product" in body
    assert "Success metric" in body and "Would be wrong if" in body
    # Legacy string recommendation still renders (dual-shape, no crash)
    assert "Legacy string recommendation stays valid." in body
    # Priority matrix + quadrants
    assert "Priority matrix" in body
    assert "Quick wins" in body and "Big bets" in body
    # 30-60-90 plan bucketed by horizon
    assert "Activation plan" in body and "30 days" in body


def test_report_export_personas(client, auth_headers, db_session, project_with_analysis):
    project, analysis = project_with_analysis
    analysis.report = json.dumps(_make_rich_report())
    db_session.commit()
    body = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers).text

    assert "Personas" in body
    assert "The Anxious Reorderer" in body
    assert "Built from" in body and "persona__pill" in body
    assert "Stop worrying about delivery" in body


def test_report_export_journey(client, auth_headers, db_session, project_with_analysis):
    project, analysis = project_with_analysis
    analysis.report = json.dumps(_make_rich_report())
    db_session.commit()
    body = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers).text

    assert "Experience journey" in body
    assert "Reordering online" in body
    assert "<polyline" in body  # the emotion arc SVG
    assert "journey__table" in body
    assert "Silence on delays" in body


def test_report_export_journey_omitted_when_not_applicable(client, auth_headers, db_session, project_with_analysis):
    project, analysis = project_with_analysis
    rep = _make_rich_report()
    rep["journey"] = {"applicable": False, "stages": []}
    analysis.report = json.dumps(rep)
    db_session.commit()
    body = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers).text
    assert "Experience journey" not in body


def test_report_export_personas_omitted_when_empty(client, auth_headers, db_session, project_with_analysis):
    project, analysis = project_with_analysis
    rep = _make_rich_report()
    rep["personas"] = []
    analysis.report = json.dumps(rep)
    db_session.commit()
    body = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers).text
    assert "The Anxious Reorderer" not in body
    assert "Built from" not in body  # persona-card label, only present when a card renders


def test_report_export_unverified_persona_quote_flagged(client, auth_headers, db_session, project_with_analysis):
    project, analysis = project_with_analysis
    rep = _make_rich_report()
    rep["personas"][0]["anchor_quote"]["verified"] = False
    analysis.report = json.dumps(rep)
    db_session.commit()
    body = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers).text
    assert "verify before citing" in body


def test_report_export_new_sections_french(client, auth_headers, db_session, project_with_analysis):
    project, analysis = project_with_analysis
    project.company.preferred_language = "fr"
    analysis.report = json.dumps(_make_rich_report())
    db_session.commit()
    body = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers).text
    assert "Matrice de priorisation" in body and "Gains rapides" in body
    assert "Parcours d'expérience" in body
    assert "Plan d'activation" in body
    assert "Responsable" in body  # reco owner label localised


# ── Decision report: a strict superset of the qualitative + survey reports ──

from types import SimpleNamespace as _NS  # noqa: E402
from app.services.report_export import render_decision_report_html  # noqa: E402


def _fake_dashboard():
    q1 = _NS(type="mc_single", n_answered=48, mean=None, prompt="Why did you last cancel?",
             takeaway="Price is the #1 trigger.",
             breakdown={"choices": [
                 {"choice_id": "a", "label": "Price increase", "count": 22, "percentage": 46.0, "ci_low": 32, "ci_high": 60},
                 {"choice_id": "b", "label": "Finished a show", "count": 14, "percentage": 29.0, "ci_low": 17, "ci_high": 44}]})
    q2 = _NS(type="likert", n_answered=40, mean=3.8, prompt="How likely to return?", takeaway=None,
             breakdown={"histogram": [{"bucket": str(b), "count": c} for b, c in enumerate([3, 5, 10, 14, 8], 1)]})
    return _NS(name="Streaming pulse", status="closed", n_completed=48, questions=[q1, q2])


def _decision_fixture(lang="en"):
    qual = _make_rich_report()  # themes, personas, journey, object recs
    turn = _NS(turn_index=0, question_text="Q", response_transcript="I always check the tracking page twice a day", tts_audio_url=None)
    parts = [
        _NS(id=f"p{i}", status="completed", display_name=n, profession="PM", age_range="30-44",
            country="UK", quality_label="strong", quality_score=0.9,
            completed_at=datetime(2026, 7, i + 1), started_at=datetime(2026, 7, i + 1), turns=[turn])
        for i, n in enumerate(["Alice M.", "Ben K."])
    ]
    pa = _NS(report=json.dumps(qual), generated_at=datetime(2026, 7, 10), version=2)
    study = _NS(name="Why subscribers churn", company=_NS(preferred_language=lang, name="Acme"))
    integration = {
        "verdict": "Ship the pause feature and simplify cancellation.",
        "confidence": "supported",
        "joint_display": [{"theme_title": "Trust is earned at delivery",
                           "survey_signal": "46% cancelled on a price increase (n=48)",
                           "confidence": "supported", "counter_evidence": "Heavy users unaffected."}],
        "gaps": ["No active-subscriber contrast group."],
    }
    return study, pa, [_fake_dashboard()], integration, parts


def test_decision_report_is_superset():
    study, pa, dashboards, integration, parts = _decision_fixture("en")
    html = render_decision_report_html(study, pa, dashboards, integration, parts, {"p0": 7, "p1": 6}, company_name="Acme")
    # qualitative exhibits (from ProjectAnalysis)
    assert "Personas" in html and "persona__name" in html
    assert "<polyline" in html          # journey emotion arc
    assert "Priority matrix" in html and "<circle" in html
    assert "Activation plan" in html
    assert "Owner" in html              # activated recommendations
    # survey layer
    assert "Survey evidence" in html and "chart-title" in html and "<rect" in html
    # integration layer (neither single report has these)
    assert "decision-verdict" in html and "Ship the pause feature" in html
    assert 'class="joint"' in html and "46% cancelled" in html
    assert "gaps-list" in html and "contrast group" in html


def test_decision_report_survey_only_degrades():
    # No ProjectAnalysis (survey-only study) → still renders survey + verdict/gaps,
    # just omits the qual-only exhibits. Still >= the standalone survey report.
    study, _, dashboards, integration, parts = _decision_fixture("en")
    html = render_decision_report_html(study, None, dashboards, integration, [], {}, company_name="Acme")
    assert "Survey evidence" in html and "chart-title" in html
    assert "Ship the pause feature" in html   # verdict still present
    assert "The Anxious Reorderer" not in html  # no qual data → persona omitted, no crash
    assert "Built from" not in html


def test_decision_report_french_chrome():
    study, pa, dashboards, integration, parts = _decision_fixture("fr")
    html = render_decision_report_html(study, pa, dashboards, integration, parts, {}, company_name="Acme")
    assert "Rapport de décision" in html
    assert "Signal quantitatif" in html
    assert "Quand les chiffres rejoignent les voix" in html
