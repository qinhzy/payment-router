"""
SEPA simulator rules.

Data sources (verified 2026-04-19):
- European Payments Council SCT public scheme page:
  https://www.europeanpaymentscouncil.eu/what-we-do/sepa-payment-schemes/sepa-credit-transfer
- European Payments Council SCT Inst public scheme page:
  https://www.europeanpaymentscouncil.eu/what-we-do/sepa-payment-schemes/sepa-instant-credit-transfer

Fee assumptions in this module are industry medians for simulator use only and
are not any single bank's live quotation.
"""

from __future__ import annotations

from decimal import Decimal

from payment_router.core import fx
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork

SCT_FEE_EUR = Decimal("0.25")
SCT_INST_FEE_EUR = Decimal("0.50")
SCT_TIME_HOURS = Decimal("24.0")
SCT_INST_TIME_HOURS = Decimal("0.003")


class SEPANetwork(PaymentNetwork):
    def __init__(self, instant: bool = False) -> None:
        self._instant = instant

    async def get_quote(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        _ = amount
        source_currency = from_currency.strip().upper()
        target_currency = to_currency.strip().upper()

        if source_currency != "EUR" or target_currency != "EUR":
            return None

        fee_eur = SCT_INST_FEE_EUR if self._instant else SCT_FEE_EUR
        time_hours = SCT_INST_TIME_HOURS if self._instant else SCT_TIME_HOURS
        network_name = "SEPA Instant" if self._instant else "SEPA"

        return NetworkQuote(
            network_name=network_name,
            fee_usd=fx.to_usd(fee_eur, "EUR"),
            time_hours=time_hours,
            fx_rate=Decimal("1.0"),
            data_source=DataSource.INDUSTRY_AVERAGE,
        )

    def supported_currencies(self) -> set[str]:
        return {"EUR"}
