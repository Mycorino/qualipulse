"""POST /projects/{id}/links/{lid}/invites — email invitations for a link."""

import pytest

from tests.test_projects import PROJECT_PAYLOAD


@pytest.fixture
def sent_invites(monkeypatch):
    """Capture send_interview_invite calls; every send succeeds."""
    calls = []

    def _fake(to, project_name, interview_url, sender_name, lang="en"):
        calls.append(
            {
                "to": to,
                "project_name": project_name,
                "interview_url": interview_url,
                "sender_name": sender_name,
                "lang": lang,
            }
        )
        return True

    monkeypatch.setattr("app.routers.links.send_interview_invite", _fake)
    return calls


@pytest.fixture
def project_with_link(client, auth_headers):
    resp = client.post("/projects/", json=PROJECT_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    project = resp.json()
    resp = client.post(f"/projects/{project['id']}/links", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return {"project": project, "link": resp.json()}


def _invite_url(ctx):
    return f"/projects/{ctx['project']['id']}/links/{ctx['link']['id']}/invites"


class TestSendLinkInvites:
    def test_sends_to_each_recipient(self, client, auth_headers, project_with_link, sent_invites):
        resp = client.post(
            _invite_url(project_with_link),
            json={"emails": ["a@example.com", "b@example.com"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"sent": 2, "failed": []}
        assert [c["to"] for c in sent_invites] == ["a@example.com", "b@example.com"]
        assert project_with_link["link"]["token"] in sent_invites[0]["interview_url"]
        assert "/i/" in sent_invites[0]["interview_url"]

    def test_dedupes_and_normalises_addresses(self, client, auth_headers, project_with_link, sent_invites):
        resp = client.post(
            _invite_url(project_with_link),
            json={"emails": ["Dup@Example.com", "dup@example.com "]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["sent"] == 1
        assert [c["to"] for c in sent_invites] == ["dup@example.com"]

    def test_custom_sender_name(self, client, auth_headers, project_with_link, sent_invites):
        resp = client.post(
            _invite_url(project_with_link),
            json={"emails": ["a@example.com"], "sender_name": "Marie"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert sent_invites[0]["sender_name"] == "Marie"

    def test_reports_failed_sends(self, client, auth_headers, project_with_link, monkeypatch):
        monkeypatch.setattr(
            "app.routers.links.send_interview_invite",
            lambda to, **kw: to != "broken@example.com",
        )
        resp = client.post(
            _invite_url(project_with_link),
            json={"emails": ["ok@example.com", "broken@example.com"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == {"sent": 1, "failed": ["broken@example.com"]}

    def test_rejects_invalid_email(self, client, auth_headers, project_with_link, sent_invites):
        resp = client.post(
            _invite_url(project_with_link),
            json={"emails": ["not-an-email"]},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        assert sent_invites == []

    def test_rejects_empty_and_oversized_batches(self, client, auth_headers, project_with_link, sent_invites):
        resp = client.post(_invite_url(project_with_link), json={"emails": []}, headers=auth_headers)
        assert resp.status_code == 422
        emails = [f"p{i}@example.com" for i in range(21)]
        resp = client.post(_invite_url(project_with_link), json={"emails": emails}, headers=auth_headers)
        assert resp.status_code == 422
        assert sent_invites == []

    def test_inactive_link_refused(self, client, auth_headers, project_with_link, sent_invites):
        link = project_with_link["link"]
        resp = client.patch(f"/links/{link['id']}", json={"is_active": False}, headers=auth_headers)
        assert resp.status_code == 200
        resp = client.post(
            _invite_url(project_with_link),
            json={"emails": ["a@example.com"]},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "link_inactive"
        assert sent_invites == []

    def test_unknown_link_404(self, client, auth_headers, project_with_link, sent_invites):
        resp = client.post(
            f"/projects/{project_with_link['project']['id']}/links/nope/invites",
            json={"emails": ["a@example.com"]},
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert sent_invites == []

    def test_requires_auth(self, client, project_with_link):
        resp = client.post(_invite_url(project_with_link), json={"emails": ["a@example.com"]})
        assert resp.status_code == 401
