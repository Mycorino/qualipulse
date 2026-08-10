"""Per-link participant cap + duplicate-participant guard.

Both protect the workspace credit balance from a shared interview link that
leaks: the cap bounds how many participants one link can admit, the duplicate
guard stops the same person being charged (and analysed) twice.
"""
import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, Participant
from app.models.project import Project


@pytest.fixture
def seeded(client, db_session, monkeypatch):
    """A company + project + link, with the AI engine stubbed out."""
    company = Company(
        name="Acme", email="owner@acme.com", password_hash="x", email_verified=True
    )
    db_session.add(company)
    db_session.flush()
    project = Project(company_id=company.id, name="Study", language="en")
    db_session.add(project)
    db_session.flush()
    link = InterviewLink(project_id=project.id, token="tok-guardrails", is_active=True)
    db_session.add(link)
    db_session.commit()

    # The workspace credit gate runs on every start; give the company a normal
    # trial subscription so these tests exercise the guardrails, not billing.
    from app.services.billing_service import (
        bootstrap_trial_subscription,
        ensure_plans_seeded,
    )

    ensure_plans_seeded(db_session)
    bootstrap_trial_subscription(db_session, company)

    from app.routers import interview as interview_router

    monkeypatch.setattr(
        interview_router,
        "start_interview",
        lambda pid, db: {
            "question_text": "First question?",
            "tts_audio_url": None,
            "is_warmup": False,
        },
    )
    return {"company": company, "project": project, "link": link}


def _start(client, token, **body):
    return client.post(f"/interview/{token}/start", json=body)


def _add_participant(db_session, link, project, email=None, status="in_progress"):
    p = Participant(
        link_id=link.id, project_id=project.id, email=email, status=status
    )
    db_session.add(p)
    db_session.commit()
    return p


# ── Participant cap ─────────────────────────────────────────────────────────

def test_no_cap_admits_participants(client, seeded):
    assert _start(client, seeded["link"].token, display_name="A").status_code == 200


def test_cap_blocks_once_reached(client, db_session, seeded):
    link, project = seeded["link"], seeded["project"]
    link.max_participants = 2
    db_session.commit()

    assert _start(client, link.token, email="one@x.com").status_code == 200
    assert _start(client, link.token, email="two@x.com").status_code == 200

    r = _start(client, link.token, email="three@x.com")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "link_full"
    # The blocked start must not leave a participant row behind.
    assert db_session.query(Participant).filter(
        Participant.project_id == project.id
    ).count() == 2


def test_cap_counts_in_progress_participants(client, db_session, seeded):
    """A burst of simultaneous starts can't overshoot: in-progress counts."""
    link, project = seeded["link"], seeded["project"]
    link.max_participants = 1
    _add_participant(db_session, link, project, email="early@x.com")

    r = _start(client, link.token, email="late@x.com")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "link_full"


def test_cap_is_per_link_not_per_project(client, db_session, seeded):
    """A capped link doesn't constrain a second link on the same study."""
    link, project = seeded["link"], seeded["project"]
    link.max_participants = 1
    _add_participant(db_session, link, project, email="early@x.com")
    other = InterviewLink(project_id=project.id, token="tok-other", is_active=True)
    db_session.add(other)
    db_session.commit()

    assert _start(client, other.token, email="fresh@x.com").status_code == 200


# ── Duplicate guard ─────────────────────────────────────────────────────────

def test_second_start_same_email_offers_resume(client, db_session, seeded):
    link, project = seeded["link"], seeded["project"]
    existing = _add_participant(db_session, link, project, email="dup@x.com")

    r = _start(client, link.token, email="dup@x.com")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "resume_available"
    assert detail["participant_id"] == existing.id
    assert db_session.query(Participant).filter(
        Participant.project_id == project.id
    ).count() == 1


def test_completed_email_cannot_start_again(client, db_session, seeded):
    link, project = seeded["link"], seeded["project"]
    _add_participant(db_session, link, project, email="done@x.com", status="completed")

    r = _start(client, link.token, email="done@x.com")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "already_completed"


def test_duplicate_match_is_case_insensitive(client, db_session, seeded):
    link, project = seeded["link"], seeded["project"]
    _add_participant(db_session, link, project, email="mixed@x.com", status="completed")

    r = _start(client, link.token, email="  MiXeD@X.com ")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "already_completed"


def test_duplicate_guard_is_per_link(client, db_session, seeded):
    """The same person may be invited to two different links of a study."""
    link, project = seeded["link"], seeded["project"]
    _add_participant(db_session, link, project, email="both@x.com", status="completed")
    other = InterviewLink(project_id=project.id, token="tok-second", is_active=True)
    db_session.add(other)
    db_session.commit()

    assert _start(client, other.token, email="both@x.com").status_code == 200


def test_anonymous_starts_are_never_deduped(client, db_session, seeded):
    """No email means no identity to dedupe on — must not block anyone."""
    link = seeded["link"]
    assert _start(client, link.token, display_name="A").status_code == 200
    assert _start(client, link.token, display_name="B").status_code == 200


# ── Cap management API ──────────────────────────────────────────────────────

def test_set_and_clear_cap_via_api(client, auth_headers, db_session):
    project = client.post(
        "/projects/", json={"name": "S", "language": "en"}, headers=auth_headers
    ).json()
    link = client.post(
        f"/projects/{project['id']}/links", headers=auth_headers
    ).json()
    assert link["max_participants"] is None
    assert link["participant_count"] == 0

    r = client.patch(
        f"/links/{link['id']}", json={"max_participants": 25}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["max_participants"] == 25
    # Setting a cap must not flip the active state (the legacy toggle path).
    assert r.json()["is_active"] is True

    r = client.patch(
        f"/links/{link['id']}",
        json={"clear_max_participants": True},
        headers=auth_headers,
    )
    assert r.json()["max_participants"] is None


def test_bodyless_patch_still_toggles(client, auth_headers):
    project = client.post(
        "/projects/", json={"name": "S", "language": "en"}, headers=auth_headers
    ).json()
    link = client.post(
        f"/projects/{project['id']}/links", headers=auth_headers
    ).json()

    r = client.patch(f"/links/{link['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False


def test_cap_below_current_participants_rejected(
    client, auth_headers, db_session
):
    project = client.post(
        "/projects/", json={"name": "S", "language": "en"}, headers=auth_headers
    ).json()
    link_json = client.post(
        f"/projects/{project['id']}/links", headers=auth_headers
    ).json()
    link = db_session.query(InterviewLink).filter(
        InterviewLink.id == link_json["id"]
    ).first()
    for i in range(3):
        db_session.add(
            Participant(link_id=link.id, project_id=project["id"], email=f"p{i}@x.com")
        )
    db_session.commit()

    r = client.patch(
        f"/links/{link.id}", json={"max_participants": 2}, headers=auth_headers
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "cap_below_current"
    assert r.json()["detail"]["current"] == 3
    # Setting it exactly at the current count is allowed (closes the link).
    assert client.patch(
        f"/links/{link.id}", json={"max_participants": 3}, headers=auth_headers
    ).status_code == 200
