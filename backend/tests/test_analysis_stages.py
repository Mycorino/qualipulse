"""Staged analysis pipeline: stage tracking, readiness gate, auto-tag chain.

Covers: stage transitions land in ProjectAnalysis and are cleared on
terminal states, the auto-tag pre-stage only codes untagged participants,
Tier-2 suggestion evidence keeps its machine-coded framing, and the
readiness endpoint classifies tagging state correctly.
"""

import json

from app.models.coding import ManualCode, QuoteTag, TagSuggestion
from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant, ProjectAnalysis
from app.models.project import Project
from app.services import analysis as analysis_service
from app.services.analysis import _build_suggestion_block, _suggestion_stats

REPORT = {
    "summary": "Stub report.",
    "themes": [],
    "jtbds": [],
    "tensions": [],
    "recommendations": [],
    "participant_count": 2,
}


def _seed(db, n_participants=2, company_email="stages@acme.com"):
    company = Company(
        name="Stages Co", email=company_email, password_hash="x", email_verified=True
    )
    db.add(company)
    db.flush()
    project = Project(company_id=company.id, name="Staged study", language="en")
    db.add(project)
    db.flush()
    link = InterviewLink(project_id=project.id, token=f"tok-{company_email}", is_active=True)
    db.add(link)
    db.flush()
    participants, turns = [], []
    for i in range(n_participants):
        p = Participant(
            link_id=link.id, project_id=project.id,
            display_name=f"P{i}", status="completed",
        )
        db.add(p)
        db.flush()
        t = InterviewTurn(
            participant_id=p.id, turn_index=0, question_index=0,
            question_text="Q1?", response_transcript=f"the checkout kept failing {i}",
        )
        db.add(t)
        db.flush()
        participants.append(p)
        turns.append(t)
    db.commit()
    return project, participants, turns


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


def _record_stages(monkeypatch):
    seen: list[str] = []
    original = analysis_service._set_stage

    def _recording(db, analysis, stage, detail=None):
        seen.append(stage)
        original(db, analysis, stage, detail)

    monkeypatch.setattr(analysis_service, "_set_stage", _recording)
    return seen


class TestStageTracking:
    def test_stage_sequence_and_cleared_on_ready(self, db_session, monkeypatch):
        project, _, _ = _seed(db_session)
        _patch_claude(monkeypatch)
        seen = _record_stages(monkeypatch)

        analysis_service.run_analysis(project.id, db_session)

        assert seen == ["preparing", "synthesizing", "verifying"]
        row = db_session.query(ProjectAnalysis).filter_by(project_id=project.id).one()
        assert row.status == "ready"
        assert row.stage is None
        assert row.stage_detail is None

    def test_stage_cleared_on_failure(self, db_session, monkeypatch):
        project, _, _ = _seed(db_session, company_email="fail@acme.com")
        _patch_claude(monkeypatch, fail=True)

        analysis_service.run_analysis(project.id, db_session)

        row = db_session.query(ProjectAnalysis).filter_by(project_id=project.id).one()
        assert row.status == "failed"
        assert row.stage is None


class TestAutoTagChain:
    def test_auto_tag_codes_only_untagged_participants(self, db_session, monkeypatch):
        project, participants, turns = _seed(db_session, n_participants=3, company_email="at@acme.com")
        _patch_claude(monkeypatch)
        seen = _record_stages(monkeypatch)

        # P0 already has an accepted tag; P1 has a pending suggestion;
        # only P2 should be auto-coded.
        code = ManualCode(project_id=project.id, name="Friction")
        db_session.add(code)
        db_session.flush()
        db_session.add(QuoteTag(
            turn_id=turns[0].id, manual_code_id=code.id,
            selected_text="checkout", start_index=4, end_index=12,
        ))
        db_session.add(TagSuggestion(
            participant_id=participants[1].id, turn_id=turns[1].id,
            manual_code_id=code.id, selected_text="failing",
            start_index=0, end_index=7, status="pending",
        ))
        db_session.commit()

        coded: list[str] = []
        import app.services.tag_suggestions as ts
        monkeypatch.setattr(
            ts, "suggest_tags_for_participant",
            lambda pid, db, language="en": coded.append(pid) or [],
        )

        analysis_service.run_analysis(project.id, db_session, auto_tag=True)

        assert coded == [participants[2].id]
        assert seen[0] == "auto_tagging"
        assert seen[-1] == "verifying"
        row = db_session.query(ProjectAnalysis).filter_by(project_id=project.id).one()
        assert row.status == "ready"
        assert row.stage is None

    def test_no_auto_tag_stage_without_flag(self, db_session, monkeypatch):
        project, _, _ = _seed(db_session, company_email="noat@acme.com")
        _patch_claude(monkeypatch)
        seen = _record_stages(monkeypatch)

        analysis_service.run_analysis(project.id, db_session, auto_tag=False)
        assert "auto_tagging" not in seen


class TestSuggestionTier:
    def test_pending_suggestions_grouped_with_weak_framing(self, db_session):
        project, participants, turns = _seed(db_session, company_email="tier@acme.com")
        code = ManualCode(project_id=project.id, name="Friction")
        db_session.add(code)
        db_session.flush()
        db_session.add_all([
            TagSuggestion(
                participant_id=participants[0].id, turn_id=turns[0].id,
                manual_code_id=code.id, selected_text="the checkout kept failing",
                start_index=0, end_index=25, status="pending",
            ),
            TagSuggestion(
                participant_id=participants[1].id, turn_id=turns[1].id,
                proposed_code_name="Workaround", selected_text="failing 1",
                start_index=17, end_index=26, status="pending",
            ),
            # Accepted suggestions belong to the codebook tier, not here.
            TagSuggestion(
                participant_id=participants[1].id, turn_id=turns[1].id,
                manual_code_id=code.id, selected_text="checkout",
                start_index=4, end_index=12, status="accepted",
            ),
        ])
        db_session.commit()

        stats = _suggestion_stats(db_session, participants)
        assert {s["code"] for s in stats} == {"Friction", "Workaround"}
        assert all(s["quote_count"] == 1 for s in stats)

        block = _build_suggestion_block(stats)
        assert "MACHINE-CODED CANDIDATE EVIDENCE" in block
        assert "NOT yet reviewed" in block
        # Tier-2 framing must never borrow the Tier-1 header.
        assert "RESEARCHER CODEBOOK EVIDENCE" not in block

    def test_empty_without_pending(self, db_session):
        _, participants, _ = _seed(db_session, company_email="tier2@acme.com")
        assert _suggestion_stats(db_session, participants) == []
        assert _build_suggestion_block([]) == ""


class TestReadinessEndpoint:
    def _project_for(self, db_session, registered_company):
        company = (
            db_session.query(Company).filter(Company.email == registered_company["email"]).one()
        )
        project = Project(company_id=company.id, name="Gate study", language="en")
        db_session.add(project)
        db_session.flush()
        link = InterviewLink(project_id=project.id, token="tok-gate", is_active=True)
        db_session.add(link)
        db_session.flush()
        participants, turns = [], []
        for i in range(2):
            p = Participant(
                link_id=link.id, project_id=project.id,
                display_name=f"P{i}", status="completed",
            )
            db_session.add(p)
            db_session.flush()
            t = InterviewTurn(
                participant_id=p.id, turn_index=0, question_index=0,
                question_text="Q?", response_transcript=f"an answer {i}",
            )
            db_session.add(t)
            db_session.flush()
            participants.append(p)
            turns.append(t)
        db_session.commit()
        return project, participants, turns

    def test_untagged_state(self, client, db_session, registered_company, auth_headers):
        project, _, _ = self._project_for(db_session, registered_company)
        resp = client.get(f"/projects/{project.id}/analysis/readiness", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["tagging_state"] == "untagged"
        assert body["completed_count"] == 2
        assert body["tag_count"] == 0

    def test_partial_state_with_pending_suggestions(
        self, client, db_session, registered_company, auth_headers
    ):
        project, participants, turns = self._project_for(db_session, registered_company)
        db_session.add(TagSuggestion(
            participant_id=participants[0].id, turn_id=turns[0].id,
            proposed_code_name="Friction", selected_text="an answer",
            start_index=0, end_index=9, status="pending",
        ))
        db_session.commit()
        resp = client.get(f"/projects/{project.id}/analysis/readiness", headers=auth_headers)
        body = resp.json()
        assert body["tagging_state"] == "partial"
        assert body["pending_suggestion_count"] == 1

    def test_anchored_when_half_tagged(
        self, client, db_session, registered_company, auth_headers
    ):
        project, participants, turns = self._project_for(db_session, registered_company)
        code = ManualCode(project_id=project.id, name="Friction")
        db_session.add(code)
        db_session.flush()
        db_session.add(QuoteTag(
            turn_id=turns[0].id, manual_code_id=code.id,
            selected_text="answer", start_index=3, end_index=9,
        ))
        db_session.commit()
        resp = client.get(f"/projects/{project.id}/analysis/readiness", headers=auth_headers)
        body = resp.json()
        assert body["tagging_state"] == "anchored"
        assert body["tagged_participant_count"] == 1
        assert body["code_count"] == 1

    def test_trigger_accepts_auto_tag_flag(
        self, client, db_session, registered_company, auth_headers, monkeypatch
    ):
        project, _, _ = self._project_for(db_session, registered_company)
        # Paid gate: mark the workspace as having paid so synthesis isn't 402'd.
        company = (
            db_session.query(Company).filter(Company.email == registered_company["email"]).one()
        )
        company.has_ever_paid = True
        db_session.commit()

        captured: dict = {}

        def _fake_run(project_id, db, filter_by=None, filter_values=None, auto_tag=False):
            captured["auto_tag"] = auto_tag

        import app.routers.analysis as analysis_router
        monkeypatch.setattr(analysis_router, "run_analysis", _fake_run)

        resp = client.post(
            f"/projects/{project.id}/analysis",
            json={"auto_tag": True},
            headers=auth_headers,
        )
        assert resp.status_code == 202, resp.text
        # The run happens on a daemon thread; give it a beat.
        import time
        for _ in range(50):
            if "auto_tag" in captured:
                break
            time.sleep(0.05)
        assert captured.get("auto_tag") is True
