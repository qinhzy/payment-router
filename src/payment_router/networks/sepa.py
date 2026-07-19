"""
SEPA simulator rules.

Data sources (verified 2026-04-19):
- European Payments Council SCT public scheme page:
  https://www.europeanpaymentscouncil.eu/what-we-do/sepa-payment-schemes/sepa-credit-transfer
- European Payments Council SCT Inst public scheme page:
  https://www.europeanpaymentscouncil.eu/what-we-do/sepa-payment-schemes/sepa-instant-credit-transfer

The scheme timing is source-backed. Fee values are explicit simulator
assumptions because the EPC scheme does not set end-user bank pricing.
"""

from __future__ import annotations

from decimal import Decimal

from payment_router.core import fx
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork

SCT_FEE_EUR = Decimal("0.25")
SCT_INST_FEE_EUR = Decimal("0.50")
SCT_TIME_HOURS = Decimal("24.0")
SCT_INST_TIME_HOURS = Decimal("10") / Decimal("3600")


class SEPANetwork(PaymentNetwork):
    def __init__(self, instant: bool = False) -> None:
        self._instant = instant
        self._name = "SEPA Instant" if instant else "SEPA"

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

        return NetworkQuote(
            network_name=self._name,
            fee_usd=fx.to_usd(fee_eur, "EUR"),
            time_hours=time_hours,
            fx_rate=Decimal("1.0"),
            data_source=DataSource.ESTIMATED,
            fee_data_source=DataSource.ESTIMATED,
            time_data_source=DataSource.VERIFIED,
            fx_data_source=DataSource.VERIFIED,
        )

    def supported_currencies(self) -> set[str]:
        return {"EUR"}
