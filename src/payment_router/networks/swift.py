"""
SWIFT simulator rules for correspondent-bank routing.

Data source rationale (verified 2026-04-19):
- Fee ranges reference Wise 2024 cross-border wire fee research together with
  general industry public disclosures on correspondent-banking charges.
- The simulator uses conservative median assumptions rather than any single
  bank's published tariff.

This module returns INDUSTRY_AVERAGE estimates and does not represent any
specific bank's live quote.
"""

from __future__ import annotations

from decimal import Decimal

from payment_router.core import fx
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork

# Backward-compatible alias for existing tests; the canonical source now lives
# in `payment_router.core.fx`.
_MID_RATES_TO_USD = {
    currency: fx.to_usd(Decimal("1"), currency) for currency in fx.supported_currencies()
}


class SWIFTNetwork(PaymentNetwork):
    def __init__(
        self,
        num_hops: int = 3,
        hop_fixed_fee_usd: Decimal = Decimal("20"),
        hop_percentage_fee: Decimal = Decimal("0.002"),
        hop_time_hours: float = 18.0,
        hop_fx_spread: Decimal = Decimal("0.01"),
    ) -> None:
        self._num_hops = num_hops
        self._hop_fixed_fee_usd = hop_fixed_fee_usd
        self._hop_percentage_fee = hop_percentage_fee
        self._hop_time_hours = Decimal(str(hop_time_hours))
        self._hop_fx_spread = hop_fx_spread

    async def get_quote(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        source_currency = from_currency.strip().upper()
        target_currency = to_currency.strip().upper()

        if (
            source_currency not in fx.supported_currencies()
            or target_currency not in fx.supported_currencies()
        ):
            return None

        amount_usd = fx.to_usd(amount, source_currency)
        fee_per_hop_usd = self._hop_fixed_fee_usd + (amount_usd * self._hop_percentage_fee)
        total_fee_usd = Decimal(self._num_hops) * fee_per_hop_usd
        total_time_hours = Decimal(self._num_hops) * self._hop_time_hours

        if source_currency == target_currency:
            fx_rate = fx.get_mid_rate(source_currency, target_currency)
        else:
            mid_rate = fx.get_mid_rate(source_currency, target_currency)
            spread_multiplier = (Decimal("1.0") - self._hop_fx_spread) ** self._num_hops
            fx_rate = mid_rate * spread_multiplier

        return NetworkQuote(
            network_name="SWIFT",
            fee_usd=total_fee_usd,
            time_hours=total_time_hours,
            fx_rate=fx_rate,
            data_source=DataSource.INDUSTRY_AVERAGE,
        )

    def supported_currencies(self) -> set[str]:
        return set(fx.supported_currencies())
