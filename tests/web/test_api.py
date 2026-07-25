from __future__ import annotations

from fastapi.testclient import TestClient
from helpers import FakeNetwork, make_quote

from payment_router.core.models import DataSource
from payment_router.networks.base import PaymentNetwork
from payment_router.web.app import create_app


def _stub_networks() -> list[PaymentNetwork]:
    return [
        FakeNetwork(
            "Wise",
            {"USD", "EUR", "CNY"},
            {
                ("USD", "CNY"): make_quote("Wise", "5", "1", "7.0", DataSource.VERIFIED),
                ("USD", "EUR"): make_quote("Wise", "2", "1", "0.9", DataSource.VERIFIED),
                ("EUR", "CNY"): make_quote("Wise", "2", "1", "7.6", DataSource.VERIFIED),
            },
        ),
        FakeNetwork(
            "SEPA",
            {"EUR"},
            {
                ("EUR", "EUR"): make_quote("SEPA", "0.27", "24", "1.0"),
            },
        ),
        FakeNetwork(
            "SWIFT",
            {"USD", "CNY"},
            {
                ("USD", "CNY"): make_quote("SWIFT", "20", "30", "6.8"),
            },
        ),
        FakeNetwork(
            "CIPS",
            {"USD", "EUR", "GBP", "CNY", "HKD", "SGD"},
            {
                ("HKD", "CNY"): make_quote(
                    "CIPS",
                    "18.56",
                    "12",
                    "0.91",
                    time_min_hours="2",
                    time_max_hours="24",
                ),
            },
        ),
    ]


def _client(networks_factory=_stub_networks) -> TestClient:
    return TestClient(create_app(networks_factory=networks_factory))


def test_meta_reports_currencies_networks_and_profiles() -> None:
    response = _client().get("/api/meta")

    assert response.status_code == 200
    payload = response.json()
    assert payload["currencies"] == ["CNY", "EUR", "GBP", "HKD", "SGD", "USD"]
    assert [network["name"] for network in payload["networks"]] == [
        "Wise",
        "SEPA",
        "SWIFT",
        "CIPS",
    ]
    assert payload["profiles"] == ["cheapest", "fastest", "balanced"]
    assert payload["version"]
    assert "simulator" in payload["disclaimer"]
    assert payload["fx"]["mode"] == "frozen"
    assert payload["fx"]["classification"] == "ESTIMATED"
    assert payload["fx"]["fallback"] is False


def test_route_returns_single_route_with_amounts_and_mermaid() -> None:
    response = _client().get(
        "/api/route",
        params={"source": "USD", "target": "CNY", "amount": "100", "profile": "cheapest"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["source"] == "USD"
    assert len(payload["routes"]) == 1
    route = payload["routes"][0]
    assert route["path"] == ["USD", "CNY"]
    assert len(route["amounts"]) == len(route["path"])
    assert route["hops"][0]["network"] == "Wise"
    assert route["provenance"] == ["VERIFIED"]
    assert route["mermaid"].startswith("flowchart LR")
    assert payload["warnings"] == []


def test_route_top_n_returns_distinct_parallel_routes() -> None:
    response = _client().get(
        "/api/route",
        params={"source": "USD", "target": "CNY", "amount": "100", "top_n": 3},
    )

    assert response.status_code == 200
    routes = response.json()["routes"]
    assert len(routes) == 3
    signatures = {
        (tuple(route["path"]), tuple(hop["network"] for hop in route["hops"])) for route in routes
    }
    assert len(signatures) == 3


def test_route_same_currency_uses_self_loop_rail() -> None:
    response = _client().get(
        "/api/route",
        params={"source": "EUR", "target": "EUR", "amount": "50"},
    )

    assert response.status_code == 200
    route = response.json()["routes"][0]
    assert route["path"] == ["EUR", "EUR"]
    assert route["hops"][0]["network"] == "SEPA"


def test_route_supports_hkd_to_cny_cips_corridor_with_timing_bounds() -> None:
    response = _client().get(
        "/api/route",
        params={"source": "HKD", "target": "CNY", "amount": "10000"},
    )

    assert response.status_code == 200
    route = response.json()["routes"][0]
    assert route["path"] == ["HKD", "CNY"]
    assert route["hops"][0]["network"] == "CIPS"
    assert route["total_time_hours"] == "12.0"
    assert route["total_time_min_hours"] == "2.0"
    assert route["total_time_max_hours"] == "24.0"


def test_route_rejects_unsupported_currency() -> None:
    response = _client().get(
        "/api/route",
        params={"source": "USD", "target": "XYZ", "amount": "100"},
    )

    assert response.status_code == 400
    assert "Unsupported currency code(s): XYZ" in response.json()["detail"]


def test_route_rejects_invalid_amount() -> None:
    response = _client().get(
        "/api/route",
        params={"source": "USD", "target": "CNY", "amount": "NaN"},
    )

    assert response.status_code == 400
    assert "valid decimal number" in response.json()["detail"]


def test_route_returns_404_when_no_path_exists() -> None:
    def networks() -> list[PaymentNetwork]:
        return [
            FakeNetwork(
                "OneWay",
                {"USD", "CNY"},
                {("CNY", "USD"): make_quote("OneWay", "1", "1", "0.14")},
            )
        ]

    response = _client(networks).get(
        "/api/route",
        params={"source": "USD", "target": "CNY", "amount": "100"},
    )

    assert response.status_code == 404
    assert "No route found" in response.json()["detail"]


def test_route_surfaces_provider_warnings() -> None:
    def networks() -> list[PaymentNetwork]:
        return [
            *_stub_networks(),
            FakeNetwork(
                "Flaky",
                {"USD", "CNY"},
                {("USD", "CNY"): RuntimeError("provider exploded")},
            ),
        ]

    response = _client(networks).get(
        "/api/route",
        params={"source": "USD", "target": "CNY", "amount": "100"},
    )

    assert response.status_code == 200
    warnings = response.json()["warnings"]
    assert warnings == [{"network": "Flaky", "pair": "USD->CNY", "reason": "provider exploded"}]


def test_decide_returns_three_profiles_and_tradeoff() -> None:
    response = _client().get(
        "/api/decide",
        params={"source": "USD", "target": "CNY", "amount": "100"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [decision["profile"] for decision in payload["decisions"]] == [
        "cheapest",
        "fastest",
        "balanced",
    ]
    for decision in payload["decisions"]:
        assert decision["route"]["path"][0] == "USD"
        assert decision["evidence"]
    assert payload["tradeoff"] is not None
    assert "same_route_for_all_profiles" in payload["tradeoff"]


def test_sources_returns_provenance_registry() -> None:
    response = _client().get("/api/sources")

    assert response.status_code == 200
    records = response.json()["records"]
    evidence_ids = {record["evidence_id"] for record in records}
    assert "wise-live-quote" in evidence_ids
    assert "swift-model-parameters" in evidence_ids
    assert "cips-topology" in evidence_ids
    assert "cips-model-parameters" in evidence_ids
    classifications = {record["classification"] for record in records}
    assert {"VERIFIED", "ESTIMATED"} <= classifications


def test_console_index_is_served_at_root() -> None:
    response = _client().get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "payment-router" in response.text


class _CountingFactory:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> list[PaymentNetwork]:
        self.calls += 1
        return _stub_networks()


def test_route_reuses_cached_session_within_ttl() -> None:
    factory = _CountingFactory()
    client = TestClient(create_app(networks_factory=factory, quote_ttl_seconds=60.0))
    baseline = factory.calls  # create_app snapshots the networks once for /api/meta
    params = {"source": "USD", "target": "CNY", "amount": "100"}

    first = client.get("/api/route", params=params)
    second = client.get("/api/route", params={**params, "profile": "fastest", "top_n": 3})

    assert first.status_code == 200
    assert second.status_code == 200
    assert factory.calls == baseline + 1
    assert first.json()["quotes"]["from_cache"] is False
    assert second.json()["quotes"]["from_cache"] is True
    assert second.json()["quotes"]["quoted_at"] == first.json()["quotes"]["quoted_at"]


def test_route_reuses_cache_for_equivalent_amount_spellings() -> None:
    factory = _CountingFactory()
    client = TestClient(create_app(networks_factory=factory, quote_ttl_seconds=60.0))
    baseline = factory.calls

    client.get("/api/route", params={"source": "USD", "target": "CNY", "amount": "100"})
    second = client.get("/api/route", params={"source": "USD", "target": "CNY", "amount": " 100 "})

    assert factory.calls == baseline + 1
    assert second.json()["quotes"]["from_cache"] is True


def test_route_rebuilds_for_different_amount() -> None:
    factory = _CountingFactory()
    client = TestClient(create_app(networks_factory=factory, quote_ttl_seconds=60.0))
    baseline = factory.calls

    client.get("/api/route", params={"source": "USD", "target": "CNY", "amount": "100"})
    client.get("/api/route", params={"source": "USD", "target": "CNY", "amount": "250"})

    assert factory.calls == baseline + 2


def test_zero_ttl_disables_session_cache() -> None:
    factory = _CountingFactory()
    client = TestClient(create_app(networks_factory=factory, quote_ttl_seconds=0))
    baseline = factory.calls
    params = {"source": "USD", "target": "CNY", "amount": "100"}

    first = client.get("/api/route", params=params)
    second = client.get("/api/route", params=params)

    assert factory.calls == baseline + 2
    assert first.json()["quotes"]["from_cache"] is False
    assert second.json()["quotes"]["from_cache"] is False


def test_decide_shares_cache_with_route() -> None:
    factory = _CountingFactory()
    client = TestClient(create_app(networks_factory=factory, quote_ttl_seconds=60.0))
    baseline = factory.calls
    params = {"source": "USD", "target": "CNY", "amount": "100"}

    client.get("/api/route", params=params)
    decide = client.get("/api/decide", params=params)

    assert decide.status_code == 200
    assert factory.calls == baseline + 1
    assert decide.json()["quotes"]["from_cache"] is True


def test_sensitivity_returns_regions_and_stability() -> None:
    response = _client().get(
        "/api/sensitivity",
        params={"source": "USD", "target": "CNY", "amount": "100", "steps": 50},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["steps"] == 50
    assert len(payload["regions"]) >= 1
    first = payload["regions"][0]
    assert first["cost_weight_start"] == 0.0
    assert payload["regions"][-1]["cost_weight_end"] == 1.0
    route = first["route"]
    assert "total_time_min_hours" in route
    assert "total_time_max_hours" in route
    assert payload["balanced_region"] is not None
    assert isinstance(payload["caveats"], list)


def test_sensitivity_discovers_cips_for_hkd_to_cny() -> None:
    response = _client().get(
        "/api/sensitivity",
        params={"source": "HKD", "target": "CNY", "amount": "10000", "steps": 20},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["regions"]) == 1
    route = payload["regions"][0]["route"]
    assert [hop["network"] for hop in route["hops"]] == ["CIPS"]
    assert route["total_time_min_hours"] == "2.0"
    assert route["total_time_max_hours"] == "24.0"


def test_sensitivity_returns_404_when_no_route_exists() -> None:
    def networks() -> list[PaymentNetwork]:
        return [FakeNetwork("OneWay", {"USD", "CNY"}, {})]

    response = _client(networks).get(
        "/api/sensitivity",
        params={"source": "USD", "target": "CNY", "amount": "100"},
    )

    assert response.status_code == 404


def test_sensitivity_runs_off_the_event_loop(monkeypatch) -> None:
    """The sweep is CPU-bound; it must not block the serving event loop.

    The endpoint body and the sweep must therefore run on different threads.
    Comparing them (rather than checking for the main thread) is what makes
    this fail when the sweep is called inline.
    """
    import threading

    from payment_router import sensitivity as sensitivity_module
    from payment_router.web import app as app_module
    from payment_router.web import schemas as schemas_module

    recorded: dict[str, str] = {}
    analyze = sensitivity_module.analyze
    to_json = schemas_module.sensitivity_to_json

    def recording_analyze(*args, **kwargs):
        recorded["sweep"] = threading.current_thread().name
        return analyze(*args, **kwargs)

    def recording_to_json(*args, **kwargs):
        # Runs inline in the endpoint, i.e. on the event-loop thread.
        recorded["endpoint"] = threading.current_thread().name
        return to_json(*args, **kwargs)

    monkeypatch.setattr(app_module.sensitivity, "analyze", recording_analyze)
    monkeypatch.setattr(app_module.schemas, "sensitivity_to_json", recording_to_json)

    response = _client().get(
        "/api/sensitivity",
        params={"source": "USD", "target": "CNY", "amount": "1000", "steps": 10},
    )

    assert response.status_code == 200
    assert recorded["sweep"] != recorded["endpoint"]


def test_equivalent_amount_spellings_share_one_cached_session() -> None:
    factory = _CountingFactory()
    client = _client(factory)
    baseline = factory.calls

    for amount in ("1000", "1000.0", "1000.00"):
        response = client.get(
            "/api/route",
            params={"source": "USD", "target": "CNY", "amount": amount},
        )
        assert response.status_code == 200

    assert factory.calls - baseline == 1


def test_meta_reports_the_fx_source_at_request_time() -> None:
    """The FX disclosure is process state, not a startup snapshot."""
    from payment_router.core import fx as fx_module

    client = _client()
    assert client.get("/api/meta").json()["fx"]["mode"] == "frozen"

    try:
        fx_module.configure(
            fx_module.RateSource(
                mode="live",
                label="ECB reference rates (Frankfurter)",
                classification=DataSource.VERIFIED,
                usd_rates=dict(fx_module._FROZEN_RATES_TO_USD),
                rate_date="2026-07-24",
            )
        )
        payload = client.get("/api/meta").json()["fx"]
        assert payload["mode"] == "live"
        assert payload["rate_date"] == "2026-07-24"
        assert payload["classification"] == "VERIFIED"
    finally:
        fx_module.activate("frozen")


def _compare_client(monkeypatch, tmp_path):
    from payment_router.core import fx as fx_module

    monkeypatch.setenv(fx_module.CACHE_DIR_ENV_VAR, str(tmp_path))
    return _client(_rate_sensitive_networks)


def _rate_sensitive_networks() -> list[PaymentNetwork]:
    """Scenario rails whose quoted rate tracks the active FX table."""
    from decimal import Decimal

    from payment_router.core import fx as fx_module
    from payment_router.core.models import NetworkQuote

    class Scenario(PaymentNetwork):
        def display_name(self) -> str:
            return "SWIFT"

        def supported_currencies(self) -> set[str]:
            return {"USD", "CNY"}

        def get_quote(self, amount, source, target):
            if source == target:
                return None
            return NetworkQuote(
                network_name="SWIFT",
                fee_usd=Decimal("20"),
                time_hours=Decimal("30"),
                fx_rate=fx_module.get_mid_rate(source, target) * Decimal("0.99"),
                data_source=DataSource.ESTIMATED,
            )

    return [Scenario()]


def test_compare_returns_both_sides_and_deltas(monkeypatch, tmp_path, httpx_mock) -> None:
    from payment_router.core import fx as fx_module

    january = {
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-02",
        "rates": {"CNY": 7.1, "EUR": 0.906, "GBP": 0.784, "HKD": 7.81, "SGD": 1.32},
    }
    june = {**january, "date": "2024-06-03", "rates": {**january["rates"], "CNY": 7.6}}
    httpx_mock.add_response(json=june)
    httpx_mock.add_response(json=january)

    client = _compare_client(monkeypatch, tmp_path)
    try:
        response = client.get(
            "/api/compare",
            params={
                "source": "USD",
                "target": "CNY",
                "amount": "1000",
                "on": "2024-01-02",
                "against": "2024-06-03",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["baseline"]["rate_date"] == "2024-06-03"
        assert payload["candidate"]["rate_date"] == "2024-01-02"
        assert payload["deltas"]["fee_usd"] == "0"
        assert float(payload["deltas"]["receive"]) < 0
        assert payload["deltas"]["route_changed"] is False
        assert any("Only the FX table differs" in caveat for caveat in payload["caveats"])
    finally:
        fx_module.activate("frozen")


def test_compare_rejects_a_malformed_date(monkeypatch, tmp_path) -> None:
    client = _compare_client(monkeypatch, tmp_path)

    response = client.get(
        "/api/compare",
        params={"source": "USD", "target": "CNY", "amount": "1000", "on": "not-a-date"},
    )

    assert response.status_code == 400
    assert "YYYY-MM-DD" in response.json()["detail"]


def test_fx_refresh_skips_a_source_fetched_today(monkeypatch) -> None:
    import asyncio
    from dataclasses import replace as dc_replace

    from payment_router.core import fx as fx_module
    from payment_router.web import app as app_module

    today = __import__("datetime").datetime.now(__import__("datetime").UTC).date().isoformat()
    monkeypatch.setattr(
        fx_module,
        "_active_source",
        dc_replace(fx_module._frozen_source(), mode="live", fetched_on=today),
    )
    calls = []
    monkeypatch.setattr(fx_module, "activate", lambda *a, **k: calls.append(a))

    assert asyncio.run(app_module.refresh_live_fx_once()) is False
    assert calls == []


def test_fx_refresh_refetches_a_source_from_an_earlier_day(monkeypatch) -> None:
    import asyncio
    from dataclasses import replace as dc_replace

    from payment_router.core import fx as fx_module
    from payment_router.web import app as app_module

    monkeypatch.setattr(
        fx_module,
        "_active_source",
        dc_replace(fx_module._frozen_source(), mode="live", fetched_on="2020-01-01"),
    )
    calls = []
    monkeypatch.setattr(fx_module, "activate", lambda *a, **k: calls.append(a))

    assert asyncio.run(app_module.refresh_live_fx_once()) is True
    assert calls == [("live",)]


def test_fx_refresh_never_runs_for_frozen_or_historical_sources(monkeypatch) -> None:
    """Only a live source can be superseded by a later publication."""
    import asyncio
    from dataclasses import replace as dc_replace

    from payment_router.core import fx as fx_module
    from payment_router.web import app as app_module

    calls = []
    monkeypatch.setattr(fx_module, "activate", lambda *a, **k: calls.append(a))

    for mode in ("frozen", "historical"):
        monkeypatch.setattr(
            fx_module,
            "_active_source",
            dc_replace(fx_module._frozen_source(), mode=mode, fetched_on="2020-01-01"),
        )
        assert asyncio.run(app_module.refresh_live_fx_once()) is False

    assert calls == []


def test_fx_refresh_waits_for_an_in_flight_comparison(monkeypatch) -> None:
    """The refresher must not swap the source out from under a comparison."""
    import asyncio
    from dataclasses import replace as dc_replace

    from payment_router import comparison as comparison_module
    from payment_router.core import fx as fx_module
    from payment_router.web import app as app_module

    monkeypatch.setattr(
        fx_module,
        "_active_source",
        dc_replace(fx_module._frozen_source(), mode="live", fetched_on="2020-01-01"),
    )
    order: list[str] = []
    monkeypatch.setattr(fx_module, "activate", lambda *a, **k: order.append("refresh"))

    async def scenario() -> None:
        async with comparison_module.FX_SWITCH_LOCK:
            task = asyncio.create_task(app_module.refresh_live_fx_once())
            await asyncio.sleep(0)
            order.append("comparison-still-running")
            await asyncio.sleep(0)
        await task

    asyncio.run(scenario())

    assert order == ["comparison-still-running", "refresh"]
