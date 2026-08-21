"""Live synthesis progress: section narration, throttled persistence, time estimate."""

from datetime import datetime, timedelta

from app.models.company import Company
from app.models.interview import InterviewLink, Participant, ProjectAnalysis
from app.models.project import Project
from app.routers.analysis import _EST_FIXED_SECONDS, _EST_PER_INTERVIEW_SECONDS, _estimate_seconds
from app.services.analysis import REPORT_SECTIONS, _detect_section, _progress_reporter


class TestSectionDetection:
    def test_advances_in_schema_order(self):
        idx = _detect_section('{"summary": "x", "themes": [', -1)
        assert REPORT_SECTIONS[idx] == "themes"

    def test_never_moves_backwards(self):
        # "summary" mentioned inside a later string value must not regress.
        idx = _detect_section('"recommendations": [{"rationale": "see summary"}]', 4)
        assert idx == 4

    def test_skips_nothing_out_of_order(self):
        # A later key alone (without the intermediate ones) doesn't jump ahead.
        assert _detect_section('"personas": []', 0) == 0


class TestProgressReporter:
    def test_throttles_but_reports_section_changes(self, db_session):
        company = Company(name="LP", email="lp@x.com", password_hash="x")
        db_session.add(company)
        db_session.flush()
        project = Project(company_id=company.id, name="S", language="en")
        db_session.add(project)
        db_session.flush()
        analysis = ProjectAnalysis(project_id=project.id, version=1, status="generating")
        db_session.add(analysis)
        db_session.commit()

        report = _progress_reporter(db_session, analysis, min_interval=60.0)
        report("summary", 100)
        assert analysis.stage == "synthesizing"
        assert '"section": "summary"' in analysis.stage_detail
        report("summary", 200)  # same section, inside the interval → dropped
        assert '"output_tokens": 100' in analysis.stage_detail
        report("themes", 300)  # section change bypasses the throttle
        assert '"section": "themes"' in analysis.stage_detail


class TestEstimate:
    def test_fallback_without_history(self, db_session):
        assert _estimate_seconds(db_session, 3) == _EST_FIXED_SECONDS + 3 * _EST_PER_INTERVIEW_SECONDS

    def test_learns_from_past_runs(self, db_session):
        company = Company(name="E", email="e@x.com", password_hash="x")
        db_session.add(company)
        db_session.flush()
        project = Project(company_id=company.id, name="S", language="en")
        db_session.add(project)
        db_session.flush()
        link = InterviewLink(project_id=project.id, token="tok-est")
        db_session.add(link)
        db_session.flush()
        db_session.add(Participant(link_id=link.id, project_id=project.id, status="completed"))
        base = datetime(2026, 6, 1, 10, 0, 0)
        for v in range(1, 5):
            db_session.add(ProjectAnalysis(
                project_id=project.id, version=v, status="ready", participant_count=5,
                created_at=base + timedelta(hours=v),
                generated_at=base + timedelta(hours=v, seconds=120),
            ))
        db_session.commit()
        # Four 120s runs at N=5 → ~120s at N=5, rescaled for N=1: 120 * 4/8.
        assert _estimate_seconds(db_session, 5) == 120
        assert _estimate_seconds(db_session, 1) == 60
