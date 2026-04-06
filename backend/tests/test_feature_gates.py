"""Tests for feature gate enforcement across all tiers."""
import pytest
from unittest.mock import MagicMock

from app.services.feature_gates import (
    TIER_LIMITS,
    get_limits,
    require_feature,
    require_link_limit,
    require_participant_limit,
    require_project_limit,
    require_question_limit,
)
from fastapi import HTTPException


def make_company(tier: str):
    company = MagicMock()
    company.subscription_tier = tier
    return company


class TestGetLimits:
    def test_returns_free_limits_for_unknown_tier(self):
        limits = get_limits("unknown_tier")
        assert limits == TIER_LIMITS["free"]

    def test_all_tiers_present(self):
        for tier in ("free", "starter", "pro", "enterprise"):
            limits = get_limits(tier)
            assert limits.name is not None


class TestRequireProjectLimit:
    def test_free_tier_allows_one_project(self):
        require_project_limit(make_company("free"), 0)  # no exception

    def test_free_tier_blocks_second_project(self):
        with pytest.raises(HTTPException) as exc_info:
            require_project_limit(make_company("free"), 1)
        assert exc_info.value.status_code == 403

    def test_pro_tier_unlimited_projects(self):
        # Should never raise
        require_project_limit(make_company("pro"), 999)

    def test_starter_tier_allows_up_to_limit(self):
        require_project_limit(make_company("starter"), 4)  # 5 max, 4 current → ok
        with pytest.raises(HTTPException):
            require_project_limit(make_company("starter"), 5)  # at limit → blocked


class TestRequireQuestionLimit:
    def test_free_tier_allows_five_questions(self):
        require_question_limit(make_company("free"), 5)  # exactly at limit

    def test_free_tier_blocks_six_questions(self):
        with pytest.raises(HTTPException) as exc_info:
            require_question_limit(make_company("free"), 6)
        assert exc_info.value.status_code == 403

    def test_enterprise_unlimited(self):
        require_question_limit(make_company("enterprise"), 999)


class TestRequireParticipantLimit:
    def test_free_tier_allows_up_to_limit(self):
        project = MagicMock()
        require_participant_limit(make_company("free"), project, 9)

    def test_free_tier_blocks_at_limit(self):
        project = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            require_participant_limit(make_company("free"), project, 10)
        assert exc_info.value.status_code == 403


class TestRequireLinkLimit:
    def test_free_tier_allows_one_link(self):
        require_link_limit(make_company("free"), 0)

    def test_free_tier_blocks_second_link(self):
        with pytest.raises(HTTPException) as exc_info:
            require_link_limit(make_company("free"), 1)
        assert exc_info.value.status_code == 403

    def test_pro_tier_allows_up_to_limit(self):
        require_link_limit(make_company("pro"), 9)  # 10 max

    def test_enterprise_unlimited(self):
        require_link_limit(make_company("enterprise"), 999)


class TestRequireFeature:
    def test_free_tier_cannot_use_ai_analysis(self):
        with pytest.raises(HTTPException) as exc_info:
            require_feature(make_company("free"), "ai_analysis")
        assert exc_info.value.status_code == 403

    def test_starter_tier_can_use_ai_analysis(self):
        require_feature(make_company("starter"), "ai_analysis")  # no exception

    def test_free_tier_cannot_export_csv(self):
        with pytest.raises(HTTPException):
            require_feature(make_company("free"), "export_csv")

    def test_starter_can_export_csv(self):
        require_feature(make_company("starter"), "export_csv")

    def test_free_tier_cannot_use_custom_branding(self):
        with pytest.raises(HTTPException):
            require_feature(make_company("free"), "custom_branding")

    def test_pro_can_use_custom_branding(self):
        require_feature(make_company("pro"), "custom_branding")
