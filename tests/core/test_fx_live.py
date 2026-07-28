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
    "rates": {"CNY": 7.2, "EUR": 0.925, "GBP": 0.79, "HKD": 7.8, "SGD": 1.35},
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
    assert source.usd_rates["HKD"] == Decimal("1.0") / Decimal("7.8")
    assert source.usd_rates["SGD"] == Decimal("1.0") / Decimal("1.35")
    request = httpx_mock.get_requests()[0]
    assert request.url.params["symbols"] == "CNY,EUR,GBP,HKD,SGD"
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
        "usd_rates": {
            "USD": "1.0",
            "EUR": "1.07",
            "GBP": "1.25",
            "CNY": "0.139",
            "HKD": "0.128",
            "SGD": "0.74",
        },
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


def _live_source(rate_date: str, fetched_on: str) -> fx.RateSource:
    return fx.RateSource(
        mode="live",
        label="ECB reference rates (Frankfurter)",
        classification=DataSource.VERIFIED,
        usd_rates={code: Decimal("1.0") for code in fx.supported_currencies()},
        rate_date=rate_date,
        fetched_on=fetched_on,
    )


def test_refresh_keeps_live_rates_when_the_fetch_fails(fx_cache_dir, httpx_mock) -> None:
    """A refresh must never leave the source worse than it found it.

    Rates already active were published by ECB; the frozen teaching table is
    not a better answer than them just because a later fetch failed.
    """
    fx.configure(_live_source("2026-07-16", "2026-07-16"))
    httpx_mock.add_exception(httpx.ConnectError("offline"))

    status = fx.refresh_live()

    assert status.mode == "live"
    assert status.classification is DataSource.VERIFIED
    assert status.rate_date == "2026-07-16"
    assert status.fallback is False


def test_refresh_does_not_commit_an_older_publication(fx_cache_dir, httpx_mock) -> None:
    fx.configure(_live_source("2026-07-17", "2026-07-17"))
    httpx_mock.add_response(json={**FRANKFURTER_JSON, "date": "2026-07-10"})

    status = fx.refresh_live()

    assert status.rate_date == "2026-07-17"


def test_refresh_commits_a_newer_publication(fx_cache_dir, httpx_mock) -> None:
    fx.configure(_live_source("2026-07-16", "2026-07-16"))
    httpx_mock.add_response(json={**FRANKFURTER_JSON, "date": "2026-07-17"})

    status = fx.refresh_live()

    assert status.rate_date == "2026-07-17"
    assert status.classification is DataSource.VERIFIED
    _assert_consistent(fx._state)


def test_refresh_is_a_no_op_for_frozen_and_historical_sources(fx_cache_dir) -> None:
    fx.activate("frozen")

    status = fx.refresh_live()

    assert status.mode == "frozen"


def _assert_consistent(state) -> None:
    """The disclosure must describe the rates that are actually active."""
    assert state.status.mode == state.source.mode
    assert state.status.rate_date == state.source.rate_date
    assert state.status.classification is state.source.classification


def test_every_source_switch_leaves_rates_and_disclosure_consistent(
    fx_cache_dir,
    httpx_mock,
) -> None:
    fx.activate("frozen")
    _assert_consistent(fx._state)

    httpx_mock.add_response(json=FRANKFURTER_JSON)
    fx.activate("live")
    _assert_consistent(fx._state)

    fx.configure(_live_source("2026-07-19", "2026-07-19"))
    _assert_consistent(fx._state)


def test_live_fallback_leaves_rates_and_disclosure_consistent(
    fx_cache_dir,
    httpx_mock,
) -> None:
    httpx_mock.add_exception(httpx.ConnectError("offline"))

    status = fx.activate("live")

    assert status.fallback is True
    _assert_consistent(fx._state)


def test_a_concurrent_reader_never_sees_new_rates_with_the_old_disclosure(
    fx_cache_dir,
    monkeypatch,
) -> None:
    """The three pieces of FX state must move together.

    Assigning them one at a time let a reader on another thread pair rates
    that had already been swapped with the disclosure that still described
    the previous ones.
    """
    import threading
    import time

    fx.configure(_live_source("2026-07-16", "2026-07-16"))
    newer = fx.RateSource(
        mode="live",
        label="ECB reference rates (Frankfurter)",
        classification=DataSource.VERIFIED,
        usd_rates={code: Decimal("2.0") for code in fx.supported_currencies()},
        rate_date="2026-07-17",
        fetched_on="2026-07-17",
    )

    # Widen the window a scheduler would otherwise hit only rarely.
    real_status = fx.FxStatus

    def slow_status(*args, **kwargs):
        time.sleep(0.02)
        return real_status(*args, **kwargs)

    monkeypatch.setattr(fx, "FxStatus", slow_status)
    monkeypatch.setattr(fx, "live_source", lambda **_: newer)

    observed: list[tuple[str, str | None]] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            state = fx._state
            observed.append((str(state.source.usd_rates["EUR"]), state.status.rate_date))
            time.sleep(0.001)

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        time.sleep(0.03)
        fx.refresh_live()
        time.sleep(0.03)
    finally:
        stop.set()
        thread.join()

    consistent = {("1.0", "2026-07-16"), ("2.0", "2026-07-17")}
    torn = [pair for pair in set(observed) if pair not in consistent]
    assert torn == []
