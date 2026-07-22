from __future__ import annotations

from decimal import Decimal

import pytest

from payment_router.core.fx import (
    UnsupportedCurrencyError,
    get_mid_rate,
    supported_currencies,
    to_usd,
)


def test_get_mid_rate_for_gbp_to_cny() -> None:
    rate = get_mid_rate("GBP", "CNY")

    assert float(rate) == pytest.approx(float(Decimal("1.27") / Decimal("0.14")))


def test_get_mid_rate_for_same_currency_returns_one() -> None:
    assert get_mid_rate("USD", "USD") == Decimal("1.0")


def test_get_mid_rate_raises_for_unsupported_currency() -> None:
    with pytest.raises(UnsupportedCurrencyError):
        get_mid_rate("JPY", "USD")


def test_to_usd_converts_eur_amount() -> None:
    assert to_usd(Decimal("100"), "EUR") == Decimal("108")


def test_new_asian_corridor_rates_are_available() -> None:
    assert to_usd(Decimal("100"), "HKD") == Decimal("12.8000")
    assert to_usd(Decimal("100"), "SGD") == Decimal("74.0000")
    assert get_mid_rate("HKD", "CNY") == Decimal("0.128") / Decimal("0.14")


def test_to_usd_raises_for_unsupported_currency() -> None:
    with pytest.raises(UnsupportedCurrencyError):
        to_usd(Decimal("100"), "JPY")


def test_supported_currencies_returns_immutable_six_currency_set() -> None:
    currencies = supported_currencies()

    assert isinstance(currencies, frozenset)
    assert currencies == frozenset({"USD", "EUR", "GBP", "CNY", "HKD", "SGD"})


def test_get_mid_rate_has_at_least_four_decimal_places_of_precision() -> None:
    rate = get_mid_rate("GBP", "CNY")

    assert rate.quantize(Decimal("0.0001")) == Decimal("9.0714")
