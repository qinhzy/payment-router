from decimal import Decimal

from payment_router.core.models import DataSource, Hop, Route
from payment_router.decision import (
    DecisionProfile,
    build_decision_board,
    summarize_tradeoff,
)


def _route(network: str, fee: str, hours: str, final_amount: str) -> Route:
    return Route(
        hops=[
            Hop(
                from_node="USD",
                to_node="CNY",
                network_name=network,
                fee_usd=Decimal(fee),
                time_hours=Decimal(hours),
                currency_in="USD",
                currency_out="CNY",
                fx_rate=Decimal("7"),
                data_source=DataSource.VERIFIED,
            )
        ],
        total_fee_usd=Decimal(fee),
        total_time_hours=Decimal(hours),
        source_currency="USD",
        target_currency="CNY",
        source_amount=Decimal("100"),
        final_amount=Decimal(final_amount),
    )


class StubRouter:
    def __init__(self) -> None:
        self.cheapest = _route("Value", "5", "10", "700")
        self.fastest = _route("Fast", "10", "1", "690")
        self.balanced = _route("Balanced", "7", "4", "696")

    def find_cheapest(self, *_args):
        return self.cheapest

    def find_fastest(self, *_args):
        return self.fastest

    def find_route(self, *_args):
        return self.balanced


def test_decision_board_evaluates_all_three_profiles() -> None:
    decisions = build_decision_board(
        StubRouter(),  # type: ignore[arg-type]
        "USD",
        "CNY",
        Decimal("100"),
    )

    assert [decision.profile for decision in decisions] == [
        DecisionProfile.CHEAPEST,
        DecisionProfile.FASTEST,
        DecisionProfile.BALANCED,
    ]
    assert all(decision.evidence == "VERIFIED" for decision in decisions)


def test_tradeoff_explains_balanced_route_against_cheapest() -> None:
    decisions = build_decision_board(
        StubRouter(),  # type: ignore[arg-type]
        "USD",
        "CNY",
        Decimal("100"),
    )

    summary = summarize_tradeoff(decisions)

    assert summary is not None
    assert summary.same_route_for_all_profiles is False
    assert summary.balanced_fee_delta_usd == Decimal("2")
    assert summary.balanced_hours_saved_vs_cheapest == Decimal("6")
    assert summary.balanced_receive_delta == Decimal("-4")
