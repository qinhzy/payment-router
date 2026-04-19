from __future__ import annotations

from decimal import Decimal

import pytest

from payment_router.core.models import DataSource
from payment_router.networks.sepa import SEPANetwork

pytestmark = pytest.mark.anyio


async def test_default_sct_quote_for_eur_to_eur() -> None:
    network = SEPANetwork()

    quote = await network.get_quote(Decimal("100"), "EUR", "EUR")

    assert quote is not None
    assert quote.network_name == "SEPA"
    assert quote.fee_usd == Decimal("0.27")
    assert quote.time_hours == Decimal("24.0")
    assert quote.fx_rate == Decimal("1.0")
    assert quote.data_source is DataSource.INDUSTRY_AVERAGE


async def test_instant_quote_for_eur_to_eur() -> None:
    network = SEPANetwork(instant=True)

    quote = await network.get_quote(Decimal("100"), "EUR", "EUR")

    assert quote is not None
    assert quote.network_name == "SEPA Instant"
    assert quote.fee_usd == Decimal("0.54")
    assert quote.time_hours == Decimal("0.003")
    assert quote.data_source is DataSource.INDUSTRY_AVERAGE


async def test_non_eur_source_corridor_returns_none() -> None:
    network = SEPANetwork()

    quote = await network.get_quote(Decimal("100"), "USD", "EUR")

    assert quote is None


async def test_non_eur_target_corridor_returns_none() -> None:
    network = SEPANetwork()

    quote = await network.get_quote(Decimal("100"), "EUR", "CNY")

    assert quote is None


def test_supported_currencies_is_eur_only() -> None:
    network = SEPANetwork()

    assert network.supported_currencies() == {"EUR"}


async def test_zero_amount_still_returns_fixed_quote() -> None:
    network = SEPANetwork()

    quote = await network.get_quote(Decimal("0"), "EUR", "EUR")

    assert quote is not None
    assert quote.network_name == "SEPA"
    assert quote.fee_usd == Decimal("0.27")
    assert quote.time_hours == Decimal("24.0")
