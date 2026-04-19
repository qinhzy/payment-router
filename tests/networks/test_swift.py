from __future__ import annotations

from decimal import Decimal

import pytest

from payment_router.core.models import DataSource
from payment_router.networks.swift import _MID_RATES_TO_USD, SWIFTNetwork

pytestmark = pytest.mark.anyio


async def test_default_gbp_to_cny_quote_uses_three_hops() -> None:
    network = SWIFTNetwork()

    quote = await network.get_quote(Decimal("1000"), "GBP", "CNY")

    expected_fee = Decimal("3") * (
        Decimal("20") + (Decimal("1000") * _MID_RATES_TO_USD["GBP"] * Decimal("0.002"))
    )
    expected_fx_rate = (
        _MID_RATES_TO_USD["GBP"]
        / _MID_RATES_TO_USD["CNY"]
        * (Decimal("1.0") - Decimal("0.01")) ** 3
    )

    assert quote is not None
    assert quote.network_name == "SWIFT"
    assert quote.fee_usd == expected_fee
    assert quote.time_hours == Decimal("54.0")
    assert float(quote.fx_rate) == pytest.approx(float(expected_fx_rate))
    assert quote.data_source is DataSource.INDUSTRY_AVERAGE


async def test_more_hops_increase_fee_and_time_proportionally() -> None:
    network = SWIFTNetwork(num_hops=4)

    quote = await network.get_quote(Decimal("1000"), "GBP", "CNY")

    expected_fee = Decimal("4") * (
        Decimal("20") + (Decimal("1000") * _MID_RATES_TO_USD["GBP"] * Decimal("0.002"))
    )
    expected_fx_rate = (
        _MID_RATES_TO_USD["GBP"]
        / _MID_RATES_TO_USD["CNY"]
        * (Decimal("1.0") - Decimal("0.01")) ** 4
    )

    assert quote is not None
    assert quote.fee_usd == expected_fee
    assert quote.time_hours == Decimal("72.0")
    assert float(quote.fx_rate) == pytest.approx(float(expected_fx_rate))


async def test_same_currency_usd_to_usd_keeps_fx_rate_at_one() -> None:
    network = SWIFTNetwork()

    quote = await network.get_quote(Decimal("1000"), "USD", "USD")

    assert quote is not None
    assert quote.fx_rate == Decimal("1.0")
    assert quote.fee_usd == Decimal("66.000")
    assert quote.time_hours == Decimal("54.0")


async def test_unsupported_source_currency_returns_none() -> None:
    network = SWIFTNetwork()

    quote = await network.get_quote(Decimal("1000"), "JPY", "USD")

    assert quote is None


async def test_small_amount_is_fixed_fee_dominated() -> None:
    network = SWIFTNetwork()

    quote = await network.get_quote(Decimal("10"), "USD", "EUR")

    assert quote is not None
    assert quote.fee_usd >= Decimal("60")
    assert quote.fee_usd == Decimal("60.060")


async def test_large_amount_is_percentage_fee_dominated() -> None:
    network = SWIFTNetwork()

    quote = await network.get_quote(Decimal("100000"), "USD", "EUR")

    assert quote is not None
    assert quote.fee_usd == Decimal("660.000")
    assert quote.fee_usd - Decimal("60") == Decimal("600.000")
    assert quote.fee_usd - Decimal("60") > Decimal("60")


def test_supported_currencies_returns_mvp_currency_set() -> None:
    network = SWIFTNetwork()

    assert network.supported_currencies() == {"USD", "EUR", "GBP", "CNY"}


async def test_zero_fees_and_zero_spread_reduce_to_mid_rate() -> None:
    network = SWIFTNetwork(
        hop_fixed_fee_usd=Decimal("0"),
        hop_percentage_fee=Decimal("0"),
        hop_fx_spread=Decimal("0"),
    )

    quote = await network.get_quote(Decimal("1000"), "USD", "EUR")

    assert quote is not None
    assert quote.fee_usd == Decimal("0")
    assert float(quote.fx_rate) == pytest.approx(float(Decimal("1.0") / Decimal("1.08")))
