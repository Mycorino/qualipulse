"""Small-sample marking: N<3 analyses are stamped and rendered as a first read.

The flag is deterministic (set in Python by the analysis service, never by
the model) so the Analysis tab, the shared report, and the HTML export all
show the same honest "first read, not findings" notice.
"""

import json
from datetime import datetime

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant, ProjectAnalysis
from app.models.project import Project
from app.services import analysis as analysis_service

REPORT = {
    "summary": "Early signal only.",
    "themes": [],
    "jtbds": [],
    "tensions": [],
    "recommendations": [],
    "confidence": "low",
    "confidence_rationale": "N=1, anecdotal.",
    "participant_count": 1,
}


def _seed(db, registered_company, n_participants):
    company = db.query(Company).filter(Company.email == registered_company["email"]).first()
    company.preferred_language = "en"
    project = Project(company_id=company.id, name="Tiny study", language="en")
    db.add(project)
    db.flush()
    link = InterviewLink(project_id=project.id, token=f"tok-small-{n_participants}", is_active=True)
    db.add(link)
    db.flush()
    for i in range(n_participants):
        p = Participant(
            link_id=link.id, project_id=project.id,
            display_name=f"P{i}", status="completed",
            completed_at=datetime(2026, 6, 1 + i),
        )
        db.add(p)
        db.flush()
        db.add(InterviewTurn(
            participant_id=p.id, turn_index=0, question_index=0,
            question_text="Q?", response_transcript=f"an answer {i}",
        ))
    db.commit()
    return project


def _patch_claude(monkeypatch):
    monkeypatch.setattr(
        analysis_service, "_synthesize_response", lambda prompt, effort="high": object()
    )
    monkeypatch.setattr(analysis_service, "_raise_on_bad_stop", lambda response: None)
    monkeypatch.setattr(analysis_service, "_parse_report", lambda response: dict(REPORT))
    monkeypatch.setattr(analysis_service, "log_claude_usage", lambda *a, **k: None)


class TestFlag:
    @pytest.mark.parametrize("n,expected", [(1, True), (2, True), (3, False)])
    def test_small_sample_flag_tracks_n(self, db_session, registered_company, monkeypatch, n, expected):
        project = _seed(db_session, registered_company, n)
        _patch_claude(monkeypatch)

        analysis_service.run_analysis(project.id, db_session)

        row = db_session.query(ProjectAnalysis).filter_by(project_id=project.id).one()
        assert row.status == "ready"
        assert json.loads(row.report)["small_sample"] is expected


class TestExportNotice:
    def _analysis(self, db, project, n, small_sample):
        report = dict(REPORT)
        report["participant_count"] = n
        report["small_sample"] = small_sample
        row = ProjectAnalysis(
            project_id=project.id, version=1, status="ready",
            participant_count=n, report=json.dumps(report),
            generated_at=datetime(2026, 6, 5),
        )
        db.add(row)
        db.commit()
        return row

    def test_export_shows_notice_for_small_sample(self, client, db_session, registered_company, auth_headers):
        project = _seed(db_session, registered_company, 1)
        self._analysis(db_session, project, 1, True)
        resp = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert "First read, not findings" in resp.text

    def test_export_no_notice_at_healthy_n(self, client, db_session, registered_company, auth_headers):
        project = _seed(db_session, registered_company, 3)
        self._analysis(db_session, project, 3, False)
        resp = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert "First read, not findings" not in resp.text

    def test_export_falls_back_to_count_for_legacy_reports(self, client, db_session, registered_company, auth_headers):
        # Reports generated before the flag existed carry no small_sample key;
        # the renderer falls back to the analysed participant count.
        project = _seed(db_session, registered_company, 1)
        report = dict(REPORT)
        report.pop("small_sample", None)
        row = ProjectAnalysis(
            project_id=project.id, version=1, status="ready",
            participant_count=1, report=json.dumps(report),
            generated_at=datetime(2026, 6, 5),
        )
        db_session.add(row)
        db_session.commit()
        resp = client.get(f"/projects/{project.id}/analysis/report.html", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert "First read, not findings" in resp.text
