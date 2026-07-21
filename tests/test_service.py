from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from helpers import FakeNetwork, make_quote

from payment_router.decision import DecisionProfile
from payment_router.networks.base import PaymentNetwork
from payment_router.service import (
    RoutingRequestError,
    build_session,
    network_display_name,
    parse_amount,
    preference_for_profile,
    select_route_for_profile,
)


def test_parse_amount_accepts_decimal_strings() -> None:
    assert parse_amount("100.50") == Decimal("100.50")


@pytest.mark.parametrize("raw_amount", ["abc", "NaN", "Infinity", ""])
def test_parse_amount_rejects_non_decimal_input(raw_amount: str) -> None:
    with pytest.raises(RoutingRequestError, match="valid decimal number"):
        parse_amount(raw_amount)


@pytest.mark.parametrize("raw_amount", ["0", "-5"])
def test_parse_amount_rejects_non_positive_amounts(raw_amount: str) -> None:
    with pytest.raises(RoutingRequestError, match="greater than zero"):
        parse_amount(raw_amount)


def test_preference_for_profile_maps_weights() -> None:
    cheapest = preference_for_profile(DecisionProfile.CHEAPEST)
    fastest = preference_for_profile(DecisionProfile.FASTEST)
    balanced = preference_for_profile(DecisionProfile.BALANCED)

    assert (cheapest.alpha, cheapest.beta) == (1.0, 0.0)
    assert (fastest.alpha, fastest.beta) == (0.0, 1.0)
    assert (balanced.alpha, balanced.beta) == (0.5, 0.5)


def test_network_display_name_prefers_explicit_name() -> None:
    assert network_display_name(FakeNetwork("SEPA Instant", {"EUR"})) == "SEPA Instant"


def test_network_display_name_strips_class_suffix() -> None:
    class DemoRailNetwork(PaymentNetwork):
        async def get_quote(self, amount, from_currency, to_currency):
            return None

        def supported_currencies(self) -> set[str]:
            return {"USD"}

    assert network_display_name(DemoRailNetwork()) == "DemoRail"


def test_build_session_rejects_unsupported_currency() -> None:
    networks = [FakeNetwork("Demo", {"USD", "CNY"})]

    with pytest.raises(RoutingRequestError, match="Unsupported currency code"):
        asyncio.run(build_session("USD", "XYZ", "100", networks=networks))


def test_build_session_normalizes_request_and_collects_warnings() -> None:
    networks = [
        FakeNetwork(
            "Demo",
            {"USD", "CNY"},
            {
                ("USD", "CNY"): make_quote("Demo", "5", "1", "7.0"),
                ("CNY", "USD"): RuntimeError("corridor offline"),
            },
        )
    ]

    session = asyncio.run(build_session(" usd ", "cny", "100", networks=networks))

    assert session.source_currency == "USD"
    assert session.target_currency == "CNY"
    assert session.amount == Decimal("100")
    assert [
        (warning.network, warning.from_currency, warning.to_currency, warning.reason)
        for warning in session.warnings
    ] == [("Demo", "CNY", "USD", "corridor offline")]

    route = select_route_for_profile(
        session.router, "USD", "CNY", session.amount, DecisionProfile.CHEAPEST
    )
    assert route is not None
    assert [hop.network_name for hop in route.hops] == ["Demo"]
