from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from payment_router.core.models import DataSource, Route
from payment_router.router import PaymentRouter, RoutingPreference


class DecisionProfile(StrEnum):
    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    BALANCED = "balanced"


@dataclass(frozen=True, slots=True)
class RouteDecision:
    profile: DecisionProfile
    route: Route

    @property
    def path(self) -> tuple[str, ...]:
        return (self.route.source_currency, *(hop.to_node for hop in self.route.hops))

    @property
    def evidence(self) -> str:
        sources = {hop.data_source for hop in self.route.hops}
        if not sources:
            return "NO_HOPS"
        if len(sources) == 1:
            return next(iter(sources)).value
        ordered = [source.value for source in DataSource if source in sources]
        return "MIXED: " + ", ".join(ordered)

    @property
    def signature(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return self.path, tuple(hop.network_name for hop in self.route.hops)


@dataclass(frozen=True, slots=True)
class DecisionTradeoff:
    same_route_for_all_profiles: bool
    balanced_fee_delta_usd: Decimal
    balanced_hours_saved_vs_cheapest: Decimal
    balanced_receive_delta: Decimal


def build_decision_board(
    router: PaymentRouter,
    from_currency: str,
    to_currency: str,
    amount: Decimal,
) -> list[RouteDecision]:
    selectors = (
        (
            DecisionProfile.CHEAPEST,
            lambda: router.find_cheapest(from_currency, to_currency, amount),
        ),
        (
            DecisionProfile.FASTEST,
            lambda: router.find_fastest(from_currency, to_currency, amount),
        ),
        (
            DecisionProfile.BALANCED,
            lambda: router.find_route(
                from_currency,
                to_currency,
                amount,
                RoutingPreference(cost_weight=0.5, time_weight=0.5),
            ),
        ),
    )
    decisions: list[RouteDecision] = []
    for profile, select in selectors:
        route = select()
        if route is not None:
            decisions.append(RouteDecision(profile=profile, route=route))
    return decisions


def summarize_tradeoff(decisions: list[RouteDecision]) -> DecisionTradeoff | None:
    by_profile = {decision.profile: decision for decision in decisions}
    if DecisionProfile.BALANCED not in by_profile or DecisionProfile.CHEAPEST not in by_profile:
        return None

    balanced = by_profile[DecisionProfile.BALANCED]
    cheapest = by_profile[DecisionProfile.CHEAPEST]
    signatures = {decision.signature for decision in decisions}
    return DecisionTradeoff(
        same_route_for_all_profiles=len(signatures) == 1,
        balanced_fee_delta_usd=balanced.route.total_fee_usd - cheapest.route.total_fee_usd,
        balanced_hours_saved_vs_cheapest=(
            cheapest.route.total_time_hours - balanced.route.total_time_hours
        ),
        balanced_receive_delta=balanced.route.final_amount - cheapest.route.final_amount,
    )
