from __future__ import annotations

from decimal import Decimal

import pytest

from payment_router.core.fx import get_mid_rate
from payment_router.core.graph import PaymentGraph
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork
from payment_router.router import PaymentRouter, RoutingPreference


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
        from_cur: str,
        to_cur: str,
    ) -> NetworkQuote | None:
        _ = amount
        result = self._quotes.get((from_cur, to_cur))
        if isinstance(result, Exception):
            raise result
        return result

    def supported_currencies(self) -> set[str]:
        return self._supported


async def _build_router(
    networks: list[PaymentNetwork],
    currencies: list[str],
    amount: Decimal,
) -> PaymentRouter:
    graph = PaymentGraph(networks=networks, currencies=currencies, amount=amount)
    await graph.build()
    return PaymentRouter(graph)


pytestmark = pytest.mark.anyio


async def test_cheapest_prefers_wise_direct_route() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "wise",
                {"GBP", "CNY"},
                {("GBP", "CNY"): _quote("Wise", "5", "1", "9.0", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "swift",
                {"GBP", "CNY"},
                {
                    ("GBP", "CNY"): _quote(
                        "SWIFT",
                        "60",
                        "54",
                        "8.7",
                    )
                },
            ),
        ],
        currencies=["GBP", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_cheapest("GBP", "CNY", Decimal("100"))

    assert route is not None
    assert len(route.hops) == 1
    assert route.hops[0].network_name == "Wise"


async def test_fastest_prefers_wise_direct_route() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "wise",
                {"GBP", "CNY"},
                {("GBP", "CNY"): _quote("Wise", "5", "1", "9.0", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "swift",
                {"GBP", "CNY"},
                {("GBP", "CNY"): _quote("SWIFT", "60", "54", "8.7")},
            ),
        ],
        currencies=["GBP", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_fastest("GBP", "CNY", Decimal("100"))

    assert route is not None
    assert route.hops[0].network_name == "Wise"


async def test_balanced_preference_still_picks_consistent_best_route() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "wise",
                {"GBP", "CNY"},
                {("GBP", "CNY"): _quote("Wise", "5", "1", "9.0", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "swift",
                {"GBP", "CNY"},
                {("GBP", "CNY"): _quote("SWIFT", "60", "54", "8.7")},
            ),
        ],
        currencies=["GBP", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_route(
        "GBP",
        "CNY",
        Decimal("100"),
        RoutingPreference(cost_weight=0.5, time_weight=0.5),
    )

    assert route is not None
    assert route.hops[0].network_name == "Wise"
    assert route.routing_preference is not None


async def test_same_currency_returns_zero_hop_route() -> None:
    router = await _build_router(
        networks=[],
        currencies=["USD"],
        amount=Decimal("25"),
    )

    route = router.find_route(
        "USD",
        "USD",
        Decimal("25"),
        RoutingPreference(cost_weight=0.5, time_weight=0.5),
    )

    assert route is not None
    assert route.hops == []
    assert route.total_fee_usd == Decimal("0")
    assert route.total_time_hours == Decimal("0")
    assert route.final_amount == Decimal("25")


async def test_disconnected_target_returns_none() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "bridge",
                {"USD", "EUR"},
                {("USD", "EUR"): _quote("Bridge", "2", "2", "0.9")},
            )
        ],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_route(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(cost_weight=0.5, time_weight=0.5),
    )

    assert route is None


async def test_max_hops_limit_blocks_longer_route() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "wise-hop-1",
                {"USD", "EUR"},
                {("USD", "EUR"): _quote("Wise EUR", "3", "1", "0.8", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "wise-hop-2",
                {"EUR", "CNY"},
                {("EUR", "CNY"): _quote("Wise CNY", "4", "1", "9.0", DataSource.VERIFIED)},
            ),
        ],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_route(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(cost_weight=1.0, time_weight=0.0, max_hops=1),
    )

    assert route is None


async def test_parallel_edges_choose_cheapest_option() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "wise",
                {"USD", "CNY"},
                {("USD", "CNY"): _quote("Wise", "5", "1", "7.0", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "alt",
                {"USD", "CNY"},
                {("USD", "CNY"): _quote("Alt", "20", "1", "7.0")},
            ),
        ],
        currencies=["USD", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_cheapest("USD", "CNY", Decimal("100"))

    assert route is not None
    assert route.hops[0].network_name == "Wise"


async def test_two_hop_route_is_found_when_no_direct_path_exists() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "hop-1",
                {"USD", "EUR"},
                {("USD", "EUR"): _quote("Hop 1", "3", "2", "0.8")},
            ),
            FakeNetwork(
                "hop-2",
                {"EUR", "CNY"},
                {("EUR", "CNY"): _quote("Hop 2", "4", "3", "9.0")},
            ),
        ],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_cheapest("USD", "CNY", Decimal("100"))

    assert route is not None
    assert [hop.network_name for hop in route.hops] == ["Hop 1", "Hop 2"]
    assert route.total_fee_usd == Decimal("7")
    assert route.total_time_hours == Decimal("5")


async def test_find_all_routes_returns_top_n_sorted_by_weight() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "direct",
                {"USD", "CNY"},
                {("USD", "CNY"): _quote("Direct", "10", "1", "7.0")},
            ),
            FakeNetwork(
                "eur-hop-1",
                {"USD", "EUR"},
                {("USD", "EUR"): _quote("USD->EUR", "3", "2", "0.8")},
            ),
            FakeNetwork(
                "eur-hop-2",
                {"EUR", "CNY"},
                {("EUR", "CNY"): _quote("EUR->CNY", "3", "2", "9.0")},
            ),
            FakeNetwork(
                "gbp-hop-1",
                {"USD", "GBP"},
                {("USD", "GBP"): _quote("USD->GBP", "4", "2", "0.7")},
            ),
            FakeNetwork(
                "gbp-hop-2",
                {"GBP", "CNY"},
                {("GBP", "CNY"): _quote("GBP->CNY", "4", "2", "10.0")},
            ),
        ],
        currencies=["USD", "EUR", "GBP", "CNY"],
        amount=Decimal("100"),
    )

    routes = router.find_all_routes(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(cost_weight=1.0, time_weight=0.0),
        top_n=3,
    )

    assert len(routes) == 3
    assert [route.total_fee_usd for route in routes] == [Decimal("6"), Decimal("8"), Decimal("10")]


def test_zero_total_weight_preference_is_rejected() -> None:
    with pytest.raises(ValueError):
        RoutingPreference(cost_weight=0.0, time_weight=0.0)


async def test_amount_zero_returns_none() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "wise",
                {"USD", "CNY"},
                {("USD", "CNY"): _quote("Wise", "5", "1", "7.0", DataSource.VERIFIED)},
            )
        ],
        currencies=["USD", "CNY"],
        amount=Decimal("0"),
    )

    route = router.find_cheapest("USD", "CNY", Decimal("0"))

    assert route is None


async def test_final_amount_accounts_for_fx_and_converted_fees() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "hop-1",
                {"GBP", "EUR"},
                {("GBP", "EUR"): _quote("GBP->EUR", "5", "1", "0.8")},
            ),
            FakeNetwork(
                "hop-2",
                {"EUR", "CNY"},
                {("EUR", "CNY"): _quote("EUR->CNY", "10", "1", "9.0")},
            ),
        ],
        currencies=["GBP", "EUR", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_cheapest("GBP", "CNY", Decimal("100"))
    expected = (Decimal("100") * Decimal("0.8") * Decimal("9.0")) - (
        Decimal("15") * get_mid_rate("USD", "CNY")
    )

    assert route is not None
    assert float(route.final_amount) == pytest.approx(float(expected))


async def test_normalization_prevents_single_dimension_from_dominating() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "fast-expensive",
                {"USD", "CNY"},
                {("USD", "CNY"): _quote("FastExpensive", "600", "1", "7.0")},
            ),
            FakeNetwork(
                "slow-cheap",
                {"USD", "CNY"},
                {("USD", "CNY"): _quote("SlowCheap", "10", "100", "7.0")},
            ),
        ],
        currencies=["USD", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_route(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(cost_weight=0.5, time_weight=0.5),
    )

    assert route is not None
    assert route.hops[0].network_name == "FastExpensive"
