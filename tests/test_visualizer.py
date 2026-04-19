from __future__ import annotations

from decimal import Decimal

from payment_router.core.models import DataSource, Hop, Route
from payment_router.router import RoutingPreference
from payment_router.visualizer import route_to_mermaid, routes_to_comparison_table


def _hop(
    from_node: str,
    to_node: str,
    network_name: str,
    fee_usd: str,
    time_hours: str,
    fx_rate: str,
) -> Hop:
    return Hop(
        from_node=from_node,
        to_node=to_node,
        network_name=network_name,
        fee_usd=Decimal(fee_usd),
        time_hours=Decimal(time_hours),
        currency_in=from_node,
        currency_out=to_node,
        fx_rate=Decimal(fx_rate),
        data_source=DataSource.VERIFIED,
    )


def test_route_to_mermaid_renders_single_hop_flowchart() -> None:
    assert RoutingPreference(cost_weight=0.5, time_weight=0.5)
    route = Route(
        hops=[_hop("USD", "CNY", "Wise", "5.20", "1", "7.1754")],
        total_fee_usd=Decimal("5.20"),
        total_time_hours=Decimal("1"),
        source_currency="USD",
        target_currency="CNY",
        source_amount=Decimal("100"),
        final_amount=Decimal("712.34"),
    )

    mermaid = route_to_mermaid(route)

    assert mermaid.startswith("flowchart LR")
    assert 'USD["USD<br/>100.00"]' in mermaid
    assert 'CNY["CNY<br/>712.34"]' in mermaid
    assert 'USD -->|"Wise<br/>fee: $5.20<br/>1.0h"| CNY' in mermaid


def test_route_to_mermaid_connects_multi_hop_path() -> None:
    route = Route(
        hops=[
            _hop("USD", "EUR", "Wise", "2.00", "1", "0.80"),
            _hop("EUR", "CNY", "SWIFT", "3.00", "5", "9.10"),
        ],
        total_fee_usd=Decimal("5.00"),
        total_time_hours=Decimal("6"),
        source_currency="USD",
        target_currency="CNY",
        source_amount=Decimal("100"),
        final_amount=Decimal("716.10"),
    )

    mermaid = route_to_mermaid(route)

    assert 'USD -->|"Wise<br/>fee: $2.00<br/>1.0h"| EUR' in mermaid
    assert 'EUR -->|"SWIFT<br/>fee: $3.00<br/>5.0h"| CNY' in mermaid


def test_route_to_mermaid_for_zero_hop_route_renders_single_node() -> None:
    route = Route(
        hops=[],
        total_fee_usd=Decimal("0"),
        total_time_hours=Decimal("0"),
        source_currency="USD",
        target_currency="USD",
        source_amount=Decimal("100"),
        final_amount=Decimal("100"),
    )

    mermaid = route_to_mermaid(route)

    assert mermaid == 'flowchart LR\n    USD["USD<br/>100.00"]'


def test_routes_to_comparison_table_empty_list_returns_empty_string() -> None:
    assert routes_to_comparison_table([]) == ""


def test_routes_to_comparison_table_preserves_route_order() -> None:
    routes = [
        Route(
            hops=[_hop("USD", "CNY", "Wise", "5.00", "1", "7.0")],
            total_fee_usd=Decimal("5.00"),
            total_time_hours=Decimal("1"),
            source_currency="USD",
            target_currency="CNY",
            source_amount=Decimal("100"),
            final_amount=Decimal("695.00"),
        ),
        Route(
            hops=[
                _hop("USD", "EUR", "Bridge", "2.00", "2", "0.80"),
                _hop("EUR", "CNY", "Bridge", "3.00", "2", "9.00"),
            ],
            total_fee_usd=Decimal("5.00"),
            total_time_hours=Decimal("4"),
            source_currency="USD",
            target_currency="CNY",
            source_amount=Decimal("100"),
            final_amount=Decimal("700.00"),
        ),
    ]

    table = routes_to_comparison_table(routes)
    lines = table.splitlines()

    assert lines[0] == "| Route | Total Fee (USD) | Total Time (hours) | Final Amount | Path |"
    assert "| Route 1 | 5.00 | 1.0 | 695.00 CNY | USD → CNY |" in lines[2]
    assert "| Route 2 | 5.00 | 4.0 | 700.00 CNY | USD → EUR → CNY |" in lines[3]
