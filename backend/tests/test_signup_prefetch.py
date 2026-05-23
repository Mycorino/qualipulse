"""W2.5 — domain-based website pre-fetch at signup.

Covers the pure helpers (extract_domain / is_freemail) and the
background prefetch logic with the actual website-fetch mocked. We
don't hit the network — that's an integration concern, not a unit one.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from app.models.company import Company
from app.services.signup_prefetch import (
    _prefetch_in_background,
    extract_domain,
    is_freemail,
    prefetch_company_intel,
)


# ── Pure helpers ─────────────────────────────────────────────────────────────

class TestExtractDomain:
    def test_basic(self):
        assert extract_domain("alice@stripe.com") == "stripe.com"

    def test_lowercases(self):
        assert extract_domain("Alice@Stripe.COM") == "stripe.com"

    def test_strips_whitespace(self):
        assert extract_domain("  alice@stripe.com  ") == "stripe.com"

    def test_missing_at(self):
        assert extract_domain("alicestripe.com") is None

    def test_empty_local_or_domain(self):
        assert extract_domain("alice@") is None
        assert extract_domain("@stripe.com") == "stripe.com"  # mailformed but parseable
        assert extract_domain("@") is None

    def test_no_tld(self):
        assert extract_domain("alice@localhost") is None

    def test_none_input(self):
        assert extract_domain(None) is None
        assert extract_domain("") is None

    def test_plus_addressing(self):
        # Gmail's `+tag` lives in the local part, so domain extraction is
        # unaffected.
        assert extract_domain("alice+work@gmail.com") == "gmail.com"


class TestIsFreemail:
    @pytest.mark.parametrize(
        "domain",
        [
            "gmail.com",
            "GMAIL.COM",  # case-insensitive isn't auto, we lowercase upstream
            "outlook.com",
            "hotmail.fr",
            "free.fr",
            "yandex.ru",
            "proton.me",
        ],
    )
    def test_known_freemail_domains(self, domain):
        # The `extract_domain` step lowercases; tests against the
        # frozenset directly need lowercase too.
        assert is_freemail(domain.lower()) is True

    @pytest.mark.parametrize(
        "domain", ["stripe.com", "anthropic.com", "qualipulse.com", "acme.co.uk"]
    )
    def test_corporate_domains_pass_through(self, domain):
        assert is_freemail(domain) is False

    def test_none_treated_as_freemail(self):
        assert is_freemail(None) is True
        assert is_freemail("") is True


# ── prefetch_company_intel — the public entry ────────────────────────────────

class TestPrefetchEntry:
    def test_skips_freemail_without_starting_thread(self):
        with patch(
            "app.services.signup_prefetch.threading.Thread"
        ) as thread_cls:
            prefetch_company_intel(
                company_id="c-1", email="alice@gmail.com", language="en"
            )
        thread_cls.assert_not_called()

    def test_starts_thread_for_corporate_domain(self):
        with patch(
            "app.services.signup_prefetch.threading.Thread"
        ) as thread_cls:
            prefetch_company_intel(
                company_id="c-2", email="alice@stripe.com", language="en"
            )
        thread_cls.assert_called_once()
        # The thread we spawn is daemonised so a container shutdown
        # doesn't block on it.
        assert thread_cls.call_args.kwargs.get("daemon") is True

    def test_skips_bad_email_gracefully(self):
        with patch(
            "app.services.signup_prefetch.threading.Thread"
        ) as thread_cls:
            prefetch_company_intel(
                company_id="c-3", email="not-an-email", language="en"
            )
        thread_cls.assert_not_called()


# ── _prefetch_in_background — the actual work ───────────────────────────────

class TestBackgroundPrefetch:
    """The background worker opens its OWN DB session (the signup
    request session is gone by the time it runs). We patch
    ``SessionLocal`` so it sees the test's in-memory database."""

    @pytest.fixture(autouse=True)
    def _bind_session_local_to_test_db(self, db_session, monkeypatch):
        # Return a no-op-close wrapper so tests can keep using db_session
        # after the worker finishes.
        class _StickySession:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                pass  # don't close the shared test session

        monkeypatch.setattr(
            "app.services.signup_prefetch.SessionLocal",
            lambda: _StickySession(db_session),
        )

    def _seed_company(self, db_session, *, email="alice@stripe.com"):
        company = Company(
            name="Acme",
            email=email,
            password_hash="x",
            preferred_language="en",
        )
        db_session.add(company)
        db_session.commit()
        db_session.refresh(company)
        return company

    def test_writes_summary_and_industry_on_success(self, db_session):
        company = self._seed_company(db_session)
        with patch(
            "app.services.signup_prefetch._run_async",
            return_value={
                "summary": "Stripe is a payments infrastructure company.",
                "industry": "Financial services",
                "primary_country": "us",
            },
        ):
            _prefetch_in_background(company.id, "stripe.com", "en")
        db_session.refresh(company)
        assert company.business_summary.startswith("Stripe is a payments")
        assert company.industry == "Financial services"
        assert company.website_url == "https://stripe.com/"

    def test_does_not_overwrite_existing_user_content(self, db_session):
        company = self._seed_company(db_session)
        company.website_url = "https://user-typed.com"
        company.business_summary = "User-typed summary."
        company.industry = "Healthcare"
        db_session.commit()

        with patch(
            "app.services.signup_prefetch._run_async",
            return_value={
                "summary": "Different summary from prefetch.",
                "industry": "Tech",
                "primary_country": "us",
            },
        ):
            _prefetch_in_background(company.id, "stripe.com", "en")
        db_session.refresh(company)
        # Every user-set field survives.
        assert company.website_url == "https://user-typed.com"
        assert company.business_summary == "User-typed summary."
        assert company.industry == "Healthcare"

    def test_swallows_fetch_error(self, db_session):
        from app.services.website_intelligence import WebsiteIntelligenceError

        company = self._seed_company(db_session)
        with patch(
            "app.services.signup_prefetch._run_async",
            side_effect=WebsiteIntelligenceError(
                "ai_failed", "fetch blocked"
            ),
        ):
            # Must not raise.
            _prefetch_in_background(company.id, "stripe.com", "en")
        db_session.refresh(company)
        # Nothing written.
        assert (company.business_summary or "") == ""
        assert (company.website_url or "") == ""

    def test_swallows_any_other_exception(self, db_session):
        company = self._seed_company(db_session)
        with patch(
            "app.services.signup_prefetch._run_async",
            side_effect=RuntimeError("boom"),
        ):
            _prefetch_in_background(company.id, "stripe.com", "en")
        # The test just needs to NOT crash. Reaching this line is the assert.

    def test_no_op_when_summary_empty(self, db_session):
        company = self._seed_company(db_session)
        with patch(
            "app.services.signup_prefetch._run_async",
            return_value={"summary": "   ", "industry": "", "primary_country": None},
        ):
            _prefetch_in_background(company.id, "stripe.com", "en")
        db_session.refresh(company)
        assert (company.business_summary or "") == ""


# ── End-to-end: signup should NOT block on prefetch ─────────────────────────

class TestSignupIntegration:
    def test_signup_returns_promptly_even_if_prefetch_runs(self, client):
        """The whole point — signup must not block. We patch the
        background worker to a no-op so the test is fast + deterministic."""
        with patch(
            "app.services.signup_prefetch._prefetch_in_background"
        ) as worker:
            # Make the worker sleep enough that, if signup awaited it,
            # the test would notice.
            worker.side_effect = lambda *a, **kw: time.sleep(0.5)
            start = time.time()
            resp = client.post(
                "/auth/signup",
                json={
                    "name": "Acme",
                    "email": "founder@stripe.com",
                    "password": "Demo1234!",
                    "first_name": "Alice",
                    "preferred_language": "en",
                },
            )
            elapsed = time.time() - start
        assert resp.status_code == 201
        # Tolerant bound — we expect ~10-50ms in practice; 400ms is well
        # under the 500ms artificial sleep so any blocking awaitwould fail.
        assert elapsed < 0.4, f"signup blocked on prefetch ({elapsed:.2f}s)"
        # And the thread is daemonised so it doesn't hang the test runner.
        for t in threading.enumerate():
            if t.name.startswith("signup-prefetch-"):
                assert t.daemon is True
