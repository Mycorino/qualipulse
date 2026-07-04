"""Tests for per-project participant-facing branding (branding_mode +
brand color/font), the custom_branding gate, and anonymous-mode stripping
of identity fields from the public interview payload."""

from app.models.company import Company

PROJECT_PAYLOAD = {
    "name": "Branding Test Project",
    "language": "en",
    "interview_duration_minutes": 20,
    "questions": [
        {
            "section_index": 0,
            "section_title": "Background",
            "question_index": 0,
            "main_question": "Tell me about yourself.",
            "interview_notes": "",
            "desired_learning": "",
        }
    ],
    "screening_questions": [],
}


def _create_project(client, auth_headers, **extra):
    resp = client.post("/projects/", json={**PROJECT_PAYLOAD, **extra}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _set_tier(db_session, tier: str):
    company = db_session.query(Company).filter(Company.email == "test@example.com").first()
    company.subscription_tier = tier
    # Kill the 14-day trial so the tier's own limits apply, not the
    # trial's Team-level boost.
    company.trial_ends_at = None
    db_session.commit()


class TestBrandingSettings:
    def test_defaults_to_standard(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        assert project["branding_mode"] == "standard"
        assert project["brand_primary_color"] is None
        assert project["brand_font"] is None

    def test_identity_fields_are_free(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            json={
                "researcher_name": "Acme Research",
                "researcher_logo_url": "https://example.com/logo.png",
                "privacy_policy_url": "https://example.com/privacy",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["researcher_name"] == "Acme Research"
        assert data["researcher_logo_url"] == "https://example.com/logo.png"
        assert data["privacy_policy_url"] == "https://example.com/privacy"

    def test_anonymous_mode_is_free(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            json={"branding_mode": "anonymous"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["branding_mode"] == "anonymous"

    def test_branded_mode_requires_entitlement(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            json={"branding_mode": "branded"},
            headers=auth_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "custom_branding_required"

    def test_brand_color_requires_entitlement(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            json={"brand_primary_color": "#ff5500"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_branded_allowed_on_lab_tier(self, client, auth_headers, db_session):
        project = _create_project(client, auth_headers)
        _set_tier(db_session, "lab")
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            json={
                "branding_mode": "branded",
                "brand_primary_color": "#FF5500",
                "brand_font": "serif",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["branding_mode"] == "branded"
        assert data["brand_primary_color"] == "#ff5500"  # normalised to lowercase
        assert data["brand_font"] == "serif"

    def test_invalid_color_rejected(self, client, auth_headers, db_session):
        project = _create_project(client, auth_headers)
        _set_tier(db_session, "lab")
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            json={"brand_primary_color": "red"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_invalid_font_rejected(self, client, auth_headers, db_session):
        project = _create_project(client, auth_headers)
        _set_tier(db_session, "lab")
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            json={"brand_font": "comic-sans"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_invalid_mode_rejected(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            json={"branding_mode": "stealth"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_project_with_anonymous_mode(self, client, auth_headers):
        project = _create_project(client, auth_headers, branding_mode="anonymous")
        assert project["branding_mode"] == "anonymous"


class TestPublicInterviewPayload:
    def _link_token(self, client, auth_headers, project_id):
        resp = client.post(f"/projects/{project_id}/links", headers=auth_headers)
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["token"]

    def test_standard_mode_exposes_identity(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        client.patch(
            f"/projects/{project['id']}/settings",
            json={"researcher_name": "Acme Research"},
            headers=auth_headers,
        )
        token = self._link_token(client, auth_headers, project["id"])
        info = client.get(f"/interview/{token}").json()
        assert info["company_name"] == "Test Co"
        assert info["researcher_name"] == "Acme Research"
        assert info["branding"]["mode"] == "standard"
        assert info["branding"]["primary_color"] is None

    def test_anonymous_mode_strips_identity(self, client, auth_headers):
        project = _create_project(client, auth_headers)
        client.patch(
            f"/projects/{project['id']}/settings",
            json={
                "branding_mode": "anonymous",
                "researcher_name": "Acme Research",
                "researcher_logo_url": "https://example.com/logo.png",
            },
            headers=auth_headers,
        )
        token = self._link_token(client, auth_headers, project["id"])
        info = client.get(f"/interview/{token}").json()
        assert info["company_name"] is None
        assert info["researcher_name"] is None
        assert info["researcher_logo_url"] is None
        assert info["branding"]["mode"] == "anonymous"

    def test_branded_mode_ships_theme(self, client, auth_headers, db_session):
        project = _create_project(client, auth_headers)
        _set_tier(db_session, "lab")
        resp = client.patch(
            f"/projects/{project['id']}/settings",
            json={
                "branding_mode": "branded",
                "brand_primary_color": "#00aa88",
                "brand_font": "elegant",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        token = self._link_token(client, auth_headers, project["id"])
        info = client.get(f"/interview/{token}").json()
        assert info["branding"] == {
            "mode": "branded",
            "primary_color": "#00aa88",
            "font": "elegant",
        }
