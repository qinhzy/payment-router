from __future__ import annotations

from decimal import Decimal

import pytest
from helpers import FakeNetwork, make_quote

from payment_router.core.fx import get_mid_rate
from payment_router.core.graph import PaymentGraph
from payment_router.core.models import DataSource
from payment_router.networks.base import PaymentNetwork
from payment_router.router import PaymentRouter, RoutingPreference


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
                {("GBP", "CNY"): make_quote("Wise", "5", "1", "9.0", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "swift",
                {"GBP", "CNY"},
                {
                    ("GBP", "CNY"): make_quote(
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
                {("GBP", "CNY"): make_quote("Wise", "5", "1", "9.0", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "swift",
                {"GBP", "CNY"},
                {("GBP", "CNY"): make_quote("SWIFT", "60", "54", "8.7")},
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
                {("GBP", "CNY"): make_quote("Wise", "5", "1", "9.0", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "swift",
                {"GBP", "CNY"},
                {("GBP", "CNY"): make_quote("SWIFT", "60", "54", "8.7")},
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


async def test_same_currency_routes_compare_parallel_payment_rails() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "standard",
                {"EUR"},
                {("EUR", "EUR"): make_quote("SEPA", "0.27", "24", "1.0")},
            ),
            FakeNetwork(
                "instant",
                {"EUR"},
                {("EUR", "EUR"): make_quote("SEPA Instant", "0.54", "0.003", "1.0")},
            ),
        ],
        currencies=["EUR"],
        amount=Decimal("100"),
    )

    cheapest = router.find_cheapest("EUR", "EUR", Decimal("100"))
    fastest = router.find_fastest("EUR", "EUR", Decimal("100"))
    routes = router.find_all_routes(
        "EUR",
        "EUR",
        Decimal("100"),
        RoutingPreference(cost_weight=0.5, time_weight=0.5),
        top_n=2,
    )

    assert cheapest is not None
    assert fastest is not None
    assert cheapest.hops[0].network_name == "SEPA"
    assert fastest.hops[0].network_name == "SEPA Instant"
    assert {route.hops[0].network_name for route in routes} == {"SEPA", "SEPA Instant"}


async def test_disconnected_target_returns_none() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "bridge",
                {"USD", "EUR"},
                {("USD", "EUR"): make_quote("Bridge", "2", "2", "0.9")},
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


async def test_find_all_routes_returns_empty_for_disconnected_target() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "bridge",
                {"USD", "EUR"},
                {("USD", "EUR"): make_quote("Bridge", "2", "2", "0.9")},
            )
        ],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("100"),
    )

    routes = router.find_all_routes(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(cost_weight=0.5, time_weight=0.5),
    )

    assert routes == []


async def test_max_hops_limit_blocks_longer_route() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "wise-hop-1",
                {"USD", "EUR"},
                {("USD", "EUR"): make_quote("Wise EUR", "3", "1", "0.8", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "wise-hop-2",
                {"EUR", "CNY"},
                {("EUR", "CNY"): make_quote("Wise CNY", "4", "1", "9.0", DataSource.VERIFIED)},
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
                {("USD", "CNY"): make_quote("Wise", "5", "1", "7.0", DataSource.VERIFIED)},
            ),
            FakeNetwork(
                "alt",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("Alt", "20", "1", "7.0")},
            ),
        ],
        currencies=["USD", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_cheapest("USD", "CNY", Decimal("100"))

    assert route is not None
    assert route.hops[0].network_name == "Wise"


async def test_find_all_routes_preserves_parallel_network_options() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "wise",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("Wise", "5", "1", "7.0")},
            ),
            FakeNetwork(
                "swift",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("SWIFT", "20", "30", "6.8")},
            ),
        ],
        currencies=["USD", "CNY"],
        amount=Decimal("100"),
    )

    routes = router.find_all_routes(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(cost_weight=0.5, time_weight=0.5),
        top_n=2,
    )

    assert [route.hops[0].network_name for route in routes] == ["Wise", "SWIFT"]


async def test_two_hop_route_is_found_when_no_direct_path_exists() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "hop-1",
                {"USD", "EUR"},
                {("USD", "EUR"): make_quote("Hop 1", "3", "2", "0.8")},
            ),
            FakeNetwork(
                "hop-2",
                {"EUR", "CNY"},
                {("EUR", "CNY"): make_quote("Hop 2", "4", "3", "9.0")},
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


async def test_find_all_routes_returns_top_n_sorted_by_all_in_cost() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "direct",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("Direct", "10", "1", "7.0")},
            ),
            FakeNetwork(
                "eur-hop-1",
                {"USD", "EUR"},
                {("USD", "EUR"): make_quote("USD->EUR", "3", "2", "0.8")},
            ),
            FakeNetwork(
                "eur-hop-2",
                {"EUR", "CNY"},
                {("EUR", "CNY"): make_quote("EUR->CNY", "3", "2", "9.0")},
            ),
            FakeNetwork(
                "gbp-hop-1",
                {"USD", "GBP"},
                {("USD", "GBP"): make_quote("USD->GBP", "4", "2", "0.7")},
            ),
            FakeNetwork(
                "gbp-hop-2",
                {"GBP", "CNY"},
                {("GBP", "CNY"): make_quote("GBP->CNY", "4", "2", "10.0")},
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
    assert [route.total_fee_usd for route in routes] == [Decimal("10"), Decimal("8"), Decimal("6")]


def test_zero_total_weight_preference_is_rejected() -> None:
    with pytest.raises(ValueError):
        RoutingPreference(cost_weight=0.0, time_weight=0.0)


@pytest.mark.parametrize(
    ("field", "value"),
    [("cost_weight", -0.1), ("time_weight", -0.1), ("max_hops", 0)],
)
def test_invalid_preference_values_are_rejected(field: str, value: float) -> None:
    with pytest.raises(ValueError):
        RoutingPreference(**{field: value})


async def test_amount_zero_returns_none() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "wise",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("Wise", "5", "1", "7.0", DataSource.VERIFIED)},
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
                {("GBP", "EUR"): make_quote("GBP->EUR", "5", "1", "0.8")},
            ),
            FakeNetwork(
                "hop-2",
                {"EUR", "CNY"},
                {("EUR", "CNY"): make_quote("EUR->CNY", "10", "1", "9.0")},
            ),
        ],
        currencies=["GBP", "EUR", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_cheapest("GBP", "CNY", Decimal("100"))
    expected = (
        (Decimal("100") - (Decimal("5") * get_mid_rate("USD", "GBP"))) * Decimal("0.8")
        - (Decimal("10") * get_mid_rate("USD", "EUR"))
    ) * Decimal("9.0")

    assert route is not None
    assert float(route.final_amount) == pytest.approx(float(expected))


async def test_router_falls_back_when_best_static_path_cannot_cover_its_fee() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "unusable-direct",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("Unusable", "101", "1", "7.0")},
            ),
            FakeNetwork(
                "hop-1",
                {"USD", "EUR"},
                {("USD", "EUR"): make_quote("Hop 1", "1", "2", "0.8")},
            ),
            FakeNetwork(
                "hop-2",
                {"EUR", "CNY"},
                {("EUR", "CNY"): make_quote("Hop 2", "1", "2", "9.0")},
            ),
        ],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_fastest("USD", "CNY", Decimal("100"))

    assert route is not None
    assert [hop.network_name for hop in route.hops] == ["Hop 1", "Hop 2"]
    assert route.final_amount > 0


async def test_find_all_routes_excludes_routes_that_cannot_pay_fixed_fees() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "unusable",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("Unusable", "100", "1", "7.0")},
            ),
            FakeNetwork(
                "usable",
                {"USD", "EUR", "CNY"},
                {
                    ("USD", "EUR"): make_quote("USD->EUR", "1", "2", "0.8"),
                    ("EUR", "CNY"): make_quote("EUR->CNY", "1", "2", "9.0"),
                },
            ),
        ],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("100"),
    )

    routes = router.find_all_routes(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(cost_weight=0.0, time_weight=1.0),
        top_n=3,
    )

    assert len(routes) == 1
    assert routes[0].final_amount > 0


async def test_cheapest_includes_fx_spread_in_all_in_cost() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "zero-fee-poor-rate",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("Poor rate", "0", "1", "5.0")},
            ),
            FakeNetwork(
                "fee-good-rate",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("Good rate", "3", "1", "7.0")},
            ),
        ],
        currencies=["USD", "CNY"],
        amount=Decimal("100"),
    )

    route = router.find_cheapest("USD", "CNY", Decimal("100"))

    assert route is not None
    assert route.hops[0].network_name == "Good rate"


async def test_normalization_prevents_single_dimension_from_dominating() -> None:
    router = await _build_router(
        networks=[
            FakeNetwork(
                "fast-expensive",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("FastExpensive", "600", "1", "7.0")},
            ),
            FakeNetwork(
                "slow-cheap",
                {"USD", "CNY"},
                {("USD", "CNY"): make_quote("SlowCheap", "10", "100", "7.0")},
            ),
        ],
        currencies=["USD", "CNY"],
        amount=Decimal("1000"),
    )

    route = router.find_route(
        "USD",
        "CNY",
        Decimal("1000"),
        RoutingPreference(cost_weight=0.5, time_weight=0.5),
    )

    assert route is not None
    assert route.hops[0].network_name == "FastExpensive"


async def _dense_router(currencies: list[str], fee: str) -> PaymentRouter:
    """A fully connected corridor set: every pair quoted by three networks."""
    quotes = {
        (source, target): make_quote(f"{source}{target}", fee, "2", "1.0")
        for source in currencies
        for target in currencies
        if source != target
    }
    networks = [FakeNetwork(f"net-{index}", set(currencies), quotes) for index in range(3)]
    return await _build_router(
        networks=networks,
        currencies=currencies,
        amount=Decimal("1000"),
    )


async def test_top_n_stops_after_the_candidate_budget() -> None:
    # Fees exceed the amount, so no candidate is fundable and the search can
    # never reach top_n. Without a budget it would enumerate every simple path.
    router = await _dense_router(["USD", "EUR", "GBP", "CNY"], fee="500")

    routes = router.find_all_routes(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(),
        top_n=5,
        max_candidate_paths=1,
    )

    assert routes == []


async def test_candidate_budget_does_not_truncate_healthy_corridors() -> None:
    router = await _dense_router(["USD", "EUR", "GBP", "CNY"], fee="1")

    bounded = router.find_all_routes(
        "USD",
        "CNY",
        Decimal("1000"),
        RoutingPreference(),
        top_n=3,
    )
    unbounded = router.find_all_routes(
        "USD",
        "CNY",
        Decimal("1000"),
        RoutingPreference(),
        top_n=3,
        max_candidate_paths=10_000,
    )

    assert len(bounded) == 3
    assert [hop.network_name for route in bounded for hop in route.hops] == [
        hop.network_name for route in unbounded for hop in route.hops
    ]


async def test_candidate_budget_keeps_the_best_ranked_routes_it_found() -> None:
    # Only the direct USD->CNY hop is fundable; the budget must not disturb it.
    router = await _build_router(
        networks=[
            FakeNetwork(
                "cheap-direct",
                {"USD", "EUR", "CNY"},
                {
                    ("USD", "CNY"): make_quote("CheapDirect", "1", "5", "7.0"),
                    ("USD", "EUR"): make_quote("Pricey", "80", "1", "0.9"),
                    ("EUR", "CNY"): make_quote("Pricey", "80", "1", "7.6"),
                },
            ),
        ],
        currencies=["USD", "EUR", "GBP", "CNY"],
        amount=Decimal("100"),
    )

    routes = router.find_all_routes(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(),
        top_n=5,
    )

    assert [hop.network_name for route in routes for hop in route.hops] == ["CheapDirect"]


async def test_candidate_budget_must_be_positive() -> None:
    router = await _dense_router(["USD", "CNY"], fee="1")

    with pytest.raises(ValueError, match="max_candidate_paths"):
        router.find_all_routes(
            "USD",
            "CNY",
            Decimal("1000"),
            RoutingPreference(),
            max_candidate_paths=0,
        )


async def test_unfundable_corridor_does_not_enumerate_every_simple_path(monkeypatch) -> None:
    """The regression guard for the top-N enumeration blow-up.

    A dense corridor set whose candidates are all unfundable used to walk
    ``shortest_simple_paths`` to exhaustion, which grows combinatorially with
    the number of currencies.
    """
    import networkx as nx

    from payment_router import router as router_module

    yielded = 0
    original = nx.shortest_simple_paths

    def counting_shortest_simple_paths(*args, **kwargs):
        nonlocal yielded
        for path in original(*args, **kwargs):
            yielded += 1
            yield path

    monkeypatch.setattr(
        router_module.nx,
        "shortest_simple_paths",
        counting_shortest_simple_paths,
    )

    router = await _dense_router(["USD", "EUR", "GBP", "CNY"], fee="500")
    routes = router.find_all_routes(
        "USD",
        "CNY",
        Decimal("100"),
        RoutingPreference(),
        top_n=5,
        max_candidate_paths=25,
    )

    assert routes == []
    assert yielded == 25


async def test_edge_stats_are_cached_across_preferences() -> None:
    router = await _dense_router(["USD", "EUR", "CNY"], fee="1")
    preference = RoutingPreference()

    first = router._build_score_context(preference)
    cached = router._edge_stats_cache
    second = router._build_score_context(RoutingPreference(cost_weight=1.0, time_weight=0.0))

    assert cached is not None
    assert router._edge_stats_cache is cached
    assert (second.max_cost, second.max_time) == (first.max_cost, first.max_time)


async def test_edge_stats_recompute_when_the_fx_source_changes() -> None:
    from payment_router.core import fx as fx_module

    router = await _dense_router(["USD", "EUR", "CNY"], fee="1")
    before = router._build_score_context(RoutingPreference())
    generation_before = router._edge_stats_cache[1]

    doubled = {code: rate * 2 for code, rate in fx_module._FROZEN_RATES_TO_USD.items()}
    doubled["USD"] = Decimal("1.0")
    try:
        fx_module.configure(
            fx_module.RateSource(
                mode="frozen",
                label="doubled test table",
                classification=DataSource.ESTIMATED,
                usd_rates=doubled,
            )
        )
        after = router._build_score_context(RoutingPreference())
        assert router._edge_stats_cache[1] != generation_before
        assert after.max_cost != before.max_cost
    finally:
        fx_module.activate("frozen")
