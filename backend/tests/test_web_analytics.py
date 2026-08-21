"""First-party funnel analytics: /telemetry/event + signup attribution.

Covers the two halves of the homepage tracking story:
  * the public ingest endpoint (catalogue, sanitisation, path redaction,
    bot filter, anonymous visitor hashing), and
  * first-touch utm_* attribution surviving into the Company row and the
    ``signup`` funnel event.
"""
import logging

import pytest

from app.models.company import Company


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
