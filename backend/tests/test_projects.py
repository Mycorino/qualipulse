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

    def test_free_tier_project_limit(self, client, auth_headers):
        """Free tier allows 1 project; the second should be rejected."""
        client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers)
        resp = client.post("/projects/", json={**PROJECT_PAYLOAD, "name": "Second Project"}, headers=auth_headers)
        assert resp.status_code == 403
        assert "limit" in resp.json()["detail"].lower()

    def test_free_tier_question_limit(self, client, auth_headers):
        """Free tier allows 5 questions; 6 should be rejected."""
        questions = [
            {**QUESTION, "question_index": i, "main_question": f"Q{i}"}
            for i in range(6)
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
