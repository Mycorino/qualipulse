"""Email-verification gate: unverified researchers can't create studies or
interview links (the outward-facing, data-collecting actions), but can still
log in and explore. Verifying unblocks both.
"""
PROJECT_PAYLOAD = {
    "name": "Gate Project",
    "language": "en",
    "interview_duration_minutes": 20,
    "questions": [{
        "section_index": 0, "section_title": "Bg", "question_index": 0,
        "main_question": "Tell me about yourself.", "interview_notes": "", "desired_learning": "",
    }],
    "screening_questions": [],
}


def _signup(client, email="unverified@example.com"):
    resp = client.post("/auth/signup", json={"name": "Co", "email": email, "password": "Password123!"})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_unverified_cannot_create_project(client):
    headers = _signup(client)
    resp = client.post("/projects/", json=PROJECT_PAYLOAD, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "email_unverified"


def test_unverified_cannot_create_link(client, db_session):
    headers = _signup(client)
    # Verify so we can create a project to hang a link off, then un-verify and
    # confirm link creation is blocked on its own.
    from app.models.company import Company
    co = db_session.query(Company).filter(Company.email == "unverified@example.com").first()
    co.email_verified = True
    db_session.commit()
    proj = client.post("/projects/", json=PROJECT_PAYLOAD, headers=headers)
    assert proj.status_code == 201, proj.text
    project_id = proj.json()["id"]

    co.email_verified = False
    db_session.commit()
    resp = client.post(f"/projects/{project_id}/links", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "email_unverified"


def test_verified_can_create_project_and_link(client, db_session):
    headers = _signup(client, email="verified@example.com")
    from app.models.company import Company
    co = db_session.query(Company).filter(Company.email == "verified@example.com").first()
    co.email_verified = True
    db_session.commit()

    proj = client.post("/projects/", json=PROJECT_PAYLOAD, headers=headers)
    assert proj.status_code == 201, proj.text
    link = client.post(f"/projects/{proj.json()['id']}/links", headers=headers)
    assert link.status_code == 201, link.text
