"""Sprint 6 — survey CRUD + public response collection.

Covers the wedge-critical paths:
  - Creating a survey auto-creates a Study (Decision 8).
  - Question types are validated server-side via Pydantic.
  - Public response endpoint validates link, answers, and is_complete.
  - Constant-time-ish "Survey not available" for any unhappy path.
  - StudyParticipant identity resolution: magic_token > email > new.
"""

from app.models.study import Study, StudyParticipant
from app.models.survey import Survey, SurveyLink, SurveyResponse, SurveyResponseAnswer
from app.services.stats import (
    DEFAULT_MIN_N,
    completion_rate,
    wilson_proportion,
)


# ── Wilson CI / methodology contract (services/stats.py) ──────────────


def test_wilson_returns_none_below_min_n():
    result = wilson_proportion(successes=8, n=20)
    assert result.percentage is None
    assert result.ci_low is None
    assert result.ci_high is None
    assert result.successes == 8
    assert result.n == 20


def test_wilson_returns_percentage_at_min_n():
    result = wilson_proportion(successes=15, n=DEFAULT_MIN_N)
    assert result.percentage is not None
    assert result.ci_low is not None
    assert result.ci_high is not None
    # Wilson centre should be near the observed proportion.
    assert 40 < result.percentage < 60


def test_wilson_extreme_proportions_stay_in_bounds():
    # 0% and 100% are where the normal approx breaks; Wilson must not.
    near_zero = wilson_proportion(successes=0, n=100)
    assert near_zero.ci_low == 0.0
    assert 0.0 <= near_zero.ci_high <= 5.0
    near_full = wilson_proportion(successes=100, n=100)
    # Float math: ci_high may be very slightly under 100 (e.g. 99.999...).
    # The contract is "never exceed 100"; that's what we assert.
    assert near_full.ci_high <= 100.0
    assert 95.0 <= near_full.ci_low <= 100.0
    assert 95.0 <= near_full.ci_high <= 100.0


def test_completion_rate_below_min_n_returns_none():
    assert completion_rate(started=10, completed=8).rate_percentage is None
    assert completion_rate(started=50, completed=40).rate_percentage == 80.0


# ── Survey + Question CRUD ────────────────────────────────────────────


def test_create_survey_auto_creates_study(client, auth_headers, db_session):
    resp = client.post(
        "/surveys/",
        headers=auth_headers,
        json={"name": "Pricing perception", "role": "screener"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Pricing perception"
    assert data["role"] == "screener"
    assert data["study_id"]

    study = db_session.query(Study).filter(Study.id == data["study_id"]).first()
    assert study is not None
    assert study.name == "Pricing perception"


def test_list_surveys_excludes_archived(client, auth_headers):
    a = client.post("/surveys/", headers=auth_headers, json={"name": "A"}).json()
    b = client.post("/surveys/", headers=auth_headers, json={"name": "B"}).json()
    client.delete(f"/surveys/{b['id']}", headers=auth_headers)
    listing = client.get("/surveys/", headers=auth_headers).json()
    ids = {s["id"] for s in listing}
    assert a["id"] in ids
    assert b["id"] not in ids


def test_create_question_validates_likert_config(client, auth_headers):
    survey = client.post("/surveys/", headers=auth_headers, json={"name": "Q1"}).json()
    # Valid Likert: scale 5
    ok = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "likert",
            "prompt": "How satisfied are you?",
            "is_required": True,
            "config": {"scale": 5, "anchors": ["Strongly disagree", "Strongly agree"]},
        },
    )
    assert ok.status_code == 201, ok.text

    # Invalid Likert scale.
    bad = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "likert",
            "prompt": "Bad scale",
            "config": {"scale": 9},
        },
    )
    assert bad.status_code == 422


def test_create_mc_single_requires_choices(client, auth_headers):
    survey = client.post("/surveys/", headers=auth_headers, json={"name": "Q"}).json()
    bad = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "mc_single",
            "prompt": "Pick one",
            "config": {"choices": [{"id": "a", "label": "Only one"}]},
        },
    )
    # min_length=2 on choices.
    assert bad.status_code == 422


def test_deprecated_question_excluded_from_listing(client, auth_headers):
    survey = client.post("/surveys/", headers=auth_headers, json={"name": "Q"}).json()
    q = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "open_text",
            "prompt": "Anything?",
            "config": {"max_chars": 200, "ai_cluster": False},
        },
    ).json()
    client.delete(
        f"/surveys/{survey['id']}/questions/{q['id']}", headers=auth_headers
    )
    listing = client.get(
        f"/surveys/{survey['id']}/questions", headers=auth_headers
    ).json()
    assert all(item["id"] != q["id"] for item in listing)


# ── Survey link + public response ─────────────────────────────────────


def _build_live_survey(client, auth_headers, db_session):
    """Fixture-ish helper: builds a 2-question live survey + a link.

    Returns (survey, link, questions) where the survey is already in the
    'live' status so the public endpoint will accept submissions.
    """

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Live"}
    ).json()
    q1 = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "nps",
            "prompt": "Recommend?",
            "is_required": True,
            "config": {"context": "the product"},
        },
    ).json()
    q2 = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "open_text",
            "prompt": "Why?",
            "config": {"max_chars": 200, "ai_cluster": False},
        },
    ).json()
    link = client.post(
        f"/surveys/{survey['id']}/links",
        headers=auth_headers,
        json={"is_anonymous": False},
    ).json()
    # Activate the survey via PATCH.
    client.patch(
        f"/surveys/{survey['id']}", headers=auth_headers, json={"status": "live"}
    )
    return survey, link, (q1, q2)


def test_public_response_creates_participant_and_answers(
    client, auth_headers, db_session
):
    survey, link, (q1, q2) = _build_live_survey(client, auth_headers, db_session)

    resp = client.post(
        f"/surveys/{survey['id']}/responses",
        json={
            "link_token": link["token"],
            "email": "Alice+test@Example.com",
            "display_name": "Alice",
            "answers": [
                {"question_id": q1["id"], "value_numeric": 9},
                {"question_id": q2["id"], "value_text": "Love it."},
            ],
            "is_complete": True,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["is_complete"] is True
    assert data["study_participant_id"]

    # Email is normalized: plus-stripped, lowercased.
    participant = (
        db_session.query(StudyParticipant)
        .filter(StudyParticipant.id == data["study_participant_id"])
        .first()
    )
    assert participant is not None
    assert participant.email_normalized == "alice@example.com"

    # Two answers stored.
    answers = db_session.query(SurveyResponseAnswer).all()
    assert len(answers) == 2


def test_public_response_rejects_inactive_link(
    client, auth_headers, db_session
):
    survey, link, (q1, q2) = _build_live_survey(client, auth_headers, db_session)
    # Manually deactivate the link.
    link_row = db_session.query(SurveyLink).filter(SurveyLink.id == link["id"]).first()
    link_row.is_active = False
    db_session.commit()

    resp = client.post(
        f"/surveys/{survey['id']}/responses",
        json={
            "link_token": link["token"],
            "answers": [
                {"question_id": q1["id"], "value_numeric": 9},
            ],
            "is_complete": False,
        },
    )
    assert resp.status_code == 404


def test_public_response_rejects_missing_required(
    client, auth_headers, db_session
):
    survey, link, (q1, q2) = _build_live_survey(client, auth_headers, db_session)
    resp = client.post(
        f"/surveys/{survey['id']}/responses",
        json={
            "link_token": link["token"],
            "answers": [
                # q2 only — q1 (required) is missing.
                {"question_id": q2["id"], "value_text": "incomplete"},
            ],
            "is_complete": True,
        },
    )
    assert resp.status_code == 422


def test_public_response_rejects_out_of_range_nps(
    client, auth_headers, db_session
):
    survey, link, (q1, _) = _build_live_survey(client, auth_headers, db_session)
    resp = client.post(
        f"/surveys/{survey['id']}/responses",
        json={
            "link_token": link["token"],
            "answers": [
                {"question_id": q1["id"], "value_numeric": 11},
            ],
            "is_complete": False,
        },
    )
    assert resp.status_code == 422


def test_public_response_anonymous_link_skips_participant(
    client, auth_headers, db_session
):
    survey = client.post("/surveys/", headers=auth_headers, json={"name": "Anon"}).json()
    q = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "nps",
            "prompt": "Score?",
            "config": {},
        },
    ).json()
    link = client.post(
        f"/surveys/{survey['id']}/links",
        headers=auth_headers,
        json={"is_anonymous": True},
    ).json()
    client.patch(f"/surveys/{survey['id']}", headers=auth_headers, json={"status": "live"})

    resp = client.post(
        f"/surveys/{survey['id']}/responses",
        json={
            "link_token": link["token"],
            "email": "should-be-ignored@example.com",
            "answers": [{"question_id": q["id"], "value_numeric": 7}],
            "is_complete": True,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    # Anonymous link → no StudyParticipant.
    assert data["study_participant_id"] is None
    # Email was provided but ignored — no participant row created.
    assert db_session.query(StudyParticipant).count() == 0


def test_email_match_within_study_reuses_participant(
    client, auth_headers, db_session
):
    survey, link, (q1, _) = _build_live_survey(client, auth_headers, db_session)

    first = client.post(
        f"/surveys/{survey['id']}/responses",
        json={
            "link_token": link["token"],
            "email": "bob@example.com",
            "answers": [{"question_id": q1["id"], "value_numeric": 8}],
            "is_complete": False,
        },
    ).json()
    second = client.post(
        f"/surveys/{survey['id']}/responses",
        json={
            "link_token": link["token"],
            "email": "BOB+resume@example.com",  # case + plus-tag
            "answers": [{"question_id": q1["id"], "value_numeric": 9}],
            "is_complete": False,
        },
    ).json()
    assert first["study_participant_id"] == second["study_participant_id"]
    # Single participant row in the Study.
    assert db_session.query(StudyParticipant).count() == 1


# ── Sprint 8: public response endpoint + dashboard ──────────────────


def test_public_get_returns_survey_by_token(client, auth_headers, db_session):
    survey, link, (q1, q2) = _build_live_survey(client, auth_headers, db_session)
    resp = client.get(f"/r/{link['token']}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "Live"
    assert data["is_anonymous"] is False
    assert len(data["questions"]) == 2
    assert data["questions"][0]["id"] == q1["id"]


def test_public_get_404_for_draft_survey(client, auth_headers, db_session):
    """Draft-status surveys are never publicly visible."""

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Drafty"}
    ).json()
    link = client.post(
        f"/surveys/{survey['id']}/links",
        headers=auth_headers,
        json={"is_anonymous": False},
    ).json()
    # No PATCH to live — survey stays in draft.
    resp = client.get(f"/r/{link['token']}")
    assert resp.status_code == 404
    assert "not available" in resp.json()["detail"].lower()


def test_public_post_via_r_token_endpoint(client, auth_headers, db_session):
    survey, link, (q1, q2) = _build_live_survey(client, auth_headers, db_session)
    resp = client.post(
        f"/r/{link['token']}/responses",
        json={
            "link_token": "",
            "email": "publicpost@example.com",
            "answers": [
                {"question_id": q1["id"], "value_numeric": 8},
                {"question_id": q2["id"], "value_text": "It's good."},
            ],
            "is_complete": True,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["is_complete"] is True
    assert data["study_participant_id"]


def test_dashboard_nps_histogram_and_score(client, auth_headers, db_session):
    """End-to-end: drop 30 NPS scores → dashboard returns histogram + NPS."""

    # Set up a live survey with a single NPS question.
    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "NPS"}
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
    client.patch(f"/surveys/{survey['id']}", headers=auth_headers, json={"status": "live"})

    # Submit 30 responses to clear the min_n threshold:
    # 6 detractors (0-6 scored as 3), 4 passives (7), 20 promoters (10).
    for i in range(30):
        if i < 6:
            score = 3
        elif i < 10:
            score = 7
        else:
            score = 10
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "email": f"resp-{i}@example.com",
                "answers": [{"question_id": q["id"], "value_numeric": score}],
                "is_complete": True,
            },
        )

    # Now fetch the dashboard.
    resp = client.get(f"/surveys/{survey['id']}/dashboard", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["n_started"] == 30
    assert data["n_completed"] == 30
    assert data["completion_rate_percentage"] == 100.0
    q_payload = data["questions"][0]
    assert q_payload["n_answered"] == 30
    # NPS score: (20 promoters - 6 detractors) / 30 * 100 = 46-47
    nps = q_payload["breakdown"]["nps_score"]
    assert 46 <= nps <= 47
    # Histogram has 11 buckets (0-10).
    assert len(q_payload["breakdown"]["histogram"]) == 11
    # Bucket 10 has count 20.
    bucket_10 = next(b for b in q_payload["breakdown"]["histogram"] if b["bucket"] == 10)
    assert bucket_10["count"] == 20


def test_dashboard_below_min_n_suppresses_percentages(
    client, auth_headers, db_session
):
    """The methodology contract: n<30 → percentage is None."""

    survey, link, (q1, _) = _build_live_survey(client, auth_headers, db_session)
    # Send only 5 responses — far below min_n.
    for i in range(5):
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "email": f"small-n-{i}@example.com",
                "answers": [{"question_id": q1["id"], "value_numeric": 9}],
                "is_complete": True,
            },
        )

    resp = client.get(f"/surveys/{survey['id']}/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["n_completed"] == 5
    # Completion rate is suppressed because total is below min_n.
    assert data["completion_rate_percentage"] is None
    # All histogram percentages are None.
    histogram = data["questions"][0]["breakdown"]["histogram"]
    for bucket in histogram:
        assert bucket["percentage"] is None, f"bucket {bucket['bucket']} leaked a percentage"
        assert bucket["ci_low"] is None
        assert bucket["ci_high"] is None


# ── Templates ────────────────────────────────────────────────────────


def test_templates_list_is_workspace_safe(client, auth_headers):
    resp = client.get("/surveys/templates", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    ids = {item["id"] for item in items}
    assert "churn_pricing_onboarding" in ids


def test_create_from_template_seeds_questions(client, auth_headers, db_session):
    resp = client.post(
        "/surveys/from-template/churn_pricing_onboarding", headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    survey = resp.json()
    assert survey["name"].startswith("Why new users churn")
    assert survey["role"] == "screener"
    assert survey["question_count"] == 5

    qs = client.get(
        f"/surveys/{survey['id']}/questions", headers=auth_headers
    ).json()
    assert len(qs) == 5
    types = [q["type"] for q in qs]
    assert "likert" in types and "nps" in types and "mc_multi" in types
    # First question is a Likert about pricing-page clarity.
    assert "pricing page" in qs[0]["prompt"].lower()
    assert qs[0]["is_required"] is True


def test_create_from_unknown_template_returns_404(client, auth_headers):
    resp = client.post("/surveys/from-template/nope", headers=auth_headers)
    assert resp.status_code == 404


# ── Sprint 9: screener-bridge segment filtering + invite ─────────────


def _seed_responses_for_segment(client, auth_headers, db_session):
    """Helper: build a live NPS survey with 6 completed responses spanning
    detractors / passives / promoters so segment filters have something
    to slice."""

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Segment test"}
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
    client.patch(f"/surveys/{survey['id']}", headers=auth_headers, json={"status": "live"})

    # 2 detractors, 2 passives, 2 promoters.
    scores = [3, 4, 7, 8, 9, 10]
    for i, score in enumerate(scores):
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "email": f"resp-{i}@example.com",
                "answers": [{"question_id": q["id"], "value_numeric": score}],
                "is_complete": True,
            },
        )

    return survey, q, link


def test_segment_preview_lte_returns_detractors(client, auth_headers, db_session):
    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    resp = client.post(
        f"/surveys/{survey['id']}/segment/preview",
        headers=auth_headers,
        json={"filters": [{"question_id": q["id"], "operator": "lte", "value": 6}]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 2 detractors qualify (scores 3 and 4).
    assert data["match_count"] == 2
    assert data["invitable_count"] == 2
    assert data["skipped_anonymous_count"] == 0
    assert len(data["sample_invitees"]) == 2


def test_segment_preview_gte_returns_promoters(client, auth_headers, db_session):
    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    resp = client.post(
        f"/surveys/{survey['id']}/segment/preview",
        headers=auth_headers,
        json={"filters": [{"question_id": q["id"], "operator": "gte", "value": 9}]},
    ).json()
    assert resp["match_count"] == 2


def test_segment_preview_empty_filters_returns_all_completed(
    client, auth_headers, db_session
):
    survey, _, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    resp = client.post(
        f"/surveys/{survey['id']}/segment/preview",
        headers=auth_headers,
        json={"filters": []},
    ).json()
    assert resp["match_count"] == 6


def test_segment_invite_creates_interview_links_for_matched(
    client, auth_headers, db_session
):
    """The wedge: matching respondents -> interview links.

    Email sending is disabled in tests (no SENDGRID_API_KEY), so
    `invited_count` will be 0 and the failed list will hold the matched
    emails. The actual link creation still happens, which is the part of
    the contract we care about here.
    """

    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    # Need a project to invite into — survey's company has none yet, so create one.
    client.post(
        "/projects/",
        headers=auth_headers,
        json={
            "name": "Follow-up interviews",
            "language": "en",
            "questions": [
                {
                    "section_index": 0,
                    "section_title": "Intro",
                    "question_index": 0,
                    "main_question": "Tell me about your experience.",
                }
            ],
        },
    )

    resp = client.post(
        f"/surveys/{survey['id']}/segment/invite",
        headers=auth_headers,
        json={"filters": [{"question_id": q["id"], "operator": "lte", "value": 6}]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 2 detractors → 2 tokens created.
    assert len(data["interview_link_tokens"]) == 2
    # invited_count counts successful EMAIL sends. With email disabled it's 0
    # and the 2 emails land in failed_emails. The links still got created
    # in the DB — that's what makes the wedge real.
    assert data["invited_count"] + len(data["failed_emails"]) == 2


def test_segment_invite_400_without_project(client, auth_headers, db_session):
    """No interview track available → can't invite."""

    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    resp = client.post(
        f"/surveys/{survey['id']}/segment/invite",
        headers=auth_headers,
        json={"filters": [{"question_id": q["id"], "operator": "lte", "value": 6}]},
    )
    assert resp.status_code == 400
    assert "interview project" in resp.json()["detail"].lower()


# ── Sprint 10: Segment Discoveries ───────────────────────────────────


def _build_two_question_survey(client, auth_headers):
    """Survey with one mc_single segment question and one NPS metric question."""

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Discovery test"}
    ).json()
    seg_q = client.post(
        f"/surveys/{survey['id']}/questions",
        headers=auth_headers,
        json={
            "type": "mc_single",
            "prompt": "Your role?",
            "config": {
                "choices": [
                    {"id": "pm", "label": "Product Manager"},
                    {"id": "designer", "label": "Designer"},
                    {"id": "eng", "label": "Engineer"},
                ],
                "randomize": False,
                "has_other": False,
            },
        },
    ).json()
    metric_q = client.post(
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
    return survey, seg_q, metric_q, link


def test_discoveries_detects_segment_with_lower_nps(client, auth_headers):
    """A clear over-indexing segment surfaces as a discovery."""

    survey, seg_q, metric_q, link = _build_two_question_survey(client, auth_headers)

    # 40 PMs averaging 3 (detractors) — well below overall.
    # 40 Engineers averaging 9 (promoters) — well above overall.
    cohorts = [("pm", 3, 40), ("eng", 9, 40)]
    counter = 0
    for role, score, n in cohorts:
        for _ in range(n):
            counter += 1
            client.post(
                f"/r/{link['token']}/responses",
                json={
                    "link_token": link["token"],
                    "email": f"r-{counter}@example.com",
                    "answers": [
                        {"question_id": seg_q["id"], "value_choice_ids": [role]},
                        {"question_id": metric_q["id"], "value_numeric": score},
                    ],
                    "is_complete": True,
                },
            )

    resp = client.get(f"/surveys/{survey['id']}/discoveries", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["survey_id"] == survey["id"]
    titles = [d["title"] for d in data["discoveries"]]
    # PMs score below overall — at least one card mentions them.
    assert any("Product Manager" in t.lower().title() or "product manager" in t.lower() for t in titles), titles
    # Ready filter clauses point at the segment question.
    for d in data["discoveries"]:
        assert d["ready_filter"]
        assert d["ready_filter"][0]["question_id"] == seg_q["id"]


def test_discoveries_confidence_pills(client, auth_headers):
    """Larger samples should produce a higher confidence pill."""

    survey, seg_q, metric_q, link = _build_two_question_survey(client, auth_headers)

    # 100 PMs at score 2, 100 Engineers at score 10 — should produce "strong" evidence.
    for role, score in [("pm", 2)] * 100 + [("eng", 10)] * 100:
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "answers": [
                    {"question_id": seg_q["id"], "value_choice_ids": [role]},
                    {"question_id": metric_q["id"], "value_numeric": score},
                ],
                "is_complete": True,
            },
        )

    data = client.get(f"/surveys/{survey['id']}/discoveries", headers=auth_headers).json()
    confs = [d["confidence"] for d in data["discoveries"]]
    # At this sample size + effect size, at least one finding should be "strong".
    assert "strong" in confs or "supported" in confs, confs


def test_discoveries_directional_for_small_segments(client, auth_headers):
    """A segment with n<30 should max out at 'directional', never 'strong'."""

    survey, seg_q, metric_q, link = _build_two_question_survey(client, auth_headers)

    # Only 10 designers + 40 engineers. Designer segment is below the n=30 threshold.
    cohorts = [("designer", 1, 10), ("eng", 10, 40)]
    counter = 0
    for role, score, n in cohorts:
        for _ in range(n):
            counter += 1
            client.post(
                f"/r/{link['token']}/responses",
                json={
                    "link_token": link["token"],
                    "answers": [
                        {"question_id": seg_q["id"], "value_choice_ids": [role]},
                        {"question_id": metric_q["id"], "value_numeric": score},
                    ],
                    "is_complete": True,
                },
            )

    data = client.get(f"/surveys/{survey['id']}/discoveries", headers=auth_headers).json()
    # Find any discovery surfaced for the designer cohort.
    designer_discos = [
        d for d in data["discoveries"]
        if any(rf["value"] == ["designer"] for rf in d["ready_filter"])
    ]
    for d in designer_discos:
        assert d["confidence"] == "directional", d


def test_discoveries_empty_for_under_used_survey(client, auth_headers):
    """A survey with too few responses returns no discoveries."""

    survey, _, _, link = _build_two_question_survey(client, auth_headers)
    # 3 responses total — well below the MIN_SEGMENT_N floor.
    for i in range(3):
        client.post(
            f"/r/{link['token']}/responses",
            json={"link_token": link["token"], "answers": [], "is_complete": True},
        )
    data = client.get(f"/surveys/{survey['id']}/discoveries", headers=auth_headers).json()
    assert data["discoveries"] == []


def test_response_only_visible_to_owner_workspace(client, auth_headers, db_session):
    """Auth isolation — a survey created by company A is not listable by B."""

    # Company A creates a survey.
    a_survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "A's"}
    ).json()

    # Company B signs up.
    client.post(
        "/auth/signup",
        json={"name": "B Co", "email": "b@example.com", "password": "Password123!"},
    )
    b_login = client.post(
        "/auth/login", json={"email": "b@example.com", "password": "Password123!"}
    ).json()
    b_headers = {"Authorization": f"Bearer {b_login['access_token']}"}

    # B sees nothing of A's.
    listing = client.get("/surveys/", headers=b_headers).json()
    assert all(s["id"] != a_survey["id"] for s in listing)

    # B can't fetch A's survey directly.
    resp = client.get(f"/surveys/{a_survey['id']}", headers=b_headers)
    assert resp.status_code == 404
