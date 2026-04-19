from decimal import Decimal

import pytest

from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork


class DummyNetwork(PaymentNetwork):
    def get_quote(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        _ = (amount, from_currency, to_currency)
        return NetworkQuote(
            network_name="dummy",
            fee_usd=Decimal("1.00"),
            time_hours=Decimal("2"),
            fx_rate=Decimal("1.00"),
            data_source=DataSource.ESTIMATED,
        )

    def supported_currencies(self) -> set[str]:
        return {"USD", "EUR"}


def test_payment_network_requires_abstract_methods() -> None:
    class IncompleteNetwork(PaymentNetwork):
        pass

    with pytest.raises(TypeError):
        IncompleteNetwork()


def test_payment_network_subclass_can_return_quote() -> None:
    network = DummyNetwork()

    assert network.supported_currencies() == {"USD", "EUR"}
    assert network.get_quote(Decimal("100"), "USD", "EUR") is not None
