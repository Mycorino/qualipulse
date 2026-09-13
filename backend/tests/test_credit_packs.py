"""Prepaid credit packs: pricing invariants + the Stripe price-mismatch guard."""

from types import SimpleNamespace

import pytest

from app.routers.billing import _PackPriceMismatch, _assert_pack_price_matches
from app.services.billing_plans import ALL_PLANS, CREDIT_PACKS, get_credit_pack

# A pack is the top-up for one plan; its per-credit price must equal that
# plan's overage rate so prepaying is never dearer than going over.
PACK_TO_PLAN = {"pack_25": "exploration", "pack_50": "team", "pack_100": "agency"}


class TestPackPricing:
    def test_three_packs_in_catalogue(self):
        assert [p.id for p in CREDIT_PACKS] == ["pack_25", "pack_50", "pack_100"]

    @pytest.mark.parametrize("pack_id,plan_id", PACK_TO_PLAN.items())
    def test_pack_per_credit_equals_plan_overage(self, pack_id, plan_id):
        pack = get_credit_pack(pack_id)
        plan = next(p for p in ALL_PLANS if p.id == plan_id)
        assert pack.price_cents % pack.credits == 0
        assert pack.price_cents // pack.credits == plan.overage_price_cents

    def test_public_prices(self):
        """Pinned because the marketing page hardcodes these (MARKETING_PACKS)."""
        assert {p.id: p.price_cents for p in CREDIT_PACKS} == {
            "pack_25": 17500,
            "pack_50": 30000,
            "pack_100": 50000,
        }


def _fake_stripe(unit_amount, currency="eur"):
    price = SimpleNamespace(unit_amount=unit_amount, currency=currency)
    return SimpleNamespace(Price=SimpleNamespace(retrieve=lambda _id: price))


class TestPriceMismatchGuard:
    def test_matching_price_passes(self):
        pack = get_credit_pack("pack_25")
        _assert_pack_price_matches(_fake_stripe(pack.price_cents), "price_x", pack)

    def test_stale_stripe_price_raises(self):
        pack = get_credit_pack("pack_25")
        with pytest.raises(_PackPriceMismatch):
            _assert_pack_price_matches(_fake_stripe(30000), "price_x", pack)

    def test_wrong_currency_raises(self):
        pack = get_credit_pack("pack_50")
        with pytest.raises(_PackPriceMismatch):
            _assert_pack_price_matches(_fake_stripe(pack.price_cents, "usd"), "price_x", pack)

    def test_lookup_failure_is_ignored(self):
        """A Stripe hiccup must not block a purchase; only a confirmed mismatch does."""
        def boom(_id):
            raise RuntimeError("network")
        pack = get_credit_pack("pack_100")
        _assert_pack_price_matches(SimpleNamespace(Price=SimpleNamespace(retrieve=boom)), "price_x", pack)
