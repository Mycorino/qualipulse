"""Research Copilot — onboarding surface.

Tests run with ANTHROPIC_API_KEY blank, exercising the deterministic
stub in services/copilot_onboarding.py.
"""

from types import SimpleNamespace

from app.models.company import Company
from app.services.copilot_onboarding import _onboarding_run_tool


class TestOnboardingCopilot:
    def test_proposes_a_first_study(self, client, auth_headers, drain_sse):
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
        data = drain_sse(resp)
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


class TestRecommendedParticipants:
    """W2.4 — recommended N is normalised against company_size, so
    the suggestion stays consistent regardless of what the model emits."""

    def _propose(self, db_session, company, payload_extra=None):
        turn = SimpleNamespace(actions=[])
        payload = {
            "study_name": "Test study",
            "objective": "Understand a thing.",
            "questions": [
                {
                    "section_title": "Background",
                    "main_question": "Tell me about it.",
                    "desired_learning": "Context.",
                    "rationale": "Warm opener.",
                }
            ],
        }
        if payload_extra:
            payload.update(payload_extra)
        _onboarding_run_tool(
            db_session, company, company, turn, "propose_study", payload
        )
        return turn.actions[0]

    def test_uses_captured_company_size_bucket(self, db_session):
        company = Company(
            id="r-1", name="Acme", email="alice@acme.com",
            password_hash="x", company_size="51–200",
        )
        action = self._propose(db_session, company)
        # Server bucket wins, regardless of what the model would have said.
        assert action["recommended_participants"] == 50

    def test_overrides_model_value_when_size_captured(self, db_session):
        # Even if the model emits a wildly different number, the server
        # snaps it back to the size bucket.
        company = Company(
            id="r-2", name="Acme", email="b@acme.com",
            password_hash="x", company_size="1–10",
        )
        action = self._propose(
            db_session, company,
            payload_extra={"recommended_participants": 500},
        )
        assert action["recommended_participants"] == 10

    def test_falls_back_to_default_when_size_missing(self, db_session):
        company = Company(
            id="r-3", name="Acme", email="c@acme.com", password_hash="x",
        )
        action = self._propose(db_session, company)
        assert action["recommended_participants"] == 20

    def test_honours_model_value_when_size_missing_but_value_reasonable(
        self, db_session
    ):
        company = Company(
            id="r-4", name="Acme", email="d@acme.com", password_hash="x",
        )
        action = self._propose(
            db_session, company,
            payload_extra={"recommended_participants": 40},
        )
        assert action["recommended_participants"] == 40

    def test_clamps_obvious_garbage(self, db_session):
        company = Company(
            id="r-5", name="Acme", email="e@acme.com", password_hash="x",
        )
        action = self._propose(
            db_session, company,
            payload_extra={"recommended_participants": -1000},
        )
        assert action["recommended_participants"] == 20


class TestV2StrategicCapture:
    """V2 onboarding — propose_study captures decision / timeline /
    success criteria / audience, save_profile captures referral_source
    + current_tool. These flow through to Project on accept and into
    the memory recap."""

    def _propose(self, db_session, payload):
        company = Company(
            id="v2-1", name="Acme", email="v2@acme.com",
            password_hash="x", company_size="11–50",
        )
        turn = SimpleNamespace(actions=[])
        _onboarding_run_tool(
            db_session, company, company, turn, "propose_study", payload
        )
        return turn.actions[0]

    def test_propose_study_carries_strategic_context(self, db_session):
        action = self._propose(db_session, {
            "study_name": "Why trial users churn",
            "objective": "Understand churn moment.",
            "questions": [
                {
                    "section_title": "Background",
                    "main_question": "Tell me about your trial.",
                    "desired_learning": "Context.",
                    "rationale": "Warm opener.",
                }
            ],
            "decision_to_inform": "Rebuild onboarding vs polish.",
            "timeline": "2 weeks",
            "success_criteria": "Trial-to-paid lifts by 5 points.",
            "target_customer_description": "Lapsed trial users in the last 60 days.",
        })
        assert action["decision_to_inform"] == "Rebuild onboarding vs polish."
        assert action["timeline"] == "2 weeks"
        assert action["success_criteria"] == "Trial-to-paid lifts by 5 points."
        assert action["target_customer_description"] == (
            "Lapsed trial users in the last 60 days."
        )

    def test_save_profile_writes_referral_source(self, db_session):
        company = Company(
            id="v2-2", name="Acme", email="v2b@acme.com", password_hash="x",
        )
        db_session.add(company)
        db_session.commit()
        turn = SimpleNamespace(actions=[])
        msg = _onboarding_run_tool(
            db_session, company, company, turn, "save_profile",
            {"referral_source": "LinkedIn"},
        )
        assert "Saved" in msg
        db_session.refresh(company)
        assert company.referral_source == "LinkedIn"

    def test_save_profile_writes_current_tool(self, db_session):
        company = Company(
            id="v2-3", name="Acme", email="v2c@acme.com", password_hash="x",
        )
        db_session.add(company)
        db_session.commit()
        turn = SimpleNamespace(actions=[])
        _onboarding_run_tool(
            db_session, company, company, turn, "save_profile",
            {"current_tool": "Typeform"},
        )
        db_session.refresh(company)
        assert company.current_tool == "Typeform"

    def test_canonical_chips_include_v2_contexts(self):
        """The canonical-options set the server enforces must cover the
        three new chip contexts so they're predictable across sessions."""
        from app.services.copilot_onboarding import _CANONICAL_REPLIES
        assert "referral_source" in _CANONICAL_REPLIES
        assert "current_tool" in _CANONICAL_REPLIES
        assert "timeline" in _CANONICAL_REPLIES
        assert "Other" in _CANONICAL_REPLIES["referral_source"]
        assert "Nothing yet" in _CANONICAL_REPLIES["current_tool"]
        assert "2 weeks" in _CANONICAL_REPLIES["timeline"]

    def test_copilot_onboarding_no_locale_duplicate_chips(self, db_session):
        """Wave A Fix 2 — FR researchers must never see English-only labels
        leaking into a canonical chip set. The substitution path picks
        ``_CANONICAL_REPLIES_FR`` based on ``company.preferred_language``."""
        company = Company(
            id="r-fr",
            name="Acme FR",
            email="fr@acme.com",
            password_hash="x",
            preferred_language="fr",
        )
        db_session.add(company)
        db_session.commit()
        turn = SimpleNamespace(actions=[])
        # Agent emits English options for `decision_role` — server must
        # discard them and substitute the FR canonical set.
        _onboarding_run_tool(
            db_session, company, company, turn, "suggest_replies",
            {
                "context": "decision_role",
                "options": ["I'll decide", "Just exploring", "Other"],
            },
        )
        assert len(turn.actions) == 1
        options = turn.actions[0]["options"]
        # No English-only labels — every label must be in the FR set.
        from app.services.copilot_onboarding import _CANONICAL_REPLIES_FR
        for label in options:
            assert label in _CANONICAL_REPLIES_FR["decision_role"], (
                f"FR researcher saw non-FR chip: {label!r}"
            )
        # Specifically, "Other" must not appear when "Autre" would be
        # used as the escape hatch (decision_role has no "Autre"
        # canonically — it has "J'explore" etc., so just guard against
        # the bilingual mix).
        assert "Other" not in options
        assert "I'll decide" not in options

    def test_custom_context_dedupes_other_against_autre(self, db_session):
        """When the agent emits a free `custom` chip set that already
        contains 'Other' and the locale is FR, we must end up with one
        escape hatch ('Autre'), not both 'Other' AND 'Autre'."""
        company = Company(
            id="r-fr2",
            name="Acme FR2",
            email="fr2@acme.com",
            password_hash="x",
            preferred_language="fr",
        )
        db_session.add(company)
        db_session.commit()
        turn = SimpleNamespace(actions=[])
        _onboarding_run_tool(
            db_session, company, company, turn, "suggest_replies",
            {
                "context": "custom",
                "options": [
                    "Taux de complétion +X%",
                    "Réduction",
                    "Validation",
                    "Other",
                ],
            },
        )
        options = turn.actions[0]["options"]
        # "Autre" appended as the escape hatch; the agent's "Other" is
        # dropped via the synonym map.
        assert "Autre" in options
        assert "Other" not in options
        # The genuine custom chips survive.
        assert "Taux de complétion +X%" in options
        assert "Réduction" in options
        assert "Validation" in options
