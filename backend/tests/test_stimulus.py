"""Stimulus assets: the artefact a participant is shown mid-interview.

Covers the library CRUD, the ownership boundary, the guide-question
attachment, what reaches the participant payload, and what the interviewer
prompt is told.
"""
import io

import pytest

QUESTION = {
    "section_index": 0,
    "section_title": "Concept",
    "question_index": 0,
    "main_question": "What do you make of this?",
    "interview_notes": "",
    "desired_learning": "",
}

PROJECT_PAYLOAD = {
    "name": "Concept test",
    "language": "en",
    "interview_duration_minutes": 20,
    "questions": [QUESTION],
    "screening_questions": [],
}

# Smallest valid PNG: 1x1, transparent.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def project(client, auth_headers):
    resp = client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_text_stimulus(client, auth_headers, project_id, **overrides):
    payload = {
        "name": "Concept A",
        "kind": "text",
        "body": "A refillable pouch that costs 30% less than the bottle.",
        "caption": "Take a moment to read this.",
        "ai_description": "Watch for reactions to the refill format, not the price.",
        **overrides,
    }
    return client.post(
        f"/projects/{project_id}/stimuli", json=payload, headers=auth_headers
    )


class TestStimulusCrud:
    def test_create_text_stimulus(self, client, auth_headers, project):
        resp = _make_text_stimulus(client, auth_headers, project["id"])
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["kind"] == "text"
        assert data["body"].startswith("A refillable pouch")
        assert data["question_count"] == 0

    def test_text_stimulus_requires_body(self, client, auth_headers, project):
        resp = _make_text_stimulus(client, auth_headers, project["id"], body="  ")
        assert resp.status_code == 400

    def test_image_kind_rejected_on_json_endpoint(self, client, auth_headers, project):
        """Images must go through the upload endpoint so the magic-byte
        check runs; a JSON create could otherwise set an arbitrary URL."""
        resp = _make_text_stimulus(client, auth_headers, project["id"], kind="image")
        assert resp.status_code == 400

    def test_unknown_kind_rejected(self, client, auth_headers, project):
        resp = _make_text_stimulus(client, auth_headers, project["id"], kind="video")
        assert resp.status_code == 422

    def test_upload_image_stimulus(self, client, auth_headers, project, tmp_path, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
        resp = client.post(
            f"/projects/{project['id']}/stimuli/upload",
            files={"file": ("pack.png", io.BytesIO(PNG_BYTES), "image/png")},
            data={"name": "Pack A", "caption": "Have a look at this pack."},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["kind"] == "image"
        assert data["url"]
        assert data["name"] == "Pack A"

    def test_upload_rejects_mismatched_content(self, client, auth_headers, project, tmp_path, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
        resp = client.post(
            f"/projects/{project['id']}/stimuli/upload",
            files={"file": ("evil.png", io.BytesIO(b"not a png at all"), "image/png")},
            data={"name": "Nope"},
            headers=auth_headers,
        )
        assert resp.status_code == 415

    def test_list_and_patch(self, client, auth_headers, project):
        sid = _make_text_stimulus(client, auth_headers, project["id"]).json()["id"]
        resp = client.patch(
            f"/projects/{project['id']}/stimuli/{sid}",
            json={"name": "Concept A (v2)"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Concept A (v2)"

        listed = client.get(f"/projects/{project['id']}/stimuli", headers=auth_headers)
        assert [a["name"] for a in listed.json()] == ["Concept A (v2)"]

    def test_delete_leaves_the_question_standing(self, client, auth_headers, project, db_session):
        """Deleting an asset unsticks the picture. It must never take the
        guide question with it."""
        sid = _make_text_stimulus(client, auth_headers, project["id"]).json()["id"]
        qid = project["questions"][0]["id"]
        client.patch(
            f"/projects/{project['id']}/questions/{qid}",
            json={"stimulus_id": sid},
            headers=auth_headers,
        )
        resp = client.delete(
            f"/projects/{project['id']}/stimuli/{sid}", headers=auth_headers
        )
        assert resp.status_code == 204

        detail = client.get(f"/projects/{project['id']}", headers=auth_headers).json()
        assert len(detail["questions"]) == 1
        assert detail["questions"][0]["stimulus_id"] is None
        assert detail["stimuli"] == []


class TestOwnership:
    def test_cannot_read_another_companys_stimuli(self, client, auth_headers, project):
        other = client.post(
            "/auth/signup",
            json={"name": "Other Co", "email": "other@example.com", "password": "Password123!"},
        ).json()
        headers = {"Authorization": f"Bearer {other['access_token']}"}
        resp = client.get(f"/projects/{project['id']}/stimuli", headers=headers)
        assert resp.status_code == 404

    def test_cannot_attach_a_foreign_asset(self, client, auth_headers, project, db_session):
        """A stimulus id from another study must not be attachable: it would
        surface that study's artefact in this study's interview payload."""
        from app.models.company import Company
        from app.models.project import Project, StimulusAsset

        other_company = Company(name="Other", email="foreign@example.com", password_hash="x")
        db_session.add(other_company)
        db_session.flush()
        other_project = Project(company_id=other_company.id, name="Theirs")
        db_session.add(other_project)
        db_session.flush()
        foreign = StimulusAsset(project_id=other_project.id, name="Their pack", kind="text", body="x")
        db_session.add(foreign)
        db_session.commit()

        qid = project["questions"][0]["id"]
        resp = client.patch(
            f"/projects/{project['id']}/questions/{qid}",
            json={"stimulus_id": foreign.id},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestAttachment:
    def test_attach_and_clear(self, client, auth_headers, project):
        sid = _make_text_stimulus(client, auth_headers, project["id"]).json()["id"]
        qid = project["questions"][0]["id"]

        attached = client.patch(
            f"/projects/{project['id']}/questions/{qid}",
            json={"stimulus_id": sid},
            headers=auth_headers,
        )
        assert attached.status_code == 200
        assert attached.json()["stimulus_id"] == sid

        listed = client.get(f"/projects/{project['id']}/stimuli", headers=auth_headers)
        assert listed.json()[0]["question_count"] == 1

        cleared = client.patch(
            f"/projects/{project['id']}/questions/{qid}",
            json={"clear_stimulus": True},
            headers=auth_headers,
        )
        assert cleared.json()["stimulus_id"] is None

    def test_patching_other_fields_leaves_the_attachment_alone(self, client, auth_headers, project):
        """An absent stimulus_id means unchanged, not detach: the Setup tab
        patches notes and wording constantly."""
        sid = _make_text_stimulus(client, auth_headers, project["id"]).json()["id"]
        qid = project["questions"][0]["id"]
        client.patch(
            f"/projects/{project['id']}/questions/{qid}",
            json={"stimulus_id": sid},
            headers=auth_headers,
        )
        resp = client.patch(
            f"/projects/{project['id']}/questions/{qid}",
            json={"researcher_notes": "probe the refill format"},
            headers=auth_headers,
        )
        assert resp.json()["stimulus_id"] == sid


class TestEnginePlumbing:
    def test_guide_string_names_the_stimulus(self, db_session):
        from app.models.company import Company
        from app.models.project import (
            InterviewGuideQuestion,
            Project,
            StimulusAsset,
        )
        from app.services.interview_engine import _build_interview_guide_str

        company = Company(name="C", email="e@example.com", password_hash="x")
        db_session.add(company)
        db_session.flush()
        project = Project(company_id=company.id, name="P")
        db_session.add(project)
        db_session.flush()
        asset = StimulusAsset(
            project_id=project.id,
            name="Pack A",
            kind="text",
            body="Refill pouch, 30% cheaper.",
            ai_description="Watch for format reactions.",
        )
        db_session.add(asset)
        db_session.flush()
        db_session.add(
            InterviewGuideQuestion(
                project_id=project.id,
                section_index=0,
                section_title="Concept",
                question_index=0,
                main_question="What do you make of this?",
                stimulus_id=asset.id,
            )
        )
        db_session.commit()
        db_session.refresh(project)

        guide = _build_interview_guide_str(project)
        assert "Stimulus on screen: Pack A" in guide
        assert "Refill pouch, 30% cheaper." in guide
        assert "Watch for format reactions." in guide

    def test_payload_hides_the_ai_briefing(self, db_session):
        """ai_description is the researcher briefing the interviewer. It must
        never reach the participant's browser."""
        from app.models.project import StimulusAsset
        from app.services.interview_engine import stimulus_payload

        asset = StimulusAsset(
            project_id="p", name="Pack A", kind="image",
            url="https://cdn.example/pack.png",
            caption="Have a look.",
            ai_description="Do not reveal: this is the challenger pack.",
        )
        payload = stimulus_payload(asset)
        assert payload["url"] == "https://cdn.example/pack.png"
        assert payload["caption"] == "Have a look."
        assert "ai_description" not in payload
        assert "challenger" not in str(payload)

    def test_payload_is_none_without_an_asset(self):
        from app.services.interview_engine import stimulus_payload

        assert stimulus_payload(None) is None

    def test_lookup_ignores_deprecated_questions(self, db_session):
        """question_index is the ordinal into the live guide, so a deprecated
        question must not shift which asset a later question resolves to."""
        from app.models.company import Company
        from app.models.project import (
            InterviewGuideQuestion,
            Project,
            StimulusAsset,
        )
        from app.services.interview_engine import stimulus_for_question_index
        from datetime import datetime

        company = Company(name="C", email="e2@example.com", password_hash="x")
        db_session.add(company)
        db_session.flush()
        project = Project(company_id=company.id, name="P")
        db_session.add(project)
        db_session.flush()
        asset = StimulusAsset(project_id=project.id, name="Pack A", kind="text", body="x")
        db_session.add(asset)
        db_session.flush()
        db_session.add_all([
            InterviewGuideQuestion(
                project_id=project.id, section_index=0, section_title="S",
                question_index=0, main_question="dropped",
                deprecated_at=datetime.utcnow(),
            ),
            InterviewGuideQuestion(
                project_id=project.id, section_index=0, section_title="S",
                question_index=1, main_question="live", stimulus_id=asset.id,
            ),
        ])
        db_session.commit()
        db_session.refresh(project)

        # The live guide has one question, at ordinal 0.
        assert stimulus_for_question_index(project, 0) is not None
        assert stimulus_for_question_index(project, 1) is None

    def test_lookup_tolerates_sentinel_indices(self, db_session):
        """Warm-up and final-check turns use negative sentinels."""
        from app.models.company import Company
        from app.models.project import Project
        from app.services.interview_engine import stimulus_for_question_index

        company = Company(name="C", email="e3@example.com", password_hash="x")
        db_session.add(company)
        db_session.flush()
        project = Project(company_id=company.id, name="P")
        db_session.add(project)
        db_session.commit()

        assert stimulus_for_question_index(project, None) is None
        assert stimulus_for_question_index(project, -1) is None
        assert stimulus_for_question_index(project, 99) is None


class TestDecisionCall:
    """What actually reaches Claude when a stimulus is on screen."""

    def _capture(self, monkeypatch):
        """Stub the Anthropic client and return the captured kwargs."""
        captured = {}

        class _FakeBlock:
            type = "tool_use"
            name = "interview_decision"
            input = {"action": "follow_up", "question": "What stands out?"}

        class _FakeResponse:
            content = [_FakeBlock()]
            usage = None

        class _FakeMessages:
            def create(self, **kwargs):
                captured.update(kwargs)
                return _FakeResponse()

        class _FakeClient:
            messages = _FakeMessages()

        from app.services import interview_engine

        monkeypatch.setattr(
            interview_engine, "get_anthropic_client", lambda *a, **k: _FakeClient()
        )
        return captured

    def _call(self, **overrides):
        from app.services.interview_engine import decide_next_action

        kwargs = dict(
            system_prompt="You are an interviewer.",
            interview_guide_str="Q1: What do you make of this?",
            conversation_history="",
            current_question_index=0,
            elapsed_minutes=1.0,
            total_minutes=20,
            all_questions_done=False,
            total_questions=1,
            language="en",
        )
        kwargs.update(overrides)
        return decide_next_action(**kwargs)

    def _message_text(self, captured):
        return "".join(
            b["text"] for b in captured["messages"][0]["content"] if b["type"] == "text"
        )

    def test_no_stimulus_sends_plain_text(self, monkeypatch):
        captured = self._capture(monkeypatch)
        self._call()
        blocks = captured["messages"][0]["content"]
        assert [b["type"] for b in blocks] == ["text"]
        assert "<stimulus>" not in self._message_text(captured)

    def test_text_stimulus_briefs_the_model(self, monkeypatch):
        from app.models.project import StimulusAsset

        captured = self._capture(monkeypatch)
        asset = StimulusAsset(
            project_id="p", name="Concept A", kind="text",
            body="A refillable pouch, 30% cheaper.",
            ai_description="Watch for format reactions.",
        )
        self._call(stimulus=asset)
        text = self._message_text(captured)
        assert "<stimulus>" in text
        assert "Concept A" in text
        assert "refillable pouch" in text
        # A text concept has no picture, so no image block is sent.
        assert [b["type"] for b in captured["messages"][0]["content"]] == ["text"]

    def test_image_stimulus_is_sent_as_a_cached_prefix(self, monkeypatch, tmp_path):
        """The picture leads the message and carries the cache breakpoint, so
        every later turn on the same question reads it from cache."""
        from app.config import settings
        from app.models.project import StimulusAsset

        (tmp_path / "stimuli").mkdir()
        img = tmp_path / "stimuli" / "pack.png"
        img.write_bytes(PNG_BYTES)
        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

        from app.services import interview_engine

        interview_engine._STIMULUS_IMAGE_CACHE.clear()
        captured = self._capture(monkeypatch)
        asset = StimulusAsset(
            project_id="p", name="Pack A", kind="image",
            url="/api/files/stimuli/pack.png",
        )
        self._call(stimulus=asset)

        blocks = captured["messages"][0]["content"]
        assert [b["type"] for b in blocks] == ["image", "text"]
        assert blocks[0]["source"]["media_type"] == "image/png"
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}

    def test_missing_image_degrades_to_text(self, monkeypatch, tmp_path):
        """A dead URL must cost the interviewer some specificity, never the
        participant their turn."""
        from app.config import settings
        from app.models.project import StimulusAsset
        from app.services import interview_engine

        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
        interview_engine._STIMULUS_IMAGE_CACHE.clear()
        captured = self._capture(monkeypatch)
        asset = StimulusAsset(
            project_id="p", name="Pack A", kind="image",
            url="/api/files/stimuli/does-not-exist.png",
        )
        result = self._call(stimulus=asset)

        assert result["action"] == "follow_up"
        assert [b["type"] for b in captured["messages"][0]["content"]] == ["text"]
        assert "<stimulus>" in self._message_text(captured)

    def test_image_path_escape_is_refused(self, monkeypatch, tmp_path):
        """A URL that walks out of UPLOAD_DIR must not read arbitrary files."""
        from app.config import settings
        from app.models.project import StimulusAsset
        from app.services import interview_engine

        secret = tmp_path / "secret.png"
        secret.write_bytes(PNG_BYTES)
        upload = tmp_path / "uploads"
        upload.mkdir()
        monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload))
        interview_engine._STIMULUS_IMAGE_CACHE.clear()

        asset = StimulusAsset(
            project_id="p", name="Escape", kind="image",
            url="/api/files/../secret.png",
        )
        assert interview_engine._stimulus_image_block(asset) is None


class TestAnalysisAwareness:
    """The synthesis prompt knows what each named material was and which
    turns were answered in front of it."""

    def _seed_interview(self, db_session, *, with_stimulus=True):
        from app.models.company import Company
        from app.models.interview import InterviewLink, InterviewTurn, Participant
        from app.models.project import Project, StimulusAsset

        company = Company(name="C", email="an@example.com", password_hash="x")
        db_session.add(company)
        db_session.flush()
        project = Project(company_id=company.id, name="P")
        db_session.add(project)
        db_session.flush()
        link = InterviewLink(project_id=project.id, token="tok-analysis-1")
        db_session.add(link)
        db_session.flush()
        participant = Participant(
            link_id=link.id, project_id=project.id,
            display_name="Ana", status="completed",
        )
        db_session.add(participant)
        db_session.flush()

        stim = None
        if with_stimulus:
            stim = StimulusAsset(
                project_id=project.id, name="Pack A", kind="text",
                body="Refill pouch, 30% cheaper.",
                caption="Take a look.",
                ai_description="Watch for format reactions.",
            )
            db_session.add(stim)
            db_session.flush()

        db_session.add(
            InterviewTurn(
                participant_id=participant.id, turn_index=0, question_index=0,
                is_follow_up=False, follow_up_index=0,
                question_text="What stands out?",
                response_transcript="The pouch looks cheap to me.",
                stimulus_id=stim.id if stim else None,
            )
        )
        db_session.commit()
        db_session.refresh(participant)
        return participant

    def test_transcript_q_lines_carry_the_material_label(self, db_session):
        from app.services.analysis import _build_transcripts_block

        participant = self._seed_interview(db_session)
        block, _ = _build_transcripts_block([participant])
        assert '[material shown: "Pack A"]' in block

    def test_stimulus_block_glosses_each_material(self, db_session):
        from app.services.analysis import _build_stimulus_block

        participant = self._seed_interview(db_session)
        block = _build_stimulus_block([participant])
        assert "MATERIALS SHOWN" in block
        assert '"Pack A" (text)' in block
        assert "Refill pouch, 30% cheaper." in block
        assert "Watch for format reactions." in block

    def test_no_stimulus_leaves_prompt_untouched(self, db_session):
        from app.services.analysis import (
            _build_stimulus_block,
            _build_transcripts_block,
        )

        participant = self._seed_interview(db_session, with_stimulus=False)
        assert _build_stimulus_block([participant]) == ""
        block, _ = _build_transcripts_block([participant])
        assert "[material shown" not in block


class TestResearcherSurface:
    def test_transcript_endpoint_names_the_material(
        self, client, auth_headers, project, db_session
    ):
        """The Responses view can say what was on screen for each turn."""
        from app.models.interview import InterviewLink, InterviewTurn, Participant
        from app.models.project import StimulusAsset

        stim = StimulusAsset(project_id=project["id"], name="Pack A", kind="text", body="B.")
        db_session.add(stim)
        db_session.flush()
        link = InterviewLink(project_id=project["id"], token="tok-surface-1")
        db_session.add(link)
        db_session.flush()
        participant = Participant(
            link_id=link.id, project_id=project["id"],
            display_name="Sam", status="completed",
        )
        db_session.add(participant)
        db_session.flush()
        db_session.add(
            InterviewTurn(
                participant_id=participant.id, turn_index=0, question_index=0,
                is_follow_up=False, follow_up_index=0,
                question_text="What stands out?",
                response_transcript="Looks fine.",
                stimulus_id=stim.id,
            )
        )
        db_session.commit()

        resp = client.get(
            f"/projects/{project['id']}/participants/{participant.id}/transcript",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        turn = resp.json()["turns"][0]
        assert turn["stimulus_name"] == "Pack A"
        assert turn["stimulus_kind"] == "text"


class TestFailureCacheTtl:
    def test_failed_fetch_is_retried_after_the_ttl(self, monkeypatch, tmp_path):
        """A transient blip must not blind the interviewer for the process
        lifetime: the cached failure expires and the next turn retries."""
        from app.config import settings
        from app.models.project import StimulusAsset
        from app.services import interview_engine

        (tmp_path / "stimuli").mkdir()
        img = tmp_path / "stimuli" / "pack.png"
        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
        interview_engine._STIMULUS_IMAGE_CACHE.clear()
        interview_engine._STIMULUS_FAILURE_AT.clear()

        asset = StimulusAsset(
            project_id="p", name="Pack A", kind="image",
            url="/api/files/stimuli/pack.png",
        )
        # First read fails (file absent) and the failure is cached.
        assert interview_engine._stimulus_image_block(asset) is None
        # The file appears (blip over), but the failure cache still holds.
        img.write_bytes(PNG_BYTES)
        assert interview_engine._stimulus_image_block(asset) is None
        # Past the TTL the failure entry expires and the image loads.
        stale = next(iter(interview_engine._STIMULUS_FAILURE_AT))
        interview_engine._STIMULUS_FAILURE_AT[stale] -= (
            interview_engine._STIMULUS_FAILURE_TTL_SECONDS + 1
        )
        block = interview_engine._stimulus_image_block(asset)
        assert block is not None
        assert block["source"]["media_type"] == "image/png"
