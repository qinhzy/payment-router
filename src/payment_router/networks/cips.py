"""CIPS scenario rules for RMB-bound cross-border routing.

Structural facts (VERIFIED on 2026-07-21):
- CIPS overview and operating schedule:
  https://www.cips.com.cn/kjjqgs/jrcips/index.shtml
- CIPS business rules defining direct and indirect participants:
  https://www.cips.com.cn/kjjqgs/articleFileDir/2025-12/30/8eeaecf1a3164597a0b73b9c329f7a6f.pdf

CIPS is a wholesale payment system for cross-border RMB clearing and
settlement, has direct and indirect participants, and operates on a
5 x 24 hours + 4 hours schedule.

Those facts do not establish customer pricing or end-to-end delivery times.
Hop count, fees, delays, timing bounds, and FX spread below are explicit
teaching assumptions. This module therefore returns only ESTIMATED numeric
values and does not represent a participant bank quote or settlement promise.
"""

from __future__ import annotations

from decimal import Decimal

from payment_router.core import fx
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork


class CIPSNetwork(PaymentNetwork):
    """Configurable CNY-destination scenario with a shorter chain than SWIFT."""

    def __init__(
        self,
        num_hops: int = 2,
        hop_fixed_fee_usd: Decimal = Decimal("8"),
        hop_percentage_fee: Decimal = Decimal("0.001"),
        hop_time_hours: float = 6.0,
        hop_time_min_hours: float = 1.0,
        hop_time_max_hours: float = 12.0,
        hop_fx_spread: Decimal = Decimal("0.003"),
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
        normalized_time_min = Decimal(str(hop_time_min_hours))
        normalized_time_max = Decimal(str(hop_time_max_hours))
        if not (
            normalized_time_min.is_finite()
            and normalized_time_max.is_finite()
            and Decimal("0") <= normalized_time_min <= normalized_time <= normalized_time_max
        ):
            raise ValueError("hop time bounds must satisfy 0 <= min <= expected <= max")
        if not hop_fx_spread.is_finite() or not Decimal("0") <= hop_fx_spread < 1:
            raise ValueError("hop_fx_spread must be at least 0 and less than 1")

        self._num_hops = num_hops
        self._hop_fixed_fee_usd = hop_fixed_fee_usd
        self._hop_percentage_fee = hop_percentage_fee
        self._hop_time_hours = normalized_time
        self._hop_time_min_hours = normalized_time_min
        self._hop_time_max_hours = normalized_time_max
        self._hop_fx_spread = hop_fx_spread

    async def get_quote(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        source_currency = from_currency.strip().upper()
        target_currency = to_currency.strip().upper()

        if source_currency not in fx.supported_currencies() or target_currency != "CNY":
            return None

        amount_usd = fx.to_usd(amount, source_currency)
        fee_per_hop_usd = self._hop_fixed_fee_usd + (amount_usd * self._hop_percentage_fee)
        total_fee_usd = Decimal(self._num_hops) * fee_per_hop_usd
        total_time_hours = Decimal(self._num_hops) * self._hop_time_hours
        total_time_min = Decimal(self._num_hops) * self._hop_time_min_hours
        total_time_max = Decimal(self._num_hops) * self._hop_time_max_hours

        if source_currency == target_currency:
            fx_rate = fx.get_mid_rate(source_currency, target_currency)
        else:
            mid_rate = fx.get_mid_rate(source_currency, target_currency)
            spread_multiplier = (Decimal("1.0") - self._hop_fx_spread) ** self._num_hops
            fx_rate = mid_rate * spread_multiplier

        return NetworkQuote(
            network_name="CIPS",
            fee_usd=total_fee_usd,
            time_hours=total_time_hours,
            time_min_hours=total_time_min,
            time_max_hours=total_time_max,
            fx_rate=fx_rate,
            data_source=DataSource.ESTIMATED,
            fee_data_source=DataSource.ESTIMATED,
            time_data_source=DataSource.ESTIMATED,
            fx_data_source=DataSource.ESTIMATED,
        )

    def supported_currencies(self) -> set[str]:
        return set(fx.supported_currencies())
