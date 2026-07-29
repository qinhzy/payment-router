from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from payment_router import breakeven
from payment_router.core import fx
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.decision import DecisionProfile
from payment_router.networks.base import PaymentNetwork


class Rail(PaymentNetwork):
    """A rail with the fee shape that makes crossovers exist.

    A fixed fee dominates small amounts; an FX spread dominates large ones.
    Two rails that differ in which of the two they lean on must cross.
    """

    def __init__(
        self,
        name: str,
        fixed: str = "0",
        percentage: str = "0",
        spread: str = "0",
        hours: str = "24",
    ) -> None:
        self._name = name
        self._fixed = Decimal(fixed)
        self._percentage = Decimal(percentage)
        self._spread = Decimal(spread)
        self._hours = Decimal(hours)

    def display_name(self) -> str:
        return self._name

    def supported_currencies(self) -> set[str]:
        return {"USD", "CNY"}

    def get_quote(self, amount, source, target):
        if source == target:
            return None
        return NetworkQuote(
            network_name=self._name,
            fee_usd=self._fixed + amount * self._percentage,
            time_hours=self._hours,
            fx_rate=fx.get_mid_rate(source, target) * (Decimal("1") - self._spread),
            data_source=DataSource.ESTIMATED,
        )


def _crossing_rails():
    # Break-even where the fixed fee equals the spread cost: 40 = 0.01 * A,
    # so A = 4000.
    return [Rail("FlatFee", fixed="40"), Rail("SpreadHeavy", spread="0.01")]


def _analyze(networks_factory, **kwargs):
    params = {
        "min_amount": Decimal("10"),
        "max_amount": Decimal("100000"),
        **kwargs,
    }
    return asyncio.run(breakeven.analyze("USD", "CNY", networks_factory, **params))


def test_locates_a_crossover_with_a_known_analytic_answer() -> None:
    report = _analyze(_crossing_rails, samples=12, refine_steps=8)

    assert len(report.crossovers) == 1
    crossover = report.crossovers[0]
    # The true crossing is 4000; the bracket must contain it.
    assert crossover.bracket_low <= Decimal("4000") <= crossover.bracket_high
    assert crossover.below[1] == ("SpreadHeavy",)
    assert crossover.above[1] == ("FlatFee",)


def test_bisection_narrows_the_bracket_without_dense_sampling() -> None:
    coarse = _analyze(_crossing_rails, samples=12, refine_steps=0)
    refined = _analyze(_crossing_rails, samples=12, refine_steps=10)

    assert refined.crossovers[0].bracket_width < coarse.crossovers[0].bracket_width
    # Precision came from bisection, not from more provider load.
    assert refined.builds <= coarse.builds + 10


def test_regions_cover_the_requested_range_without_gaps() -> None:
    report = _analyze(_crossing_rails, samples=12, refine_steps=6)

    assert report.regions[0].amount_start == Decimal("10")
    assert report.regions[-1].amount_end == Decimal("100000")
    for lower, higher in zip(report.regions, report.regions[1:], strict=False):
        assert lower.amount_end == higher.amount_start
    signatures = [region.signature for region in report.regions]
    assert len(signatures) == len(set(signatures)), "adjacent regions must differ"


def test_a_dominated_rail_produces_no_crossover() -> None:
    """One rail better on every parameter never yields a break-even."""

    def rails():
        return [
            Rail("Worse", fixed="40", percentage="0.002", spread="0.01"),
            Rail("Better", fixed="8", percentage="0.001", spread="0.003"),
        ]

    report = _analyze(rails, samples=10, refine_steps=4)

    assert report.crossovers == ()
    assert len(report.regions) == 1
    assert report.regions[0].signature[1] == ("Better",)
    assert any("No crossover was found" in caveat for caveat in report.caveats)


def test_reports_the_bracket_as_a_caveat_not_an_exact_figure() -> None:
    report = _analyze(_crossing_rails, samples=12, refine_steps=3)

    assert any("bracket, not an exact figure" in caveat for caveat in report.caveats)
    assert any("quoted independently" in caveat for caveat in report.caveats)


def test_estimated_fees_are_flagged_as_a_model_property() -> None:
    report = _analyze(_crossing_rails, samples=8, refine_steps=2)

    assert any("scenario assumptions" in caveat for caveat in report.caveats)


def test_the_profile_is_applied_at_every_amount() -> None:
    def rails():
        return [
            Rail("SlowCheap", fixed="1", hours="72"),
            Rail("FastPricey", fixed="60", hours="1"),
        ]

    # Start above FastPricey's fixed fee: below it that route is unfundable and
    # "fastest" correctly falls back, which would test the fallback, not the profile.
    span = {"min_amount": Decimal("500"), "max_amount": Decimal("100000")}
    cheapest = _analyze(rails, samples=8, refine_steps=2, profile=DecisionProfile.CHEAPEST, **span)
    fastest = _analyze(rails, samples=8, refine_steps=2, profile=DecisionProfile.FASTEST, **span)

    assert {region.signature[1] for region in cheapest.regions} == {("SlowCheap",)}
    assert {region.signature[1] for region in fastest.regions} == {("FastPricey",)}


def test_unroutable_amounts_are_reported_rather_than_hidden() -> None:
    """Below the fee floor no route is fundable; that must be visible."""

    def rails():
        return [Rail("Pricey", fixed="500")]

    report = _analyze(rails, samples=8, refine_steps=2)

    assert any("had no route at all" in caveat for caveat in report.caveats)


def test_no_route_at_any_amount_yields_no_regions() -> None:
    def rails():
        return [Rail("Unaffordable", fixed="10000000")]

    report = _analyze(rails, samples=6, refine_steps=1)

    assert report.regions == ()
    assert report.crossovers == ()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"min_amount": Decimal("0")}, "greater than zero"),
        ({"min_amount": Decimal("100"), "max_amount": Decimal("10")}, "below"),
        ({"samples": 1}, "at least 2"),
        ({"refine_steps": -1}, "cannot be negative"),
    ],
)
def test_rejects_an_unusable_range(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _analyze(_crossing_rails, **kwargs)


def test_samples_are_geometrically_spaced() -> None:
    """Fee structure is scale-driven, so the scan must be too."""
    spaced = breakeven._log_spaced(Decimal("10"), Decimal("10000"), 4)

    assert spaced[0] == Decimal("10.00")
    assert spaced[-1] == Decimal("10000.00")
    # Equal ratios rather than equal differences.
    assert spaced[1] == Decimal("100.00")
    assert spaced[2] == Decimal("1000.00")
