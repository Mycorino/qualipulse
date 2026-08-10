"""GDPR deletion tooling tests.

Covers:
- participant cascade (turns + tags gone, siblings untouched)
- project cascade (all project tables emptied, ResearchPlanStep unlinked)
- self-serve account deletion (password gate + full company cascade)
- admin retention purge (dry-run vs real, only old completed participants)
- cross-tenant 404 on DELETE /projects/{id}
- storage delete helper (local disk + path-traversal protection)
"""
import os
import uuid
from datetime import datetime, timedelta

import pytest

from app.config import settings
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
from app.models.research_plan import ResearchPlan, ResearchPlanStep

QUESTION = {
    "section_index": 0,
    "section_title": "Background",
    "question_index": 0,
    "main_question": "Tell me about yourself.",
    "interview_notes": "",
    "desired_learning": "",
}

PROJECT_PAYLOAD = {
    "name": "GDPR Project",
    "language": "en",
    "interview_duration_minutes": 20,
    "questions": [QUESTION],
    "screening_questions": [],
}


def _create_project(client, auth_headers, name="GDPR Project") -> str:
    resp = client.post(
        "/projects/", json={**PROJECT_PAYLOAD, "name": name}, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _seed_participant(db, project_id, *, name="Alice", completed_days_ago=None):
    """Create link + participant + 2 turns (with audio URLs) + a tagged quote."""
    link = InterviewLink(project_id=project_id, token=uuid.uuid4().hex)
    db.add(link)
    db.flush()

    participant = Participant(
        link_id=link.id,
        project_id=project_id,
        display_name=name,
        status="completed" if completed_days_ago is not None else "in_progress",
        completed_at=(
            datetime.utcnow() - timedelta(days=completed_days_ago)
            if completed_days_ago is not None
            else None
        ),
    )
    db.add(participant)
    db.flush()

    turns = []
    for i in range(2):
        turn = InterviewTurn(
            participant_id=participant.id,
            turn_index=i,
            question_index=0,
            question_text=f"Q{i}?",
            response_transcript=f"Answer {i} from {name}",
            audio_recording_url=f"/audio/interviews/{participant.id}/rec{i}.mp3",
            tts_audio_url=f"/audio/tts/{participant.id}/tts{i}.mp3",
        )
        db.add(turn)
        turns.append(turn)
    db.flush()

    code = ManualCode(project_id=project_id, name=f"Code-{name}", color="#ff0000")
    db.add(code)
    db.flush()
    tag = QuoteTag(
        turn_id=turns[0].id,
        manual_code_id=code.id,
        selected_text="Answer 0",
        start_index=0,
        end_index=8,
    )
    db.add(tag)
    db.commit()
    return participant, turns, tag


class TestParticipantDeletion:
    def test_participant_cascade(self, client, auth_headers, db_session):
        project_id = _create_project(client, auth_headers)
        p1, p1_turns, p1_tag = _seed_participant(db_session, project_id, name="Alice")
        p2, p2_turns, _ = _seed_participant(db_session, project_id, name="Ben")
        p1_id, p2_id, p1_tag_id = p1.id, p2.id, p1_tag.id

        resp = client.delete(
            f"/projects/{project_id}/participants/{p1_id}", headers=auth_headers
        )
        assert resp.status_code == 204

        db_session.expire_all()
        assert db_session.query(Participant).filter_by(id=p1_id).first() is None
        assert (
            db_session.query(InterviewTurn)
            .filter(InterviewTurn.participant_id == p1_id)
            .count()
            == 0
        )
        assert db_session.query(QuoteTag).filter_by(id=p1_tag_id).first() is None

        # Sibling participant untouched
        assert db_session.query(Participant).filter_by(id=p2_id).first() is not None
        assert (
            db_session.query(InterviewTurn)
            .filter(InterviewTurn.participant_id == p2_id)
            .count()
            == 2
        )

    def test_participant_delete_404_for_other_company(self, client, auth_headers, db_session):
        project_id = _create_project(client, auth_headers)
        p1, _, _ = _seed_participant(db_session, project_id)

        client.post(
            "/auth/signup",
            json={"name": "Other", "email": "other@example.com", "password": "Pass1234!"},
        )
        login = client.post(
            "/auth/login", json={"email": "other@example.com", "password": "Pass1234!"}
        )
        other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = client.delete(
            f"/projects/{project_id}/participants/{p1.id}", headers=other_headers
        )
        assert resp.status_code == 404
        assert db_session.query(Participant).filter_by(id=p1.id).first() is not None


class TestProjectDeletion:
    def test_project_cascade(self, client, auth_headers, db_session):
        project_id = _create_project(client, auth_headers, name="Doomed")
        keep_project_id = None  # starter tier caps at 1 project; seed second directly
        company = db_session.query(Company).filter_by(email="test@example.com").first()
        keep = Project(company_id=company.id, name="Keeper", language="en")
        db_session.add(keep)
        db_session.commit()
        keep_project_id = keep.id

        _seed_participant(db_session, project_id)
        _seed_participant(db_session, keep_project_id, name="KeeperP")

        analysis = ProjectAnalysis(
            project_id=project_id, version=1, status="ready", report="{}"
        )
        db_session.add(analysis)
        db_session.flush()
        db_session.add(
            AnalysisThemeAnnotation(
                analysis_id=analysis.id, theme_title="T", status="confirmed"
            )
        )
        db_session.add(ProjectMemo(project_id=project_id, type="general", content="m"))
        db_session.add(
            ScreeningQuestion(
                project_id=project_id, question="Q?", options="[]",
                disqualifying_options="[]",
            )
        )
        plan = ResearchPlan(company_id=company.id, name="Plan")
        db_session.add(plan)
        db_session.flush()
        step = ResearchPlanStep(
            plan_id=plan.id,
            order_index=0,
            method="voice_interview",
            title="Interviews",
            project_id=project_id,
            status="drafted",
        )
        db_session.add(step)
        db_session.commit()
        analysis_id, step_id = analysis.id, step.id

        resp = client.delete(f"/projects/{project_id}", headers=auth_headers)
        assert resp.status_code == 204

        db_session.expire_all()
        assert db_session.query(Project).filter_by(id=project_id).first() is None
        for model in (
            Participant,
            InterviewLink,
            ProjectAnalysis,
            ManualCode,
            ProjectMemo,
            InterviewGuideQuestion,
            ScreeningQuestion,
        ):
            assert (
                db_session.query(model).filter_by(project_id=project_id).count() == 0
            ), f"{model.__name__} rows survived project deletion"
        assert (
            db_session.query(AnalysisThemeAnnotation)
            .filter_by(analysis_id=analysis_id)
            .count()
            == 0
        )
        # Research-plan step survives but is unlinked
        surviving_step = db_session.query(ResearchPlanStep).filter_by(id=step_id).first()
        assert surviving_step is not None
        assert surviving_step.project_id is None

        # Other project untouched
        assert db_session.query(Project).filter_by(id=keep_project_id).first() is not None
        assert (
            db_session.query(Participant).filter_by(project_id=keep_project_id).count()
            == 1
        )

    def test_delete_other_company_project_404(self, client, auth_headers, db_session):
        project_id = _create_project(client, auth_headers)

        client.post(
            "/auth/signup",
            json={"name": "Other", "email": "other2@example.com", "password": "Pass1234!"},
        )
        login = client.post(
            "/auth/login", json={"email": "other2@example.com", "password": "Pass1234!"}
        )
        other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = client.delete(f"/projects/{project_id}", headers=other_headers)
        assert resp.status_code == 404
        assert db_session.query(Project).filter_by(id=project_id).first() is not None


class TestAccountDeletion:
    def test_password_required(self, client, auth_headers):
        resp = client.post("/auth/delete-account", json={}, headers=auth_headers)
        assert resp.status_code == 403

    def test_wrong_password_403(self, client, auth_headers, db_session):
        resp = client.post(
            "/auth/delete-account", json={"password": "WrongPass1"}, headers=auth_headers
        )
        assert resp.status_code == 403
        assert (
            db_session.query(Company).filter_by(email="test@example.com").first()
            is not None
        )

    def test_correct_password_deletes_everything(self, client, auth_headers, db_session):
        project_id = _create_project(client, auth_headers)
        _seed_participant(db_session, project_id)
        company = db_session.query(Company).filter_by(email="test@example.com").first()
        company_id = company.id

        resp = client.post(
            "/auth/delete-account",
            json={"password": "Password123!"},
            headers=auth_headers,
        )
        assert resp.status_code == 204

        db_session.expire_all()
        assert db_session.query(Company).filter_by(id=company_id).first() is None
        assert (
            db_session.query(Project).filter_by(company_id=company_id).count() == 0
        )
        assert db_session.query(Participant).count() == 0
        assert db_session.query(InterviewTurn).count() == 0

        # Old token no longer works
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 401

    def test_oauth_only_account_requires_delete_confirm(
        self, client, auth_headers, db_session
    ):
        company = db_session.query(Company).filter_by(email="test@example.com").first()
        company.password_hash = None
        db_session.commit()

        resp = client.post(
            "/auth/delete-account", json={"confirm": "nope"}, headers=auth_headers
        )
        assert resp.status_code == 400

        resp = client.post(
            "/auth/delete-account", json={"confirm": "DELETE"}, headers=auth_headers
        )
        assert resp.status_code == 204
        assert (
            db_session.query(Company).filter_by(email="test@example.com").first() is None
        )


ADMIN_KEY = "test-admin-secret-gdpr"


@pytest.fixture
def admin_headers():
    prev = settings.ADMIN_SECRET_KEY
    settings.ADMIN_SECRET_KEY = ADMIN_KEY
    try:
        yield {"Authorization": f"Bearer {ADMIN_KEY}", "X-Admin-Identity": "tester"}
    finally:
        settings.ADMIN_SECRET_KEY = prev


class TestRetentionPurge:
    def test_disabled_by_default(self, client, admin_headers):
        resp = client.post("/admin/retention/run", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_dry_run_counts_without_deleting(self, client, auth_headers, db_session, admin_headers):
        project_id = _create_project(client, auth_headers)
        old, old_turns, _ = _seed_participant(
            db_session, project_id, name="Old", completed_days_ago=100
        )

        resp = client.post(
            "/admin/retention/run?dry_run=true&days=30", headers=admin_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dry_run"] is True
        assert body["participants"] == 1
        assert body["turns"] == 2

        db_session.expire_all()
        turn = db_session.query(InterviewTurn).filter_by(id=old_turns[0].id).first()
        assert turn.audio_recording_url is not None
        assert turn.tts_audio_url is not None

    def test_real_run_nulls_only_old_completed(
        self, client, auth_headers, db_session, admin_headers
    ):
        project_id = _create_project(client, auth_headers)
        old, old_turns, _ = _seed_participant(
            db_session, project_id, name="Old", completed_days_ago=100
        )
        recent, recent_turns, _ = _seed_participant(
            db_session, project_id, name="Recent", completed_days_ago=5
        )
        in_progress, ip_turns, _ = _seed_participant(
            db_session, project_id, name="Ongoing"
        )

        resp = client.post("/admin/retention/run?days=30", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["participants"] == 1
        assert body["turns"] == 2

        db_session.expire_all()
        for t in old_turns:
            row = db_session.query(InterviewTurn).filter_by(id=t.id).first()
            assert row.audio_recording_url is None
            assert row.tts_audio_url is None
            assert row.response_transcript  # transcripts kept
        for t in list(recent_turns) + list(ip_turns):
            row = db_session.query(InterviewTurn).filter_by(id=t.id).first()
            assert row.audio_recording_url is not None
            assert row.tts_audio_url is not None


class TestStorageDeleteHelper:
    def test_deletes_local_file(self, tmp_path):
        from app.services import storage

        prev = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = str(tmp_path)
        try:
            key = "interviews/p1/rec.mp3"
            path = tmp_path / key
            path.parent.mkdir(parents=True)
            path.write_bytes(b"audio")
            assert storage.delete_audio(key) is True
            assert not path.exists()
            # Idempotent: second delete just reports False
            assert storage.delete_audio(key) is False
        finally:
            settings.UPLOAD_DIR = prev

    def test_refuses_path_traversal(self, tmp_path):
        from app.services import storage

        outside = tmp_path / "outside.txt"
        outside.write_bytes(b"secret")
        uploads = tmp_path / "uploads"
        uploads.mkdir()

        prev = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = str(uploads)
        try:
            assert storage.delete_audio("../outside.txt") is False
            assert outside.exists()
        finally:
            settings.UPLOAD_DIR = prev

    def test_delete_by_url(self, tmp_path):
        from app.services import storage

        prev = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = str(tmp_path)
        try:
            key = "tts/p1/clip.mp3"
            path = tmp_path / key
            path.parent.mkdir(parents=True)
            path.write_bytes(b"audio")
            assert storage.delete_audio_by_url(f"/audio/{key}") is True
            assert not path.exists()
            assert storage.delete_audio_by_url("") is False
            assert storage.delete_audio_by_url("https://elsewhere.example/x") is False
        finally:
            settings.UPLOAD_DIR = prev
