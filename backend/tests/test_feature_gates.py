"""Tests for feature gate enforcement across all tiers."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.services.feature_gates import (
    TIER_LIMITS,
    get_effective_limits,
    get_limits,
    require_feature,
    require_link_limit,
    require_participant_limit,
    require_project_limit,
    require_question_limit,
)
from fastapi import HTTPException


def make_company(tier: str, trial_ends_at=None):
    company = MagicMock()
    company.subscription_tier = tier
    company.trial_ends_at = trial_ends_at
    return company


class TestGetLimits:
    def test_returns_starter_limits_for_unknown_tier(self):
        limits = get_limits("unknown_tier")
        assert limits == TIER_LIMITS["starter"]

    def test_all_tiers_present(self):
        for tier in ("starter", "team", "lab", "enterprise"):
            limits = get_limits(tier)
            assert limits.name is not None

    def test_legacy_aliases(self):
        """Legacy DB values ('solo', 'pro') still resolve. 'free' is now its own tier."""
        assert get_limits("free").name == "Free"
        assert get_limits("solo").name == "Starter"
        assert get_limits("pro").name == "Lab"

    def test_starter_tier_name(self):
        limits = get_limits("starter")
        assert limits.name == "Starter"


class TestGetEffectiveLimits:
    def test_starter_tier_no_trial(self):
        company = make_company("starter")
        limits = get_effective_limits(company)
        assert limits.name == "Starter"

    def test_starter_tier_with_active_trial_gets_team(self):
        future = datetime.utcnow() + timedelta(days=7)
        company = make_company("starter", trial_ends_at=future)
        limits = get_effective_limits(company)
        assert limits.name == "Team"

    def test_starter_tier_with_expired_trial_stays_starter(self):
        past = datetime.utcnow() - timedelta(days=1)
        company = make_company("starter", trial_ends_at=past)
        limits = get_effective_limits(company)
        assert limits.name == "Starter"

    def test_free_tier_does_not_get_trial_upgrade(self):
        """'free' is its own tier now — no trial upgrade to Team."""
        future = datetime.utcnow() + timedelta(days=7)
        company = make_company("free", trial_ends_at=future)
        limits = get_effective_limits(company)
        assert limits.name == "Free"

    def test_free_tier_no_trial(self):
        company = make_company("free")
        limits = get_effective_limits(company)
        assert limits.name == "Free"
        # Free tier limits sanity check
        assert limits.max_projects == 1
        assert limits.max_participants_per_project == 5
        assert limits.ai_analysis is True
        assert limits.export_csv is False

    def test_team_tier_ignores_trial(self):
        future = datetime.utcnow() + timedelta(days=7)
        company = make_company("team", trial_ends_at=future)
        limits = get_effective_limits(company)
        assert limits.name == "Team"

    def test_lab_tier_ignores_trial(self):
        company = make_company("lab")
        limits = get_effective_limits(company)
        assert limits.name == "Lab"


class TestRequireProjectLimit:
    def test_starter_tier_allows_one_project(self):
        require_project_limit(make_company("starter"), 0)  # no exception

    def test_starter_tier_blocks_second_project(self):
        with pytest.raises(HTTPException) as exc_info:
            require_project_limit(make_company("starter"), 1)
        assert exc_info.value.status_code == 403

    def test_lab_tier_unlimited_projects(self):
        require_project_limit(make_company("lab"), 999)

    def test_team_tier_allows_up_to_limit(self):
        require_project_limit(make_company("team"), 4)  # 5 max, 4 current -> ok
        with pytest.raises(HTTPException):
            require_project_limit(make_company("team"), 5)  # at limit -> blocked

    def test_starter_with_trial_gets_team_limit(self):
        future = datetime.utcnow() + timedelta(days=7)
        company = make_company("starter", trial_ends_at=future)
        require_project_limit(company, 4)  # team allows 5
        with pytest.raises(HTTPException):
            require_project_limit(company, 5)


class TestRequireQuestionLimit:
    def test_starter_tier_allows_ten_questions(self):
        require_question_limit(make_company("starter"), 10)  # exactly at limit

    def test_starter_tier_blocks_eleven_questions(self):
        with pytest.raises(HTTPException) as exc_info:
            require_question_limit(make_company("starter"), 11)
        assert exc_info.value.status_code == 403

    def test_enterprise_unlimited(self):
        require_question_limit(make_company("enterprise"), 999)


class TestRequireParticipantLimit:
    def test_starter_tier_allows_up_to_limit(self):
        project = MagicMock()
        require_participant_limit(make_company("starter"), project, 9)

    def test_starter_tier_blocks_at_limit(self):
        project = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            require_participant_limit(make_company("starter"), project, 10)
        assert exc_info.value.status_code == 403


class TestRequireLinkLimit:
    def test_starter_tier_allows_up_to_two_links(self):
        require_link_limit(make_company("starter"), 1)

    def test_starter_tier_blocks_third_link(self):
        with pytest.raises(HTTPException) as exc_info:
            require_link_limit(make_company("starter"), 2)
        assert exc_info.value.status_code == 403

    def test_lab_tier_allows_up_to_limit(self):
        require_link_limit(make_company("lab"), 9)  # 10 max

    def test_enterprise_unlimited(self):
        require_link_limit(make_company("enterprise"), 999)


class TestRequireFeature:
    def test_starter_tier_can_use_ai_analysis(self):
        require_feature(make_company("starter"), "ai_analysis")  # no exception

    def test_team_tier_can_use_ai_analysis(self):
        require_feature(make_company("team"), "ai_analysis")  # no exception

    def test_starter_tier_cannot_export_csv(self):
        with pytest.raises(HTTPException):
            require_feature(make_company("starter"), "export_csv")

    def test_team_can_export_csv(self):
        require_feature(make_company("team"), "export_csv")

    def test_starter_tier_cannot_use_custom_branding(self):
        with pytest.raises(HTTPException):
            require_feature(make_company("starter"), "custom_branding")

    def test_lab_can_use_custom_branding(self):
        require_feature(make_company("lab"), "custom_branding")

    def test_starter_with_trial_can_export_csv(self):
        future = datetime.utcnow() + timedelta(days=7)
        company = make_company("starter", trial_ends_at=future)
        require_feature(company, "export_csv")  # team allows this

    def test_starter_with_expired_trial_cannot_export_csv(self):
        past = datetime.utcnow() - timedelta(days=1)
        company = make_company("starter", trial_ends_at=past)
        with pytest.raises(HTTPException):
            require_feature(company, "export_csv")
