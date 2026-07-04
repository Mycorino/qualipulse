"""Research Copilot — interview-guide surface.

Tests run with ANTHROPIC_API_KEY blanked out, so they exercise the
deterministic stub path in services/copilot_interview.py.
"""

from types import SimpleNamespace

from app.models.company import Company
from app.models.project import Project

from app.services.copilot import _suppress_opening_chips
from app.services.copilot_interview import (
    INTERVIEW_ADAPTER,
    _analysis_snapshot,
    _guide_run_tool,
    _interviews_index,
    _one_interview,
    _progress_snapshot,
    _study_snapshot,
)
from app.services.demo_seeder import seed_demo_project


def _create_project(client, auth_headers, name: str = "Interview test") -> dict:
    return client.post(
        "/projects/",
        headers=auth_headers,
        json={
            "name": name,
            "language": "en",
            "interview_duration_minutes": 20,
            "questions": [],
            "screening_questions": [],
        },
    ).json()


class TestInterviewCopilot:
    def test_proposes_objective_and_questions_for_empty_guide(
        self, client, auth_headers, drain_sse
    ):
        project = _create_project(client, auth_headers)

        resp = client.post(
            f"/projects/{project['id']}/copilot",
            headers=auth_headers,
            json={
                "messages": [
                    {"role": "user", "content": "Help me build an interview guide"}
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        data = drain_sse(resp)
        assert data["reply"]
        kinds = [a["type"] for a in data["proposed_actions"]]
        # A brand-new round with no objective: the copilot proposes the
        # research objective first, then starter questions.
        assert "edit_objective" in kinds
        assert kinds.count("add_guide_question") == 2

        objective = next(
            a for a in data["proposed_actions"] if a["type"] == "edit_objective"
        )
        assert objective["new_objective"]

        for action in data["proposed_actions"]:
            if action["type"] != "add_guide_question":
                continue
            q = action["question"]
            assert q["section_title"]
            assert q["main_question"]
            assert q["desired_learning"]
            assert q["rationale"]

    def test_copilot_accepts_active_section(self, client, auth_headers, drain_sse):
        """Tab awareness — the endpoint accepts an optional active_section
        telling the copilot which tab the researcher is viewing."""
        project = _create_project(client, auth_headers)
        resp = client.post(
            f"/projects/{project['id']}/copilot",
            headers=auth_headers,
            json={
                "messages": [{"role": "user", "content": "What should I do?"}],
                "active_section": "Analysis",
            },
        )
        assert resp.status_code == 200, resp.text
        assert drain_sse(resp)["reply"]

    def test_settings_patch_accepts_objective_and_name(self, client, auth_headers):
        """The copilot's edit_objective and inline-rename apply via /settings."""
        project = _create_project(client, auth_headers)
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            headers=auth_headers,
            json={
                "research_objective": "Understand why trial users churn.",
                "name": "Trial churn — round 1",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["research_objective"] == "Understand why trial users churn."
        assert resp.json()["name"] == "Trial churn — round 1"

    def test_conversation_round_trip(self, client, auth_headers):
        project = _create_project(client, auth_headers, name="Convo project")

        empty = client.get(
            f"/projects/{project['id']}/copilot/conversation", headers=auth_headers
        )
        assert empty.status_code == 200
        assert empty.json()["thread"] == []

        thread = [{"kind": "user", "text": "Draft the guide"}]
        client.put(
            f"/projects/{project['id']}/copilot/conversation",
            headers=auth_headers,
            json={"thread": thread},
        )
        reloaded = client.get(
            f"/projects/{project['id']}/copilot/conversation", headers=auth_headers
        )
        assert reloaded.json()["thread"] == thread

    def test_copilot_404_for_other_workspace(self, client, auth_headers):
        project = _create_project(client, auth_headers, name="A's project")
        client.post(
            "/auth/signup",
            json={"name": "B Co", "email": "bproj@example.com", "password": "Password123!"},
        )
        b_login = client.post(
            "/auth/login",
            json={"email": "bproj@example.com", "password": "Password123!"},
        ).json()
        b_headers = {"Authorization": f"Bearer {b_login['access_token']}"}

        resp = client.post(
            f"/projects/{project['id']}/copilot",
            headers=b_headers,
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 404


class TestAddGuideQuestionEndpoint:
    def test_add_question_derives_section_indices(self, client, auth_headers):
        project = _create_project(client, auth_headers, name="Guide endpoint")

        first = client.post(
            f"/projects/{project['id']}/questions",
            headers=auth_headers,
            json={
                "section_title": "Background",
                "main_question": "Tell me about your day-to-day.",
                "desired_learning": "Context.",
            },
        )
        assert first.status_code == 201, first.text
        assert first.json()["section_title"] == "Background"
        assert first.json()["section_index"] == 0

        # A second question in the same section reuses the section index.
        second = client.post(
            f"/projects/{project['id']}/questions",
            headers=auth_headers,
            json={"section_title": "Background", "main_question": "And then?"},
        )
        assert second.json()["section_index"] == 0
        assert second.json()["question_index"] == 1

        # A new section title starts a new section.
        third = client.post(
            f"/projects/{project['id']}/questions",
            headers=auth_headers,
            json={"section_title": "Experience", "main_question": "Walk me through it."},
        )
        assert third.json()["section_index"] == 1
        assert third.json()["question_index"] == 0


class TestStudyAwareInterviewCopilot:
    def test_read_study_sees_sibling_survey(self, client, auth_headers, db_session):
        """The interview copilot can see the survey in the same Study —
        so in a hybrid study it acts as the deep-dive arm."""
        project = _create_project(client, auth_headers, name="Deep dive round")
        study_id = project["study_id"]

        survey = client.post(
            "/surveys/",
            headers=auth_headers,
            json={"name": "Churn pulse", "study_id": study_id},
        ).json()
        client.post(
            f"/surveys/{survey['id']}/questions",
            headers=auth_headers,
            json={"type": "nps", "prompt": "How likely to recommend us?", "config": {}},
        )

        db_session.expire_all()
        proj = db_session.query(Project).filter(Project.id == project["id"]).one()
        snapshot = _study_snapshot(db_session, proj)

        assert len(snapshot["surveys"]) == 1
        sibling = snapshot["surveys"][0]
        assert sibling["name"] == "Churn pulse"
        assert "How likely to recommend us?" in sibling["questions"]
        assert sibling["completed_responses"] == 0
        # This round is not listed as its own sibling.
        assert snapshot["interview_rounds"] == []

    def test_read_study_empty_when_no_siblings(self, client, auth_headers, db_session):
        project = _create_project(client, auth_headers, name="Lone round")
        db_session.expire_all()
        proj = db_session.query(Project).filter(Project.id == project["id"]).one()
        snapshot = _study_snapshot(db_session, proj)
        assert snapshot["surveys"] == []
        assert snapshot["interview_rounds"] == []


class TestResultsCopilotReads:
    """The interview copilot can read this round's conducted interviews and
    analysis — so it can answer about results, not just build the guide."""

    def _seed(self, db_session) -> Project:
        company = Company(
            name="Results Co",
            email="results@example.com",
            password_hash="x",
            preferred_language="en",
        )
        db_session.add(company)
        db_session.commit()
        db_session.refresh(company)
        return seed_demo_project(db_session, company.id)

    def test_progress_snapshot_counts_completed_and_quality(self, db_session):
        project = self._seed(db_session)
        snap = _progress_snapshot(project)
        assert snap["completed_interviews"] == 4
        assert snap["in_progress"] == 0
        assert sum(snap["quality_spread"].values()) == 4
        assert snap["has_analysis"] is True

    def test_interviews_index_lists_completed_without_transcripts(self, db_session):
        project = self._seed(db_session)
        index = _interviews_index(project)
        assert len(index) == 4
        for entry in index:
            assert entry["id"]
            assert entry["name"]
            assert entry["turns"] > 0
            assert "transcript" not in entry

    def test_one_interview_returns_full_transcript(self, db_session):
        project = self._seed(db_session)
        first_id = _interviews_index(project)[0]["id"]
        interview = _one_interview(project, first_id)
        assert interview["transcript"]
        assert "Q:" in interview["transcript"] and "A:" in interview["transcript"]
        assert "profession" in interview["segments"]

    def test_one_interview_unknown_id_returns_error(self, db_session):
        project = self._seed(db_session)
        assert "error" in _one_interview(project, "does-not-exist")

    def test_analysis_snapshot_returns_latest_ready_report(self, db_session):
        project = self._seed(db_session)
        snap = _analysis_snapshot(project)
        assert snap["status"] == "ready"
        # Demo seeds two analyses (v1, v2) — latest version wins.
        assert snap["version"] == 2
        assert "themes" in snap["report"]


class TestResultsCopilotProposals:
    """Phase 2 — the copilot can propose running / refining the analysis.
    These exercise the tool executor directly (the model picks the tool)."""

    def _seed(self, db_session) -> Project:
        company = Company(
            name="Proposals Co",
            email="proposals@example.com",
            password_hash="x",
            preferred_language="en",
        )
        db_session.add(company)
        db_session.commit()
        db_session.refresh(company)
        return company, seed_demo_project(db_session, company.id)

    def test_propose_run_analysis_records_action(self, db_session):
        company, project = self._seed(db_session)
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, company, project, turn,
            "propose_run_analysis", {"rationale": "Four interviews are in."},
        )
        assert "Recorded" in msg
        assert turn.actions == [
            {"type": "run_analysis", "rationale": "Four interviews are in."}
        ]

    def test_propose_run_analysis_blocked_without_interviews(
        self, client, auth_headers, db_session
    ):
        project = _create_project(client, auth_headers, name="No data round")
        db_session.expire_all()
        proj = db_session.query(Project).filter(Project.id == project["id"]).one()
        company = proj.company
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, company, proj, turn,
            "propose_run_analysis", {"rationale": "x"},
        )
        assert "No completed interviews" in msg
        assert turn.actions == []

    def test_propose_refine_analysis_records_action(self, db_session):
        company, project = self._seed(db_session)
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, company, project, turn,
            "propose_refine_analysis", {"rationale": "Themes annotated."},
        )
        assert "Recorded" in msg
        assert turn.actions[0]["type"] == "refine_analysis"

    def test_propose_refine_analysis_blocked_without_analysis(
        self, client, auth_headers, db_session
    ):
        project = _create_project(client, auth_headers, name="Unanalysed round")
        db_session.expire_all()
        proj = db_session.query(Project).filter(Project.id == project["id"]).one()
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, proj.company, proj, turn,
            "propose_refine_analysis", {"rationale": "x"},
        )
        assert "No ready analysis" in msg
        assert turn.actions == []

    def test_suggest_replies_records_chip_options(self, db_session):
        company, project = self._seed(db_session)
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, company, project, turn,
            "suggest_replies",
            {
                "question": "Which market?",
                "options": ["FR only", " Europe ", "Other", ""],
            },
        )
        assert "Recorded" in msg
        assert turn.actions == [
            {
                "type": "suggest_replies",
                "question_text": "Which market?",
                # blanks trimmed/dropped
                "options": ["FR only", "Europe", "Other"],
            }
        ]

    def test_suggest_replies_needs_options(self, db_session):
        company, project = self._seed(db_session)
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, company, project, turn,
            "suggest_replies", {"question": "Which market?", "options": []},
        )
        assert "No reply options" in msg
        assert turn.actions == []

    def test_propose_settings_records_changed_fields(self, db_session):
        company, project = self._seed(db_session)
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, company, project, turn,
            "propose_settings",
            {
                "interview_duration_minutes": 60,
                "target_participants": 12,
                "rationale": "In-depth qual round.",
            },
        )
        assert "Recorded" in msg
        assert turn.actions[0]["type"] == "edit_settings"
        assert turn.actions[0]["settings"] == {
            "interview_duration_minutes": 60,
            "target_participants": 12,
        }

    def test_propose_settings_records_branding(self, db_session):
        company, project = self._seed(db_session)
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, company, project, turn,
            "propose_settings",
            {
                "branding_mode": "anonymous",
                "researcher_name": "  Acme Research  ",
                "rationale": "Blind study requested.",
            },
        )
        assert "Recorded" in msg
        assert turn.actions[0]["settings"] == {
            "branding_mode": "anonymous",
            "researcher_name": "Acme Research",
        }

    def test_propose_settings_drops_invalid_branding(self, db_session):
        """Hallucinated colours/fonts/modes never reach the accept flow."""
        company, project = self._seed(db_session)
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, company, project, turn,
            "propose_settings",
            {
                "branding_mode": "stealth",
                "brand_primary_color": "red",
                "brand_font": "comic-sans",
                "rationale": "Bad values.",
            },
        )
        assert "No settings" in msg
        assert turn.actions == []

    def test_propose_settings_normalises_brand_color(self, db_session):
        company, project = self._seed(db_session)
        turn = SimpleNamespace(actions=[])
        _guide_run_tool(
            db_session, company, project, turn,
            "propose_settings",
            {
                "branding_mode": "branded",
                "brand_primary_color": "#FF5500",
                "brand_font": "serif",
                "rationale": "Brand it.",
            },
        )
        assert turn.actions[0]["settings"] == {
            "branding_mode": "branded",
            "brand_primary_color": "#ff5500",
            "brand_font": "serif",
        }

    def test_opening_turn_strips_chips(self):
        """The interview opener must be a chip-free open context question."""
        actions = [
            {"type": "suggest_replies", "question_text": "Which market?", "options": ["FR"]},
            {"type": "edit_objective", "new_objective": "x"},
        ]
        out = _suppress_opening_chips(actions, INTERVIEW_ADAPTER, is_first_turn=True)
        assert [a["type"] for a in out] == ["edit_objective"]

    def test_later_turn_keeps_chips(self):
        actions = [{"type": "suggest_replies", "options": ["FR"]}]
        out = _suppress_opening_chips(actions, INTERVIEW_ADAPTER, is_first_turn=False)
        assert out == actions

    def test_propose_screening_drops_disqualifying_not_in_options(self, db_session):
        company, project = self._seed(db_session)
        turn = SimpleNamespace(actions=[])
        msg = _guide_run_tool(
            db_session, company, project, turn,
            "propose_screening_questions",
            {
                "questions": [
                    {
                        "question": "How often do you shop online?",
                        "options": ["Weekly", "Monthly"],
                        "disqualifying_options": ["Never"],
                    }
                ]
            },
        )
        assert "Recorded 1" in msg
        action = turn.actions[0]
        assert action["type"] == "add_screening_question"
        assert action["screening"]["disqualifying_options"] == []
