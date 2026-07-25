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

    def quotes_at_request_time(self) -> bool:
        """Whether a quote reflects the moment it is requested.

        A live-quoting adapter cannot be replayed against a past rate date:
        its fee and delivery estimate are today's whatever FX table is
        active, so mixing the two would describe a route that never existed.
        Scheme rules and scenario parameters are date-independent, so those
        models answer ``False`` and stay eligible for historical runs.
        """
        return False

    def display_name(self) -> str:
        """Human-readable network name used in warnings, tables, and the API."""
        explicit_name = getattr(self, "_name", None)
        if explicit_name:
            return str(explicit_name)

        class_name = type(self).__name__
        return class_name.removesuffix("Network") or class_name
