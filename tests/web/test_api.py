from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork
from payment_router.web.app import create_app


def _quote(
    network_name: str,
    fee_usd: str,
    time_hours: str,
    fx_rate: str,
    data_source: DataSource = DataSource.INDUSTRY_AVERAGE,
) -> NetworkQuote:
    return NetworkQuote(
        network_name=network_name,
        fee_usd=Decimal(fee_usd),
        time_hours=Decimal(time_hours),
        fx_rate=Decimal(fx_rate),
        data_source=data_source,
    )


class FakeNetwork(PaymentNetwork):
    def __init__(
        self,
        name: str,
        supported: set[str],
        quotes: dict[tuple[str, str], NetworkQuote | None | Exception],
    ) -> None:
        self._name = name
        self._supported = supported
        self._quotes = quotes

    async def get_quote(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        _ = amount
        result = self._quotes.get((from_currency, to_currency))
        if isinstance(result, Exception):
            raise result
        return result

    def supported_currencies(self) -> set[str]:
        return self._supported


def _stub_networks() -> list[PaymentNetwork]:
    return [
        FakeNetwork(
            "Wise",
            {"USD", "EUR", "CNY"},
            {
                ("USD", "CNY"): _quote("Wise", "5", "1", "7.0", DataSource.VERIFIED),
                ("USD", "EUR"): _quote("Wise", "2", "1", "0.9", DataSource.VERIFIED),
                ("EUR", "CNY"): _quote("Wise", "2", "1", "7.6", DataSource.VERIFIED),
            },
        ),
        FakeNetwork(
            "SEPA",
            {"EUR"},
            {
                ("EUR", "EUR"): _quote("SEPA", "0.27", "24", "1.0"),
            },
        ),
        FakeNetwork(
            "SWIFT",
            {"USD", "CNY"},
            {
                ("USD", "CNY"): _quote("SWIFT", "20", "30", "6.8"),
            },
        ),
    ]


def _client(networks_factory=_stub_networks) -> TestClient:
    return TestClient(create_app(networks_factory=networks_factory))


def test_meta_reports_currencies_networks_and_profiles() -> None:
    response = _client().get("/api/meta")

    assert response.status_code == 200
    payload = response.json()
    assert payload["currencies"] == ["CNY", "EUR", "USD"]
    assert [network["name"] for network in payload["networks"]] == ["Wise", "SEPA", "SWIFT"]
    assert payload["profiles"] == ["cheapest", "fastest", "balanced"]
    assert payload["version"]
    assert "simulator" in payload["disclaimer"]


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
                {("CNY", "USD"): _quote("OneWay", "1", "1", "0.14")},
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
    params = {"source": "USD", "target": "CNY", "amount": "100"}

    first = client.get("/api/route", params=params)
    second = client.get("/api/route", params={**params, "profile": "fastest", "top_n": 3})

    assert first.status_code == 200
    assert second.status_code == 200
    assert factory.calls == 1
    assert first.json()["quotes"]["from_cache"] is False
    assert second.json()["quotes"]["from_cache"] is True
    assert second.json()["quotes"]["quoted_at"] == first.json()["quotes"]["quoted_at"]


def test_route_rebuilds_for_different_amount() -> None:
    factory = _CountingFactory()
    client = TestClient(create_app(networks_factory=factory, quote_ttl_seconds=60.0))

    client.get("/api/route", params={"source": "USD", "target": "CNY", "amount": "100"})
    client.get("/api/route", params={"source": "USD", "target": "CNY", "amount": "250"})

    assert factory.calls == 2


def test_zero_ttl_disables_session_cache() -> None:
    factory = _CountingFactory()
    client = TestClient(create_app(networks_factory=factory, quote_ttl_seconds=0))
    params = {"source": "USD", "target": "CNY", "amount": "100"}

    first = client.get("/api/route", params=params)
    second = client.get("/api/route", params=params)

    assert factory.calls == 2
    assert first.json()["quotes"]["from_cache"] is False
    assert second.json()["quotes"]["from_cache"] is False


def test_decide_shares_cache_with_route() -> None:
    factory = _CountingFactory()
    client = TestClient(create_app(networks_factory=factory, quote_ttl_seconds=60.0))
    params = {"source": "USD", "target": "CNY", "amount": "100"}

    client.get("/api/route", params=params)
    decide = client.get("/api/decide", params=params)

    assert decide.status_code == 200
    assert factory.calls == 1
    assert decide.json()["quotes"]["from_cache"] is True
