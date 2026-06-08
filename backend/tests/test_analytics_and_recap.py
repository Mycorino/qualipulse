"""Tests for the funnel analytics emitter and lifecycle email templates."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from app.models.company import Company
from app.services.analytics import emit_event


class TestAnalyticsEmitter:
    def test_emits_structured_log_line(self, caplog):
        company = Company(
            id="c-1",
            name="Acme",
            email="alice@acme.com",
            first_name="Alice",
            role="Product Manager",
            company_size="11–50",
            industry="SaaS / Tech",
            use_case="Product discovery",
            subscription_tier="starter",
        )
        with caplog.at_level(logging.INFO):
            emit_event("signup", company=company, plan_requested="starter")
        records = [r for r in caplog.records if r.message.startswith("analytics ")]
        assert records, "no analytics line emitted"
        msg = records[-1].message
        assert "event=signup" in msg
        assert "company_id=c-1" in msg
        assert 'role="Product Manager"' in msg
        assert "plan_id=starter" in msg
        assert "plan_requested=starter" in msg

    def test_works_without_company(self, caplog):
        with caplog.at_level(logging.INFO):
            emit_event("trial_paywall_hit", reason="participant_limit")
        records = [r for r in caplog.records if r.message.startswith("analytics ")]
        assert records
        assert "event=trial_paywall_hit" in records[-1].message
        assert "reason=participant_limit" in records[-1].message

    def test_never_raises_on_bad_input(self, caplog):
        broken = SimpleNamespace()
        with caplog.at_level(logging.INFO):
            emit_event("study_created", company=broken)  # type: ignore[arg-type]


class TestFirstResponseEmail:
    def test_template_renders_subject_and_body(self):
        from app.services.email import send_first_response_in
        from unittest.mock import patch

        with patch("app.services.email.send_email", return_value=True) as mock:
            ok = send_first_response_in(
                to="alice@acme.com",
                project_name="Trial drop-off study",
                project_url="https://app.qualipulse.com/projects/p-1?tab=responses",
                lang="en",
            )
        assert ok is True
        kwargs = mock.call_args.kwargs
        assert kwargs["to"] == "alice@acme.com"
        assert "Trial drop-off study" in kwargs["subject"]
        assert "first response" in kwargs["subject"].lower()
        assert "Listen to the response" in kwargs["body_html"]
        assert "Trial drop-off study" in kwargs["body_html"]

    def test_template_renders_french(self):
        from app.services.email import send_first_response_in
        from unittest.mock import patch

        with patch("app.services.email.send_email", return_value=True) as mock:
            send_first_response_in(
                to="x@x.com",
                project_name="Étude pilote",
                project_url="https://example.com",
                lang="fr",
            )
        body = mock.call_args.kwargs["body_html"]
        assert "Écouter la réponse" in body
        assert "Étude pilote" in body
