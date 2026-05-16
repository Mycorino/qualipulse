"""Sprint 12 — survey quota wiring.

Covers:
  - PlanEntitlement seeding picks up the new survey-quota keys.
  - GET /billing/survey-quota returns the workspace's quota state.
  - Public response endpoint gates "Survey is not available" when the
    workspace is over its cap.
"""

from datetime import datetime, timedelta, timezone

from app.models.billing import PlanEntitlement, WorkspaceSubscription
from app.models.company import Company
from app.models.survey import SurveyResponse


def _build_live_survey(client, auth_headers):
    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Quota test"}
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


def test_survey_quota_entitlements_are_seeded(client, auth_headers, db_session):
    """The plan catalogue contains survey_responses_per_period for every paid plan.

    The startup lifespan hook seeds plans against ``SessionLocal``, but tests
    use a per-test in-memory engine — so we invoke the seeder explicitly
    against the test session before reading rows.
    """

    from app.services.billing_service import ensure_plans_seeded
    ensure_plans_seeded(db_session)

    rows = (
        db_session.query(PlanEntitlement)
        .filter(PlanEntitlement.key == "survey_responses_per_period")
        .all()
    )
    plans = {r.plan_id: r.value for r in rows}
    # Decision 2 numbers — see roadmap §1.6.
    assert plans.get("exploration") == 500
    assert plans.get("team") == 2500
    assert plans.get("agency") == 10000


def test_get_billing_survey_quota_returns_status(client, auth_headers):
    resp = client.get("/billing/survey-quota", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Pre-onboarding the workspace is on a legacy plan; it still gets a number.
    assert "responses_used" in body
    assert body["responses_used"] >= 0
    assert "responses_cap" in body
    # All three booleans always present.
    for k in ("is_over_response_cap", "is_near_response_cap", "is_over_surveys_cap"):
        assert k in body


def test_quota_blocks_public_response_when_over_cap(
    client, auth_headers, db_session
):
    """Setting the workspace cap to 0 should immediately block new
    completed responses with a 'not available' response. We override
    the entitlement directly on the in-memory test plan to avoid having
    to plumb a per-workspace override into the data model."""

    survey, q, link = _build_live_survey(client, auth_headers)
    # Find the workspace's plan and force its cap to 0.
    company = db_session.query(Company).first()
    sub = (
        db_session.query(WorkspaceSubscription)
        .filter(WorkspaceSubscription.workspace_id == company.id)
        .first()
    )
    target_plan_id = sub.plan_id if sub else "legacy_starter"
    row = (
        db_session.query(PlanEntitlement)
        .filter(
            PlanEntitlement.plan_id == target_plan_id,
            PlanEntitlement.key == "survey_responses_per_period",
        )
        .first()
    )
    if row is None:
        row = PlanEntitlement(
            plan_id=target_plan_id, key="survey_responses_per_period", value=0
        )
        db_session.add(row)
    else:
        row.value = 0
    db_session.commit()

    resp = client.post(
        f"/r/{link['token']}/responses",
        json={
            "link_token": link["token"],
            "email": "blocked@example.com",
            "answers": [{"question_id": q["id"], "value_numeric": 9}],
            "is_complete": True,
        },
    )
    assert resp.status_code == 404
    assert "not available" in resp.json()["detail"].lower()


def test_quota_allows_response_when_well_under_cap(client, auth_headers):
    """Default seeded caps are well above what a single test response hits."""

    survey, q, link = _build_live_survey(client, auth_headers)
    resp = client.post(
        f"/r/{link['token']}/responses",
        json={
            "link_token": link["token"],
            "email": "ok@example.com",
            "answers": [{"question_id": q["id"], "value_numeric": 9}],
            "is_complete": True,
        },
    )
    assert resp.status_code == 201, resp.text


def test_near_cap_flag_fires_at_80_percent(client, auth_headers, db_session):
    survey, q, link = _build_live_survey(client, auth_headers)
    company = db_session.query(Company).first()
    sub = (
        db_session.query(WorkspaceSubscription)
        .filter(WorkspaceSubscription.workspace_id == company.id)
        .first()
    )
    target_plan_id = sub.plan_id if sub else "legacy_starter"
    row = (
        db_session.query(PlanEntitlement)
        .filter(
            PlanEntitlement.plan_id == target_plan_id,
            PlanEntitlement.key == "survey_responses_per_period",
        )
        .first()
    )
    if row is None:
        row = PlanEntitlement(
            plan_id=target_plan_id, key="survey_responses_per_period", value=10
        )
        db_session.add(row)
    else:
        row.value = 10
    db_session.commit()

    # Insert 8 completed responses (= 80% of 10) directly to bypass the
    # public flow's own quota gate.
    now = datetime.now(timezone.utc)
    if sub:
        sub.current_period_start = now - timedelta(days=1)
        sub.current_period_end = now + timedelta(days=29)
        db_session.commit()
    for i in range(8):
        db_session.add(
            SurveyResponse(
                survey_id=survey["id"],
                company_id=company.id,
                started_at=now,
                completed_at=now,
            )
        )
    db_session.commit()

    resp = client.get("/billing/survey-quota", headers=auth_headers).json()
    assert resp["responses_cap"] == 10
    assert resp["responses_used"] == 8
    assert resp["is_near_response_cap"] is True
    assert resp["is_over_response_cap"] is False
