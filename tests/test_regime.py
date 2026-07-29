from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from payment_router import regime
from payment_router.analysis import RouteSignature
from payment_router.core import fx
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork


class Rail(PaymentNetwork):
    """A source-labelled fixed-fee or spread-cost teaching rail."""

    def __init__(self, name: str, *, fixed: str = "0", spread: str = "0") -> None:
        self._name = name
        self._fixed = Decimal(fixed)
        self._spread = Decimal(spread)

    def display_name(self) -> str:
        return self._name

    def supported_currencies(self) -> set[str]:
        return {"USD", "CNY"}

    def get_quote(self, amount, source, target):
        if source == target:
            return None
        return NetworkQuote(
            network_name=self._name,
            fee_usd=self._fixed,
            time_hours=Decimal("24"),
            fx_rate=fx.get_mid_rate(source, target) * (Decimal("1") - self._spread),
            data_source=DataSource.ESTIMATED,
        )


def _crossing_rails() -> list[PaymentNetwork]:
    # Pure-cost break-even: fixed fee F = 40 versus spread s = 0.01.
    # Therefore A = F / s = 4000.
    return [Rail("FlatFee", fixed="40"), Rail("SpreadHeavy", spread="0.01")]


def _analyze(**kwargs) -> regime.RegimeMap:
    params = {
        "min_amount": Decimal("100"),
        "max_amount": Decimal("100000"),
        "amount_samples": 9,
        "weight_steps": 8,
        **kwargs,
    }
    return asyncio.run(regime.analyze("USD", "CNY", _crossing_rails, **params))


def test_pure_cost_boundary_brackets_the_known_analytic_answer() -> None:
    report = _analyze()

    pure_cost_row = report.grid[-1]
    changes = [
        index
        for index, (below, above) in enumerate(zip(pure_cost_row, pure_cost_row[1:], strict=False))
        if below is not None and above is not None and below != above
    ]

    assert len(changes) == 1
    boundary_index = changes[0]
    assert report.amounts[boundary_index] <= Decimal("4000") <= report.amounts[boundary_index + 1]
    assert pure_cost_row[boundary_index][1] == ("SpreadHeavy",)
    assert pure_cost_row[boundary_index + 1][1] == ("FlatFee",)
    assert any("sampled, not exact" in caveat for caveat in report.caveats)
    assert any("properties of the model" in caveat for caveat in report.caveats)


def test_builds_once_per_amount_not_once_per_grid_cell(monkeypatch) -> None:
    calls = 0
    real_build_session = regime.build_session

    async def counting_build_session(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await real_build_session(*args, **kwargs)

    monkeypatch.setattr(regime, "build_session", counting_build_session)
    report = _analyze(amount_samples=5, weight_steps=40)

    assert calls == report.builds == 5
    assert len(report.grid) == 41
    assert all(len(row) == 5 for row in report.grid)
    assert calls < sum(len(row) for row in report.grid)


def test_connected_regions_use_four_neighbour_adjacency() -> None:
    first: RouteSignature = (("USD", "CNY"), ("First",))
    second: RouteSignature = (("USD", "CNY"), ("Second",))
    grid = ((first, second), (second, first))

    regions, labels = regime._connected_regions(grid)

    assert len(regions) == 4
    assert {region.cell_count for region in regions} == {1}
    assert len({label for row in labels for label in row}) == 4


def test_regions_and_region_grid_cover_every_routed_cell() -> None:
    report = _analyze()

    routed_cells = sum(cell is not None for row in report.grid for cell in row)
    assert sum(region.cell_count for region in report.regions) == routed_cells
    for weight_index, row in enumerate(report.grid):
        for amount_index, signature in enumerate(row):
            region_id = report.region_grid[weight_index][amount_index]
            assert region_id is not None
            assert report.regions[region_id].signature == signature


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"min_amount": Decimal("NaN")}, "finite"),
        ({"min_amount": Decimal("0")}, "greater than zero"),
        ({"min_amount": Decimal("1000"), "max_amount": Decimal("100")}, "below"),
        ({"amount_samples": 1}, "at least 2"),
        ({"weight_steps": 0}, "positive integer"),
    ],
)
def test_rejects_an_unusable_grid(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _analyze(**kwargs)
