"""Research Copilot — onboarding surface.

Tests run with ANTHROPIC_API_KEY blank, exercising the deterministic
stub in services/copilot_onboarding.py.
"""

from types import SimpleNamespace

from app.models.company import Company
from app.services.copilot_onboarding import _onboarding_run_tool


class TestOnboardingCopilot:
    def test_proposes_a_first_study(self, client, auth_headers):
        resp = client.post(
            "/onboarding/copilot",
            headers=auth_headers,
            json={
                "messages": [
                    {"role": "user", "content": "I want to learn why trial users churn"}
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["reply"]
        actions = data["proposed_actions"]
        assert len(actions) == 1
        study = actions[0]
        assert study["type"] == "create_first_study"
        assert study["study_name"]
        assert study["objective"]
        assert len(study["questions"]) >= 1
        for q in study["questions"]:
            assert q["section_title"]
            assert q["main_question"]
            assert q["desired_learning"]

    def test_conversation_round_trip(self, client, auth_headers):
        empty = client.get(
            "/onboarding/copilot/conversation", headers=auth_headers
        )
        assert empty.status_code == 200
        assert empty.json()["thread"] == []

        thread = [{"kind": "user", "text": "Hello copilot"}]
        client.put(
            "/onboarding/copilot/conversation",
            headers=auth_headers,
            json={"thread": thread},
        )
        reloaded = client.get(
            "/onboarding/copilot/conversation", headers=auth_headers
        )
        assert reloaded.json()["thread"] == thread

    def test_requires_auth(self, client):
        resp = client.post(
            "/onboarding/copilot",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code in (401, 403)


class TestOnboardingTools:
    def test_save_profile_writes_company_fields(
        self, client, auth_headers, db_session
    ):
        company = (
            db_session.query(Company)
            .filter(Company.email == "test@example.com")
            .one()
        )
        turn = SimpleNamespace(actions=[])
        msg = _onboarding_run_tool(
            db_session,
            company,
            company,
            turn,
            "save_profile",
            {"role": "Founder", "industry": "SaaS"},
        )
        assert "Saved" in msg
        db_session.refresh(company)
        assert company.role == "Founder"
        assert company.industry == "SaaS"

    def test_propose_study_records_action(self, db_session):
        turn = SimpleNamespace(actions=[])
        msg = _onboarding_run_tool(
            db_session,
            None,
            None,
            turn,
            "propose_study",
            {
                "study_name": "Churn study",
                "objective": "Understand why trial users churn.",
                "questions": [
                    {
                        "section_title": "Background",
                        "main_question": "Tell me about your trial.",
                        "desired_learning": "Context.",
                        "rationale": "A warm opener.",
                    }
                ],
            },
        )
        assert "Proposed" in msg
        assert turn.actions[0]["type"] == "create_first_study"
        assert turn.actions[0]["study_name"] == "Churn study"
        assert len(turn.actions[0]["questions"]) == 1

    def test_propose_study_rejects_incomplete(self, db_session):
        turn = SimpleNamespace(actions=[])
        msg = _onboarding_run_tool(
            db_session, None, None, turn, "propose_study",
            {"study_name": "X", "objective": "", "questions": []},
        )
        assert "needs" in msg.lower()
        assert turn.actions == []
