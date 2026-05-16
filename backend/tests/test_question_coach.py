"""Sprint 13 — question coach lint.

Covers the regex layer + the endpoint contract. The Claude Haiku
rewrite layer is gated on ANTHROPIC_API_KEY which is blank in tests,
so suggested_replacement stays None — that's the intended fallback
shape and we verify it.
"""

import pytest


@pytest.fixture
def survey(client, auth_headers):
    return client.post(
        "/surveys/", headers=auth_headers, json={"name": "Lint test"}
    ).json()


def _lint(client, auth_headers, survey_id, **payload):
    body = {
        "prompt": "",
        "type": "likert",
        "config": {},
        "with_rewrite": True,
        **payload,
    }
    return client.post(
        f"/surveys/{survey_id}/questions/lint",
        headers=auth_headers,
        json=body,
    )


def test_double_barreled_flag_fires(client, auth_headers, survey):
    resp = _lint(
        client,
        auth_headers,
        survey["id"],
        prompt="How satisfied are you with the speed and reliability?",
    )
    assert resp.status_code == 200, resp.text
    codes = [f["code"] for f in resp.json()["flags"]]
    assert "double_barreled" in codes


def test_leading_wording_flag_fires(client, auth_headers, survey):
    resp = _lint(
        client,
        auth_headers,
        survey["id"],
        prompt="How much do you love our amazing onboarding?",
    ).json()
    codes = [f["code"] for f in resp["flags"]]
    assert "leading_wording" in codes


def test_agree_disagree_bias_flag_fires(client, auth_headers, survey):
    resp = _lint(
        client,
        auth_headers,
        survey["id"],
        prompt="Don't you agree that pricing is fair?",
    ).json()
    codes = [f["code"] for f in resp["flags"]]
    assert "agree_disagree_bias" in codes


def test_too_short_flag_fires(client, auth_headers, survey):
    resp = _lint(
        client, auth_headers, survey["id"], prompt="Why?"
    ).json()
    codes = [f["code"] for f in resp["flags"]]
    assert "too_short" in codes


def test_clean_prompt_returns_no_flags(client, auth_headers, survey):
    resp = _lint(
        client,
        auth_headers,
        survey["id"],
        prompt="How clearly did the checkout step explain what you were paying for?",
        type="open_text",
    ).json()
    # The clean prompt above doesn't trip any regex.
    assert resp["flags"] == []


def test_lint_404_for_other_workspace_survey(client, auth_headers):
    client.post(
        "/auth/signup",
        json={"name": "B Co", "email": "b@example.com", "password": "Password123!"},
    )
    b_tokens = client.post(
        "/auth/login",
        json={"email": "b@example.com", "password": "Password123!"},
    ).json()
    b_headers = {"Authorization": f"Bearer {b_tokens['access_token']}"}

    # B can't lint A's survey.
    a_survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "A's"}
    ).json()
    resp = _lint(client, b_headers, a_survey["id"], prompt="Anything?")
    assert resp.status_code == 404


def test_suggested_replacement_is_null_without_api_key(
    client, auth_headers, survey
):
    """Tests run without ANTHROPIC_API_KEY → no Haiku rewrite, but the
    regex flag still fires. This is the documented fallback shape."""

    resp = _lint(
        client,
        auth_headers,
        survey["id"],
        prompt="How much do you love our amazing onboarding?",
    ).json()
    leading = next(f for f in resp["flags"] if f["code"] == "leading_wording")
    assert leading["suggested_replacement"] is None
