"""Guardrails on the survey-segment invite path.

Before these, the endpoint looped over an unbounded segment, sent inside the
request, and committed only at the very end. Three consequences it now
defends against: a reputation-damaging burst, a re-run that re-invites
everyone, and (worst) a mid-loop timeout that rolled back every interview
link while the already-sent emails kept pointing at the dead tokens.
"""
from app.config import settings
from app.models.interview import InterviewLink
from app.models.panel import StudyInvite

from tests.test_surveys import _seed_responses_for_segment


def _invite(client, auth_headers, survey, q):
    return client.post(
        f"/surveys/{survey['id']}/segment/invite",
        headers=auth_headers,
        json={"filters": [{"question_id": q["id"], "operator": "lte", "value": 6}]},
    )


def test_invite_records_study_invite_rows(client, auth_headers, db_session):
    """Without these rows the sends are invisible to the daily cap, the
    cooldown, and the invite funnel."""
    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    resp = _invite(client, auth_headers, survey, q)
    assert resp.status_code == 200, resp.text

    invites = db_session.query(StudyInvite).all()
    assert len(invites) == 2
    assert {i.email for i in invites} == {"resp-0@example.com", "resp-1@example.com"}
    # Denormalised workspace id is what the daily-cap query reads.
    assert all(i.company_id for i in invites)


def test_rerunning_the_same_segment_does_not_reinvite(client, auth_headers, db_session):
    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    first = _invite(client, auth_headers, survey, q).json()
    assert first["invited_count"] == 2

    second = _invite(client, auth_headers, survey, q).json()
    assert second["invited_count"] == 0
    assert second["already_invited_count"] == 2
    # No second link minted for someone who was never emailed again.
    assert second["interview_link_tokens"] == []
    assert db_session.query(StudyInvite).count() == 2


def test_link_is_committed_before_the_email_is_sent(client, auth_headers, db_session):
    """The dead-token bug: a link referenced by a sent email must survive
    even if the request dies before finishing the batch."""
    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    tokens = _invite(client, auth_headers, survey, q).json()["interview_link_tokens"]

    for token in tokens:
        assert (
            db_session.query(InterviewLink).filter_by(token=token).first() is not None
        ), "emailed token has no committed link row"


def test_batch_is_capped_and_the_overflow_is_reported(
    client, auth_headers, db_session, monkeypatch
):
    """Truncation must be visible: a silent cap reads as a full send."""
    from app.services import panel_invites as pi

    monkeypatch.setattr(pi, "INVITE_BATCH_MAX", 1)
    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)

    data = _invite(client, auth_headers, survey, q).json()
    assert data["invited_count"] == 1
    assert data["capped_count"] == 1
    assert db_session.query(StudyInvite).count() == 1


def test_daily_allowance_bounds_the_send(client, auth_headers, db_session, monkeypatch):
    """The segment path shares the panel flow's budget, not its own."""
    monkeypatch.setattr(settings, "INVITE_DAILY_LIMIT", 1, raising=False)
    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)

    data = _invite(client, auth_headers, survey, q).json()
    assert data["invited_count"] == 1
    assert data["capped_count"] == 1


def test_exhausted_daily_allowance_is_refused(
    client, auth_headers, db_session, monkeypatch
):
    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    _invite(client, auth_headers, survey, q)  # uses 2

    monkeypatch.setattr(settings, "INVITE_DAILY_LIMIT", 1, raising=False)
    survey2, q2, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    resp = _invite(client, auth_headers, survey2, q2)
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "invite_daily_limit"


def test_recontact_disabled_blocks_the_endpoint(
    client, auth_headers, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "INVITE_DAILY_LIMIT", 0, raising=False)
    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    assert _invite(client, auth_headers, survey, q).status_code == 403


def test_suppressed_recipient_is_not_invited(client, auth_headers, db_session):
    """End-to-end with the suppression list: a bounced address costs a claim
    but never a send, and the claim is released so a retry is possible."""
    from app.models.email_suppression import REASON_BOUNCE
    from app.services.email_suppression import suppress

    suppress(db_session, "resp-0@example.com", REASON_BOUNCE)
    db_session.commit()

    survey, q, _ = _seed_responses_for_segment(client, auth_headers, db_session)
    data = _invite(client, auth_headers, survey, q).json()

    assert data["invited_count"] == 1
    assert data["failed_emails"] == ["resp-0@example.com"]
    remaining = {i.email for i in db_session.query(StudyInvite).all()}
    assert remaining == {"resp-1@example.com"}
