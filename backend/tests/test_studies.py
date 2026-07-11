"""Sprint 9.5 — Study Overview endpoints.

The Study is the research workspace. These tests cover the read-only
surface that powers /studies and /studies/:id, plus the recommended-
action progression as the study fills with data.
"""

from datetime import datetime, timezone


def _make_live_survey(client, auth_headers, name: str = "Test"):
    """Helper: create a survey, add an NPS question, create a link, publish."""

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": name}
    ).json()
    q = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={"type": "nps", "prompt": "Recommend?", "config": {}},
    ).json()
    link = client.post(
        f"/surveys/{survey['id']}/links",
        headers=auth_headers,
        json={"is_anonymous": False},
    ).json()
    client.patch(
        f"/surveys/{survey['id']}", headers=auth_headers, json={"status": "live"}
    )
    return survey, q, link


def test_list_studies_empty_for_new_workspace(client, auth_headers):
    resp = client.get("/studies/", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_creating_a_survey_implicitly_creates_a_study(client, auth_headers):
    """Decision 8: surveys auto-create their parent Study."""

    client.post("/surveys/", headers=auth_headers, json={"name": "Implicit"})

    studies = client.get("/studies/", headers=auth_headers).json()
    assert len(studies) == 1
    assert studies[0]["name"] == "Implicit"
    assert studies[0]["survey_count"] == 1
    assert studies[0]["project_count"] == 0
    assert studies[0]["participant_count"] == 0


def test_study_summary_carries_card_signals(client, auth_headers):
    """Sprint 17: the Studies-list cards need response/interview counts
    and a has_report flag for the instrument-mix badge + status line."""

    survey, q, link = _make_live_survey(client, auth_headers, name="Card signals")
    # Two completed responses.
    for i in range(2):
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "email": f"card-{i}@example.com",
                "answers": [{"question_id": q["id"], "value_numeric": 7}],
                "is_complete": True,
            },
        )

    studies = client.get("/studies/", headers=auth_headers).json()
    card = next(s for s in studies if s["id"] == survey["study_id"])
    assert card["survey_count"] == 1
    assert card["project_count"] == 0  # survey-only → instrument-mix badge = Survey
    assert card["completed_response_count"] == 2
    assert card["completed_interview_count"] == 0
    assert card["has_report"] is False


def test_study_detail_returns_surveys_and_progress(client, auth_headers):
    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "With detail"}
    ).json()
    study_id = survey["study_id"]

    detail = client.get(f"/studies/{study_id}", headers=auth_headers).json()
    assert detail["name"] == "With detail"
    assert len(detail["surveys"]) == 1
    assert detail["surveys"][0]["id"] == survey["id"]
    assert detail["projects"] == []
    assert detail["progress"]["has_live_survey"] is False
    assert detail["progress"]["total_completed_responses"] == 0
    assert detail["progress"]["segments_identified_placeholder"] is False
    assert detail["progress"]["report_ready_placeholder"] is False


def test_recommended_action_progression(client, auth_headers, db_session):
    """The recommended-action chip should point at the next un-done step."""

    # Step 1: no surveys → create-screener prompt
    # We need to create a Study via _another_ instrument because the
    # implicit-creation path is gated to surveys. So we create a draft
    # survey, then ARCHIVE it to leave the study otherwise empty.
    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Bootstrap"}
    ).json()
    study_id = survey["study_id"]
    client.delete(f"/surveys/{survey['id']}", headers=auth_headers)
    detail = client.get(f"/studies/{study_id}", headers=auth_headers).json()
    assert "Create a screener survey" in detail["recommended_action"]
    assert detail["recommended_action_key"] == "create_survey"

    # Step 2: draft survey exists → publish prompt
    s2 = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Draft"}
    ).json()
    # Use the existing draft's study_id (creating S2 will create a different
    # study; we want the same one) — switch to the s2 study for clarity.
    study_id = s2["study_id"]
    detail = client.get(f"/studies/{study_id}", headers=auth_headers).json()
    assert "Publish your survey" in detail["recommended_action"]
    assert detail["recommended_action_key"] == "publish_survey"

    # Step 3: published, 0 responses → share link prompt
    q = client.post(
        f"/surveys/{s2['id']}/questions",
        headers=auth_headers,
        json={"type": "nps", "prompt": "Recommend?", "config": {}},
    ).json()
    link = client.post(
        f"/surveys/{s2['id']}/links", headers=auth_headers, json={"is_anonymous": False}
    ).json()
    client.patch(f"/surveys/{s2['id']}", headers=auth_headers, json={"status": "live"})
    detail = client.get(f"/studies/{study_id}", headers=auth_headers).json()
    assert "Share your survey link" in detail["recommended_action"]
    assert detail["recommended_action_key"] == "share_survey_link"

    # Step 4: partial responses (below n=30) → keep collecting prompt
    for i in range(5):
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "email": f"r-{i}@example.com",
                "answers": [{"question_id": q["id"], "value_numeric": 8}],
                "is_complete": True,
            },
        )
    detail = client.get(f"/studies/{study_id}", headers=auth_headers).json()
    assert "more responses" in detail["recommended_action"]
    assert detail["recommended_action_key"] == "collect_more_responses"
    assert detail["recommended_action_params"] == {"count": 25}


def test_study_detail_404_for_other_workspace(client, auth_headers):
    """Workspace isolation — Company A's study is not visible to Company B."""

    s = client.post(
        "/surveys/", headers=auth_headers, json={"name": "A's study"}
    ).json()
    study_id = s["study_id"]

    # Sign up Company B.
    client.post(
        "/auth/signup",
        json={"name": "B Co", "email": "b@example.com", "password": "Password123!"},
    )
    b_login = client.post(
        "/auth/login", json={"email": "b@example.com", "password": "Password123!"}
    ).json()
    b_headers = {"Authorization": f"Bearer {b_login['access_token']}"}

    resp = client.get(f"/studies/{study_id}", headers=b_headers)
    assert resp.status_code == 404
    listing = client.get("/studies/", headers=b_headers).json()
    assert listing == []


# ── Sprint 11: Quantified Themes report ──────────────────────────────


def _seed_full_study(client, auth_headers):
    """Build a study with one survey (mc_single + nps + mc_multi) seeded
    with 4 cohorts to exercise the discoveries → themes pipeline."""

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Sprint 11 fixture"}
    ).json()
    seg = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "mc_single",
            "prompt": "Your role?",
            "config": {
                "choices": [
                    {"id": "pm", "label": "Product Manager"},
                    {"id": "eng", "label": "Engineer"},
                ],
                "randomize": False,
                "has_other": False,
            },
        },
    ).json()
    nps = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={"type": "nps", "prompt": "How likely to recommend?", "config": {}},
    ).json()
    link = client.post(
        f"/surveys/{survey['id']}/links",
        headers=auth_headers,
        json={"is_anonymous": False},
    ).json()
    client.patch(f"/surveys/{survey['id']}", headers=auth_headers, json={"status": "live"})

    cohorts = [("pm", 3, 40), ("eng", 9, 40)]
    counter = 0
    for role, score, n in cohorts:
        for _ in range(n):
            counter += 1
            client.post(
                f"/r/{link['token']}/responses",
                json={
                    "link_token": link["token"],
                    "email": f"sp11-{counter}@example.com",
                    "answers": [
                        {"question_id": seg["id"], "value_choice_ids": [role]},
                        {"question_id": nps["id"], "value_numeric": score},
                    ],
                    "is_complete": True,
                },
            )
    return survey


def test_create_analysis_returns_ready_report_in_stub_mode(client, auth_headers):
    """With no ANTHROPIC_API_KEY the service emits a deterministic stub
    so the rest of the system can be exercised end-to-end without an
    AI dependency. Tests run with the key blanked out, so this hits
    the stub path."""

    survey = _seed_full_study(client, auth_headers)
    resp = client.post(
        f"/studies/{survey['study_id']}/analyses", headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "ready"
    assert data["report"] is not None
    assert isinstance(data["report"]["themes"], list)
    assert len(data["report"]["themes"]) >= 1
    # Stub uses the discovery service as its data source; cohort gap → directional or supported.
    confidences = {t["confidence"] for t in data["report"]["themes"]}
    assert confidences.issubset({"directional", "supported", "strong"})


def test_latest_analysis_returns_null_initially_then_the_one_we_made(client, auth_headers):
    survey = _seed_full_study(client, auth_headers)
    initial = client.get(
        f"/studies/{survey['study_id']}/analyses/latest", headers=auth_headers
    )
    assert initial.status_code == 200
    assert initial.json() is None

    client.post(f"/studies/{survey['study_id']}/analyses", headers=auth_headers)

    latest = client.get(
        f"/studies/{survey['study_id']}/analyses/latest", headers=auth_headers
    ).json()
    assert latest is not None
    assert latest["status"] == "ready"
    assert latest["version"] == 1


def test_versioning_increments_on_regenerate(client, auth_headers):
    survey = _seed_full_study(client, auth_headers)
    a1 = client.post(
        f"/studies/{survey['study_id']}/analyses", headers=auth_headers
    ).json()
    a2 = client.post(
        f"/studies/{survey['study_id']}/analyses", headers=auth_headers
    ).json()
    assert a2["version"] == a1["version"] + 1
    rows = client.get(
        f"/studies/{survey['study_id']}/analyses", headers=auth_headers
    ).json()
    assert len(rows) == 2


def test_report_ready_flag_flips_progress_signal(client, auth_headers):
    survey = _seed_full_study(client, auth_headers)
    before = client.get(
        f"/studies/{survey['study_id']}", headers=auth_headers
    ).json()
    assert before["progress"]["report_ready_placeholder"] is False

    client.post(f"/studies/{survey['study_id']}/analyses", headers=auth_headers)

    after = client.get(
        f"/studies/{survey['study_id']}", headers=auth_headers
    ).json()
    assert after["progress"]["report_ready_placeholder"] is True


def test_progress_reaches_inference_threshold_at_30_responses(
    client, auth_headers, db_session
):
    """The segments-identified placeholder uses the same n=30 the rest of
    the methodology contract uses."""

    survey, q, link = _make_live_survey(client, auth_headers, name="Threshold")
    for i in range(30):
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "email": f"thresh-{i}@example.com",
                "answers": [{"question_id": q["id"], "value_numeric": 7}],
                "is_complete": True,
            },
        )

    detail = client.get(f"/studies/{survey['study_id']}", headers=auth_headers).json()
    assert detail["progress"]["total_completed_responses"] == 30
    assert detail["progress"]["segments_identified_placeholder"] is True
    # Next prompt after threshold = open the dashboard / use the Bridge.
    rec = detail["recommended_action"] or ""
    assert ("dashboard" in rec.lower()) or ("bridge" in rec.lower())
