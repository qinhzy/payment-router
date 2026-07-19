"""
SWIFT simulator rules for correspondent-bank routing.

Data source rationale (reviewed 2026-07-18):
- SWIFT's public correspondent-banking material supports the network topology.
- Hop count, fee, delay, and spread values are explicit teaching assumptions;
  they are not presented as measured industry medians.

This module returns ESTIMATED values and does not represent any specific
bank's live quote.
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
        if isinstance(num_hops, bool) or not isinstance(num_hops, int) or num_hops < 1:
            raise ValueError("num_hops must be a positive integer")
        if not hop_fixed_fee_usd.is_finite() or hop_fixed_fee_usd < 0:
            raise ValueError("hop_fixed_fee_usd must be a non-negative finite decimal")
        if not hop_percentage_fee.is_finite() or not Decimal("0") <= hop_percentage_fee <= 1:
            raise ValueError("hop_percentage_fee must be between 0 and 1")
        normalized_time = Decimal(str(hop_time_hours))
        if not normalized_time.is_finite() or normalized_time < 0:
            raise ValueError("hop_time_hours must be a non-negative finite number")
        if not hop_fx_spread.is_finite() or not Decimal("0") <= hop_fx_spread < 1:
            raise ValueError("hop_fx_spread must be at least 0 and less than 1")

        self._num_hops = num_hops
        self._hop_fixed_fee_usd = hop_fixed_fee_usd
        self._hop_percentage_fee = hop_percentage_fee
        self._hop_time_hours = normalized_time
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
            data_source=DataSource.ESTIMATED,
            fee_data_source=DataSource.ESTIMATED,
            time_data_source=DataSource.ESTIMATED,
            fx_data_source=DataSource.ESTIMATED,
        )

    def supported_currencies(self) -> set[str]:
        return set(fx.supported_currencies())
