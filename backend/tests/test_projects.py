"""Tests for /projects endpoints."""
import pytest

QUESTION = {
    "section_index": 0,
    "section_title": "Background",
    "question_index": 0,
    "main_question": "Tell me about yourself.",
    "interview_notes": "",
    "desired_learning": "",
}

PROJECT_PAYLOAD = {
    "name": "Test Project",
    "language": "en",
    "interview_duration_minutes": 20,
    "questions": [QUESTION],
    "screening_questions": [],
}


class TestCreateProject:
    def test_create_project_returns_201(self, client, auth_headers):
        resp = client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Project"
        assert len(data["questions"]) == 1

    def test_create_project_requires_auth(self, client):
        resp = client.post("/projects/", json=PROJECT_PAYLOAD)
        assert resp.status_code == 401

    def test_starter_project_limit(self, client, auth_headers):
        """New signups get starter-tier limits (1 project)."""
        resp = client.post("/projects/", json={**PROJECT_PAYLOAD, "name": "Project 0"}, headers=auth_headers)
        assert resp.status_code == 201, f"First project should succeed: {resp.text}"
        resp = client.post("/projects/", json={**PROJECT_PAYLOAD, "name": "Over Limit"}, headers=auth_headers)
        assert resp.status_code == 403
        assert "limit" in resp.json()["detail"].lower()

    def test_starter_question_limit(self, client, auth_headers):
        """New signups get starter limits (10 questions); 11 should be rejected."""
        questions = [
            {**QUESTION, "question_index": i, "main_question": f"Q{i}"}
            for i in range(11)
        ]
        resp = client.post("/projects/", json={**PROJECT_PAYLOAD, "questions": questions}, headers=auth_headers)
        assert resp.status_code == 403


class TestGetProject:
    def test_get_own_project(self, client, auth_headers):
        create_resp = client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers)
        project_id = create_resp.json()["id"]
        resp = client.get(f"/projects/{project_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == project_id

    def test_cannot_get_other_company_project(self, client, auth_headers):
        # Create project with first account
        create_resp = client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers)
        project_id = create_resp.json()["id"]

        # Register a second account
        client.post("/auth/signup", json={"name": "Other Co", "email": "other@example.com", "password": "Pass123!"})
        login_resp = client.post("/auth/login", json={"email": "other@example.com", "password": "Pass123!"})
        other_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        resp = client.get(f"/projects/{project_id}", headers=other_headers)
        assert resp.status_code == 404

    def test_get_nonexistent_project_returns_404(self, client, auth_headers):
        resp = client.get("/projects/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404


class TestListProjects:
    def test_list_projects_returns_only_own(self, client, auth_headers):
        client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers)
        resp = client.get("/projects/", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestArchiveProject:
    def test_archive_and_unarchive(self, client, auth_headers):
        create_resp = client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers)
        project_id = create_resp.json()["id"]

        # Archive
        resp = client.patch(f"/projects/{project_id}/archive", headers=auth_headers)
        assert resp.status_code == 200

        # Should not appear in active list
        active = client.get("/projects/", headers=auth_headers)
        assert all(p["id"] != project_id for p in active.json())

        # Should appear in archived list
        archived = client.get("/projects/?archived=true", headers=auth_headers)
        assert any(p["id"] == project_id for p in archived.json())

        # Unarchive
        resp = client.patch(f"/projects/{project_id}/unarchive", headers=auth_headers)
        assert resp.status_code == 200

        active = client.get("/projects/", headers=auth_headers)
        assert any(p["id"] == project_id for p in active.json())


class TestSetupCopilotEndpoints:
    """Endpoints powering the interview-setup Research Copilot's accept flow."""

    def _make_project(self, client, auth_headers):
        return client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]

    def test_patch_settings_duration_and_target(self, client, auth_headers):
        pid = self._make_project(client, auth_headers)
        resp = client.patch(
            f"/projects/{pid}/settings",
            json={"interview_duration_minutes": 60, "target_participants": 12},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["interview_duration_minutes"] == 60
        assert data["target_participants"] == 12

    def test_add_guide_question_persists_researcher_notes(self, client, auth_headers):
        """The Copilot's rationale lands in the question note on accept."""
        pid = self._make_project(client, auth_headers)
        resp = client.post(
            f"/projects/{pid}/questions",
            json={
                "section_title": "Experience",
                "main_question": "Walk me through the last time.",
                "desired_learning": "A concrete story.",
                "researcher_notes": "Anchors a real incident, not an opinion.",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["researcher_notes"] == "Anchors a real incident, not an opinion."

    def test_add_screening_question(self, client, auth_headers):
        pid = self._make_project(client, auth_headers)
        resp = client.post(
            f"/projects/{pid}/screening",
            json={
                "question": "Have you used PayPal in the last 6 months?",
                "options": ["Yes", "No"],
                "disqualifying_options": ["No"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["question"].startswith("Have you used PayPal")
        assert data["disqualifying_options"] == ["No"]
        # And it shows up on the project.
        proj = client.get(f"/projects/{pid}", headers=auth_headers).json()
        assert any(sq["id"] == data["id"] for sq in proj["screening_questions"])

    def test_add_screening_drops_disqualifying_not_in_options(self, client, auth_headers):
        pid = self._make_project(client, auth_headers)
        resp = client.post(
            f"/projects/{pid}/screening",
            json={
                "question": "How often do you shop online?",
                "options": ["Weekly", "Monthly"],
                "disqualifying_options": ["Never"],  # not an option
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["disqualifying_options"] == []


class TestCreditsAccountProjectLimit:
    """Credits-based accounts are gated by interview credits, not project
    count — they can create unlimited studies."""

    def test_credits_account_is_not_capped_by_project_count(
        self, client, auth_headers, db_session, registered_company
    ):
        from app.models.company import Company
        from app.services import billing_service

        company = (
            db_session.query(Company)
            .filter(Company.email == registered_company["email"])
            .first()
        )
        # Seed the plan catalogue into the test DB (startup seeds the app's
        # engine, not this session), then put the account on the
        # credits-native trial plan (is_legacy=False).
        billing_service.ensure_plans_seeded(db_session)
        billing_service.bootstrap_trial_subscription(db_session, company)
        db_session.commit()

        # Starter legacy cap is 1 project; credits accounts ignore it.
        for i in range(3):
            resp = client.post(
                "/projects/",
                json={**PROJECT_PAYLOAD, "name": f"Credits Study {i}"},
                headers=auth_headers,
            )
            assert resp.status_code == 201, f"project {i} should succeed: {resp.text}"


class TestUpdateProject:
    """PUT /projects/{id} — the Setup tab saves one section at a time, so the
    endpoint has to be partial by field."""

    def _create(self, client, auth_headers):
        resp = client.post(
            "/projects/",
            json={**PROJECT_PAYLOAD, "screening_questions": [
                {"question": "Do you work in hospitality?", "options": ["Yes", "No"],
                 "disqualifying_options": ["No"]},
            ]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_saving_screening_questions_succeeds(self, client, auth_headers):
        """Regression: the handler read `body.research_context`, a field that
        did not exist on ProjectCreate, so every PUT raised AttributeError."""
        project_id = self._create(client, auth_headers)
        resp = client.put(
            f"/projects/{project_id}",
            json={
                "name": "Test Project",
                "language": "en",
                "interview_duration_minutes": 20,
                "research_objective": None,
                "questions": [QUESTION],
                "screening_questions": [
                    {"question": "Do you work in hospitality?", "options": ["Yes", "No"],
                     "disqualifying_options": ["No"]},
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        screening = resp.json()["screening_questions"]
        assert len(screening) == 1
        assert screening[0]["disqualifying_options"] == ["No"]

    def test_omitted_fields_are_left_alone(self, client, auth_headers):
        """Saving the screening section must not wipe the welcome message,
        the language or the interview settings it never sent."""
        project_id = self._create(client, auth_headers)
        client.patch(
            f"/projects/{project_id}/settings",
            json={"warmup_enabled": False, "target_customer_description": "Hotel managers"},
            headers=auth_headers,
        )
        resp = client.put(
            f"/projects/{project_id}",
            json={
                "name": "Test Project",
                "welcome_message": "Merci",
                "questions": [QUESTION],
                "screening_questions": [],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

        # Now save only the screening section, as the Setup tab does.
        resp = client.put(
            f"/projects/{project_id}",
            json={
                "name": "Test Project",
                "language": "en",
                "interview_duration_minutes": 20,
                "questions": [QUESTION],
                "screening_questions": [
                    {"question": "Do you work in hospitality?", "options": ["Yes", "No"],
                     "disqualifying_options": ["No"]},
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["welcome_message"] == "Merci"
        assert data["target_customer_description"] == "Hotel managers"
        assert data["warmup_enabled"] is False
        assert data["language"] == "en"
        assert len(data["screening_questions"]) == 1

    def test_explicit_null_still_clears(self, client, auth_headers):
        """Sending the field explicitly is still how you clear it."""
        project_id = self._create(client, auth_headers)
        client.put(
            f"/projects/{project_id}",
            json={"name": "Test Project", "welcome_message": "Merci",
                  "questions": [QUESTION]},
            headers=auth_headers,
        )
        resp = client.put(
            f"/projects/{project_id}",
            json={"name": "Test Project", "welcome_message": None,
                  "questions": [QUESTION]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["welcome_message"] is None

    def test_omitting_screening_keeps_it(self, client, auth_headers):
        """A payload with no screening_questions key must not delete them."""
        project_id = self._create(client, auth_headers)
        resp = client.put(
            f"/projects/{project_id}",
            json={"name": "Renamed", "questions": [QUESTION]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["screening_questions"]) == 1
        assert resp.json()["name"] == "Renamed"


class TestPatchProjectSettings:
    """PATCH /projects/{id}/settings — participant-facing free text has cached
    translations that must not outlive an edit."""

    def _create(self, client, auth_headers):
        resp = client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers)
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def _project(self, db_session, project_id):
        from app.models.project import Project
        db_session.expire_all()
        return db_session.query(Project).filter(Project.id == project_id).first()

    def test_rename_drops_cached_name_translations(self, client, auth_headers, db_session):
        project_id = self._create(client, auth_headers)
        project = self._project(db_session, project_id)
        project.name_translations = '{"fr": "Ancien titre"}'
        db_session.commit()

        resp = client.patch(
            f"/projects/{project_id}/settings",
            json={"name": "New title"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert self._project(db_session, project_id).name_translations is None

    def test_editing_research_context_drops_its_translations(self, client, auth_headers, db_session):
        project_id = self._create(client, auth_headers)
        project = self._project(db_session, project_id)
        project.research_context = "Old context"
        project.research_context_translations = '{"fr": "Ancien contexte"}'
        db_session.commit()

        resp = client.patch(
            f"/projects/{project_id}/settings",
            json={"research_context": "New context"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert self._project(db_session, project_id).research_context_translations is None

    def test_unchanged_text_keeps_its_translations(self, client, auth_headers, db_session):
        """Re-saving the same text must not throw away work already paid for."""
        project_id = self._create(client, auth_headers)
        project = self._project(db_session, project_id)
        project.name_translations = '{"fr": "Titre"}'
        db_session.commit()

        resp = client.patch(
            f"/projects/{project_id}/settings",
            json={"name": PROJECT_PAYLOAD["name"], "warmup_enabled": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert self._project(db_session, project_id).name_translations == '{"fr": "Titre"}'
