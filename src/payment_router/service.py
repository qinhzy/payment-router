"""Shared routing services used by both the CLI and the web API.

This module owns the request lifecycle that every frontend repeats:
instantiate networks, validate currencies and amount, build the payment
graph, and select routes for a decision profile. Frontends only decide how
to render the results and how to report :class:`RoutingRequestError`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from payment_router.core import fx
from payment_router.core.graph import PaymentGraph
from payment_router.core.models import Route
from payment_router.decision import DecisionProfile
from payment_router.networks.base import PaymentNetwork
from payment_router.networks.cips import CIPSNetwork
from payment_router.networks.sepa import SEPANetwork
from payment_router.networks.swift import SWIFTNetwork
from payment_router.networks.wise import WiseNetwork
from payment_router.router import PaymentRouter, RoutingPreference


class RoutingRequestError(ValueError):
    """A routing request that cannot be fulfilled because of invalid input.

    ``code`` and ``params`` identify the message independently of its English
    wording, so a frontend can show it in another language.
    """

    def __init__(self, message: str, *, code: str | None = None, **params: object) -> None:
        super().__init__(message)
        self.code = code
        self.params = {name: str(value) for name, value in params.items()}


@dataclass(frozen=True, slots=True)
class BuildWarning:
    """A provider failure captured while building the payment graph.

    ``code`` and ``params`` are set when the failure identifies itself (the
    simulator's own statements, and exceptions carrying ``code`` and
    ``params``), so a frontend can translate the reason. An unclassified
    exception keeps only its English text.
    """

    network: str
    from_currency: str
    to_currency: str
    reason: str
    code: str | None = None
    params: tuple[tuple[str, str], ...] = ()


def error_code(exception: BaseException) -> tuple[str | None, dict[str, str]]:
    """An exception's stable code and parameters, when it declares them.

    Only a string ``code`` with a mapping of ``params`` counts: an unrelated
    ``code`` attribute (an HTTP status on a client error, say) is not a
    statement a frontend could translate.
    """
    code = getattr(exception, "code", None)
    params = getattr(exception, "params", None)
    if not isinstance(code, str) or not isinstance(params, Mapping):
        return None, {}
    return code, {str(name): str(value) for name, value in params.items()}


def _warning_for(
    network: str, from_currency: str, to_currency: str, exception: Exception
) -> BuildWarning:
    code, params = error_code(exception)
    return BuildWarning(
        network=network,
        from_currency=from_currency,
        to_currency=to_currency,
        reason=str(exception),
        code=code,
        params=tuple(params.items()),
    )


@dataclass(frozen=True, slots=True)
class RoutingSession:
    """A validated request plus the router built for it."""

    source_currency: str
    target_currency: str
    amount: Decimal
    router: PaymentRouter
    warnings: tuple[BuildWarning, ...]


def default_networks() -> list[PaymentNetwork]:
    return [
        WiseNetwork(),
        SEPANetwork(),
        SEPANetwork(instant=True),
        SWIFTNetwork(),
        CIPSNetwork(),
    ]


def network_display_name(network: PaymentNetwork) -> str:
    return network.display_name()


def networks_for_active_fx(
    networks: list[PaymentNetwork],
) -> tuple[list[PaymentNetwork], tuple[BuildWarning, ...]]:
    """Drop adapters that cannot answer for the active rate date.

    Under a historical fixing a live-quoting adapter would contribute today's
    fee and delivery estimate to a route priced at a past rate, describing a
    corridor that never existed. Excluding it is disclosed as a warning rather
    than done silently, because a missing provider changes which route wins.
    """
    if fx.current_status().mode != "historical":
        return networks, ()

    eligible = [network for network in networks if not network.quotes_at_request_time()]
    excluded = tuple(
        BuildWarning(
            network=network_display_name(network),
            from_currency="*",
            to_currency="*",
            reason=(
                "excluded from a historical run: this provider quotes at request "
                "time and has no rate for a past date"
            ),
            code="historical_excluded",
        )
        for network in networks
        if network.quotes_at_request_time()
    )
    return eligible, excluded


def supported_currencies(networks: list[PaymentNetwork]) -> set[str]:
    supported: set[str] = set()
    for network in networks:
        supported.update(currency.strip().upper() for currency in network.supported_currencies())
    return supported


def parse_amount(raw_amount: str) -> Decimal:
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation:
        raise RoutingRequestError(
            "Amount must be a valid decimal number.", code="amount_invalid"
        ) from None
    if not amount.is_finite():
        raise RoutingRequestError("Amount must be a valid decimal number.", code="amount_invalid")
    if amount <= 0:
        raise RoutingRequestError("Amount must be greater than zero.", code="amount_not_positive")
    return amount


@dataclass(frozen=True, slots=True)
class WarningGroup:
    """Provider failures that share a network and a reason."""

    network: str
    reason: str
    pairs: tuple[tuple[str, str], ...]


def group_warnings(warnings: tuple[BuildWarning, ...]) -> tuple[WarningGroup, ...]:
    """Collapse failures by network and reason, keeping first-seen order.

    An unreachable provider fails every corridor with the same reason; one
    entry per network and reason keeps a failure that differs from it visible
    instead of burying it among dozens of identical rows.
    """
    pairs: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for warning in warnings:
        pairs.setdefault((warning.network, warning.reason), []).append(
            (warning.from_currency, warning.to_currency)
        )
    return tuple(
        WarningGroup(network=network, reason=reason, pairs=tuple(corridors))
        for (network, reason), corridors in pairs.items()
    )


def merge_warnings(*groups: tuple[BuildWarning, ...]) -> tuple[BuildWarning, ...]:
    """Combine warnings from several graph builds, keeping first-seen order.

    Analyses that build one graph per sampled amount see the same provider
    failure once per build; reporting it once keeps the disclosure readable
    without hiding a failure that only some builds hit.
    """
    return tuple(dict.fromkeys(warning for group in groups for warning in group))


def no_route_message(source_currency: str, target_currency: str, amount: Decimal) -> str:
    """The user-facing sentence shared by every frontend when routing fails."""
    return f"No route found from {source_currency} to {target_currency} for {amount}."


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

    networks, excluded_warnings = networks_for_active_fx(networks)
    supported = supported_currencies(networks)
    unsupported = [
        currency for currency in (source_currency, target_currency) if currency not in supported
    ]
    if unsupported:
        supported_list = ", ".join(sorted(supported))
        raise RoutingRequestError(
            "Unsupported currency code(s): "
            f"{', '.join(unsupported)}. Supported currencies: {supported_list}.",
            code="unsupported_currency",
            currencies=", ".join(unsupported),
            supported=supported_list,
        )

    graph = PaymentGraph(
        networks=networks,
        currencies=sorted(supported),
        amount=amount,
        amount_currency=source_currency,
    )
    await graph.build()
    warnings = excluded_warnings + tuple(
        _warning_for(network_name, warning_from, warning_to, exception)
        for network_name, warning_from, warning_to, exception in graph.build_errors
    )
    return RoutingSession(
        source_currency=source_currency,
        target_currency=target_currency,
        amount=amount,
        router=PaymentRouter(graph),
        warnings=warnings,
    )
