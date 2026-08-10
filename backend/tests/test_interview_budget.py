"""Tests for the per-workspace daily spend ceiling on the interview loop."""

import uuid

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models.company import Company
from app.models.usage import AIUsageLog
from app.routers.interview import _check_interview_budget


def _seed_company_with_spend(db, spend_usd: float) -> Company:
    company = Company(name="Acme", email=f"b-{uuid.uuid4().hex[:6]}@x.com", password_hash="x")
    db.add(company)
    db.flush()
    if spend_usd > 0:
        db.add(
            AIUsageLog(
                company_id=company.id,
                operation="interview_turn",
                model="claude-sonnet-4-6",
                cost_usd=spend_usd,
            )
        )
    db.commit()
    return company


def test_under_limit_passes(db_session, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_COST_LIMIT_USD", 50.0)
    company = _seed_company_with_spend(db_session, 10.0)
    _check_interview_budget(db_session, company.id)  # no raise


def test_over_limit_blocks_new_starts(db_session, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_COST_LIMIT_USD", 50.0)
    company = _seed_company_with_spend(db_session, 55.0)
    with pytest.raises(HTTPException) as exc:
        _check_interview_budget(db_session, company.id)
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "interview_daily_limit_reached"


def test_in_flight_gets_2x_grace(db_session, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_COST_LIMIT_USD", 50.0)
    company = _seed_company_with_spend(db_session, 55.0)
    # Between 1x and 2x: new starts blocked, in-flight turns still allowed.
    _check_interview_budget(db_session, company.id, in_flight=True)


def test_in_flight_hard_stops_at_2x(db_session, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_COST_LIMIT_USD", 50.0)
    company = _seed_company_with_spend(db_session, 101.0)
    with pytest.raises(HTTPException):
        _check_interview_budget(db_session, company.id, in_flight=True)


def test_zero_limit_disables_gate(db_session, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_COST_LIMIT_USD", 0.0)
    company = _seed_company_with_spend(db_session, 10_000.0)
    _check_interview_budget(db_session, company.id)  # disabled -> no raise


def test_other_operations_do_not_count(db_session, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_DAILY_COST_LIMIT_USD", 50.0)
    company = _seed_company_with_spend(db_session, 0.0)
    db_session.add(
        AIUsageLog(
            company_id=company.id,
            operation="copilot",
            model="claude-opus-4-8",
            cost_usd=500.0,
        )
    )
    db_session.commit()
    _check_interview_budget(db_session, company.id)  # copilot spend is separate
