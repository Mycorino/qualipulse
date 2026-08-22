"""Participant review + reward tools for compensated studies.

The hinge: `Participant.counts_for_research` is the one definition of
"does this interview count". Rejected interviews must vanish from every
research output (analysis input, counts, CSV export, copilot snapshot)
while billing / paywall keep counting plain completions.
"""
import uuid
from datetime import datetime

from app.models.company import Company
from app.models.interview import (
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    InterviewLink,
    InterviewTurn,
    Participant,
)
from app.models.project import Project
from app.services.interview_engine import _mark_completed
from app.services.paywall import get_visibility_state


def _project(db, company_id, *, incentive=None) -> Project:
    p = Project(
        id=str(uuid.uuid4()), company_id=company_id, name="Study", language="en",
        incentive_text=incentive,
    )
    db.add(p)
    db.commit()
    return p


def _participant(db, project_id, *, status="completed", review=REVIEW_APPROVED, with_turn=True) -> Participant:
    link = InterviewLink(id=str(uuid.uuid4()), project_id=project_id, token=uuid.uuid4().hex)
    db.add(link)
    db.flush()
    p = Participant(
        id=str(uuid.uuid4()), link_id=link.id, project_id=project_id, status=status,
        started_at=datetime.utcnow(), completed_at=datetime.utcnow() if status == "completed" else None,
        review_status=review, email="p@example.com", display_name="Pat",
    )
    db.add(p)
    db.flush()
    if with_turn:
        db.add(InterviewTurn(
            participant_id=p.id, turn_index=1, question_index=0, is_follow_up=False,
            question_text="Q?", response_transcript="An answer with enough words to count.",
        ))
    db.commit()
    db.refresh(p)
    return p


def _company(db) -> Company:
    c = db.query(Company).filter(Company.email == "test@example.com").first()
    return c


# ── Model-level definition ──────────────────────────────────────────────────


def test_counts_for_research_python_and_sql(db_session, registered_company):
    company = _company(db_session)
    project = _project(db_session, company.id)
    ok = _participant(db_session, project.id)
    rejected = _participant(db_session, project.id, review=REVIEW_REJECTED)
    pending = _participant(db_session, project.id, review=REVIEW_PENDING)
    in_progress = _participant(db_session, project.id, status="in_progress")

    assert ok.counts_for_research is True
    assert pending.counts_for_research is True  # pending still counts, only reject excludes
    assert rejected.counts_for_research is False
    assert in_progress.counts_for_research is False

    ids = {
        pid for (pid,) in db_session.query(Participant.id)
        .filter(Participant.project_id == project.id, Participant.counts_for_research)
    }
    assert ids == {ok.id, pending.id}


def test_mark_completed_queues_review_only_with_incentive(db_session, registered_company):
    company = _company(db_session)
    paid = _project(db_session, company.id, incentive="€20 voucher")
    free = _project(db_session, company.id)
    p_paid = _participant(db_session, paid.id, status="in_progress")
    p_free = _participant(db_session, free.id, status="in_progress")

    _mark_completed(p_paid, db_session, reason="natural", bill=False, completed_via="test")
    _mark_completed(p_free, db_session, reason="natural", bill=False, completed_via="test")
    db_session.commit()

    assert p_paid.review_status == REVIEW_PENDING
    assert p_free.review_status == REVIEW_APPROVED


# ── Rejected interviews vanish from research outputs ───────────────────────


def test_rejected_excluded_from_list_counts_and_csv(client, auth_headers, db_session, registered_company):
    company = _company(db_session)
    project = _project(db_session, company.id, incentive="€20")
    good = _participant(db_session, project.id)
    bad = _participant(db_session, project.id, review=REVIEW_REJECTED)

    # Project list: completed count excludes the rejected row.
    listing = client.get("/projects/", headers=auth_headers).json()
    row = next(r for r in listing if r["id"] == project.id)
    assert row["completed_count"] == 1

    # Participant list still shows the rejected row (researcher must be able
    # to un-reject) with its review state.
    parts = client.get(f"/projects/{project.id}/participants", headers=auth_headers).json()
    by_id = {p["id"]: p for p in parts}
    assert by_id[good.id]["review_status"] == "approved"
    assert by_id[bad.id]["review_status"] == "rejected"

    # CSV export: rejected participant never reaches the file.
    company.subscription_tier = "lab"  # csv export entitlement (legacy gate)
    db_session.commit()
    resp = client.get(f"/projects/{project.id}/export", headers=auth_headers)
    if resp.status_code == 200:
        assert good.id in resp.text
        assert bad.id not in resp.text


def test_rejected_excluded_from_analysis_input_and_copilot_snapshot(db_session, registered_company):
    from app.services.copilot_interview import _progress_snapshot, _interviews_index

    company = _company(db_session)
    project = _project(db_session, company.id, incentive="€20")
    good = _participant(db_session, project.id)
    _participant(db_session, project.id, review=REVIEW_REJECTED)
    db_session.refresh(project)

    snap = _progress_snapshot(project)
    assert snap["completed_interviews"] == 1
    assert [i["id"] for i in _interviews_index(project)] == [good.id]

    # Same filter the analysis pipeline applies before building transcript blocks.
    assert [p.id for p in project.participants if p.counts_for_research and p.turns] == [good.id]


def test_rejected_still_counts_for_paywall(db_session, registered_company):
    """Rejecting is not a refund: the free-preview slot stays consumed."""
    company = _company(db_session)
    company.has_ever_paid = False
    company.subscription_status = "trialing"
    project = _project(db_session, company.id, incentive="€20")
    _participant(db_session, project.id, review=REVIEW_REJECTED)
    db_session.commit()
    state = get_visibility_state(db_session, company)
    assert state.free_used == 1


# ── Endpoints ───────────────────────────────────────────────────────────────


def test_review_and_reward_endpoints(client, auth_headers, db_session, registered_company):
    company = _company(db_session)
    project = _project(db_session, company.id, incentive="€20 voucher")
    p = _participant(db_session, project.id, review=REVIEW_PENDING)
    in_prog = _participant(db_session, project.id, status="in_progress", review=REVIEW_PENDING)
    base = f"/projects/{project.id}/participants"

    # Reward before approval is refused.
    r = client.patch(f"{base}/{p.id}/reward", json={"sent": True}, headers=auth_headers)
    assert r.status_code == 400 and r.json()["detail"] == "participant_not_approved"

    # Cannot review an unfinished interview.
    r = client.patch(f"{base}/{in_prog.id}/review", json={"status": "approved"}, headers=auth_headers)
    assert r.status_code == 400 and r.json()["detail"] == "participant_not_completed"

    r = client.patch(f"{base}/{p.id}/review", json={"status": "bogus"}, headers=auth_headers)
    assert r.status_code == 400

    r = client.patch(f"{base}/{p.id}/review", json={"status": "approved", "note": " looks good "}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["review_status"] == "approved"
    assert r.json()["review_note"] == "looks good"
    assert r.json()["reviewed_at"]

    r = client.patch(f"{base}/{p.id}/reward", json={"sent": True}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["reward_sent_at"]

    # Payout CSV: pending_only hides the already-rewarded row; full list shows it.
    r = client.get(f"{base}/rewards.csv", headers=auth_headers)
    assert r.status_code == 200 and p.id not in r.text
    r = client.get(f"{base}/rewards.csv?pending_only=false", headers=auth_headers)
    assert p.id in r.text and "€20 voucher" in r.text and "p@example.com" in r.text

    # Rejecting clears the reward stamp and drops the row from the payout list.
    r = client.patch(f"{base}/{p.id}/review", json={"status": "rejected"}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["reward_sent_at"] is None
    r = client.get(f"{base}/rewards.csv?pending_only=false", headers=auth_headers)
    assert p.id not in r.text


def test_bulk_reward_skips_unapproved(client, auth_headers, db_session, registered_company):
    company = _company(db_session)
    project = _project(db_session, company.id, incentive="€20")
    a = _participant(db_session, project.id)
    b = _participant(db_session, project.id, review=REVIEW_PENDING)
    r = client.post(
        f"/projects/{project.id}/participants/rewards/bulk",
        json={"participant_ids": [a.id, b.id], "sent": True},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert [row["id"] for row in r.json()] == [a.id]


def test_incentive_text_round_trips_and_reaches_participant(client, auth_headers, db_session, registered_company):
    r = client.post(
        "/projects/",
        json={"name": "Paid study", "questions": [{"section_index": 0, "section_title": "S", "question_index": 0, "main_question": "Why?"}],
              "incentive_text": "  €20 Amazon voucher  "},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["incentive_text"] == "€20 Amazon voucher"

    r = client.patch(f"/projects/{pid}/settings", json={"incentive_text": ""}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["incentive_text"] is None

    client.patch(f"/projects/{pid}/settings", json={"incentive_text": "€10"}, headers=auth_headers)
    link = client.post(f"/projects/{pid}/links", json={}, headers=auth_headers)
    assert link.status_code == 201, link.text
    info = client.get(f"/interview/{link.json()['token']}")
    assert info.status_code == 200
    assert info.json()["incentive_text"] == "€10"
