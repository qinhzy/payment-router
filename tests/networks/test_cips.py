from __future__ import annotations

from decimal import Decimal

import pytest

from payment_router.core import fx
from payment_router.core.models import DataSource
from payment_router.networks.cips import CIPSNetwork
from payment_router.networks.swift import SWIFTNetwork

pytestmark = pytest.mark.anyio


async def test_default_hkd_to_cny_quote_uses_two_estimated_hops() -> None:
    network = CIPSNetwork()

    quote = await network.get_quote(Decimal("10000"), "HKD", "CNY")

    expected_fee = Decimal("2") * (
        Decimal("8") + Decimal("10000") * Decimal("0.128") * Decimal("0.001")
    )
    expected_fx_rate = fx.get_mid_rate("HKD", "CNY") * (Decimal("1.0") - Decimal("0.003")) ** 2

    assert quote is not None
    assert quote.network_name == "CIPS"
    assert quote.fee_usd == expected_fee
    assert quote.time_hours == Decimal("12.0")
    assert quote.time_min_hours == Decimal("2.0")
    assert quote.time_max_hours == Decimal("24.0")
    assert quote.fx_rate == expected_fx_rate
    assert quote.data_source is DataSource.ESTIMATED
    assert quote.fee_data_source is DataSource.ESTIMATED
    assert quote.time_data_source is DataSource.ESTIMATED
    assert quote.fx_data_source is DataSource.ESTIMATED


async def test_default_cips_scenario_is_shorter_and_faster_than_swift() -> None:
    cips_quote = await CIPSNetwork().get_quote(Decimal("1000"), "USD", "CNY")
    swift_quote = await SWIFTNetwork().get_quote(Decimal("1000"), "USD", "CNY")

    assert cips_quote is not None
    assert swift_quote is not None
    assert cips_quote.fee_usd < swift_quote.fee_usd
    assert cips_quote.time_hours < swift_quote.time_hours
    assert cips_quote.time_max_hours < swift_quote.time_max_hours
    assert cips_quote.fx_rate > swift_quote.fx_rate


@pytest.mark.parametrize("target_currency", ["USD", "EUR", "GBP", "HKD", "SGD"])
async def test_non_cny_target_corridors_are_not_supported(target_currency: str) -> None:
    quote = await CIPSNetwork().get_quote(Decimal("1000"), "USD", target_currency)

    assert quote is None


async def test_cny_to_cny_cross_border_self_loop_keeps_identity_fx() -> None:
    quote = await CIPSNetwork().get_quote(Decimal("1000"), "CNY", "CNY")

    assert quote is not None
    assert quote.fx_rate == Decimal("1.0")
    assert quote.time_min_hours == Decimal("2.0")
    assert quote.time_max_hours == Decimal("24.0")


async def test_unsupported_source_currency_returns_none() -> None:
    quote = await CIPSNetwork().get_quote(Decimal("1000"), "JPY", "CNY")

    assert quote is None


def test_supported_currencies_matches_simulator_currency_set() -> None:
    assert CIPSNetwork().supported_currencies() == {
        "USD",
        "EUR",
        "GBP",
        "CNY",
        "HKD",
        "SGD",
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"num_hops": 0}, "num_hops"),
        ({"num_hops": True}, "num_hops"),
        ({"hop_fixed_fee_usd": Decimal("-1")}, "hop_fixed_fee_usd"),
        ({"hop_percentage_fee": Decimal("1.1")}, "hop_percentage_fee"),
        ({"hop_time_hours": float("nan")}, "hop_time_hours"),
        ({"hop_time_min_hours": 7.0}, "hop time bounds"),
        ({"hop_time_max_hours": 5.0}, "hop time bounds"),
        ({"hop_fx_spread": Decimal("1")}, "hop_fx_spread"),
    ],
)
def test_constructor_rejects_invalid_scenario_parameters(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        CIPSNetwork(**kwargs)


async def test_configurable_zero_fee_and_spread_quote_uses_mid_rate() -> None:
    network = CIPSNetwork(
        num_hops=1,
        hop_fixed_fee_usd=Decimal("0"),
        hop_percentage_fee=Decimal("0"),
        hop_time_hours=2.0,
        hop_time_min_hours=0.5,
        hop_time_max_hours=3.0,
        hop_fx_spread=Decimal("0"),
    )

    quote = await network.get_quote(Decimal("1000"), "SGD", "CNY")

    assert quote is not None
    assert quote.fee_usd == Decimal("0")
    assert quote.time_hours == Decimal("2.0")
    assert quote.time_min_hours == Decimal("0.5")
    assert quote.time_max_hours == Decimal("3.0")
    assert quote.fx_rate == fx.get_mid_rate("SGD", "CNY")
