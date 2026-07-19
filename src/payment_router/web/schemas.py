"""JSON views of routing results for the web API.

Decimal values are serialized as strings with the same formatting the CLI
uses, so both frontends always display identical numbers.
"""

from __future__ import annotations

from payment_router.core.models import DataSource, Hop, Route
from payment_router.decision import DecisionTradeoff, RouteDecision
from payment_router.provenance import ProvenanceRecord
from payment_router.service import BuildWarning
from payment_router.visualizer import (
    format_amount,
    format_hours,
    route_node_amounts,
    route_to_mermaid,
)


def hop_to_json(hop: Hop) -> dict[str, object]:
    return {
        "from": hop.from_node,
        "to": hop.to_node,
        "network": hop.network_name,
        "fee_usd": format_amount(hop.fee_usd),
        "time_hours": format_hours(hop.time_hours),
        "fx_rate": str(hop.fx_rate),
        "data_source": hop.data_source.value,
        "fee_data_source": hop.fee_data_source.value if hop.fee_data_source else None,
        "time_data_source": hop.time_data_source.value if hop.time_data_source else None,
        "fx_data_source": hop.fx_data_source.value if hop.fx_data_source else None,
    }


def route_to_json(route: Route) -> dict[str, object]:
    path = [route.source_currency, *(hop.to_node for hop in route.hops)]
    provenance = {source for hop in route.hops for source in hop.provenance_sources}
    return {
        "path": path,
        "amounts": [format_amount(amount) for amount in route_node_amounts(route)],
        "hops": [hop_to_json(hop) for hop in route.hops],
        "total_fee_usd": format_amount(route.total_fee_usd),
        "total_time_hours": format_hours(route.total_time_hours),
        "source_currency": route.source_currency,
        "target_currency": route.target_currency,
        "source_amount": format_amount(route.source_amount),
        "final_amount": format_amount(route.final_amount),
        "provenance": [source.value for source in DataSource if source in provenance],
        "mermaid": route_to_mermaid(route),
    }


def decision_to_json(decision: RouteDecision) -> dict[str, object]:
    return {
        "profile": decision.profile.value,
        "evidence": decision.evidence,
        "route": route_to_json(decision.route),
    }


def tradeoff_to_json(tradeoff: DecisionTradeoff) -> dict[str, object]:
    return {
        "same_route_for_all_profiles": tradeoff.same_route_for_all_profiles,
        "balanced_fee_delta_usd": format_amount(tradeoff.balanced_fee_delta_usd),
        "balanced_hours_saved_vs_cheapest": format_hours(tradeoff.balanced_hours_saved_vs_cheapest),
        "balanced_receive_delta": format_amount(tradeoff.balanced_receive_delta),
    }


def warning_to_json(warning: BuildWarning) -> dict[str, object]:
    return {
        "network": warning.network,
        "pair": f"{warning.from_currency}->{warning.to_currency}",
        "reason": warning.reason,
    }


def provenance_to_json(record: ProvenanceRecord) -> dict[str, object]:
    return {
        "evidence_id": record.evidence_id,
        "network": record.network,
        "metric": record.metric,
        "classification": record.classification.value,
        "value": record.value,
        "checked_on": record.checked_on,
        "reference": record.reference,
        "caveat": record.caveat,
    }
