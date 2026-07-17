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
from app.models.study import StudyAnalysis
from app.models.survey import Survey, SurveyQuestion, SurveyResponse
from app.services.demo_seeder import (
    DEMO_PROJECT_NAME,
    DEMO_PROJECT_NAME_FR,
    seed_demo_project,
)


def _make_company(db_session, preferred_language: str = "en") -> Company:
    """Create a test company. Defaults to English so existing assertions
    continue to reference the EN project name; pass ``preferred_language="fr"``
    to exercise the French seeding path."""
    company = Company(
        name="Test Co",
        email="seed@example.com",
        password_hash="x",
        preferred_language=preferred_language,
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

        # Guide: 3 main questions across 3 sections, each with interviewer
        # notes + desired learning so the Setup tab shows the full craft.
        questions = (
            db_session.query(InterviewGuideQuestion)
            .filter(InterviewGuideQuestion.project_id == project.id)
            .all()
        )
        assert len(questions) == 3
        assert all(q.interview_notes for q in questions)
        assert all(q.desired_learning for q in questions)
        assert any(q.researcher_notes for q in questions)

        # 1 screening question with a disqualifying option
        screening = (
            db_session.query(ScreeningQuestion)
            .filter(ScreeningQuestion.project_id == project.id)
            .all()
        )
        assert len(screening) == 1
        assert json.loads(screening[0].disqualifying_options) == ["No"]

        # 1 interview link (active)
        links = (
            db_session.query(InterviewLink)
            .filter(InterviewLink.project_id == project.id)
            .all()
        )
        assert len(links) == 1
        assert links[0].is_active is True

        # 3 manual codes
        codes = (
            db_session.query(ManualCode)
            .filter(ManualCode.project_id == project.id)
            .all()
        )
        assert len(codes) == 3

        # 4 participants: all completed (2 FR + 2 EN)
        participants = (
            db_session.query(Participant)
            .filter(Participant.project_id == project.id)
            .all()
        )
        assert len(participants) == 4
        assert sum(1 for p in participants if p.status == "completed") == 4

        # Demographics: at least two distinct countries among the 4 EN participants
        countries = {p.country for p in participants}
        assert len(countries) >= 2

        # Interview turns (4 turns per participant × 4 = 16 minimum)
        turns = (
            db_session.query(InterviewTurn)
            .join(Participant)
            .filter(Participant.project_id == project.id)
            .all()
        )
        assert len(turns) >= 16

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
        assert len(tags) >= 4
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

        # 2 annotations on v2 (confirmed / needs_evidence)
        annotations = (
            db_session.query(AnalysisThemeAnnotation)
            .filter(AnalysisThemeAnnotation.analysis_id == v2.id)
            .all()
        )
        assert len(annotations) == 2
        statuses = {a.status for a in annotations}
        assert statuses == {"confirmed", "needs_evidence"}

        # 3 memos
        memos = (
            db_session.query(ProjectMemo)
            .filter(ProjectMemo.project_id == project.id)
            .all()
        )
        assert len(memos) == 3
        memo_types = {m.type for m in memos}
        assert "general" in memo_types
        assert "theme_note" in memo_types
        assert "tension_note" in memo_types

    def test_seed_uses_french_scaffolding_for_fr_company(self, db_session):
        """A company with preferred_language=fr gets the FR project (online
        grocery topic) end-to-end: scaffolding, guide, screening, AND
        participants are all French."""
        company = _make_company(db_session, preferred_language="fr")
        project = seed_demo_project(db_session, company.id)

        assert project.name == DEMO_PROJECT_NAME_FR
        assert project.language == "fr"
        # Welcome should open in French.
        assert project.welcome_message.startswith("Bonjour")
        # Objective should be in French.
        assert "comprendre" in project.research_objective.lower()

        # Screening question should be French with French disqualifier.
        screening = (
            db_session.query(ScreeningQuestion)
            .filter(ScreeningQuestion.project_id == project.id)
            .one()
        )
        assert json.loads(screening.disqualifying_options) == ["Non"]

        # Guide questions should be French, preserving 3 main questions,
        # and on-topic for online grocery shopping.
        questions = (
            db_session.query(InterviewGuideQuestion)
            .filter(InterviewGuideQuestion.project_id == project.id)
            .order_by(InterviewGuideQuestion.sort_order)
            .all()
        )
        assert len(questions) == 3
        joined = " ".join(q.main_question.lower() for q in questions)
        assert any(word in joined for word in ("course", "livraison", "alimentaire"))
        # Interviewer notes are localised too, not left in English.
        assert all(q.interview_notes for q in questions)
        notes_joined = " ".join(q.interview_notes.lower() for q in questions)
        assert any(word in notes_joined for word in ("enseigne", "commande", "magasin"))

        # Participants must all be in French-speaking countries — the FR
        # demo is now mono-language.
        countries = {
            p.country
            for p in db_session.query(Participant)
            .filter(Participant.project_id == project.id)
            .all()
        }
        french_speaking = {"France", "Belgique", "Suisse", "Canada"}
        english_speaking = {"United Kingdom", "United States", "Australia"}
        assert countries & french_speaking, f"Expected at least one French-speaking country, got {countries}"
        assert not (countries & english_speaking), f"Did not expect English-speaking countries in FR seed, got {countries}"

    def test_seed_populates_quality_assessment_fields(self, db_session):
        """All completed demo participants should have AI-quality assessment
        fields pre-populated, using valid quality labels."""
        company = _make_company(db_session)
        project = seed_demo_project(db_session, company.id)

        participants = (
            db_session.query(Participant)
            .filter(Participant.project_id == project.id)
            .all()
        )
        valid_labels = {"low", "fair", "good", "strong"}
        for p in participants:
            assert p.quality_score is not None, f"{p.display_name} missing quality_score"
            assert p.quality_label in valid_labels, f"{p.display_name} has invalid label '{p.quality_label}'"
            assert p.quality_summary is not None, f"{p.display_name} missing quality_summary"
            assert p.avg_response_words is not None, f"{p.display_name} missing avg_response_words"
            assert p.short_answer_pct is not None, f"{p.display_name} missing short_answer_pct"
            strengths = json.loads(p.quality_strengths)
            assert isinstance(strengths, list) and len(strengths) > 0
            issues = json.loads(p.quality_issues)
            assert isinstance(issues, list)  # can be empty (Emma)

    def test_seed_quality_in_researcher_language(self, db_session):
        """FR company should get quality summaries in French."""
        company = _make_company(db_session, preferred_language="fr")
        project = seed_demo_project(db_session, company.id)

        participants = (
            db_session.query(Participant)
            .filter(Participant.project_id == project.id)
            .all()
        )
        # At least one summary should contain French text
        summaries = [p.quality_summary for p in participants if p.quality_summary]
        assert any("réponse" in s.lower() or "confiance" in s.lower() or "fourni" in s.lower() for s in summaries), \
            "Expected French text in quality summaries for FR company"

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


class TestDemoStudyIsHybrid:
    """The demo Study ships with an interview track AND a survey + report,
    so a new user lands on a genuine mixed-methods Study."""

    def test_seed_creates_sibling_survey_with_responses(self, db_session):
        company = _make_company(db_session)
        project = seed_demo_project(db_session, company.id)

        surveys = (
            db_session.query(Survey)
            .filter(Survey.study_id == project.study_id)
            .all()
        )
        assert len(surveys) == 1
        survey = surveys[0]
        assert survey.status == "live"
        assert survey.company_id == company.id

        # A real stat instrument: frequency, current stack, stack size, a
        # three-item likert battery (value / price-rise tolerance / a
        # reverse-coded friction item), NPS, and an open churn question.
        questions = (
            db_session.query(SurveyQuestion)
            .filter(SurveyQuestion.survey_id == survey.id)
            .order_by(SurveyQuestion.sort_order)
            .all()
        )
        assert [q.type for q in questions] == [
            "mc_single", "mc_multi", "mc_single",
            "likert", "likert", "likert",
            "nps", "open_text",
        ]
        # One battery item is reverse-coded — the demo should showcase it.
        likert_configs = [json.loads(q.config) for q in questions if q.type == "likert"]
        assert any(c.get("reverse_coded") for c in likert_configs)

        # 44 completed responses → above the n>=30 inference threshold.
        responses = (
            db_session.query(SurveyResponse)
            .filter(SurveyResponse.survey_id == survey.id)
            .all()
        )
        assert len(responses) == 44
        assert all(r.completed_at is not None for r in responses)

    def test_seed_creates_decision_report(self, db_session):
        company = _make_company(db_session)
        project = seed_demo_project(db_session, company.id)

        analyses = (
            db_session.query(StudyAnalysis)
            .filter(StudyAnalysis.study_id == project.study_id)
            .all()
        )
        assert len(analyses) == 1
        analysis = analyses[0]
        assert analysis.status == "ready"
        assert analysis.generated_at is not None

        # The demo now ships the canonical Decision report (approach B): a
        # decision_v1 integration layer that report.html composes with the
        # interview themes (from the ProjectAnalysis) and the survey charts.
        report = json.loads(analysis.report)
        assert report["schema"] == "decision_v1"

        # The demo must showcase the full rigor furniture — a verdict, open
        # gaps, and per-row survey signal + counter-evidence — so first
        # impressions match what real generations produce.
        assert report["verdict"]
        assert report["gaps"]
        jd = report["joint_display"]
        assert len(jd) == 3
        for row in jd:
            assert row["theme_title"]
            assert row["survey_signal"]      # keyed to a real seeded survey number
            assert row["counter_evidence"]

    def _assert_joint_display_lines_up_with_qual(self, db_session, company):
        """Every joint-display theme_title must be copied verbatim from the
        refined ProjectAnalysis, so the Decision report's integration layer can
        never drift from the interview themes it sits beside. (The qual anchor
        quotes themselves are verbatim-checked by
        test_seed_quotes_are_substrings_of_real_transcripts.)"""
        project = seed_demo_project(db_session, company.id)
        analysis = (
            db_session.query(StudyAnalysis)
            .filter(StudyAnalysis.study_id == project.study_id)
            .one()
        )
        report = json.loads(analysis.report)
        qual = (
            db_session.query(ProjectAnalysis)
            .filter(
                ProjectAnalysis.project_id == project.id,
                ProjectAnalysis.status == "ready",
            )
            .order_by(ProjectAnalysis.version.desc())
            .first()
        )
        qual_titles = {t["title"] for t in json.loads(qual.report)["themes"]}
        for row in report["joint_display"]:
            assert row["theme_title"] in qual_titles, (
                f"joint-display theme not in qual analysis: {row['theme_title']!r}"
            )

    def test_demo_survey_responses_do_not_consume_survey_quota(self, db_session):
        """The demo Study's survey + its 44 seeded responses are showcase
        content — they must not count toward the workspace survey quota."""
        from app.services.survey_quotas import get_status

        company = _make_company(db_session)
        seed_demo_project(db_session, company.id)
        db_session.expire_all()

        status = get_status(db_session, company)
        assert status.responses_used == 0, (
            f"demo responses leaked into quota: {status.responses_used}"
        )
        assert status.surveys_active == 0, (
            f"demo survey leaked into quota: {status.surveys_active}"
        )

    def test_en_joint_display_lines_up_with_qual(self, db_session):
        company = _make_company(db_session, preferred_language="en")
        self._assert_joint_display_lines_up_with_qual(db_session, company)

    def test_fr_joint_display_lines_up_with_qual(self, db_session):
        company = _make_company(db_session, preferred_language="fr")
        self._assert_joint_display_lines_up_with_qual(db_session, company)


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

        # Confirm both demo projects exist (flagship + exit-interview sibling).
        demo_count = (
            db_session.query(Project)
            .filter(Project.company_id == company.id, Project.is_demo == True)  # noqa: E712
            .count()
        )
        assert demo_count == 2

        # Starter users (no legacy trial) get starter limits = 1 project.
        # The demo project should NOT count against that limit — we should be
        # able to create 1 real project on top of the demo.
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
        resp = client.post(
            "/projects/",
            json={**payload, "name": "Real 0"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        # 2nd real project should be blocked (starter limit = 1).
        resp = client.post(
            "/projects/",
            json={**payload, "name": "Over limit"},
            headers=auth_headers,
        )
        assert resp.status_code == 403


class TestDemoSecondStudy:
    """The demo seeds a second exit-interview study with its own ready
    qualitative analysis, so a new account lands with two studies — the
    flagship mixed-methods Decision report plus a qualitative-findings report.
    (The cross-study decision memo feature was retired; the second study now
    stands on its own as a qualitative report.)"""

    def test_seed_creates_two_studies(self, db_session):
        from app.models.study import Study
        from app.services.demo_seeder import DEMO2_PROJECT_NAME

        company = _make_company(db_session)
        seed_demo_project(db_session, company.id)

        studies = db_session.query(Study).filter(Study.company_id == company.id).all()
        assert len(studies) == 2
        assert DEMO2_PROJECT_NAME in {s.name for s in studies}

    def test_second_study_projects_are_demo_flagged(self, db_session):
        company = _make_company(db_session)
        seed_demo_project(db_session, company.id)
        projects = db_session.query(Project).filter(Project.company_id == company.id).all()
        assert len(projects) == 2
        assert all(p.is_demo for p in projects)

    def test_second_study_analysis_quotes_are_verbatim(self, db_session):
        from app.services.demo_seeder import DEMO2_PROJECT_NAME

        company = _make_company(db_session)
        seed_demo_project(db_session, company.id)
        project2 = (
            db_session.query(Project)
            .filter(Project.company_id == company.id, Project.name == DEMO2_PROJECT_NAME)
            .one()
        )
        transcripts = "\n".join(
            t.response_transcript or ""
            for t in db_session.query(InterviewTurn)
            .join(Participant)
            .filter(Participant.project_id == project2.id)
            .all()
        )
        analysis = (
            db_session.query(ProjectAnalysis)
            .filter(ProjectAnalysis.project_id == project2.id)
            .one()
        )
        assert analysis.status == "ready"
        for theme in json.loads(analysis.report)["themes"]:
            for q in theme["quotes"]:
                assert q["text"] in transcripts, f"Quote not in transcripts: {q['text']!r}"

    def test_fr_seed_creates_two_french_studies(self, db_session):
        from app.models.study import Study
        from app.services.demo_seeder import DEMO2_PROJECT_NAME_FR

        company = _make_company(db_session, preferred_language="fr")
        seed_demo_project(db_session, company.id)

        study_names = {
            s.name for s in db_session.query(Study).filter(Study.company_id == company.id).all()
        }
        assert DEMO2_PROJECT_NAME_FR in study_names

    def test_seed_creates_no_cross_study_memo(self, db_session):
        """The retired cross-study synthesis is no longer seeded."""
        from app.models.synthesis import CrossStudySynthesis

        company = _make_company(db_session)
        seed_demo_project(db_session, company.id)
        memos = (
            db_session.query(CrossStudySynthesis)
            .filter(CrossStudySynthesis.company_id == company.id)
            .all()
        )
        assert memos == []


class TestDecisionIntegration:
    """Phase 3: the integration pass sources qual from the ProjectAnalysis
    (not transcripts) and produces the verdict/joint-display/gaps layer that,
    with the reused ProjectAnalysis + dashboards, renders the Decision report
    superset. Forced onto the deterministic stub so CI makes no API call."""

    def test_integration_stub_covers_themes_and_renders(self, db_session, monkeypatch):
        monkeypatch.setattr("app.config.settings.ANTHROPIC_API_KEY", "")  # force stub
        from app.models.study import Study
        from app.services import report_export as R
        from app.services.study_analysis import (
            run_decision_integration,
            _latest_ready_project_analysis,
            _build_survey_inputs,
        )
        from app.services.survey_analytics import build_dashboard
        from app.models.survey import Survey as _Survey
        from app.models.project import Project as _Project

        company = _make_company(db_session)
        seed_demo_project(db_session, company.id)
        db_session.commit()
        study = db_session.query(Study).filter(Study.company_id == company.id).first()

        integ = run_decision_integration(db_session, study)
        assert integ["schema"] == "decision_v1"
        assert integ["verdict"]
        assert integ["confidence"] in ("directional", "supported", "strong")
        assert integ["gaps"]

        # joint_display must cover exactly the qualitative theme titles.
        pa = _latest_ready_project_analysis(db_session, study)
        qual_titles = {t["title"] for t in json.loads(pa.report)["themes"]}
        jd_titles = {x["theme_title"] for x in integ["joint_display"]}
        assert jd_titles == qual_titles

        # And the whole thing renders as a superset Decision report.
        surveys = [s for s in db_session.query(_Survey).filter(_Survey.study_id == study.id).all()
                   if s.role != "validation"]
        dashboards = [build_dashboard(db_session, s) for s in surveys]
        parts = [p for pr in db_session.query(_Project).filter(_Project.study_id == study.id).all()
                 for p in pr.participants if p.status == "completed"]
        html = R.render_decision_report_html(study, pa, dashboards, integ, parts, {}, company_name="Co")
        for needle in ("Decision report", "persona__name", "<polyline",
                       "Priority matrix", "Survey evidence", "decision-verdict", 'class="joint"'):
            assert needle in html, f"missing {needle}"

    def test_post_analyses_generates_and_serves_decision_report(self, client, auth_headers, db_session, registered_company, monkeypatch):
        """POST /studies/{id}/analyses now generates the Decision report
        (schema:"decision_v1"), and report.html serves the composed superset."""
        monkeypatch.setattr("app.config.settings.ANTHROPIC_API_KEY", "")  # force stub
        from app.models.company import Company
        from app.models.study import Study, StudyAnalysis

        company = db_session.query(Company).filter(Company.email == registered_company["email"]).first()
        company.preferred_language = "en"           # pin so EN chrome assertions hold
        db_session.commit()
        seed_demo_project(db_session, company.id)
        db_session.commit()
        study = db_session.query(Study).filter(Study.company_id == company.id).first()

        # The flipped endpoint generates the Decision report.
        posted = client.post(f"/studies/{study.id}/analyses", headers=auth_headers).json()
        assert posted["status"] == "ready"
        analysis = db_session.query(StudyAnalysis).filter(StudyAnalysis.id == posted["id"]).first()
        integ = json.loads(analysis.report)
        assert integ["schema"] == "decision_v1" and integ["verdict"]

        resp = client.get(
            f"/studies/{study.id}/analyses/{analysis.id}/report.html",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.text
        assert "Decision report" in body            # bordeaux chrome
        assert integ["verdict"] in body             # integration verdict rendered
        assert "Survey evidence" in body            # survey layer
        assert "Built from" in body                 # qual persona card (from ProjectAnalysis)
        assert "<polyline" in body                  # journey emotion arc

    def test_report_catalog_lists_all_three_types(
        self, client, auth_headers, db_session, registered_company
    ):
        """The Reports hub catalog surfaces every ready report by type — the
        seeded demo (mixed flagship + qual-only exit study) yields qualitative
        (green), survey (blue), AND decision (bordeaux) rows, each opening a
        ready standalone document."""
        from app.models.company import Company

        company = (
            db_session.query(Company)
            .filter(Company.email == registered_company["email"])
            .first()
        )
        seed_demo_project(db_session, company.id)
        db_session.commit()

        entries = client.get("/studies/report-catalog", headers=auth_headers).json()
        kinds = {e["kind"] for e in entries}
        assert {"qualitative", "survey", "decision"} <= kinds, kinds
        assert all(e["is_demo"] for e in entries)

        # Every catalog row opens its own ready report document.
        for e in entries:
            if e["kind"] == "qualitative":
                r = client.get(
                    f"/projects/{e['project_id']}/analysis/report.html",
                    headers=auth_headers,
                )
            elif e["kind"] == "survey":
                r = client.get(
                    f"/surveys/{e['survey_id']}/dashboard/report.html",
                    headers=auth_headers,
                )
            else:
                r = client.get(
                    f"/studies/{e['study_id']}/analyses/{e['analysis_id']}/report.html",
                    headers=auth_headers,
                )
            assert r.status_code == 200, (e["kind"], r.text[:200])

        # Evidence counts are populated per type.
        assert any(e["interviews"] > 0 for e in entries if e["kind"] == "qualitative")
        assert any(e["responses"] > 0 for e in entries if e["kind"] == "survey")
