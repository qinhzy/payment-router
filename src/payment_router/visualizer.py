from __future__ import annotations

from decimal import Decimal

from payment_router.core.fx import get_mid_rate
from payment_router.core.models import Route


def route_to_mermaid(route: Route) -> str:
    node_currencies = _node_currencies(route)
    node_ids = _node_ids(node_currencies)
    node_amounts = _node_amounts(route)

    lines = ["flowchart LR"]
    for node_id, currency, amount in zip(
        node_ids,
        node_currencies,
        node_amounts,
        strict=True,
    ):
        lines.append(f'    {node_id}["{currency}<br/>{_format_amount(amount)}"]')

    for hop, from_node, to_node in zip(
        route.hops,
        node_ids[:-1],
        node_ids[1:],
        strict=True,
    ):
        edge_label = (
            f"{hop.network_name}<br/>"
            f"fee: ${_format_amount(hop.fee_usd)}<br/>"
            f"{_format_hours(hop.time_hours)}h"
        )
        lines.append(f'    {from_node} -->|"{edge_label}"| {to_node}')

    return "\n".join(lines)


def routes_to_comparison_table(routes: list[Route]) -> str:
    if not routes:
        return ""

    lines = [
        "| Route | Total Fee (USD) | Total Time (hours) | Final Amount | Path |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for index, route in enumerate(routes, start=1):
        path = " → ".join(_node_currencies(route))
        lines.append(
            "| "
            f"Route {index} | "
            f"{_format_amount(route.total_fee_usd)} | "
            f"{_format_hours(route.total_time_hours)} | "
            f"{_format_amount(route.final_amount)} {route.target_currency} | "
            f"{path} |"
        )

    return "\n".join(lines)


def _node_currencies(route: Route) -> list[str]:
    if not route.hops:
        return [route.source_currency]
    return [route.source_currency, *[hop.to_node for hop in route.hops]]


def _node_ids(currencies: list[str]) -> list[str]:
    if len(currencies) == len(set(currencies)):
        return currencies
    return [f"{currency}_{index}" for index, currency in enumerate(currencies)]


def _node_amounts(route: Route) -> list[Decimal]:
    if not route.hops:
        return [route.source_amount]

    amounts = [route.source_amount]
    current_amount = route.source_amount
    for hop in route.hops:
        fee_in_source_currency = hop.fee_usd * get_mid_rate("USD", hop.currency_in)
        current_amount = max(
            (current_amount - fee_in_source_currency) * hop.fx_rate,
            Decimal("0"),
        )
        amounts.append(current_amount)

    amounts[-1] = route.final_amount
    return amounts


def _format_amount(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01')):.2f}"


def _format_hours(hours: Decimal) -> str:
    normalized = format(hours.quantize(Decimal("0.001")).normalize(), "f")
    if "." not in normalized:
        return f"{normalized}.0"

    trimmed = normalized.rstrip("0").rstrip(".")
    return trimmed if "." in trimmed else f"{trimmed}.0"
