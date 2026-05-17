"""Sprint 15 — every Project belongs to a Study.

v1 left projects created after Alembic 0024 with study_id=NULL. These
tests pin the fix: project creation auto-creates (or joins) a Study,
and the Screener Bridge creates a study-linked interview round instead
of borrowing an unrelated project.
"""

from app.models.project import InterviewGuideQuestion, Project
from app.models.study import Study


def _make_project(client, auth_headers, name="Test project", study_id=None):
    body = {
        "name": name,
        "language": "en",
        "questions": [
            {
                "section_index": 0,
                "section_title": "Intro",
                "question_index": 0,
                "main_question": "Tell me about your experience.",
            }
        ],
    }
    if study_id:
        body["study_id"] = study_id
    return client.post("/projects/", headers=auth_headers, json=body)


def test_create_project_auto_creates_a_study(client, auth_headers, db_session):
    resp = _make_project(client, auth_headers, name="Churn research")
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["id"]

    project = db_session.query(Project).filter(Project.id == project_id).first()
    assert project.study_id is not None
    study = db_session.query(Study).filter(Study.id == project.study_id).first()
    assert study is not None
    assert study.name == "Churn research"


def test_create_project_joins_existing_study_when_study_id_passed(
    client, auth_headers, db_session
):
    # Create a survey first → that auto-creates a Study.
    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Screener"}
    ).json()
    study_id = survey["study_id"]

    # Now create a project INTO that study.
    resp = _make_project(client, auth_headers, name="Follow-ups", study_id=study_id)
    assert resp.status_code == 201, resp.text
    project = db_session.query(Project).filter(Project.id == resp.json()["id"]).first()
    assert project.study_id == study_id

    # The study now has both instruments.
    detail = client.get(f"/studies/{study_id}", headers=auth_headers).json()
    assert len(detail["surveys"]) == 1
    assert len(detail["projects"]) == 1


def test_create_project_404_for_unknown_study_id(client, auth_headers):
    resp = _make_project(client, auth_headers, study_id="does-not-exist")
    assert resp.status_code == 404


def test_create_project_404_for_other_workspace_study(client, auth_headers):
    # Company B owns a study.
    client.post(
        "/auth/signup",
        json={"name": "B Co", "email": "b@example.com", "password": "Password123!"},
    )
    b_tokens = client.post(
        "/auth/login",
        json={"email": "b@example.com", "password": "Password123!"},
    ).json()
    b_headers = {"Authorization": f"Bearer {b_tokens['access_token']}"}
    b_survey = client.post(
        "/surveys/", headers=b_headers, json={"name": "B's survey"}
    ).json()

    # Company A tries to file a project into B's study.
    resp = _make_project(client, auth_headers, study_id=b_survey["study_id"])
    assert resp.status_code == 404


def test_screener_bridge_creates_study_linked_interview_round(
    client, auth_headers, db_session
):
    """The v1 gap: the bridge borrowed an unrelated project. Now it
    creates a study-linked interview round when the Study has none."""

    # Live survey with an NPS question + a respondent pool.
    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Bridge test"}
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
    for i in range(3):
        client.post(
            f"/r/{link['token']}/responses",
            json={
                "link_token": link["token"],
                "email": f"bridge-{i}@example.com",
                "answers": [{"question_id": q["id"], "value_numeric": 3}],
                "is_complete": True,
            },
        )

    study_id = survey["study_id"]
    # Study has NO interview project yet.
    before = client.get(f"/studies/{study_id}", headers=auth_headers).json()
    assert len(before["projects"]) == 0

    # Fire the bridge.
    resp = client.post(
        f"/surveys/{survey['id']}/segment/invite",
        headers=auth_headers,
        json={"filters": [{"question_id": q["id"], "operator": "lte", "value": 6}]},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["interview_link_tokens"]) == 3

    # A study-linked interview project now exists — NOT an orphan.
    after = client.get(f"/studies/{study_id}", headers=auth_headers).json()
    assert len(after["projects"]) == 1
    created = (
        db_session.query(Project)
        .filter(Project.study_id == study_id)
        .first()
    )
    assert created is not None
    assert created.study_id == study_id
    # Seeded with one functional guide question so the interview runs.
    q_count = (
        db_session.query(InterviewGuideQuestion)
        .filter(InterviewGuideQuestion.project_id == created.id)
        .count()
    )
    assert q_count == 1


def test_screener_bridge_reuses_existing_study_project(
    client, auth_headers, db_session
):
    """When a sibling interview project already exists on the Study, the
    bridge uses it — doesn't spawn a second one."""

    survey = client.post(
        "/surveys/", headers=auth_headers, json={"name": "Reuse test"}
    ).json()
    study_id = survey["study_id"]
    # Pre-create an interview project IN this study.
    existing = _make_project(
        client, auth_headers, name="Existing round", study_id=study_id
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
    client.post(
        f"/r/{link['token']}/responses",
        json={
            "link_token": link["token"],
            "email": "reuse@example.com",
            "answers": [{"question_id": q["id"], "value_numeric": 2}],
            "is_complete": True,
        },
    )

    client.post(
        f"/surveys/{survey['id']}/segment/invite",
        headers=auth_headers,
        json={"filters": [{"question_id": q["id"], "operator": "lte", "value": 6}]},
    )

    # Still exactly one interview project on the study.
    projects = (
        db_session.query(Project).filter(Project.study_id == study_id).all()
    )
    assert len(projects) == 1
    assert projects[0].id == existing["id"]
