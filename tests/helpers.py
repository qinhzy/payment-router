"""Shared test doubles for payment-network behavior.

One canonical fake replaces the per-file copies that used to drift apart:
it supports every suite's needs (optional explicit name, per-corridor
quotes or exceptions, and call recording for graph-construction tests).
"""

from __future__ import annotations

from decimal import Decimal

from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork


def make_quote(
    network_name: str,
    fee_usd: str,
    time_hours: str,
    fx_rate: str = "1.0",
    data_source: DataSource = DataSource.INDUSTRY_AVERAGE,
    *,
    time_min_hours: str | None = None,
    time_max_hours: str | None = None,
) -> NetworkQuote:
    return NetworkQuote(
        network_name=network_name,
        fee_usd=Decimal(fee_usd),
        time_hours=Decimal(time_hours),
        time_min_hours=Decimal(time_min_hours) if time_min_hours is not None else None,
        time_max_hours=Decimal(time_max_hours) if time_max_hours is not None else None,
        fx_rate=Decimal(fx_rate),
        data_source=data_source,
    )


class FakeNetwork(PaymentNetwork):
    def __init__(
        self,
        name: str | None,
        supported: set[str],
        quotes: dict[tuple[str, str], NetworkQuote | None | Exception] | None = None,
    ) -> None:
        if name is not None:
            self._name = name
        self._supported = supported
        self._quotes = quotes or {}
        self.calls: list[tuple[str, str, Decimal]] = []

    async def get_quote(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        self.calls.append((from_currency, to_currency, amount))
        result = self._quotes.get((from_currency, to_currency))
        if isinstance(result, Exception):
            raise result
        return result

    def supported_currencies(self) -> set[str]:
        return self._supported
