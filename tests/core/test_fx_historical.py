from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from payment_router.core import fx
from payment_router.core.models import DataSource

HISTORICAL_JSON = {
    "amount": 1.0,
    "base": "USD",
    "date": "2024-01-02",
    "rates": {"CNY": 7.1, "EUR": 0.906, "GBP": 0.784, "HKD": 7.81, "SGD": 1.32},
}


@pytest.fixture
def fx_cache_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv(fx.CACHE_DIR_ENV_VAR, str(tmp_path))
    yield tmp_path
    fx.activate("frozen")


def _snapshot_file(cache_dir: Path, on_date: str) -> Path:
    return cache_dir / f"fx_snapshot_{on_date}.json"


def test_historical_fetch_uses_the_dated_endpoint_and_caches_per_date(
    fx_cache_dir,
    httpx_mock,
) -> None:
    httpx_mock.add_response(json=HISTORICAL_JSON)

    source = fx.historical_source("2024-01-02")

    assert source.mode == "historical"
    assert source.classification is DataSource.VERIFIED
    assert source.rate_date == "2024-01-02"
    assert source.requested_date == "2024-01-02"
    assert source.usd_rates["EUR"] == Decimal("1.0") / Decimal("0.906")
    request = httpx_mock.get_requests()[0]
    assert request.url.path.endswith("/2024-01-02")
    assert _snapshot_file(fx_cache_dir, "2024-01-02").exists()


def test_historical_snapshot_is_reused_without_a_second_request(
    fx_cache_dir,
    httpx_mock,
) -> None:
    """A past fixing is immutable, so the cache never needs revalidating."""
    httpx_mock.add_response(json=HISTORICAL_JSON)
    first = fx.historical_source("2024-01-02")

    second = fx.historical_source("2024-01-02")

    assert len(httpx_mock.get_requests()) == 1
    assert second.usd_rates == first.usd_rates
    assert second.requested_date == "2024-01-02"
    assert second.mode == "historical"


def test_separate_dates_use_separate_snapshots(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=HISTORICAL_JSON)
    january = fx.historical_source("2024-01-02")

    httpx_mock.add_response(
        json={
            **HISTORICAL_JSON,
            "date": "2024-06-03",
            "rates": {**HISTORICAL_JSON["rates"], "EUR": 0.92},
        }
    )
    june = fx.historical_source("2024-06-03")

    assert january.usd_rates["EUR"] != june.usd_rates["EUR"]
    assert _snapshot_file(fx_cache_dir, "2024-01-02").exists()
    assert _snapshot_file(fx_cache_dir, "2024-06-03").exists()


def test_weekend_request_reports_the_publication_it_actually_got(
    fx_cache_dir,
    httpx_mock,
) -> None:
    """ECB publishes on business days; the gap must stay visible."""
    # 2024-01-06 is a Saturday; Frankfurter answers with Friday's fixing.
    httpx_mock.add_response(json={**HISTORICAL_JSON, "date": "2024-01-05"})

    status = fx.activate("historical", on_date="2024-01-06")

    assert status.mode == "historical"
    assert status.requested_date == "2024-01-06"
    assert status.rate_date == "2024-01-05"
    assert "no published fixing" in status.detail
    assert "weekend or holiday" in status.detail


def test_historical_failure_raises_instead_of_falling_back(fx_cache_dir, httpx_mock) -> None:
    """The frozen table is not the rate that applied on a past date."""
    httpx_mock.add_exception(httpx.ConnectError("offline"))

    with pytest.raises(fx.FxLiveUnavailableError):
        fx.historical_source("2024-01-02")

    assert fx.current_status().mode == "frozen"


@pytest.mark.parametrize(
    "bad_date",
    ["2024-13-01", "01-02-2024", "not-a-date", "1998-12-31", "2099-01-01"],
)
def test_historical_rejects_unusable_dates(fx_cache_dir, bad_date: str) -> None:
    with pytest.raises(ValueError):
        fx.historical_source(bad_date)


def test_activate_historical_requires_a_date() -> None:
    with pytest.raises(ValueError, match="requires a date"):
        fx.activate("historical")


def test_non_historical_modes_reject_a_date() -> None:
    with pytest.raises(ValueError, match="does not accept a date"):
        fx.activate("frozen", on_date="2024-01-02")


def test_historical_snapshot_round_trips_the_requested_date(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json={**HISTORICAL_JSON, "date": "2024-01-05"})
    fx.historical_source("2024-01-06")

    payload = json.loads(_snapshot_file(fx_cache_dir, "2024-01-06").read_text())
    assert payload["requested_date"] == "2024-01-06"
    assert payload["rate_date"] == "2024-01-05"

    reloaded = fx.historical_source("2024-01-06")
    assert reloaded.requested_date == "2024-01-06"
    assert reloaded.rate_date == "2024-01-05"


def test_activate_historical_switches_the_active_rates(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=HISTORICAL_JSON)
    before = fx.get_mid_rate("EUR", "USD")
    generation_before = fx.generation()

    fx.activate("historical", on_date="2024-01-02")

    assert fx.get_mid_rate("EUR", "USD") != before
    assert fx.generation() != generation_before
    assert fx.classification() is DataSource.VERIFIED
