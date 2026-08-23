"""AI provider spend monitoring — burn-rate thresholds and the out-of-credit alarm."""

from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.models.ops_alert import OpsAlertLog
from app.models.usage import AIUsageLog
from app.services import ai_spend


NOW = datetime(2026, 8, 20, 12, 0, 0)  # 20th of a 31-day month


@pytest.fixture(autouse=True)
def quiet_alerts(monkeypatch):
    """Capture deliveries instead of emailing / posting to Slack."""
    sent: list[tuple[str, str, list[str]]] = []
    monkeypatch.setattr(
        ai_spend,
        "send_ops_alert",
        lambda subject, headline, lines: sent.append((subject, headline, lines)),
    )
    # Every threshold off by default; each test turns on the one it covers.
    monkeypatch.setattr(settings, "AI_SPEND_MONTHLY_BUDGET_USD", 0.0)
    monkeypatch.setattr(settings, "AI_SPEND_DAILY_LIMIT_USD", 0.0)
    monkeypatch.setattr(settings, "AI_SPEND_SPIKE_MULTIPLIER", 0.0)
    monkeypatch.setattr(settings, "AI_SPEND_SPIKE_FLOOR_USD", 10.0)
    return sent


def _log(db, cost: float, when: datetime, operation: str = "interview_turn"):
    db.add(
        AIUsageLog(
            operation=operation,
            model="claude-sonnet-4-6",
            cost_usd=cost,
            created_at=when,
        )
    )
    db.commit()


def _keys(alerts) -> list[str]:
    return [a["key"] for a in alerts]


# ── Summary maths ────────────────────────────────────────────────────────────

def test_summary_splits_today_from_the_trailing_week(db_session):
    _log(db_session, 30.0, NOW - timedelta(hours=2))         # last 24h
    for day in range(2, 9):                                   # the 7 days before
        _log(db_session, 7.0, NOW - timedelta(days=day))

    summary = ai_spend.spend_summary(db_session, NOW)

    assert summary["last_24h"] == pytest.approx(30.0)
    # Today is excluded from its own baseline.
    assert summary["prev_7d_daily_avg"] == pytest.approx(7.0)


def test_summary_projects_the_month_at_the_current_pace(db_session):
    # $10/day for the first 20 days of a 31-day month.
    for day in range(0, 20):
        _log(db_session, 10.0, datetime(2026, 8, 1) + timedelta(days=day, hours=1))

    summary = ai_spend.spend_summary(db_session, NOW)

    assert summary["month_to_date"] == pytest.approx(200.0)
    assert summary["projected_month"] == pytest.approx(310.0, rel=0.05)


def test_summary_ranks_the_biggest_spenders(db_session):
    _log(db_session, 5.0, NOW - timedelta(hours=1), operation="copilot")
    _log(db_session, 12.0, NOW - timedelta(hours=1), operation="analysis")
    _log(db_session, 40.0, NOW - timedelta(days=4), operation="ancient")

    top = ai_spend.spend_summary(db_session, NOW)["top_operations"]

    assert [row["operation"] for row in top] == ["analysis", "copilot"]


# ── Thresholds ───────────────────────────────────────────────────────────────

def test_no_alerts_when_everything_is_off(db_session, quiet_alerts):
    _log(db_session, 500.0, NOW - timedelta(hours=1))
    assert ai_spend.check_spend_alerts(db_session, NOW) == []
    assert quiet_alerts == []


def test_daily_ceiling_fires_once_a_day(db_session, quiet_alerts, monkeypatch):
    monkeypatch.setattr(settings, "AI_SPEND_DAILY_LIMIT_USD", 50.0)
    _log(db_session, 60.0, NOW - timedelta(hours=3))

    first = ai_spend.check_spend_alerts(db_session, NOW)
    assert _keys(first) == ["ai_spend:daily_limit:2026-08-20"]
    assert len(quiet_alerts) == 1

    # The cron runs hourly; the second pass of the same day must stay quiet.
    again = ai_spend.check_spend_alerts(db_session, NOW + timedelta(hours=1))
    assert again == []
    assert len(quiet_alerts) == 1


def test_daily_ceiling_stays_quiet_below_the_limit(db_session, monkeypatch):
    monkeypatch.setattr(settings, "AI_SPEND_DAILY_LIMIT_USD", 50.0)
    _log(db_session, 49.0, NOW - timedelta(hours=3))
    assert ai_spend.check_spend_alerts(db_session, NOW) == []


def test_spike_detector_compares_against_the_trailing_week(db_session, monkeypatch):
    monkeypatch.setattr(settings, "AI_SPEND_SPIKE_MULTIPLIER", 3.0)
    for day in range(2, 9):
        _log(db_session, 10.0, NOW - timedelta(days=day))   # $10/day baseline
    _log(db_session, 45.0, NOW - timedelta(hours=2))        # 4.5x today

    assert _keys(ai_spend.check_spend_alerts(db_session, NOW)) == ["ai_spend:spike:2026-08-20"]


def test_spike_detector_ignores_small_numbers(db_session, monkeypatch):
    """A quiet week makes any ordinary day look like a 10x spike."""
    monkeypatch.setattr(settings, "AI_SPEND_SPIKE_MULTIPLIER", 3.0)
    monkeypatch.setattr(settings, "AI_SPEND_SPIKE_FLOOR_USD", 10.0)
    for day in range(2, 9):
        _log(db_session, 0.10, NOW - timedelta(days=day))
    _log(db_session, 5.0, NOW - timedelta(hours=2))         # 50x, but only $5

    assert ai_spend.check_spend_alerts(db_session, NOW) == []


def test_budget_80_then_100_fire_once_each_per_month(db_session, quiet_alerts, monkeypatch):
    monkeypatch.setattr(settings, "AI_SPEND_MONTHLY_BUDGET_USD", 100.0)
    _log(db_session, 85.0, datetime(2026, 8, 5))

    assert _keys(ai_spend.check_spend_alerts(db_session, NOW)) == ["ai_spend:budget_80:2026-08"]
    # Still at 85% an hour later: no repeat.
    assert ai_spend.check_spend_alerts(db_session, NOW + timedelta(hours=1)) == []

    _log(db_session, 20.0, NOW - timedelta(hours=1))        # now past 100%
    assert _keys(ai_spend.check_spend_alerts(db_session, NOW)) == ["ai_spend:budget_100:2026-08"]
    assert len(quiet_alerts) == 2


def test_projection_warns_before_the_budget_is_touched(db_session, monkeypatch):
    """The 'slowly running out' case: only 70% of the budget spent, so neither
    the 80% nor the 100% rung has tripped, but the pace lands past 100%."""
    monkeypatch.setattr(settings, "AI_SPEND_MONTHLY_BUDGET_USD", 100.0)
    for day in range(0, 20):
        _log(db_session, 3.5, datetime(2026, 8, 1) + timedelta(days=day, hours=1))

    summary = ai_spend.spend_summary(db_session, NOW)
    assert summary["month_to_date"] == pytest.approx(70.0)
    assert summary["projected_month"] > 100.0

    assert _keys(ai_spend.check_spend_alerts(db_session, NOW)) == ["ai_spend:projection:2026-08"]


def test_projection_holds_off_in_the_first_days_of_the_month(db_session, monkeypatch):
    """One heavy day on the 2nd extrapolates to a wild number. Don't cry wolf."""
    monkeypatch.setattr(settings, "AI_SPEND_MONTHLY_BUDGET_USD", 100.0)
    _log(db_session, 40.0, datetime(2026, 8, 1, 12))

    assert ai_spend.check_spend_alerts(db_session, datetime(2026, 8, 2, 12)) == []


def test_dry_run_reports_without_claiming_or_sending(db_session, quiet_alerts, monkeypatch):
    monkeypatch.setattr(settings, "AI_SPEND_DAILY_LIMIT_USD", 50.0)
    _log(db_session, 60.0, NOW - timedelta(hours=3))

    dry = ai_spend.check_spend_alerts(db_session, NOW, dry_run=True)
    assert _keys(dry) == ["ai_spend:daily_limit:2026-08-20"]
    assert quiet_alerts == []
    assert db_session.query(OpsAlertLog).count() == 0

    # A dry run must not have consumed the real alert.
    assert _keys(ai_spend.check_spend_alerts(db_session, NOW)) == ["ai_spend:daily_limit:2026-08-20"]


# ── Out-of-credit detection ──────────────────────────────────────────────────

class _FakeProviderError(Exception):
    def __init__(self, message: str, body=None):
        super().__init__(message)
        self.body = body


@pytest.mark.parametrize(
    "exc",
    [
        _FakeProviderError(
            "Error code: 400 - {'type': 'invalid_request_error', 'message': "
            "'Your credit balance is too low to access the Anthropic API.'}"
        ),
        _FakeProviderError(
            "You exceeded your current quota, please check your plan and billing details."
        ),
        _FakeProviderError(
            "rate limit", body={"error": {"code": "insufficient_quota"}}
        ),
    ],
)
def test_out_of_credit_is_recognised(exc):
    assert ai_spend.is_out_of_credit(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        _FakeProviderError("Rate limit exceeded. Please retry shortly."),
        _FakeProviderError("Request timed out."),
        _FakeProviderError("overloaded_error: the model is overloaded"),
        _FakeProviderError("400 invalid_request_error: max_tokens is too large"),
        _FakeProviderError("401 authentication_error: invalid x-api-key"),
    ],
)
def test_ordinary_failures_do_not_trip_the_alarm(exc):
    assert ai_spend.is_out_of_credit(exc) is False


def test_out_of_credit_alarm_is_deduped_per_hour(db_session, quiet_alerts, monkeypatch):
    monkeypatch.setattr(ai_spend, "_last_alarm", {})
    monkeypatch.setattr(
        "app.database.SessionLocal", lambda: db_session, raising=False
    )
    exc = _FakeProviderError("Your credit balance is too low to access the Anthropic API.")

    ai_spend.note_provider_error("anthropic", "interview_turn", exc)
    assert len(quiet_alerts) == 1
    assert db_session.query(OpsAlertLog).count() == 1

    # Same instance, seconds later: the in-process cooldown swallows it.
    ai_spend.note_provider_error("anthropic", "analysis", exc)
    assert len(quiet_alerts) == 1

    # Another instance (no cooldown state) is stopped by the DB claim.
    monkeypatch.setattr(ai_spend, "_last_alarm", {})
    ai_spend.note_provider_error("anthropic", "analysis", exc)
    assert len(quiet_alerts) == 1
    assert db_session.query(OpsAlertLog).count() == 1


def test_transient_failures_raise_no_alarm(db_session, quiet_alerts, monkeypatch):
    monkeypatch.setattr(ai_spend, "_last_alarm", {})
    ai_spend.note_provider_error(
        "openai", "stt", _FakeProviderError("Connection reset by peer")
    )
    assert quiet_alerts == []


# ── Call-site wiring ─────────────────────────────────────────────────────────

def _rate_limit_error(message: str, body=None):
    """A real openai.RateLimitError — it needs an httpx response to construct."""
    import httpx
    import openai

    response = httpx.Response(
        429, request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    )
    return openai.RateLimitError(message, response=response, body=body)


def test_openai_wrapper_fails_fast_on_an_empty_balance(monkeypatch):
    """insufficient_quota arrives as a RateLimitError, which looks retryable.
    Retrying it burns three attempts on the interview's critical path."""
    import openai

    from app.services import _clients

    noted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        _clients, "_note", lambda provider, label, exc: noted.append((provider, label))
    )

    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise _rate_limit_error(
            "You exceeded your current quota, please check your plan and billing details.",
            body={"error": {"code": "insufficient_quota"}},
        )

    with pytest.raises(openai.RateLimitError):
        _clients.call_openai_with_retries(boom, label="stt", attempts=3)

    assert calls["n"] == 1          # no retries
    assert noted == [("openai", "stt")]


def test_openai_wrapper_still_retries_ordinary_rate_limits(monkeypatch):
    from app.services import _clients

    monkeypatch.setattr(_clients, "_note", lambda *a: None)
    monkeypatch.setattr(_clients.time, "sleep", lambda _s: None)

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _rate_limit_error("slow down")
        return "ok"

    assert _clients.call_openai_with_retries(flaky, label="stt", attempts=3) == "ok"
    assert calls["n"] == 3


def test_anthropic_client_reports_billing_refusals(monkeypatch):
    from app.services import _clients

    noted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        _clients, "_note", lambda provider, label, exc: noted.append((provider, label))
    )

    client = _clients.get_anthropic_client()

    class _Boom:
        def create(self, **kwargs):
            raise RuntimeError("Your credit balance is too low to access the Anthropic API.")

        def count_tokens(self, **kwargs):
            return 42

    client.messages = _clients._WatchedMessages(_Boom())

    with pytest.raises(RuntimeError):
        client.messages.create(model="claude-sonnet-4-6", messages=[])
    assert noted == [("anthropic", "messages.create")]

    # Anything that isn't create/stream passes straight through untouched.
    assert client.messages.count_tokens(model="claude-sonnet-4-6") == 42


def test_anthropic_client_wraps_messages_by_default():
    """Guards the cached_property assignment in get_anthropic_client: if a
    future SDK makes ``messages`` read-only, every call site loses the alarm."""
    from app.services._clients import _WatchedMessages, get_anthropic_client

    assert isinstance(get_anthropic_client().messages, _WatchedMessages)


# ── The cron endpoint ────────────────────────────────────────────────────────

def test_cron_reports_spend_alerts_alongside_the_lifecycle_emails(
    client, db_session, quiet_alerts, monkeypatch
):
    """The burn-rate check rides the hourly lifecycle-email cron, so there is
    one job to schedule, not two."""
    monkeypatch.setattr(settings, "ADMIN_SECRET_KEY", "test-admin-secret")
    monkeypatch.setattr(settings, "AI_SPEND_DAILY_LIMIT_USD", 10.0)
    _log(db_session, 25.0, datetime.utcnow() - timedelta(hours=1))

    resp = client.post(
        "/admin/scheduled-emails/run",
        headers={"Authorization": "Bearer test-admin-secret"},
    )

    assert resp.status_code == 200, resp.text
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert resp.json()["ai_spend_alerts"] == [f"ai_spend:daily_limit:{today}"]
    assert len(quiet_alerts) == 1

    # Hourly cron, one alert a day.
    again = client.post(
        "/admin/scheduled-emails/run",
        headers={"Authorization": "Bearer test-admin-secret"},
    )
    assert again.json()["ai_spend_alerts"] == []
    assert len(quiet_alerts) == 1


def test_anthropic_stream_reports_billing_refusals(monkeypatch):
    """The Copilot and the analysis pipeline stream; the 400 for an empty
    balance lands in __enter__, before the first token."""
    from app.services import _clients

    noted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        _clients, "_note", lambda provider, label, exc: noted.append((provider, label))
    )

    class _BoomStream:
        def __enter__(self):
            raise RuntimeError("Your credit balance is too low to access the Anthropic API.")

        def __exit__(self, *exc_info):
            return False

    class _OkStream:
        def __enter__(self):
            return "stream-handle"

        def __exit__(self, *exc_info):
            return False

    class _Inner:
        def __init__(self, manager):
            self._manager = manager

        def stream(self, **kwargs):
            return self._manager

    with pytest.raises(RuntimeError):
        with _clients._WatchedMessages(_Inner(_BoomStream())).stream(model="x"):
            pass
    assert noted == [("anthropic", "messages.stream")]

    # A healthy stream is handed through untouched.
    with _clients._WatchedMessages(_Inner(_OkStream())).stream(model="x") as handle:
        assert handle == "stream-handle"
    assert len(noted) == 1


def test_several_thresholds_in_one_pass_send_one_email(db_session, quiet_alerts, monkeypatch):
    """Daily ceiling and spike trip together on a bad day. Two near-identical
    emails in the same minute is how people learn to filter these away."""
    monkeypatch.setattr(settings, "AI_SPEND_DAILY_LIMIT_USD", 40.0)
    monkeypatch.setattr(settings, "AI_SPEND_SPIKE_MULTIPLIER", 3.0)
    monkeypatch.setattr(settings, "AI_SPEND_MONTHLY_BUDGET_USD", 100.0)
    for day in range(2, 9):
        _log(db_session, 10.0, NOW - timedelta(days=day))
    _log(db_session, 120.0, NOW - timedelta(hours=2))

    fired = _keys(ai_spend.check_spend_alerts(db_session, NOW))

    # Every threshold that tripped is claimed, so each keeps its own silence.
    assert set(fired) == {
        "ai_spend:budget_100:2026-08",
        "ai_spend:daily_limit:2026-08-20",
        "ai_spend:spike:2026-08-20",
    }
    # The worst one owns the subject line.
    assert fired[0] == "ai_spend:budget_100:2026-08"
    assert len(quiet_alerts) == 1

    subject, _headline, lines = quiet_alerts[0]
    assert "monthly budget" in subject
    # The other two are still spelled out in the body.
    body = "\n".join(lines)
    assert "daily ceiling" in body
    assert "x the 7-day daily average" in body


# ── Detection against the real SDK exception objects ─────────────────────────
#
# The fakes above pin the logic; these pin the plumbing. Both SDKs hang the
# parsed error off ``.body`` and build ``str(exc)`` themselves, so a detector
# that only reads the string is one SDK upgrade away from silently never
# firing again.

def _anthropic_error(message: str, err_type: str = "invalid_request_error"):
    import anthropic
    import httpx

    body = {"type": "error", "error": {"type": err_type, "message": message}}
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.BadRequestError(
        "Error code: 400", response=httpx.Response(400, request=request, json=body), body=body
    )


def _openai_error(message: str, code: str):
    import httpx
    import openai

    body = {"message": message, "type": code, "code": code}
    request = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    return openai.RateLimitError(
        "Error code: 429",
        response=httpx.Response(429, request=request, json={"error": body}),
        body=body,
    )


def test_real_anthropic_billing_refusal_is_recognised():
    exc = _anthropic_error(
        "Your credit balance is too low to access the Anthropic API. Please go to "
        "Plans & Billing to upgrade or purchase credits."
    )
    assert ai_spend.is_out_of_credit(exc) is True


@pytest.mark.parametrize(
    "message,err_type",
    [
        ("max_tokens: must be <= 64000", "invalid_request_error"),
        ("Overloaded", "overloaded_error"),
        ("invalid x-api-key", "authentication_error"),
    ],
)
def test_real_anthropic_failures_stay_quiet(message, err_type):
    """Same 400 shape as the billing refusal, so only the message tells them
    apart. A false positive here trains us to ignore the alarm."""
    assert ai_spend.is_out_of_credit(_anthropic_error(message, err_type)) is False


def test_real_openai_quota_error_is_recognised():
    exc = _openai_error(
        "You exceeded your current quota, please check your plan and billing details.",
        "insufficient_quota",
    )
    assert ai_spend.is_out_of_credit(exc) is True


def test_real_openai_rate_limit_stays_quiet():
    exc = _openai_error("Rate limit reached for requests", "rate_limit_exceeded")
    assert ai_spend.is_out_of_credit(exc) is False
