"""Research Copilot — survey-surface agent endpoint.

Tests run with ANTHROPIC_API_KEY blanked out, so they exercise the
deterministic stub path in services/copilot.py.
"""

from app.models.company import Company
from app.models.copilot import CopilotMemory
from app.services.copilot import append_memory, get_memory


def _create_survey(client, auth_headers, name: str = "Copilot test") -> dict:
    return client.post(
        "/surveys/", headers=auth_headers, json={"name": name}
    ).json()


class TestSurveyCopilotEndpoint:
    def test_proposes_starter_questions_for_empty_survey(self, client, auth_headers):
        survey = _create_survey(client, auth_headers)

        resp = client.post(
            f"/surveys/{survey['id']}/copilot",
            headers=auth_headers,
            json={"messages": [{"role": "user", "content": "Help me start a survey"}]},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["reply"]
        assert len(data["proposed_actions"]) == 2
        for action in data["proposed_actions"]:
            assert action["type"] == "add_question"
            # Every proposed question is a sanctioned type with a rationale.
            assert action["question"]["type"] in (
                "likert",
                "mc_single",
                "mc_multi",
                "nps",
                "open_text",
                "short_text",
            )
            assert action["question"]["rationale"]

    def test_no_proposals_once_survey_has_questions(self, client, auth_headers):
        survey = _create_survey(client, auth_headers, name="Has a question")
        client.post(
            f"/surveys/{survey['id']}/questions",
            headers=auth_headers,
            json={"type": "nps", "prompt": "Recommend us?", "config": {}},
        )

        resp = client.post(
            f"/surveys/{survey['id']}/copilot",
            headers=auth_headers,
            json={"messages": [{"role": "user", "content": "What next?"}]},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["reply"]
        assert data["proposed_actions"] == []

    def test_empty_message_history_is_rejected(self, client, auth_headers):
        survey = _create_survey(client, auth_headers)
        resp = client.post(
            f"/surveys/{survey['id']}/copilot",
            headers=auth_headers,
            json={"messages": []},
        )
        assert resp.status_code == 422

    def test_copilot_404_for_other_workspace(self, client, auth_headers):
        """Workspace isolation — Company A's survey is invisible to Company B."""
        survey = _create_survey(client, auth_headers, name="A's survey")

        client.post(
            "/auth/signup",
            json={"name": "B Co", "email": "b@example.com", "password": "Password123!"},
        )
        b_login = client.post(
            "/auth/login", json={"email": "b@example.com", "password": "Password123!"}
        ).json()
        b_headers = {"Authorization": f"Bearer {b_login['access_token']}"}

        resp = client.post(
            f"/surveys/{survey['id']}/copilot",
            headers=b_headers,
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 404


def _make_company(db_session, email: str) -> Company:
    company = Company(name="Mem Co", email=email, password_hash="x")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


class TestCopilotMemory:
    def test_append_memory_creates_then_accumulates(self, db_session):
        company = _make_company(db_session, "mem@example.com")
        assert get_memory(db_session, "company", company.id) is None

        append_memory(
            db_session, company.id, "company", company.id, "Audience is recent churners."
        )
        append_memory(
            db_session, company.id, "company", company.id, "Prefers short surveys."
        )

        rows = (
            db_session.query(CopilotMemory)
            .filter(
                CopilotMemory.scope_kind == "company",
                CopilotMemory.scope_id == company.id,
            )
            .all()
        )
        # One row per (scope_kind, scope_id), both notes accumulated.
        assert len(rows) == 1
        assert "recent churners" in rows[0].content
        assert "short surveys" in rows[0].content

    def test_memory_scopes_are_isolated(self, db_session):
        """company / study / survey memory are separate rows."""
        company = _make_company(db_session, "scope@example.com")
        append_memory(db_session, company.id, "company", company.id, "workspace fact")
        append_memory(db_session, company.id, "study", "study-xyz", "study fact")
        append_memory(db_session, company.id, "survey", "survey-abc", "survey fact")

        assert "workspace fact" in get_memory(db_session, "company", company.id).content
        assert "study fact" in get_memory(db_session, "study", "study-xyz").content
        assert "survey fact" in get_memory(db_session, "survey", "survey-abc").content
        # Tiers don't bleed into each other.
        assert "study fact" not in get_memory(db_session, "company", company.id).content

    def test_append_memory_ignores_blank_notes(self, db_session):
        company = _make_company(db_session, "blank@example.com")
        append_memory(db_session, company.id, "company", company.id, "   ")
        assert get_memory(db_session, "company", company.id) is None


class TestCopilotConversation:
    def test_conversation_round_trip(self, client, auth_headers):
        survey = _create_survey(client, auth_headers, name="Convo survey")

        empty = client.get(
            f"/surveys/{survey['id']}/copilot/conversation", headers=auth_headers
        )
        assert empty.status_code == 200
        assert empty.json()["thread"] == []

        thread = [
            {"kind": "user", "text": "Help me build it"},
            {"kind": "assistant", "text": "Sure — here's a draft.", "actions": []},
        ]
        saved = client.put(
            f"/surveys/{survey['id']}/copilot/conversation",
            headers=auth_headers,
            json={"thread": thread},
        )
        assert saved.status_code == 200

        reloaded = client.get(
            f"/surveys/{survey['id']}/copilot/conversation", headers=auth_headers
        )
        assert reloaded.json()["thread"] == thread

    def test_conversation_404_for_other_workspace(self, client, auth_headers):
        survey = _create_survey(client, auth_headers, name="A's convo")
        client.post(
            "/auth/signup",
            json={"name": "B Co", "email": "bconv@example.com", "password": "Password123!"},
        )
        b_login = client.post(
            "/auth/login",
            json={"email": "bconv@example.com", "password": "Password123!"},
        ).json()
        b_headers = {"Authorization": f"Bearer {b_login['access_token']}"}

        resp = client.get(
            f"/surveys/{survey['id']}/copilot/conversation", headers=b_headers
        )
        assert resp.status_code == 404
