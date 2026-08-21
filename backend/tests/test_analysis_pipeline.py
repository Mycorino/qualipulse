"""Direct tests for the analysis pipeline (run_analysis) with Claude mocked.

Covers the versioning + pruning contract: keep-5, but shared / annotated /
parent-of-kept versions must survive, and a synthesis failure lands as
status=failed rather than a stuck row.
"""

import json

from app.models.company import Company
from app.models.interview import (
    AnalysisThemeAnnotation,
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.project import Project
from app.services import analysis as analysis_service

REPORT = {
    "summary": "People juggle too many tools.",
    "themes": [],
    "jtbds": [],
    "tensions": [],
    "recommendations": [],
    "participant_count": 1,
}


def _seed_project(db):
    company = Company(name="Acme", email="an@acme.com", password_hash="x", email_verified=True)
    db.add(company)
    db.flush()
    project = Project(company_id=company.id, name="Study", language="en")
    db.add(project)
    db.flush()
    link = InterviewLink(project_id=project.id, token="tok-analysis", is_active=True)
    db.add(link)
    db.flush()
    p = Participant(link_id=link.id, project_id=project.id, status="completed")
    db.add(p)
    db.flush()
    db.add(
        InterviewTurn(
            participant_id=p.id,
            turn_index=0,
            question_index=0,
            question_text="Q1?",
            response_transcript="I juggle too many tools every day.",
        )
    )
    db.commit()
    return project


def _patch_claude(monkeypatch, *, fail=False):
    if fail:
        def _boom(prompt, effort="high", **kw):
            raise RuntimeError("claude down")
        monkeypatch.setattr(analysis_service, "_synthesize_response", _boom)
    else:
        monkeypatch.setattr(
            analysis_service, "_synthesize_response", lambda prompt, effort="high", **kw: object()
        )
    monkeypatch.setattr(analysis_service, "_raise_on_bad_stop", lambda response: None)
    monkeypatch.setattr(analysis_service, "_parse_report", lambda response: dict(REPORT))
    monkeypatch.setattr(analysis_service, "log_claude_usage", lambda *a, **k: None)


def test_run_analysis_produces_ready_report(db_session, monkeypatch):
    project = _seed_project(db_session)
    _patch_claude(monkeypatch)

    analysis_service.run_analysis(project.id, db_session)

    row = (
        db_session.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project.id)
        .one()
    )
    assert row.status == "ready"
    assert row.version == 1
    assert row.participant_count == 1
    assert json.loads(row.report)["summary"] == REPORT["summary"]


def test_claude_failure_marks_analysis_failed(db_session, monkeypatch):
    project = _seed_project(db_session)
    _patch_claude(monkeypatch, fail=True)

    analysis_service.run_analysis(project.id, db_session)

    row = (
        db_session.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project.id)
        .one()
    )
    assert row.status == "failed"
    assert "claude down" in (row.error or "")


def test_pruning_spares_shared_annotated_and_parents(db_session, monkeypatch):
    project = _seed_project(db_session)
    _patch_claude(monkeypatch)

    # Seed 8 prior ready versions. v2 is publicly shared; v3 is annotated;
    # v4 is the parent of v8 (which will be kept as one of the 5 newest).
    rows: dict[int, ProjectAnalysis] = {}
    for v in range(1, 9):
        row = ProjectAnalysis(
            project_id=project.id,
            version=v,
            status="ready",
            report=json.dumps(REPORT),
        )
        db_session.add(row)
        db_session.flush()
        rows[v] = row
    rows[2].share_token = "shared-token-abc"
    rows[8].parent_version_id = rows[4].id
    db_session.add(
        AnalysisThemeAnnotation(
            analysis_id=rows[3].id, theme_title="Theme A", status="confirmed"
        )
    )
    db_session.commit()

    analysis_service.run_analysis(project.id, db_session)  # creates v9

    surviving = {
        a.version
        for a in db_session.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project.id)
        .all()
    }
    # 5 newest (v5..v9) + shared v2 + annotated v3 + parent-of-kept v4.
    assert surviving == {2, 3, 4, 5, 6, 7, 8, 9}
    assert 1 not in surviving
