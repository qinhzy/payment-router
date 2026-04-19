from __future__ import annotations

import asyncio
from decimal import Decimal
from time import perf_counter

import pytest

from payment_router.core.graph import NetworkEdge, PaymentGraph
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork


def _quote(
    network_name: str,
    fee_usd: str,
    time_hours: str,
    fx_rate: str = "1.0",
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
        self.calls: list[tuple[str, str, Decimal]] = []

    async def get_quote(
        self,
        amount: Decimal,
        from_cur: str,
        to_cur: str,
    ) -> NetworkQuote | None:
        self.calls.append((from_cur, to_cur, amount))
        result = self._quotes.get((from_cur, to_cur))
        if isinstance(result, Exception):
            raise result
        return result

    def supported_currencies(self) -> set[str]:
        return self._supported


class TimingNetwork(PaymentNetwork):
    def __init__(self, delay_seconds: float = 0.05) -> None:
        self._delay_seconds = delay_seconds
        self._started_at: list[float] = []

    async def get_quote(
        self,
        amount: Decimal,
        from_cur: str,
        to_cur: str,
    ) -> NetworkQuote | None:
        _ = (amount, from_cur, to_cur)
        self._started_at.append(perf_counter())
        await asyncio.sleep(self._delay_seconds)
        return None

    def supported_currencies(self) -> set[str]:
        return {"USD", "EUR", "GBP", "CNY"}


pytestmark = pytest.mark.anyio


async def test_single_network_builds_expected_edges() -> None:
    network = FakeNetwork(
        "fake-wire",
        {"USD", "EUR", "CNY"},
        {
            ("USD", "EUR"): _quote("fake-wire", "1.25", "2.0"),
            ("EUR", "CNY"): _quote("fake-wire", "2.50", "5.0", fx_rate="7.8"),
        },
    )
    graph = PaymentGraph(
        networks=[network],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("100"),
    )

    await graph.build()

    assert graph.edge_count() == 2
    assert graph.all_nodes() == {"USD", "EUR", "CNY"}
    edges = graph.get_edges("USD", "EUR")
    assert len(edges) == 1
    assert isinstance(edges[0], NetworkEdge)
    assert edges[0].amount_at_send == Decimal("100")


async def test_parallel_edges_are_preserved_in_multidigraph() -> None:
    network_a = FakeNetwork(
        "wise",
        {"USD", "CNY"},
        {("USD", "CNY"): _quote("wise", "5.00", "1.5", fx_rate="7.1")},
    )
    network_b = FakeNetwork(
        "swift",
        {"USD", "CNY"},
        {("USD", "CNY"): _quote("swift", "25.00", "54.0", fx_rate="6.9")},
    )
    graph = PaymentGraph(
        networks=[network_a, network_b],
        currencies=["USD", "CNY"],
        amount=Decimal("500"),
    )

    await graph.build()

    edges = graph.get_edges("USD", "CNY")
    assert len(edges) == 2
    assert {edge.network_name for edge in edges} == {"wise", "swift"}


async def test_none_quotes_are_skipped() -> None:
    network = FakeNetwork(
        "empty",
        {"USD", "CNY"},
        {("USD", "CNY"): None},
    )
    graph = PaymentGraph(
        networks=[network],
        currencies=["USD", "CNY"],
        amount=Decimal("250"),
    )

    await graph.build()

    assert graph.edge_count() == 0
    assert graph.get_edges("USD", "CNY") == []


async def test_provider_exceptions_are_recorded_without_stopping_build() -> None:
    network = FakeNetwork(
        "faulty",
        {"USD", "EUR", "CNY"},
        {
            ("USD", "CNY"): RuntimeError("quote failed"),
            ("USD", "EUR"): _quote("faulty", "2.25", "3.0"),
        },
    )
    graph = PaymentGraph(
        networks=[network],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("300"),
    )

    await graph.build()

    assert graph.edge_count() == 1
    assert len(graph._build_errors) == 1
    network_name, from_currency, to_currency, error = graph._build_errors[0]
    assert network_name == "faulty"
    assert (from_currency, to_currency) == ("USD", "CNY")
    assert isinstance(error, RuntimeError)


async def test_same_currency_self_loops_are_skipped() -> None:
    network = FakeNetwork(
        "loop-test",
        {"USD", "EUR"},
        {
            ("USD", "USD"): _quote("loop-test", "9.99", "1.0"),
            ("USD", "EUR"): _quote("loop-test", "1.00", "2.0", fx_rate="0.9"),
        },
    )
    graph = PaymentGraph(
        networks=[network],
        currencies=["USD", "EUR"],
        amount=Decimal("50"),
    )

    await graph.build()

    assert ("USD", "USD", Decimal("50")) not in network.calls
    assert not graph.graph.has_edge("USD", "USD")
    assert graph.edge_count() == 1


async def test_has_path_returns_true_for_two_hop_route() -> None:
    network = FakeNetwork(
        "bridge",
        {"USD", "EUR", "CNY"},
        {
            ("USD", "EUR"): _quote("bridge", "1.00", "1.0", fx_rate="0.92"),
            ("EUR", "CNY"): _quote("bridge", "2.00", "2.0", fx_rate="7.8"),
        },
    )
    graph = PaymentGraph(
        networks=[network],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("120"),
    )

    await graph.build()

    assert graph.has_path("USD", "CNY") is True


async def test_has_path_returns_false_for_disconnected_nodes() -> None:
    network = FakeNetwork(
        "partial",
        {"USD", "EUR"},
        {("USD", "EUR"): _quote("partial", "1.00", "1.0")},
    )
    graph = PaymentGraph(
        networks=[network],
        currencies=["USD", "EUR", "CNY"],
        amount=Decimal("120"),
    )

    await graph.build()

    assert graph.has_path("USD", "CNY") is False


async def test_build_runs_quotes_concurrently() -> None:
    network = TimingNetwork(delay_seconds=0.05)
    graph = PaymentGraph(
        networks=[network],
        currencies=["USD", "EUR", "GBP", "CNY"],
        amount=Decimal("10"),
    )

    started = perf_counter()
    await graph.build()
    elapsed = perf_counter() - started

    assert len(network._started_at) == 12
    assert elapsed < 0.2
    assert max(network._started_at) - min(network._started_at) < 0.1
