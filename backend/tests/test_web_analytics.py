"""First-party funnel analytics: /telemetry/event + signup attribution.

Covers the two halves of the homepage tracking story:
  * the public ingest endpoint (catalogue, sanitisation, path redaction,
    bot filter, anonymous visitor hashing), and
  * first-touch utm_* attribution surviving into the Company row and the
    ``signup`` funnel event.
"""
import logging

import pytest

from app.config import settings
from app.models.company import Company
from app.models.web_event import WebEvent


def _post_event(client, **payload):
    return client.post("/telemetry/event", json=payload)


class TestEventIngest:
    def test_known_event_is_emitted(self, client, caplog):
        with caplog.at_level(logging.INFO):
            res = _post_event(
                client,
                event="cta_signup_click",
                location="hero",
                path="/",
                utm_source="linkedin",
                utm_medium="social",
                utm_campaign="launch",
            )
        assert res.status_code == 204
        line = _analytics_line(caplog)
        assert "event=cta_signup_click" in line
        assert "location=hero" in line
        assert "utm_source=linkedin" in line
        assert "source=web" in line
        # Anonymous, daily-rotating visitor id — never an IP.
        assert "visitor=" in line

    def test_unknown_event_is_dropped_silently(self, client, caplog):
        with caplog.at_level(logging.INFO):
            res = _post_event(client, event="totally_made_up")
        assert res.status_code == 204
        assert _analytics_lines(caplog) == []

    def test_bot_user_agent_is_dropped(self, client, caplog):
        with caplog.at_level(logging.INFO):
            res = client.post(
                "/telemetry/event",
                json={"event": "page_view", "path": "/"},
                headers={"User-Agent": "Mozilla/5.0 (compatible; SomeBot/1.0)"},
            )
        assert res.status_code == 204
        assert _analytics_lines(caplog) == []

    def test_authenticated_path_is_redacted(self, client, caplog):
        """Study ids in the path must never reach the analytics stream."""
        with caplog.at_level(logging.INFO):
            _post_event(
                client,
                event="analysis_viewed",
                path="/studies/8f14e45f-ea6d-4b39-9a11-000000000000",
            )
        line = _analytics_line(caplog)
        assert "8f14e45f" not in line
        assert "path=/redacted" in line

    def test_log_line_cannot_be_forged(self, client, caplog):
        """A newline in a value must not be able to fake a second event."""
        with caplog.at_level(logging.INFO):
            _post_event(
                client,
                event="page_view",
                path="/",
                utm_campaign="evil\nanalytics event=paid_converted",
            )
        line = _analytics_line(caplog)
        assert "\n" not in line
        # The "=" is stripped, so the injected text can't read as a token.
        assert line.count("event=") == 1
        assert "paid_converted" in line  # kept, but inert

    def test_oversized_field_is_rejected(self, client):
        res = _post_event(client, event="page_view", utm_source="x" * 500)
        assert res.status_code == 422


class TestSignupAttribution:
    def test_utm_is_persisted_and_emitted(self, client, db_session, caplog):
        with caplog.at_level(logging.INFO):
            res = client.post(
                "/auth/signup",
                json={
                    "name": "Attributed Co",
                    "email": "attributed@example.com",
                    "password": "Testpass123",
                    "utm_source": "linkedin",
                    "utm_medium": "cpc",
                    "utm_campaign": "q3-launch",
                },
            )
        assert res.status_code == 201

        company = (
            db_session.query(Company)
            .filter(Company.email == "attributed@example.com")
            .first()
        )
        assert company.utm_source == "linkedin"
        assert company.utm_medium == "cpc"
        assert company.utm_campaign == "q3-launch"

        signup_line = next(
            line for line in _analytics_lines(caplog) if "event=signup" in line
        )
        assert "utm_source=linkedin" in signup_line
        assert "method=password" in signup_line

    def test_signup_without_utm_still_works(self, client, db_session):
        res = client.post(
            "/auth/signup",
            json={
                "name": "Direct Co",
                "email": "direct@example.com",
                "password": "Testpass123",
            },
        )
        assert res.status_code == 201
        company = (
            db_session.query(Company)
            .filter(Company.email == "direct@example.com")
            .first()
        )
        assert company.utm_source is None


def _analytics_lines(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("analytics ")
    ]


def _analytics_line(caplog) -> str:
    lines = _analytics_lines(caplog)
    assert lines, "expected an analytics log line"
    return lines[-1]


ADMIN_KEY = "test-admin-secret-key"


@pytest.fixture
def admin_headers():
    prev = settings.ADMIN_SECRET_KEY
    settings.ADMIN_SECRET_KEY = ADMIN_KEY
    try:
        yield {"Authorization": f"Bearer {ADMIN_KEY}", "X-Admin-Identity": "test-admin"}
    finally:
        settings.ADMIN_SECRET_KEY = prev


class TestEventPersistence:
    def test_event_is_stored_for_the_admin_dashboard(self, client, db_session):
        _post_event(client, event="page_view", path="/", utm_source="linkedin")
        row = db_session.query(WebEvent).one()
        assert row.event == "page_view"
        assert row.path == "/"
        assert row.utm_source == "linkedin"
        assert row.visitor  # anonymous hash, always present

    def test_dropped_events_are_not_stored(self, client, db_session):
        _post_event(client, event="totally_made_up")
        assert db_session.query(WebEvent).count() == 0


class TestAdminTraffic:
    def test_rollup_counts_the_funnel(self, client, db_session, admin_headers):
        for _ in range(4):
            _post_event(client, event="page_view", path="/", utm_source="linkedin")
        _post_event(client, event="cta_signup_click", location="hero", utm_source="linkedin")
        _post_event(client, event="pricing_viewed", utm_source="linkedin")
        client.post(
            "/auth/signup",
            json={
                "name": "Funnel Co",
                "email": "funnel@example.com",
                "password": "Testpass123",
                "utm_source": "linkedin",
            },
        )

        res = client.get("/admin/traffic?days=30", headers=admin_headers)
        assert res.status_code == 200
        body = res.json()

        assert body["page_views"] == 4
        assert body["cta_clicks"] == 1
        assert body["pricing_views"] == 1
        assert body["signups"] == 1
        assert body["signup_rate_pct"] == 25.0
        assert {"label": "hero", "count": 1} in body["cta_by_location"]
        assert {"label": "linkedin", "count": 1} in body["signups_by_source"]
        assert body["daily"]

    def test_channel_split_never_double_counts_a_visitor(
        self, client, db_session, admin_headers
    ):
        """A visitor who arrives direct and later clicks a campaign link is
        one visit, not one in each channel."""
        _post_event(client, event="page_view", path="/")
        _post_event(client, event="page_view", path="/", utm_source="linkedin")

        body = client.get("/admin/traffic?days=30", headers=admin_headers).json()
        assert body["visits"] == 1
        assert sum(b["count"] for b in body["top_sources"]) == body["visits"]
        # Credited to where they were first seen.
        assert body["top_sources"] == [{"label": "(direct)", "count": 1}]

    def test_zero_traffic_does_not_divide_by_zero(self, client, admin_headers):
        res = client.get("/admin/traffic?days=7", headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["signup_rate_pct"] == 0.0

    def test_requires_admin_key(self, client):
        assert client.get("/admin/traffic").status_code == 401
