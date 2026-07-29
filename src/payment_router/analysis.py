"""Shared primitives for route-selection analyses."""

from __future__ import annotations

from payment_router.core.models import Route

RouteSignature = tuple[tuple[str, ...], tuple[str, ...]]


def route_signature(route: Route) -> RouteSignature:
    """Identify a route by its currency path and ordered payment networks."""
    path = (route.source_currency, *(hop.to_node for hop in route.hops))
    networks = tuple(hop.network_name for hop in route.hops)
    return path, networks
