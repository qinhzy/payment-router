from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
import pytest

from payment_router import comparison
from payment_router.core import fx
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.decision import DecisionProfile
from payment_router.networks.base import PaymentNetwork

JANUARY = {
    "amount": 1.0,
    "base": "USD",
    "date": "2024-01-02",
    "rates": {"CNY": 7.1, "EUR": 0.906, "GBP": 0.784, "HKD": 7.81, "SGD": 1.32},
}
JUNE = {**JANUARY, "date": "2024-06-03", "rates": {**JANUARY["rates"], "CNY": 7.6}}


@pytest.fixture
def fx_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(fx.CACHE_DIR_ENV_VAR, str(tmp_path))
    yield tmp_path
    fx.activate("frozen")


class ScenarioNetwork(PaymentNetwork):
    """Mirrors SWIFT/CIPS: the quoted rate derives from the active mid-rate.

    A stub with a hardcoded rate would be blind to the FX table and could not
    show any difference between two dates.
    """

    def __init__(self, name: str, fee_usd: str, time_hours: str, spread: str = "0.01") -> None:
        self._name = name
        self._fee_usd = Decimal(fee_usd)
        self._time_hours = Decimal(time_hours)
        self._spread = Decimal(spread)

    def display_name(self) -> str:
        return self._name

    def supported_currencies(self) -> set[str]:
        return {"USD", "CNY"}

    def get_quote(self, amount, source, target):
        if source == target:
            return None
        mid = fx.get_mid_rate(source, target)
        return NetworkQuote(
            network_name=self._name,
            fee_usd=self._fee_usd,
            time_hours=self._time_hours,
            fx_rate=mid * (Decimal("1") - self._spread),
            data_source=DataSource.ESTIMATED,
        )


class LiveQuotingNetwork(ScenarioNetwork):
    def quotes_at_request_time(self) -> bool:
        return True


def _scenario_networks():
    return [ScenarioNetwork("SWIFT", "20", "30")]


def _mixed_networks():
    return [LiveQuotingNetwork("Wise", "5", "1"), *_scenario_networks()]


def _compare(networks_factory, **kwargs):
    return asyncio.run(comparison.compare_dates("USD", "CNY", "1000", networks_factory, **kwargs))


def test_compare_two_historical_dates_reports_rate_movement(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=JUNE)  # baseline: --against
    httpx_mock.add_response(json=JANUARY)  # candidate: --on

    report = _compare(_scenario_networks, on_date="2024-01-02", against_date="2024-06-03")

    assert report.baseline.rate_date == "2024-06-03"
    assert report.candidate.rate_date == "2024-01-02"
    assert report.baseline.route is not None
    assert report.candidate.route is not None
    # USD buys fewer CNY in January than in June, so the recipient gets less.
    assert report.mid_rate_delta is not None
    assert report.mid_rate_delta < 0
    assert report.receive_delta is not None
    assert report.receive_delta < 0


def test_compare_keeps_fees_identical_because_only_fx_moves(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=JUNE)
    httpx_mock.add_response(json=JANUARY)

    report = _compare(_scenario_networks, on_date="2024-01-02", against_date="2024-06-03")

    assert report.fee_delta_usd == Decimal("0")
    assert report.time_delta_hours == Decimal("0")
    assert not report.route_changed


def test_compare_excludes_live_quoting_networks_and_says_so(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=JUNE)
    httpx_mock.add_response(json=JANUARY)

    report = _compare(_mixed_networks, on_date="2024-01-02", against_date="2024-06-03")

    # Both sides must see the same providers, or a provider-set difference
    # would show up in the deltas as if it were a rate effect.
    assert {hop.network_name for hop in report.candidate.route.hops} == {"SWIFT"}
    assert {hop.network_name for hop in report.baseline.route.hops} == {"SWIFT"}
    assert any("Excluded from both sides: Wise" in caveat for caveat in report.caveats)
    assert any("quote at request time" in caveat for caveat in report.caveats)


def test_live_baseline_drops_live_networks_to_stay_comparable(fx_cache_dir, httpx_mock) -> None:
    """A `latest` baseline is live mode, which would otherwise keep Wise."""
    httpx_mock.add_response(json=JUNE)  # baseline: latest
    httpx_mock.add_response(json=JANUARY)  # candidate: --on

    report = _compare(_mixed_networks, on_date="2024-01-02")

    assert report.baseline.label == "latest"
    assert {hop.network_name for hop in report.baseline.route.hops} == {"SWIFT"}
    assert {hop.network_name for hop in report.candidate.route.hops} == {"SWIFT"}
    assert report.fee_delta_usd == Decimal("0")
    assert not report.route_changed


def test_compare_always_states_that_only_fx_moved(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=JUNE)
    httpx_mock.add_response(json=JANUARY)

    report = _compare(_scenario_networks, on_date="2024-01-02", against_date="2024-06-03")

    assert "Only the FX table differs" in report.caveats[0]
    assert "not what a transfer actually cost" in report.caveats[0]


def test_compare_surfaces_a_weekend_resolution(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=JUNE)
    httpx_mock.add_response(json={**JANUARY, "date": "2024-01-05"})

    report = _compare(_scenario_networks, on_date="2024-01-06", against_date="2024-06-03")

    assert report.candidate.requested_date == "2024-01-06"
    assert report.candidate.rate_date == "2024-01-05"
    assert any("no published ECB fixing" in caveat for caveat in report.caveats)


def test_compare_restores_the_previously_active_source(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=JUNE)
    httpx_mock.add_response(json=JANUARY)
    before = fx.current_status()

    _compare(_scenario_networks, on_date="2024-01-02", against_date="2024-06-03")

    after = fx.current_status()
    assert after.mode == before.mode == "frozen"
    assert fx.classification() is DataSource.ESTIMATED


def test_compare_restores_the_source_even_when_a_fetch_fails(fx_cache_dir, httpx_mock) -> None:
    httpx_mock.add_response(json=JUNE)
    httpx_mock.add_exception(httpx.ConnectError("offline"))

    with pytest.raises(fx.FxLiveUnavailableError):
        _compare(_scenario_networks, on_date="2024-01-02", against_date="2024-06-03")

    assert fx.current_status().mode == "frozen"


def test_compare_honours_the_requested_profile(fx_cache_dir, httpx_mock) -> None:
    def networks():
        return [
            ScenarioNetwork("SlowCheap", "1", "60"),
            ScenarioNetwork("FastPricey", "40", "1"),
        ]

    httpx_mock.add_response(json=JUNE)
    httpx_mock.add_response(json=JANUARY)
    cheapest = _compare(
        networks,
        on_date="2024-01-02",
        against_date="2024-06-03",
        profile=DecisionProfile.CHEAPEST,
    )

    # Both dates are already cached by the first comparison, so no new fetches.
    fastest = _compare(
        networks,
        on_date="2024-01-02",
        against_date="2024-06-03",
        profile=DecisionProfile.FASTEST,
    )

    assert cheapest.candidate.route.hops[0].network_name == "SlowCheap"
    assert fastest.candidate.route.hops[0].network_name == "FastPricey"


def test_compare_rejects_a_future_date(fx_cache_dir) -> None:
    with pytest.raises(ValueError, match="future"):
        _compare(_scenario_networks, on_date="2099-01-01", against_date="2024-06-03")
