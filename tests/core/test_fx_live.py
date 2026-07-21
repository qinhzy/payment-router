from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from payment_router.core import fx
from payment_router.core.models import DataSource

FRANKFURTER_JSON = {
    "amount": 1.0,
    "base": "USD",
    "date": "2026-07-17",
    "rates": {"CNY": 7.2, "EUR": 0.925, "GBP": 0.79},
}


@pytest.fixture
def fx_cache_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv(fx.CACHE_DIR_ENV_VAR, str(tmp_path))
    yield tmp_path
    fx.activate("frozen")


def _snapshot_file(cache_dir: Path) -> Path:
    return cache_dir / "fx_snapshot.json"


def test_live_fetch_inverts_rates_and_writes_snapshot(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=FRANKFURTER_JSON)

    source = fx.live_source()

    assert source.classification is DataSource.VERIFIED
    assert source.rate_date == "2026-07-17"
    assert source.usd_rates["USD"] == Decimal("1.0")
    assert source.usd_rates["EUR"] == Decimal("1.0") / Decimal("0.925")
    assert _snapshot_file(fx_cache_dir).exists()


def test_same_day_snapshot_is_reused_without_network(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=FRANKFURTER_JSON)

    first = fx.live_source()
    second = fx.live_source()  # would fail if it issued a second request

    assert second.usd_rates == first.usd_rates
    assert len(httpx_mock.get_requests()) == 1


def test_stale_snapshot_survives_fetch_failure(fx_cache_dir, httpx_mock) -> None:
    snapshot = {
        "rate_date": "2026-07-10",
        "fetched_on": "2026-07-10",
        "usd_rates": {"USD": "1.0", "EUR": "1.07", "GBP": "1.25", "CNY": "0.139"},
    }
    _snapshot_file(fx_cache_dir).write_text(json.dumps(snapshot))
    httpx_mock.add_exception(httpx.ConnectError("offline"))

    source = fx.live_source()

    assert source.stale is True
    assert source.rate_date == "2026-07-10"
    assert source.usd_rates["EUR"] == Decimal("1.07")


def test_activate_live_falls_back_to_frozen_when_unavailable(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("offline"))

    status = fx.activate("live")

    assert status.requested_mode == "live"
    assert status.mode == "frozen"
    assert status.fallback is True
    assert fx.classification() is DataSource.ESTIMATED
    assert fx.get_mid_rate("EUR", "USD") == Decimal("1.08")


def test_activate_live_updates_module_rates_and_status(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=FRANKFURTER_JSON)

    status = fx.activate("live")

    assert status.mode == "live"
    assert status.fallback is False
    assert status.rate_date == "2026-07-17"
    assert fx.classification() is DataSource.VERIFIED
    assert fx.get_mid_rate("EUR", "USD") == Decimal("1.0") / Decimal("0.925")


def test_activate_rejects_unknown_mode(fx_cache_dir) -> None:
    with pytest.raises(ValueError, match="unknown FX mode"):
        fx.activate("floating")


def test_configure_rejects_incomplete_rate_sets(fx_cache_dir) -> None:
    partial = fx.RateSource(
        mode="live",
        label="partial",
        classification=DataSource.VERIFIED,
        usd_rates={"USD": Decimal("1.0")},
    )

    with pytest.raises(ValueError, match="missing currencies"):
        fx.configure(partial)


def test_corrupt_snapshot_is_ignored(fx_cache_dir, httpx_mock) -> None:
    _snapshot_file(fx_cache_dir).write_text("{not json")
    httpx_mock.add_response(json=FRANKFURTER_JSON)

    source = fx.live_source()

    assert source.stale is False
    assert source.rate_date == "2026-07-17"
