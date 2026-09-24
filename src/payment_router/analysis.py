"""Shared primitives for route-selection analyses."""

from __future__ import annotations

from payment_router.core.models import Route

RouteSignature = tuple[tuple[str, ...], tuple[str, ...]]


def route_signature(route: Route) -> RouteSignature:
    """Identify a route by its currency path and ordered payment networks."""
    path = (route.source_currency, *(hop.to_node for hop in route.hops))
    networks = tuple(hop.network_name for hop in route.hops)
    return path, networks


class Caveat(str):
    """A caveat sentence that also carries a stable code and its parameters.

    It is a ``str``, so every existing consumer — CLI panels, tests, the AI
    payload — keeps reading the same English sentence. The code and
    parameters let a frontend state the same limit in another language
    without parsing prose, so a translation can never drift from which
    caveat actually applies or from the figures it quotes.
    """

    code: str
    params: dict[str, str]

    def __new__(cls, code: str, text: str, params: dict[str, str]) -> Caveat:
        caveat = super().__new__(cls, text)
        caveat.code = code
        caveat.params = params
        return caveat


_CAVEAT_TEMPLATES: dict[str, str] = {}


class CaveatTemplate:
    """An English caveat with ``{name}`` placeholders, registered by code."""

    def __init__(self, code: str, text: str) -> None:
        self.code = code
        self.text = text
        _CAVEAT_TEMPLATES[code] = text

    def __call__(self, **params: object) -> Caveat:
        values = {name: str(value) for name, value in params.items()}
        return Caveat(self.code, self.text.format(**values), values)


def caveat_templates() -> dict[str, str]:
    """Every registered caveat template, keyed by code."""
    return dict(_CAVEAT_TEMPLATES)
