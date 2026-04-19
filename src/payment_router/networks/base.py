from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from payment_router.core.models import NetworkQuote


class PaymentNetwork(ABC):
    @abstractmethod
    def get_quote(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        """Return a quote for a corridor, or ``None`` when unsupported."""

    @abstractmethod
    def supported_currencies(self) -> set[str]:
        """Return the currencies this network can handle."""
