"""Screening answers: persisted at /start, then leveraged in analysis.

Previously the screener's clicked options were checked for disqualification
and thrown away. Now qualified participants carry a sanitized snapshot that
feeds the analysis prompt headers, segment filters, the heatmap, and the
participants list.
"""

import json

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant, ProjectAnalysis
from app.models.project import Project, ScreeningQuestion
from app.services.analysis import _build_transcripts_block, _filter_participants


@pytest.fixture
def screening_setup(client, db_session, registered_company, monkeypatch):
    company = db_session.query(Company).filter(Company.email == registered_company["email"]).first()
    project = Project(company_id=company.id, name="Grocery study", language="en")
    db_session.add(project)
    db_session.flush()
    sq1 = ScreeningQuestion(
        project_id=project.id, sort_order=0,
        question="How often do you shop online?",
        options=json.dumps(["Weekly", "Monthly", "Never"]),
        disqualifying_options=json.dumps(["Never"]),
    )
    sq2 = ScreeningQuestion(
        project_id=project.id, sort_order=1,
        question="Which service do you use most?",
        options=json.dumps(["Carrefour", "Picard", "Amazon"]),
        disqualifying_options=json.dumps([]),
    )
    db_session.add_all([sq1, sq2])
    link = InterviewLink(project_id=project.id, token="tok-screen-ans", is_active=True)
    db_session.add(link)
    db_session.commit()

    from app.services.billing_service import bootstrap_trial_subscription, ensure_plans_seeded
    ensure_plans_seeded(db_session)
    bootstrap_trial_subscription(db_session, company)

    from app.routers import interview as interview_router
    monkeypatch.setattr(
        interview_router,
        "start_interview",
        lambda pid, db: {"question_text": "Q1?", "tts_audio_url": None, "is_warmup": False},
    )
    return {"company": company, "project": project, "link": link, "sq1": sq1, "sq2": sq2}


class TestPersistence:
    def test_start_persists_sanitized_snapshot(self, client, db_session, screening_setup):
        s = screening_setup
        resp = client.post(
            f"/interview/{s['link'].token}/start",
            json={
                "display_name": "Alice",
                "screening_answers": {
                    s["sq1"].id: "Weekly",
                    s["sq2"].id: "Picard",
                    "not-a-question": "Injected",       # unknown id → dropped
                },
            },
        )
        assert resp.status_code == 200, resp.text
        p = db_session.query(Participant).filter(Participant.project_id == s["project"].id).one()
        answers = p.screening_answers_list
        assert [(a["question_id"], a["answer"]) for a in answers] == [
            (s["sq1"].id, "Weekly"),
            (s["sq2"].id, "Picard"),
        ]
        # Question text is frozen in the snapshot.
        assert answers[0]["question"] == "How often do you shop online?"

    def test_invalid_option_dropped(self, client, db_session, screening_setup):
        s = screening_setup
        resp = client.post(
            f"/interview/{s['link'].token}/start",
            json={"screening_answers": {s["sq1"].id: "<script>alert(1)</script>"}},
        )
        assert resp.status_code == 200, resp.text
        p = db_session.query(Participant).filter(Participant.project_id == s["project"].id).one()
        assert p.screening_answers is None

    def test_start_without_answers(self, client, db_session, screening_setup):
        s = screening_setup
        resp = client.post(f"/interview/{s['link'].token}/start", json={"display_name": "B"})
        assert resp.status_code == 200, resp.text
        p = db_session.query(Participant).filter(Participant.project_id == s["project"].id).one()
        assert p.screening_answers is None
        assert p.screening_answers_list == []


def _participant_with_answers(db_session, link, project, sq, answer, name="P"):
    p = Participant(
        link_id=link.id, project_id=project.id, display_name=name, status="completed",
        screening_answers=json.dumps(
            [{"question_id": sq.id, "question": sq.question, "answer": answer}]
        ),
    )
    db_session.add(p)
    db_session.flush()
    db_session.add(InterviewTurn(
        participant_id=p.id, turn_index=0, question_index=0,
        question_text="Q?", response_transcript=f"answer from {name}",
    ))
    db_session.commit()
    return p


class TestAnalysisLeverage:
    def test_screening_filter(self, db_session, screening_setup):
        s = screening_setup
        weekly = _participant_with_answers(db_session, s["link"], s["project"], s["sq1"], "Weekly", "W")
        monthly = _participant_with_answers(db_session, s["link"], s["project"], s["sq1"], "Monthly", "M")

        kept = _filter_participants(
            [weekly, monthly], f"screening:{s['sq1'].id}", ["Weekly"]
        )
        assert kept == [weekly]
        # Demographic filtering still works unchanged.
        weekly.profession = "Designer"
        assert _filter_participants([weekly, monthly], "profession", ["Designer"]) == [weekly]

    def test_transcript_block_carries_screener(self, db_session, screening_setup):
        s = screening_setup
        p = _participant_with_answers(db_session, s["link"], s["project"], s["sq1"], "Weekly", "Wanda")
        block, _ = _build_transcripts_block([p])
        assert "screener: How often do you shop online? = Weekly" in block

    def test_participants_list_includes_answers(self, client, db_session, screening_setup, auth_headers):
        s = screening_setup
        _participant_with_answers(db_session, s["link"], s["project"], s["sq1"], "Weekly", "Wanda")
        resp = client.get(f"/projects/{s['project'].id}/participants", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        row = resp.json()[0]
        assert row["screening_answers"][0]["answer"] == "Weekly"

    def test_heatmap_includes_screening_segments(self, client, db_session, screening_setup, auth_headers):
        s = screening_setup
        _participant_with_answers(db_session, s["link"], s["project"], s["sq1"], "Weekly", "Wanda")
        report = {"summary": "x", "themes": [{"title": "T", "quotes": []}]}
        db_session.add(ProjectAnalysis(
            project_id=s["project"].id, version=1, status="ready",
            report=json.dumps(report), participant_count=1,
        ))
        db_session.commit()

        resp = client.get(f"/projects/{s['project'].id}/analysis/heatmap", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        segments = resp.json()["segments"]
        assert any(seg.endswith(":Weekly") and "shop online" in seg for seg in segments)
