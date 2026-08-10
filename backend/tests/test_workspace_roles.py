"""Viewer/editor role enforcement on mutating project endpoints.

Viewers can read everything in a workspace but must get 403
``viewer_read_only`` on any mutation; editors pass.
"""

import uuid

import pytest

from app.models.company import Company
from app.models.project import Project
from app.models.team import ROLE_EDITOR, ROLE_VIEWER, WorkspaceMember
from app.services.auth import create_access_token


def _make_company(db, name):
    c = Company(
        name=name,
        email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@x.com",
        password_hash="x",
        email_verified=True,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _headers(company):
    token = create_access_token(
        {"sub": company.id, "tv": company.token_version or 0}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def workspace(db_session):
    owner = _make_company(db_session, "Owner")
    viewer = _make_company(db_session, "Viewer")
    editor = _make_company(db_session, "Editor")
    project = Project(company_id=owner.id, name="Shared study", language="en")
    db_session.add(project)
    for member, role in ((viewer, ROLE_VIEWER), (editor, ROLE_EDITOR)):
        db_session.add(
            WorkspaceMember(
                workspace_company_id=owner.id,
                member_company_id=member.id,
                role=role,
            )
        )
    db_session.commit()
    db_session.refresh(project)
    return {"owner": owner, "viewer": viewer, "editor": editor, "project": project}


def test_viewer_can_read_but_not_create_memo(client, workspace):
    pid = workspace["project"].id
    read = client.get(f"/projects/{pid}/memos", headers=_headers(workspace["viewer"]))
    assert read.status_code == 200

    write = client.post(
        f"/projects/{pid}/memos",
        json={"type": "general", "content": "note"},
        headers=_headers(workspace["viewer"]),
    )
    assert write.status_code == 403
    assert write.json()["detail"]["code"] == "viewer_read_only"


def test_editor_can_create_memo(client, workspace):
    pid = workspace["project"].id
    write = client.post(
        f"/projects/{pid}/memos",
        json={"type": "general", "content": "note"},
        headers=_headers(workspace["editor"]),
    )
    assert write.status_code == 201


def test_viewer_cannot_create_code_or_link(client, workspace):
    pid = workspace["project"].id
    code = client.post(
        f"/projects/{pid}/codes",
        json={"name": "Friction", "color": "#ff0000"},
        headers=_headers(workspace["viewer"]),
    )
    assert code.status_code == 403

    link = client.post(
        f"/projects/{pid}/links",
        headers=_headers(workspace["viewer"]),
    )
    assert link.status_code == 403


def test_viewer_cannot_trigger_analysis(client, workspace, db_session):
    pid = workspace["project"].id
    resp = client.post(
        f"/projects/{pid}/analysis",
        json={},
        headers=_headers(workspace["viewer"]),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "viewer_read_only"


def test_viewer_cannot_delete_project(client, workspace):
    pid = workspace["project"].id
    resp = client.delete(f"/projects/{pid}", headers=_headers(workspace["viewer"]))
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "viewer_read_only"
    # Still there.
    read = client.get(f"/projects/{pid}", headers=_headers(workspace["viewer"]))
    assert read.status_code == 200


def test_viewer_cannot_update_or_archive_project(client, workspace):
    pid = workspace["project"].id
    upd = client.put(
        f"/projects/{pid}",
        json={"name": "Renamed", "questions": []},
        headers=_headers(workspace["viewer"]),
    )
    assert upd.status_code == 403
    arch = client.patch(f"/projects/{pid}/archive", headers=_headers(workspace["viewer"]))
    assert arch.status_code == 403


def test_owner_unaffected(client, workspace):
    pid = workspace["project"].id
    write = client.post(
        f"/projects/{pid}/memos",
        json={"type": "general", "content": "owner note"},
        headers=_headers(workspace["owner"]),
    )
    assert write.status_code == 201
