"""Shared routing services used by both the CLI and the web API.

This module owns the request lifecycle that every frontend repeats:
instantiate networks, validate currencies and amount, build the payment
graph, and select routes for a decision profile. Frontends only decide how
to render the results and how to report :class:`RoutingRequestError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from payment_router.core.graph import PaymentGraph
from payment_router.core.models import Route
from payment_router.decision import DecisionProfile
from payment_router.networks.base import PaymentNetwork
from payment_router.networks.sepa import SEPANetwork
from payment_router.networks.swift import SWIFTNetwork
from payment_router.networks.wise import WiseNetwork
from payment_router.router import PaymentRouter, RoutingPreference


class RoutingRequestError(ValueError):
    """A routing request that cannot be fulfilled because of invalid input."""


@dataclass(frozen=True, slots=True)
class BuildWarning:
    """A provider failure captured while building the payment graph."""

    network: str
    from_currency: str
    to_currency: str
    reason: str


@dataclass(frozen=True, slots=True)
class RoutingSession:
    """A validated request plus the router built for it."""

    source_currency: str
    target_currency: str
    amount: Decimal
    router: PaymentRouter
    warnings: tuple[BuildWarning, ...]


def default_networks() -> list[PaymentNetwork]:
    return [WiseNetwork(), SEPANetwork(), SEPANetwork(instant=True), SWIFTNetwork()]


def network_display_name(network: PaymentNetwork) -> str:
    return network.display_name()


def supported_currencies(networks: list[PaymentNetwork]) -> set[str]:
    supported: set[str] = set()
    for network in networks:
        supported.update(currency.strip().upper() for currency in network.supported_currencies())
    return supported


def parse_amount(raw_amount: str) -> Decimal:
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation:
        raise RoutingRequestError("Amount must be a valid decimal number.") from None
    if not amount.is_finite():
        raise RoutingRequestError("Amount must be a valid decimal number.")
    if amount <= 0:
        raise RoutingRequestError("Amount must be greater than zero.")
    return amount


def preference_for_profile(profile: DecisionProfile) -> RoutingPreference:
    if profile is DecisionProfile.CHEAPEST:
        return RoutingPreference(cost_weight=1.0, time_weight=0.0)
    if profile is DecisionProfile.FASTEST:
        return RoutingPreference(cost_weight=0.0, time_weight=1.0)
    return RoutingPreference(cost_weight=0.5, time_weight=0.5)


def select_route_for_profile(
    router: PaymentRouter,
    source_currency: str,
    target_currency: str,
    amount: Decimal,
    profile: DecisionProfile,
) -> Route | None:
    if profile is DecisionProfile.CHEAPEST:
        return router.find_cheapest(source_currency, target_currency, amount)
    if profile is DecisionProfile.FASTEST:
        return router.find_fastest(source_currency, target_currency, amount)
    return router.find_route(
        source_currency,
        target_currency,
        amount,
        preference_for_profile(profile),
    )


async def build_session(
    from_currency: str,
    to_currency: str,
    raw_amount: str,
    networks: list[PaymentNetwork],
) -> RoutingSession:
    """Validate the request and build a live routing session for it.

    Raises :class:`RoutingRequestError` with a user-facing message when the
    amount or a currency code is invalid.
    """
    source_currency = from_currency.strip().upper()
    target_currency = to_currency.strip().upper()
    amount = parse_amount(raw_amount)

    supported = supported_currencies(networks)
    unsupported = [
        currency for currency in (source_currency, target_currency) if currency not in supported
    ]
    if unsupported:
        supported_list = ", ".join(sorted(supported))
        raise RoutingRequestError(
            "Unsupported currency code(s): "
            f"{', '.join(unsupported)}. Supported currencies: {supported_list}."
        )

    graph = PaymentGraph(
        networks=networks,
        currencies=sorted(supported),
        amount=amount,
        amount_currency=source_currency,
    )
    await graph.build()
    warnings = tuple(
        BuildWarning(
            network=network_name,
            from_currency=warning_from,
            to_currency=warning_to,
            reason=str(exception),
        )
        for network_name, warning_from, warning_to, exception in graph.build_errors
    )
    return RoutingSession(
        source_currency=source_currency,
        target_currency=target_currency,
        amount=amount,
        router=PaymentRouter(graph),
        warnings=warnings,
    )
