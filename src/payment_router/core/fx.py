"""Pluggable FX rate sources for the simulator.

Two sources exist:

- the **frozen teaching table** (default): manually cross-checked values,
  classified ``ESTIMATED``, kept for reproducible runs and tests;
- the **live ECB source**: daily euro reference rates served by the
  Frankfurter API, classified ``VERIFIED``, cached as an on-disk snapshot so
  reruns on the same day are reproducible and offline runs degrade
  explicitly (stale snapshot first, frozen table as the last resort).

The module-level functions (:func:`get_mid_rate`, :func:`to_usd`) always
read the active source, so routing, scoring, and fee normalization follow
one switch. The supported currency set is fixed regardless of source.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path

import httpx

from payment_router.core.models import DataSource

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
FX_MODE_ENV_VAR = "PAYMENT_ROUTER_FX"
CACHE_DIR_ENV_VAR = "PAYMENT_ROUTER_FX_CACHE_DIR"
_SNAPSHOT_FILENAME = "fx_snapshot.json"
_AMOUNT_QUANTUM = Decimal("0.0001")

_FROZEN_RATES_TO_USD: dict[str, Decimal] = {
    "USD": Decimal("1.0"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "CNY": Decimal("0.14"),
    "HKD": Decimal("0.128"),
    "SGD": Decimal("0.74"),
}
_SUPPORTED_CURRENCIES = frozenset(_FROZEN_RATES_TO_USD)


class UnsupportedCurrencyError(ValueError):
    """Raised when a currency is outside the simulator's supported set."""


class FxLiveUnavailableError(RuntimeError):
    """Raised when live rates cannot be fetched and no snapshot exists."""


@dataclass(frozen=True, slots=True)
class RateSource:
    """A complete set of USD mid-rates plus its provenance."""

    mode: str
    label: str
    classification: DataSource
    usd_rates: dict[str, Decimal]
    rate_date: str | None = None
    fetched_on: str | None = None
    stale: bool = False


@dataclass(frozen=True, slots=True)
class FxStatus:
    """What a frontend needs to disclose about the active FX source."""

    requested_mode: str
    mode: str
    label: str
    classification: DataSource
    rate_date: str | None
    stale: bool
    fallback: bool
    detail: str


def _frozen_source() -> RateSource:
    return RateSource(
        mode="frozen",
        label="frozen teaching table",
        classification=DataSource.ESTIMATED,
        usd_rates=dict(_FROZEN_RATES_TO_USD),
    )


_active_source: RateSource = _frozen_source()
_current_status = FxStatus(
    requested_mode="frozen",
    mode="frozen",
    label=_active_source.label,
    classification=_active_source.classification,
    rate_date=None,
    stale=False,
    fallback=False,
    detail="Reproducible teaching values; not current market pricing.",
)


def get_mid_rate(from_currency: str, to_currency: str) -> Decimal:
    source_currency = _normalize_currency(from_currency)
    target_currency = _normalize_currency(to_currency)

    if source_currency == target_currency:
        return Decimal("1.0")

    rates = _active_source.usd_rates
    return rates[source_currency] / rates[target_currency]


def to_usd(amount: Decimal, currency: str) -> Decimal:
    normalized_currency = _normalize_currency(currency)
    return _quantize_amount(amount * _active_source.usd_rates[normalized_currency])


def supported_currencies() -> frozenset[str]:
    return _SUPPORTED_CURRENCIES


def classification() -> DataSource:
    """Provenance class of the active source (drives fee-normalization labels)."""
    return _active_source.classification


def current_status() -> FxStatus:
    return _current_status


def configure(source: RateSource) -> None:
    """Install a rate source directly (tests and embedders)."""
    global _active_source, _current_status
    missing = _SUPPORTED_CURRENCIES - set(source.usd_rates)
    if missing:
        raise ValueError(f"rate source is missing currencies: {', '.join(sorted(missing))}")
    _active_source = source
    _current_status = FxStatus(
        requested_mode=source.mode,
        mode=source.mode,
        label=source.label,
        classification=source.classification,
        rate_date=source.rate_date,
        stale=source.stale,
        fallback=False,
        detail=source.label,
    )


def activate(mode: str = "frozen", *, timeout_seconds: float = 10.0) -> FxStatus:
    """Activate a source by mode name; live failures fall back explicitly."""
    global _active_source, _current_status
    if mode not in {"frozen", "live"}:
        raise ValueError(f"unknown FX mode: {mode}")

    if mode == "frozen":
        _active_source = _frozen_source()
        _current_status = FxStatus(
            requested_mode="frozen",
            mode="frozen",
            label=_active_source.label,
            classification=DataSource.ESTIMATED,
            rate_date=None,
            stale=False,
            fallback=False,
            detail="Reproducible teaching values; not current market pricing.",
        )
        return _current_status

    try:
        source = live_source(timeout_seconds=timeout_seconds)
    except FxLiveUnavailableError as error:
        _active_source = _frozen_source()
        _current_status = FxStatus(
            requested_mode="live",
            mode="frozen",
            label=_active_source.label,
            classification=DataSource.ESTIMATED,
            rate_date=None,
            stale=False,
            fallback=True,
            detail=f"Live FX unavailable ({error}); using the frozen teaching table.",
        )
        return _current_status

    _active_source = source
    detail = f"ECB reference rates via Frankfurter, dated {source.rate_date}."
    if source.stale:
        detail += " Refresh failed; serving the cached snapshot."
    _current_status = FxStatus(
        requested_mode="live",
        mode="live",
        label=source.label,
        classification=source.classification,
        rate_date=source.rate_date,
        stale=source.stale,
        fallback=False,
        detail=detail,
    )
    return _current_status


def live_source(*, timeout_seconds: float = 10.0) -> RateSource:
    """Return ECB rates: today's snapshot, else a fresh fetch, else stale.

    Raises :class:`FxLiveUnavailableError` when the fetch fails and no
    snapshot exists at all.
    """
    snapshot_path = _snapshot_path()
    snapshot = _load_snapshot(snapshot_path)
    today = datetime.now(UTC).date().isoformat()
    if snapshot is not None and snapshot.fetched_on == today:
        return snapshot

    try:
        fresh = _fetch_frankfurter(timeout_seconds)
    except FxLiveUnavailableError:
        if snapshot is not None:
            return replace(snapshot, stale=True)
        raise

    _write_snapshot(snapshot_path, fresh)
    return fresh


def _fetch_frankfurter(timeout_seconds: float) -> RateSource:
    symbols = sorted(_SUPPORTED_CURRENCIES - {"USD"})
    try:
        response = httpx.get(
            FRANKFURTER_URL,
            params={"base": "USD", "symbols": ",".join(symbols)},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = json.loads(response.text, parse_float=Decimal)
    except (httpx.HTTPError, ValueError) as error:
        raise FxLiveUnavailableError(f"Frankfurter request failed: {error}") from error

    rates_raw = payload.get("rates") if isinstance(payload, dict) else None
    rate_date = payload.get("date") if isinstance(payload, dict) else None
    if not isinstance(rates_raw, dict) or not isinstance(rate_date, str):
        raise FxLiveUnavailableError("Frankfurter response missing rates or date")

    usd_rates: dict[str, Decimal] = {"USD": Decimal("1.0")}
    try:
        for currency in symbols:
            units_per_usd = Decimal(str(rates_raw[currency]))
            if units_per_usd <= 0:
                raise FxLiveUnavailableError(f"non-positive rate for {currency}")
            usd_rates[currency] = Decimal("1.0") / units_per_usd
    except (KeyError, InvalidOperation) as error:
        raise FxLiveUnavailableError(f"Frankfurter response incomplete: {error}") from error

    return RateSource(
        mode="live",
        label="ECB reference rates (Frankfurter)",
        classification=DataSource.VERIFIED,
        usd_rates=usd_rates,
        rate_date=rate_date,
        fetched_on=datetime.now(UTC).date().isoformat(),
    )


def _snapshot_path() -> Path:
    base = os.environ.get(CACHE_DIR_ENV_VAR)
    root = Path(base) if base else Path.home() / ".cache" / "payment-router"
    return root / _SNAPSHOT_FILENAME


def _load_snapshot(path: Path) -> RateSource | None:
    try:
        payload = json.loads(path.read_text())
        usd_rates = {currency: Decimal(value) for currency, value in payload["usd_rates"].items()}
        source = RateSource(
            mode="live",
            label="ECB reference rates (Frankfurter)",
            classification=DataSource.VERIFIED,
            usd_rates=usd_rates,
            rate_date=str(payload["rate_date"]),
            fetched_on=str(payload["fetched_on"]),
        )
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation):
        return None
    if _SUPPORTED_CURRENCIES - set(usd_rates):
        return None
    return source


def _write_snapshot(path: Path, source: RateSource) -> None:
    payload = {
        "rate_date": source.rate_date,
        "fetched_on": source.fetched_on,
        "usd_rates": {currency: str(rate) for currency, rate in source.usd_rates.items()},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    except OSError:
        # A read-only cache directory must not break live routing.
        pass


def _normalize_currency(currency: str) -> str:
    normalized_currency = currency.strip().upper()
    if normalized_currency not in _SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyError(f"Unsupported currency: {currency}")
    return normalized_currency


def _quantize_amount(amount: Decimal) -> Decimal:
    return amount.quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_EVEN)
