"""Sensitivity analysis for routing decisions.

The weight sweep answers "how robust is this recommendation?" without any
new data: it re-runs route selection while the cost/time preference moves
from pure speed (cost weight 0) to pure cost (cost weight 1) on the same
built graph, and reports the regions where each route wins. A recommendation
whose region spans most of the axis is robust; a boundary near 0.5 means the
balanced pick is fragile.

Timing caveats are qualitative by design: the simulator flags later-hop live
delivery estimates (which assume an already-funded balance) and scenario-
estimated timings instead of inventing adjustment numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from payment_router.analysis import RouteSignature, route_signature
from payment_router.core.models import DataSource, Route
from payment_router.router import PaymentRouter, RoutingPreference

DEFAULT_STEPS = 100


@dataclass(frozen=True, slots=True)
class WeightRegion:
    """A contiguous cost-weight interval won by one route."""

    cost_weight_start: float
    cost_weight_end: float
    route: Route

    @property
    def signature(self) -> RouteSignature:
        return route_signature(self.route)


@dataclass(frozen=True, slots=True)
class SensitivityReport:
    regions: tuple[WeightRegion, ...]
    balanced_region: WeightRegion | None
    caveats: tuple[str, ...]
    steps: int


def analyze(
    router: PaymentRouter,
    source_currency: str,
    target_currency: str,
    amount: Decimal,
    *,
    steps: int = DEFAULT_STEPS,
) -> SensitivityReport:
    if steps < 1:
        raise ValueError("steps must be a positive integer")

    regions: list[WeightRegion] = []
    previous_index: int | None = None
    for index in range(steps + 1):
        cost_weight = index / steps
        preference = RoutingPreference(
            cost_weight=cost_weight,
            time_weight=1.0 - cost_weight,
        )
        route = router.find_route(source_currency, target_currency, amount, preference)
        if route is None:
            continue

        # Only merge into the previous region when this step directly follows
        # it. Weights with no route at all break the interval: extending across
        # that gap would claim the route wins over weights where it does not.
        contiguous = previous_index is not None and index == previous_index + 1
        previous_index = index

        if regions and contiguous and regions[-1].signature == route_signature(route):
            regions[-1] = WeightRegion(
                cost_weight_start=regions[-1].cost_weight_start,
                cost_weight_end=cost_weight,
                route=regions[-1].route,
            )
        else:
            regions.append(
                WeightRegion(
                    cost_weight_start=cost_weight,
                    cost_weight_end=cost_weight,
                    route=route,
                )
            )

    balanced_region = next(
        (region for region in regions if region.cost_weight_start <= 0.5 <= region.cost_weight_end),
        None,
    )
    return SensitivityReport(
        regions=tuple(regions),
        balanced_region=balanced_region,
        caveats=tuple(_caveats_for(regions)),
        steps=steps,
    )


def _caveats_for(regions: list[WeightRegion]) -> list[str]:
    caveats: list[str] = []
    seen: set[RouteSignature] = set()
    for region in regions:
        signature = region.signature
        if signature in seen:
            continue
        seen.add(signature)
        path_label = " -> ".join(signature[0])

        later_live_hops = [
            index + 1
            for index, hop in enumerate(region.route.hops)
            if index > 0 and hop.time_data_source is DataSource.VERIFIED
        ]
        if later_live_hops:
            hop_list = ", ".join(str(index) for index in later_live_hops)
            caveats.append(
                f"{path_label}: the live delivery estimate for hop {hop_list} assumes "
                "an already-funded balance; in a multi-hop route the real clock "
                "starts when the previous hop settles, so it may be understated."
            )

        if any(hop.time_data_source is DataSource.ESTIMATED for hop in region.route.hops):
            caveats.append(
                f"{path_label}: timing is scenario-estimated; the displayed range "
                "reflects the registered per-hop band, not a measured distribution."
            )
    return caveats
