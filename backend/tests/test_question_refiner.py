"""Tests for POST /research/refine-question.

The endpoint is the researcher's daily-driver AI feature: they highlight a
single guide question and ask the AI to sharpen it. The contract we're
locking in here is that refinement is **scoped** — no matter what Claude
returns, the endpoint can only ever come back with a single refined
question. Sibling questions that go in as context can never leak back
out as mutations. These tests mock the Claude call and assert on the
wire-level response shape.
"""
import json

import pytest


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeUsage:
    input_tokens = 10
    output_tokens = 10


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.content = [_FakeTextBlock(json.dumps(payload))]
        self.usage = _FakeUsage()
        self.model = "claude-sonnet-4-20250514"


class _FakeMessages:
    """Shim that stands in for ``anthropic.Anthropic().messages`` in tests."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.last_prompt: str | None = None

    def create(self, **kwargs):
        # Capture the prompt so assertions can inspect what we actually
        # sent to Claude (e.g. "did the prompt contain every sibling?").
        messages = kwargs.get("messages") or []
        if messages:
            self.last_prompt = messages[0].get("content", "")
        return _FakeResponse(self._payload)


class _FakeClaude:
    def __init__(self, payload: dict) -> None:
        self.messages = _FakeMessages(payload)


@pytest.fixture
def mock_claude(monkeypatch):
    """Replace the module-level ``_claude`` factory with a fake.

    Returns a callable the test uses to set the payload Claude "returns".
    The fake's prompt capture lives on ``messages.last_prompt`` for
    introspection.
    """
    from app.routers import research_assistant

    holder: dict = {}

    def install(payload: dict) -> _FakeClaude:
        fake = _FakeClaude(payload)
        holder["fake"] = fake
        monkeypatch.setattr(research_assistant, "_claude", lambda max_tokens=1024: fake)
        # Short-circuit usage logging so it doesn't hit the real DB schema.
        monkeypatch.setattr(
            research_assistant, "log_claude_usage", lambda *a, **kw: None
        )
        return fake

    return install


# ---------------------------------------------------------------------------
# The happy path: a single question in, a single refined question out.
# ---------------------------------------------------------------------------


def _base_body() -> dict:
    return {
        "question": {
            "section_title": "Current workflow",
            "main_question": "Do you use Trello?",
            "interview_notes": "",
            "desired_learning": "",
        },
        "question_index": 1,
        "objective": "Understand how dev teams run sprint planning",
        "learning_goals": ["Triggers for tool changes", "Team rituals"],
        "audience": "Engineering managers at 50-500 person companies",
        "all_questions": [
            {"section_title": "Warm-up", "main_question": "Tell me about your team."},
            {"section_title": "Current workflow", "main_question": "Do you use Trello?"},
            {"section_title": "Current workflow", "main_question": "Walk me through a recent sprint."},
        ],
        "language": "en",
    }


class TestRefineQuestion:
    def test_returns_refined_question_and_rationale(self, client, auth_headers, mock_claude):
        mock_claude({
            "refined": {
                "section_title": "Current workflow",
                "main_question": "Walk me through the last time you set up a new tool for your team.",
                "interview_notes": "Probe for the trigger, not the feature.",
                "desired_learning": "What prompts a tool change decision.",
            },
            "rationale": "Turned a yes/no into a walk-through so it elicits a concrete story.",
        })

        resp = client.post(
            "/research/refine-question",
            json=_base_body(),
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "refined" in data
        assert "rationale" in data
        assert data["refined"]["main_question"].startswith("Walk me through")
        assert data["rationale"]

    def test_response_is_single_question_shape(self, client, auth_headers, mock_claude):
        """The wire-level contract: the response ``refined`` is a single
        object with exactly the four fields. No list, no siblings."""
        mock_claude({
            "refined": {
                "section_title": "x",
                "main_question": "y",
                "interview_notes": "z",
                "desired_learning": "w",
            },
            "rationale": "r",
        })
        resp = client.post(
            "/research/refine-question",
            json=_base_body(),
            headers=auth_headers,
        )
        assert resp.status_code == 200
        refined = resp.json()["refined"]
        assert isinstance(refined, dict)
        assert set(refined.keys()) == {
            "section_title",
            "main_question",
            "interview_notes",
            "desired_learning",
        }

    def test_ignores_extra_fields_from_claude(self, client, auth_headers, mock_claude):
        """Defence in depth: even if Claude tries to inject extra keys or a
        sibling list, the endpoint plucks only the single refined question
        out. There is no code path where siblings can leak through."""
        mock_claude({
            "refined": {
                "section_title": "Current workflow",
                "main_question": "Walk me through your last tool switch.",
                "interview_notes": "",
                "desired_learning": "",
                # Claude tried to return an extra field — it should be
                # silently dropped by our response shaping.
                "bonus_field": "should not be returned",
            },
            # Claude also tried to suggest changes to other questions.
            "also_change": [
                {"question_index": 0, "main_question": "DIFFERENT Q1"},
                {"question_index": 2, "main_question": "DIFFERENT Q3"},
            ],
            "rationale": "ok",
        })
        resp = client.post(
            "/research/refine-question",
            json=_base_body(),
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "also_change" not in data
        assert "bonus_field" not in data["refined"]
        # And the response only describes the one target question.
        assert set(data.keys()) == {"refined", "rationale"}

    def test_empty_question_short_circuits(self, client, auth_headers, mock_claude):
        """An empty main_question is returned as-is without burning a
        Claude call. This catches double-clicks on a blank 'Add question'
        card."""
        fake = mock_claude({"refined": {}, "rationale": ""})
        body = _base_body()
        body["question"]["main_question"] = ""
        resp = client.post(
            "/research/refine-question",
            json=body,
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # We never called Claude — the fake's prompt is still None.
        assert fake.messages.last_prompt is None

    def test_prompt_marks_target_question(self, client, auth_headers, mock_claude):
        """Claude must see which question is the target. We inject a
        '→ THIS ONE' marker next to the question_index entry in the
        read-only guide view — assert it's actually in the prompt."""
        fake = mock_claude({
            "refined": {
                "section_title": "Current workflow",
                "main_question": "Walk me through your last sprint planning.",
                "interview_notes": "",
                "desired_learning": "",
            },
            "rationale": "ok",
        })
        resp = client.post(
            "/research/refine-question",
            json=_base_body(),
            headers=auth_headers,
        )
        assert resp.status_code == 200
        prompt = fake.messages.last_prompt or ""
        assert "→ THIS ONE" in prompt
        # And all three siblings should be present in the read-only view,
        # so Claude can keep the refinement coherent with the rest.
        assert "Tell me about your team." in prompt
        assert "Walk me through a recent sprint." in prompt

    def test_requires_auth(self, client):
        resp = client.post("/research/refine-question", json=_base_body())
        assert resp.status_code == 401
