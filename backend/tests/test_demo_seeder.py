"""Tests for the onboarding showcase demo project seeder."""
import json

from app.models.coding import ManualCode, QuoteTag
from app.models.company import Company
from app.models.interview import (
    AnalysisThemeAnnotation,
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.memo import ProjectMemo
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion
from app.services.demo_seeder import DEMO_PROJECT_NAME, seed_demo_project


def _make_company(db_session) -> Company:
    company = Company(
        name="Test Co",
        email="seed@example.com",
        password_hash="x",
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


class TestDemoSeeder:
    def test_seed_creates_project_with_is_demo_flag(self, db_session):
        company = _make_company(db_session)
        project = seed_demo_project(db_session, company.id)

        assert project.is_demo is True
        assert project.name == DEMO_PROJECT_NAME
        assert project.research_objective
        assert project.welcome_message

    def test_seed_creates_full_relationship_graph(self, db_session):
        company = _make_company(db_session)
        project = seed_demo_project(db_session, company.id)

        # Guide: 5 main questions across 3 sections
        questions = (
            db_session.query(InterviewGuideQuestion)
            .filter(InterviewGuideQuestion.project_id == project.id)
            .all()
        )
        assert len(questions) == 5

        # 1 screening question with a disqualifying option
        screening = (
            db_session.query(ScreeningQuestion)
            .filter(ScreeningQuestion.project_id == project.id)
            .all()
        )
        assert len(screening) == 1
        assert json.loads(screening[0].disqualifying_options) == ["Just me"]

        # 2 interview links (1 active EU, 1 paused NA)
        links = (
            db_session.query(InterviewLink)
            .filter(InterviewLink.project_id == project.id)
            .all()
        )
        assert len(links) == 2
        assert sum(1 for l in links if l.is_active) == 1

        # 4 manual codes
        codes = (
            db_session.query(ManualCode)
            .filter(ManualCode.project_id == project.id)
            .all()
        )
        assert len(codes) == 4

        # 7 participants: 6 completed + 1 in-progress (Marco)
        participants = (
            db_session.query(Participant)
            .filter(Participant.project_id == project.id)
            .all()
        )
        assert len(participants) == 7
        assert sum(1 for p in participants if p.status == "completed") == 6
        assert sum(1 for p in participants if p.status == "in_progress") == 1

        # Bilingual demographics
        countries = {p.country for p in participants}
        assert "France" in countries
        assert "United States" in countries

        # Lots of interview turns
        turns = (
            db_session.query(InterviewTurn)
            .join(Participant)
            .filter(Participant.project_id == project.id)
            .all()
        )
        assert len(turns) >= 50

        # At least one turn is flagged as manually edited
        edited = [t for t in turns if t.manually_edited]
        assert len(edited) >= 1

        # Quote tags created (and offsets are valid)
        tags = (
            db_session.query(QuoteTag)
            .join(InterviewTurn)
            .join(Participant)
            .filter(Participant.project_id == project.id)
            .all()
        )
        assert len(tags) >= 10
        for tag in tags:
            turn = next(t for t in turns if t.id == tag.turn_id)
            assert turn.response_transcript is not None
            extracted = turn.response_transcript[tag.start_index:tag.end_index]
            assert extracted == tag.selected_text

        # Two analyses (v1 ai_discovery, v2 researcher_refined linked to v1)
        analyses = (
            db_session.query(ProjectAnalysis)
            .filter(ProjectAnalysis.project_id == project.id)
            .order_by(ProjectAnalysis.version)
            .all()
        )
        assert len(analyses) == 2
        v1, v2 = analyses
        assert v1.version_label == "ai_discovery"
        assert v2.version_label == "researcher_refined"
        assert v2.parent_version_id == v1.id
        assert v1.share_token  # shareable
        assert v1.status == "ready"
        assert v2.status == "ready"

        # Report shape matches AnalysisReport interface
        report = json.loads(v1.report)
        assert set(report.keys()) >= {
            "summary",
            "themes",
            "jobs_to_be_done",
            "tensions",
            "recommendations",
            "confidence",
            "participant_count",
        }
        assert len(report["themes"]) >= 3
        first_theme = report["themes"][0]
        assert set(first_theme.keys()) >= {"title", "summary", "quotes", "frequency"}

        # 3 annotations on v2 (confirmed / needs_evidence / disputed)
        annotations = (
            db_session.query(AnalysisThemeAnnotation)
            .filter(AnalysisThemeAnnotation.analysis_id == v2.id)
            .all()
        )
        assert len(annotations) == 3
        statuses = {a.status for a in annotations}
        assert statuses == {"confirmed", "needs_evidence", "disputed"}

        # 6 memos
        memos = (
            db_session.query(ProjectMemo)
            .filter(ProjectMemo.project_id == project.id)
            .all()
        )
        assert len(memos) == 6
        memo_types = {m.type for m in memos}
        assert "general" in memo_types
        assert "theme_note" in memo_types
        assert "tension_note" in memo_types

    def test_seed_quotes_are_substrings_of_real_transcripts(self, db_session):
        """Every analysis quote must appear verbatim in some participant's turn."""
        company = _make_company(db_session)
        project = seed_demo_project(db_session, company.id)

        all_transcripts = "\n".join(
            t.response_transcript or ""
            for t in db_session.query(InterviewTurn)
            .join(Participant)
            .filter(Participant.project_id == project.id)
            .all()
        )
        v1 = (
            db_session.query(ProjectAnalysis)
            .filter(
                ProjectAnalysis.project_id == project.id,
                ProjectAnalysis.version == 1,
            )
            .one()
        )
        report = json.loads(v1.report)
        for theme in report["themes"]:
            for q in theme["quotes"]:
                text = q["text"] if isinstance(q, dict) else q
                assert text in all_transcripts, f"Quote not found in transcripts: {text!r}"


class TestDemoProjectExcludedFromQuota:
    def test_demo_project_does_not_count_against_project_limit(
        self, client, auth_headers, db_session
    ):
        """A user with a seeded demo + N real projects should still be at N/limit."""
        # Find the company we just registered.
        company = db_session.query(Company).filter(Company.email == "test@example.com").one()

        # Seed the demo project directly (the onboarding hook does the same thing).
        seed_demo_project(db_session, company.id)
        db_session.expire_all()

        # Confirm the demo exists.
        demo_count = (
            db_session.query(Project)
            .filter(Project.company_id == company.id, Project.is_demo == True)  # noqa: E712
            .count()
        )
        assert demo_count == 1

        # On a 14-day trial, starter users get team-level limits = 5 projects.
        # We should be able to create 5 real projects on top of the demo.
        question = {
            "section_index": 0,
            "section_title": "Background",
            "question_index": 0,
            "main_question": "Tell me about yourself.",
            "interview_notes": "",
            "desired_learning": "",
        }
        payload = {
            "name": "Real",
            "language": "en",
            "interview_duration_minutes": 20,
            "questions": [question],
            "screening_questions": [],
        }
        for i in range(5):
            resp = client.post(
                "/projects/",
                json={**payload, "name": f"Real {i}"},
                headers=auth_headers,
            )
            assert resp.status_code == 201, resp.text

        # 6th real project should be blocked even though demo exists alongside.
        resp = client.post(
            "/projects/",
            json={**payload, "name": "Over limit"},
            headers=auth_headers,
        )
        assert resp.status_code == 403
