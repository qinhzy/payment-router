from __future__ import annotations

import asyncio
import inspect
import math
from decimal import Decimal
from typing import Any

import networkx as nx
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from payment_router.core import fx
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork


@dataclass(config=ConfigDict(frozen=True))
class NetworkEdge:
    network_name: str
    from_currency: str
    to_currency: str
    fee_usd: Decimal
    time_hours: Decimal
    time_min_hours: Decimal
    time_max_hours: Decimal
    fx_rate: Decimal
    data_source: DataSource
    fee_data_source: DataSource
    time_data_source: DataSource
    fx_data_source: DataSource
    amount_at_send: Decimal


class PaymentGraph:
    def __init__(
        self,
        networks: list[PaymentNetwork],
        currencies: list[str],
        amount: Decimal,
        amount_currency: str | None = None,
        quote_timeout_seconds: float = 10.0,
    ) -> None:
        self._networks = networks
        self._currencies = list(dict.fromkeys(currency.strip().upper() for currency in currencies))
        if not self._currencies:
            raise ValueError("currencies cannot be empty")
        unsupported_currencies = set(self._currencies) - fx.supported_currencies()
        if unsupported_currencies:
            unsupported = ", ".join(sorted(unsupported_currencies))
            raise fx.UnsupportedCurrencyError(f"Unsupported currencies: {unsupported}")
        if not amount.is_finite() or amount < 0:
            raise ValueError("amount must be a non-negative finite decimal")
        self._amount = amount
        self._amount_currency = (amount_currency or self._currencies[0]).strip().upper()
        if self._amount_currency not in self._currencies:
            raise ValueError("amount_currency must be included in currencies")
        if not math.isfinite(quote_timeout_seconds) or quote_timeout_seconds <= 0:
            raise ValueError("quote_timeout_seconds must be a positive finite number")
        self._quote_timeout_seconds = quote_timeout_seconds
        self.graph = nx.MultiDiGraph()
        self.graph.add_nodes_from(self._currencies)
        self._build_errors: list[tuple[str, str, str, Exception]] = []

    async def build(self) -> None:
        self.graph = nx.MultiDiGraph()
        self.graph.add_nodes_from(self._currencies)
        self._build_errors = []

        tasks = []
        for network in self._networks:
            try:
                supported = {
                    currency.strip().upper() for currency in network.supported_currencies()
                }
            except Exception as exc:
                self._build_errors.append((self._network_label(network), "*", "*", exc))
                continue
            tasks.extend(
                self._build_edge(network, from_currency, to_currency)
                for from_currency in self._currencies
                for to_currency in self._currencies
                if from_currency in supported and to_currency in supported
            )
        await asyncio.gather(*tasks)
        self._build_errors.sort(
            key=lambda item: (item[0], item[1], item[2], type(item[3]).__name__, str(item[3]))
        )

    @property
    def build_errors(self) -> tuple[tuple[str, str, str, Exception], ...]:
        """Provider failures captured during the most recent graph build."""
        return tuple(self._build_errors)

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

        return sorted(
            edges,
            key=lambda edge: (
                edge.network_name,
                edge.fee_usd,
                edge.time_hours,
                edge.fx_rate,
                edge.data_source.value,
            ),
        )

    def all_nodes(self) -> set[str]:
        return set(self.graph.nodes)

    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def has_path(self, from_currency: str, to_currency: str) -> bool:
        source_currency = from_currency.strip().upper()
        target_currency = to_currency.strip().upper()

        if source_currency not in self.graph or target_currency not in self.graph:
            return False

        if source_currency == target_currency:
            return self.graph.has_edge(source_currency, target_currency)

        return nx.has_path(self.graph, source_currency, target_currency)

    async def _build_edge(
        self,
        network: PaymentNetwork,
        from_currency: str,
        to_currency: str,
    ) -> None:
        try:
            quote_amount = self._amount * fx.get_mid_rate(
                self._amount_currency,
                from_currency,
            )
            quote = await self._resolve_quote(
                network,
                quote_amount,
                from_currency,
                to_currency,
            )
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
            time_hours=quote.time_hours,
            time_min_hours=quote.time_min_hours or quote.time_hours,
            time_max_hours=quote.time_max_hours or quote.time_hours,
            fx_rate=quote.fx_rate,
            data_source=quote.data_source,
            fee_data_source=quote.fee_data_source,
            time_data_source=quote.time_data_source,
            fx_data_source=quote.fx_data_source,
            amount_at_send=quote_amount,
        )
        self.graph.add_edge(from_currency, to_currency, edge=edge)

    async def _resolve_quote(
        self,
        network: PaymentNetwork,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        result = network.get_quote(amount, from_currency, to_currency)
        if inspect.isawaitable(result):
            try:
                awaited_result = await asyncio.wait_for(
                    result,
                    timeout=self._quote_timeout_seconds,
                )
            except TimeoutError as exc:
                raise TimeoutError(
                    f"quote timed out after {self._quote_timeout_seconds:g} seconds"
                ) from exc
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
        return network.display_name()
