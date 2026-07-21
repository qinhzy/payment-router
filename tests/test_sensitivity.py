from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from helpers import FakeNetwork, make_quote

from payment_router.core import fx
from payment_router.core.graph import PaymentGraph
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.sepa import SEPANetwork
from payment_router.networks.swift import SWIFTNetwork
from payment_router.router import PaymentRouter
from payment_router.sensitivity import analyze


def _router(networks) -> PaymentRouter:
    graph = PaymentGraph(
        networks=networks,
        currencies=["USD", "CNY"],
        amount=Decimal("1000"),
        amount_currency="USD",
    )
    asyncio.run(graph.build())
    return PaymentRouter(graph)


def _boundary_networks():
    # fx_rate equals the frozen mid rate, so spread cost is zero and the
    # normalized scores cross exactly at cost weight 0.5:
    #   slow-cheap:  0.5a + (1-a)      fast-pricey: a + 0.5(1-a)
    mid = fx.get_mid_rate("USD", "CNY")
    return [
        FakeNetwork(
            "SlowCheap",
            {"USD", "CNY"},
            {("USD", "CNY"): make_quote("SlowCheap", "10", "10", str(mid))},
        ),
        FakeNetwork(
            "FastPricey",
            {"USD", "CNY"},
            {("USD", "CNY"): make_quote("FastPricey", "20", "5", str(mid))},
        ),
    ]


def test_weight_sweep_finds_the_flip_boundary() -> None:
    report = analyze(_router(_boundary_networks()), "USD", "CNY", Decimal("1000"), steps=100)

    assert len(report.regions) == 2
    first, second = report.regions
    assert first.signature[1] == ("FastPricey",)
    assert second.signature[1] == ("SlowCheap",)
    assert first.cost_weight_start == 0.0
    assert second.cost_weight_end == 1.0
    # The crossover sits at 0.5; allow one grid step of slack for the tie.
    assert 0.49 <= first.cost_weight_end <= 0.51
    assert 0.49 <= second.cost_weight_start <= 0.51
    assert report.balanced_region is not None


def test_single_winner_yields_one_full_region() -> None:
    networks = [_boundary_networks()[0]]
    report = analyze(_router(networks), "USD", "CNY", Decimal("1000"), steps=50)

    assert len(report.regions) == 1
    assert report.regions[0].cost_weight_start == 0.0
    assert report.regions[0].cost_weight_end == 1.0
    assert report.balanced_region is report.regions[0]


def test_no_route_returns_empty_report() -> None:
    networks = [FakeNetwork("OneWay", {"USD", "CNY"}, {})]
    report = analyze(_router(networks), "USD", "CNY", Decimal("1000"), steps=20)

    assert report.regions == ()
    assert report.balanced_region is None


def test_rejects_non_positive_steps() -> None:
    with pytest.raises(ValueError, match="steps"):
        analyze(_router(_boundary_networks()), "USD", "CNY", Decimal("1000"), steps=0)


def test_later_live_hop_and_estimated_band_caveats() -> None:
    mid_usd_cny = fx.get_mid_rate("USD", "CNY")
    networks = [
        FakeNetwork(
            "LiveTimed",
            {"USD", "EUR", "CNY"},
            {
                ("USD", "EUR"): NetworkQuote(
                    network_name="LiveTimed",
                    fee_usd=Decimal("1"),
                    time_hours=Decimal("1"),
                    fx_rate=fx.get_mid_rate("USD", "EUR"),
                    data_source=DataSource.VERIFIED,
                ),
                ("EUR", "CNY"): NetworkQuote(
                    network_name="LiveTimed",
                    fee_usd=Decimal("1"),
                    time_hours=Decimal("1"),
                    fx_rate=fx.get_mid_rate("EUR", "CNY"),
                    data_source=DataSource.VERIFIED,
                ),
            },
        ),
        FakeNetwork(
            "Scenario",
            {"USD", "CNY"},
            {
                ("USD", "CNY"): make_quote(
                    "Scenario", "1", "54", str(mid_usd_cny), DataSource.ESTIMATED
                )
            },
        ),
    ]
    graph = PaymentGraph(
        networks=networks,
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("1000"),
        amount_currency="USD",
    )
    asyncio.run(graph.build())
    report = analyze(PaymentRouter(graph), "USD", "CNY", Decimal("1000"), steps=40)

    assert any("assumes" in caveat and "hop 2" in caveat for caveat in report.caveats)
    assert any("scenario-estimated" in caveat for caveat in report.caveats)


def test_swift_quote_carries_per_hop_timing_band() -> None:
    quote = asyncio.run(SWIFTNetwork().get_quote(Decimal("1000"), "USD", "CNY"))

    assert quote is not None
    assert quote.time_hours == Decimal("54")  # 3 hops x 18h
    assert quote.time_min_hours == Decimal("18")  # 3 hops x 6h
    assert quote.time_max_hours == Decimal("144")  # 3 hops x 48h


def test_sepa_quote_bounds_reflect_scheme_maximum_semantics() -> None:
    quote = asyncio.run(SEPANetwork().get_quote(Decimal("1000"), "EUR", "EUR"))

    assert quote is not None
    assert quote.time_min_hours == Decimal("0")
    assert quote.time_max_hours == quote.time_hours == Decimal("24.0")


def test_quote_bounds_default_to_point_estimate_and_validate() -> None:
    quote = make_quote("Point", "1", "5", "1.0")
    assert quote.time_min_hours == quote.time_max_hours == Decimal("5")

    with pytest.raises(ValueError, match="time bounds"):
        NetworkQuote(
            network_name="Bad",
            fee_usd=Decimal("1"),
            time_hours=Decimal("5"),
            time_min_hours=Decimal("6"),
            fx_rate=Decimal("1"),
            data_source=DataSource.ESTIMATED,
        )


def test_route_totals_aggregate_hop_bounds() -> None:
    networks = [
        FakeNetwork(
            "Banded",
            {"USD", "CNY"},
            {
                ("USD", "CNY"): NetworkQuote(
                    network_name="Banded",
                    fee_usd=Decimal("1"),
                    time_hours=Decimal("10"),
                    time_min_hours=Decimal("4"),
                    time_max_hours=Decimal("20"),
                    fx_rate=fx.get_mid_rate("USD", "CNY"),
                    data_source=DataSource.ESTIMATED,
                ),
            },
        )
    ]
    router = _router(networks)
    route = router.find_cheapest("USD", "CNY", Decimal("1000"))

    assert route is not None
    assert route.total_time_min_hours == Decimal("4")
    assert route.total_time_max_hours == Decimal("20")
