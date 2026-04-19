"""
Static base FX rates for the simulator.

These rates were manually cross-checked in 2026-04 and are only intended for
route ranking inside the simulator. Real implementations should use a proper FX
source such as Frankfurter or ECB reference rates.

TODO: Extend this into an `FXProvider` abstraction with pluggable data sources
once the simulator needs live or historical FX support.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

_MID_RATES_TO_USD: dict[str, Decimal] = {
    "USD": Decimal("1.0"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "CNY": Decimal("0.14"),
}
_AMOUNT_QUANTUM = Decimal("0.0001")
_SUPPORTED_CURRENCIES = frozenset(_MID_RATES_TO_USD)


class UnsupportedCurrencyError(ValueError):
    """Raised when a currency is outside the simulator's supported set."""


def get_mid_rate(from_currency: str, to_currency: str) -> Decimal:
    source_currency = _normalize_currency(from_currency)
    target_currency = _normalize_currency(to_currency)

    if source_currency == target_currency:
        return Decimal("1.0")

    return _MID_RATES_TO_USD[source_currency] / _MID_RATES_TO_USD[target_currency]


def to_usd(amount: Decimal, currency: str) -> Decimal:
    normalized_currency = _normalize_currency(currency)
    return _quantize_amount(amount * _MID_RATES_TO_USD[normalized_currency])


def supported_currencies() -> frozenset[str]:
    return _SUPPORTED_CURRENCIES


def _normalize_currency(currency: str) -> str:
    normalized_currency = currency.strip().upper()
    if normalized_currency not in _MID_RATES_TO_USD:
        raise UnsupportedCurrencyError(f"Unsupported currency: {currency}")
    return normalized_currency


def _quantize_amount(amount: Decimal) -> Decimal:
    return amount.quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_EVEN)
