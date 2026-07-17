"""Sprint 14 — validation micro-surveys (closing the loop).

Covers the canonical happy path: generate analysis → spawn validation
survey from it → publish + collect responses → fetch validation
summary with per-theme agreement.

Stub-mode generation (no ANTHROPIC_API_KEY) produces deterministic
themes via segment discoveries, so we can reason about the resulting
question count.
"""

from app.models.survey import Survey


def _seed_study_with_analysis(client, auth_headers, db_session):
    """Build a survey + responses + a *legacy* Quantified-Themes analysis (which
    carries the top-level themes the validation feature is built around).

    POST /analyses now generates the Decision report (whose themes come from a
    ProjectAnalysis); this fixture is survey-only, so it exercises the legacy
    themed generator directly. Returns (study_id, analysis_id)."""

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Validation fixture"}
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
    client.patch(
        f"/surveys/{survey['id']}", headers=auth_headers, json={"status": "live"}
    )

    cohorts = [("pm", 3, 40), ("eng", 9, 40)]
    counter = 0
    for role, score, n in cohorts:
        for _ in range(n):
            counter += 1
            client.post(
                f"/r/{link['token']}/responses",
                json={
                    "link_token": link["token"],
                    "email": f"v14-{counter}@example.com",
                    "answers": [
                        {"question_id": seg["id"], "value_choice_ids": [role]},
                        {"question_id": nps["id"], "value_numeric": score},
                    ],
                    "is_complete": True,
                },
            )

    from app.models.study import Study
    from app.services.study_analysis import trigger_study_analysis

    study = db_session.query(Study).filter(Study.id == survey["study_id"]).first()
    row = trigger_study_analysis(db_session, study)
    return survey["study_id"], row.id


def test_generate_validation_survey_creates_one_question_per_theme(
    client, auth_headers, db_session
):
    study_id, analysis_id = _seed_study_with_analysis(client, auth_headers, db_session)
    analysis = client.get(
        f"/studies/{study_id}/analyses/{analysis_id}", headers=auth_headers
    ).json()
    theme_count = len(analysis["report"]["themes"])
    assert theme_count >= 1, "Stub should emit at least one theme"

    resp = client.post(
        f"/studies/{study_id}/analyses/{analysis_id}/validation-survey",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["question_count"] == theme_count
    assert data["study_id"] == study_id

    # Survey lands in draft + carries the source_analysis_id link.
    survey_row = (
        db_session.query(Survey).filter(Survey.id == data["survey_id"]).first()
    )
    assert survey_row is not None
    assert survey_row.role == "validation"
    assert survey_row.status == "draft"
    assert survey_row.source_analysis_id == analysis_id


def test_generate_validation_400_when_analysis_not_ready(
    client, auth_headers, db_session
):
    """Failed-status analyses shouldn't spawn validation surveys."""

    study_id, analysis_id = _seed_study_with_analysis(client, auth_headers, db_session)
    # Force the analysis into failed state.
    from app.models.study import StudyAnalysis
    a = db_session.query(StudyAnalysis).filter(StudyAnalysis.id == analysis_id).first()
    a.status = "failed"
    db_session.commit()

    resp = client.post(
        f"/studies/{study_id}/analyses/{analysis_id}/validation-survey",
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_validation_summary_null_until_generated(client, auth_headers, db_session):
    study_id, analysis_id = _seed_study_with_analysis(client, auth_headers, db_session)
    resp = client.get(
        f"/studies/{study_id}/analyses/{analysis_id}/validation",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() is None


def test_validation_summary_aggregates_responses(client, auth_headers, db_session):
    """Submit a few validation responses, then check the per-theme summary."""

    study_id, analysis_id = _seed_study_with_analysis(client, auth_headers, db_session)
    # Spawn the validation survey.
    spawn = client.post(
        f"/studies/{study_id}/analyses/{analysis_id}/validation-survey",
        headers=auth_headers,
    ).json()
    val_survey_id = spawn["survey_id"]

    # Publish + create a public link.
    client.patch(
        f"/surveys/{val_survey_id}", headers=auth_headers, json={"status": "live"}
    )
    link = client.post(
        f"/surveys/{val_survey_id}/links",
        headers=auth_headers,
        json={"is_anonymous": False},
    ).json()

    # Fetch the survey's questions.
    qs = client.get(
        f"/surveys/{val_survey_id}/questions", headers=auth_headers
    ).json()

    # Submit 5 "agree" responses (score 4 or 5).
    for i in range(5):
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "email": f"val-{i}@example.com",
                "answers": [
                    {"question_id": q["id"], "value_numeric": 5}
                    for q in qs
                ],
                "is_complete": True,
            },
        )

    summary = client.get(
        f"/studies/{study_id}/analyses/{analysis_id}/validation",
        headers=auth_headers,
    ).json()
    assert summary is not None
    assert summary["n_completed"] == 5
    # Each theme has 5 responses; agreement_pct stays None because n<30.
    for snap in summary["per_theme"].values():
        assert snap["n_answered"] == 5
        assert snap["agreement_pct"] is None
        # But all 5 landed in the "5" bucket.
        assert snap["distribution"]["5"] == 5


def test_validation_404_for_other_workspace(client, auth_headers, db_session):
    study_id, analysis_id = _seed_study_with_analysis(client, auth_headers, db_session)
    # Sign up Company B.
    client.post(
        "/auth/signup",
        json={"name": "B Co", "email": "b@example.com", "password": "Password123!"},
    )
    b_tokens = client.post(
        "/auth/login",
        json={"email": "b@example.com", "password": "Password123!"},
    ).json()
    b_headers = {"Authorization": f"Bearer {b_tokens['access_token']}"}

    resp = client.post(
        f"/studies/{study_id}/analyses/{analysis_id}/validation-survey",
        headers=b_headers,
    )
    assert resp.status_code == 404

    resp = client.get(
        f"/studies/{study_id}/analyses/{analysis_id}/validation",
        headers=b_headers,
    )
    assert resp.status_code == 404
