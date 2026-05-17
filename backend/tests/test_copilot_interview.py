"""Research Copilot — interview-guide surface.

Tests run with ANTHROPIC_API_KEY blanked out, so they exercise the
deterministic stub path in services/copilot_interview.py.
"""


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
    def test_proposes_guide_questions_for_empty_guide(self, client, auth_headers):
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
        data = resp.json()
        assert data["reply"]
        assert len(data["proposed_actions"]) == 2
        for action in data["proposed_actions"]:
            assert action["type"] == "add_guide_question"
            q = action["question"]
            assert q["section_title"]
            assert q["main_question"]
            assert q["desired_learning"]
            assert q["rationale"]

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
