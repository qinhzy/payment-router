from __future__ import annotations

import asyncio
import inspect
from decimal import Decimal
from typing import Any

import networkx as nx
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork


@dataclass(config=ConfigDict(frozen=True))
class NetworkEdge:
    network_name: str
    from_currency: str
    to_currency: str
    fee_usd: Decimal
    time_hours: float
    fx_rate: Decimal
    data_source: DataSource
    amount_at_send: Decimal


class PaymentGraph:
    def __init__(
        self,
        networks: list[PaymentNetwork],
        currencies: list[str],
        amount: Decimal,
    ) -> None:
        self._networks = networks
        self._currencies = [currency.strip().upper() for currency in dict.fromkeys(currencies)]
        self._amount = amount
        self.graph = nx.MultiDiGraph()
        self.graph.add_nodes_from(self._currencies)
        self._build_errors: list[tuple[str, str, str, Exception]] = []

    async def build(self) -> None:
        self.graph = nx.MultiDiGraph()
        self.graph.add_nodes_from(self._currencies)
        self._build_errors = []

        tasks = [
            self._build_edge(network, from_currency, to_currency)
            for network in self._networks
            for from_currency in self._currencies
            for to_currency in self._currencies
            if from_currency != to_currency
        ]
        await asyncio.gather(*tasks)

    def get_edges(self, from_currency: str, to_currency: str) -> list[NetworkEdge]:
        source_currency = from_currency.strip().upper()
        target_currency = to_currency.strip().upper()

        edges: list[NetworkEdge] = []
        for _, edge_target, _, data in self.graph.edges(source_currency, data=True, keys=True):
            if edge_target != target_currency:
                continue

            edge = data.get("edge")
            if isinstance(edge, NetworkEdge):
                edges.append(edge)

        return edges

    def all_nodes(self) -> set[str]:
        return set(self.graph.nodes)

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def has_path(self, from_currency: str, to_currency: str) -> bool:
        source_currency = from_currency.strip().upper()
        target_currency = to_currency.strip().upper()

        if source_currency not in self.graph or target_currency not in self.graph:
            return False

        return nx.has_path(self.graph, source_currency, target_currency)

    async def _build_edge(
        self,
        network: PaymentNetwork,
        from_currency: str,
        to_currency: str,
    ) -> None:
        try:
            quote = await self._resolve_quote(network, from_currency, to_currency)
        except Exception as exc:
            self._build_errors.append(
                (self._network_label(network), from_currency, to_currency, exc)
            )
            return

        if quote is None:
            return

        edge = NetworkEdge(
            network_name=quote.network_name,
            from_currency=from_currency,
            to_currency=to_currency,
            fee_usd=quote.fee_usd,
            time_hours=float(quote.time_hours),
            fx_rate=quote.fx_rate,
            data_source=quote.data_source,
            amount_at_send=self._amount,
        )
        self.graph.add_edge(
            from_currency,
            to_currency,
            key=quote.network_name,
            edge=edge,
        )

    async def _resolve_quote(
        self,
        network: PaymentNetwork,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        result = network.get_quote(self._amount, from_currency, to_currency)
        if inspect.isawaitable(result):
            awaited_result = await result
            return self._validate_quote(awaited_result)
        return self._validate_quote(result)

    @staticmethod
    def _validate_quote(result: Any) -> NetworkQuote | None:
        if result is None:
            return None
        if isinstance(result, NetworkQuote):
            return result
        raise TypeError("Payment networks must return a NetworkQuote or None")

    @staticmethod
    def _network_label(network: PaymentNetwork) -> str:
        name = getattr(network, "_name", None)
        return str(name) if name else type(network).__name__
