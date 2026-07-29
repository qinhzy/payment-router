"""Find the amounts at which the best route changes.

Fee structure makes the winner depend on how much is being sent: a fixed fee
dominates a small transfer while FX spread dominates a large one, so two
rails typically cross somewhere in between. That crossing is the single most
actionable thing this simulator can show, and nothing else in it looks along
the amount axis — `sensitivity` sweeps the cost/time weight and `comparison`
sweeps the rate date, both at one fixed amount.

Each sampled amount needs its own graph, because quotes depend on the amount
quoted. With a live provider that is a full quote round per sample, so the
search samples coarsely on a logarithmic scale and then bisects only across
the boundaries where the winner actually changed. That locates a crossing far
more precisely than dense sampling would, for a fraction of the provider load.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from payment_router.core.models import DataSource, Route
from payment_router.decision import DecisionProfile
from payment_router.service import build_session, select_route_for_profile

DEFAULT_SAMPLES = 12
DEFAULT_REFINE_STEPS = 6
_CENT = Decimal("0.01")

RouteSignature = tuple[tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class AmountRegion:
    """A contiguous amount range won by one route."""

    amount_start: Decimal
    amount_end: Decimal
    route: Route

    @property
    def signature(self) -> RouteSignature:
        return route_signature(self.route)


@dataclass(frozen=True, slots=True)
class Crossover:
    """Where the winner changes, and how precisely that was located.

    ``amount`` is the lowest amount actually tested at which the new route
    won, so it is a real observation rather than an interpolation. The true
    crossing lies somewhere in ``[bracket_low, bracket_high]``; presenting
    the bracket alongside is what keeps the figure honest.
    """

    amount: Decimal
    bracket_low: Decimal
    bracket_high: Decimal
    below: RouteSignature
    above: RouteSignature

    @property
    def bracket_width(self) -> Decimal:
        return self.bracket_high - self.bracket_low


@dataclass(frozen=True, slots=True)
class BreakevenReport:
    source_currency: str
    target_currency: str
    profile: DecisionProfile
    min_amount: Decimal
    max_amount: Decimal
    regions: tuple[AmountRegion, ...]
    crossovers: tuple[Crossover, ...]
    builds: int
    caveats: tuple[str, ...]


def route_signature(route: Route) -> RouteSignature:
    path = (route.source_currency, *(hop.to_node for hop in route.hops))
    return path, tuple(hop.network_name for hop in route.hops)


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_CENT, rounding=ROUND_HALF_EVEN)


def _log_spaced(minimum: Decimal, maximum: Decimal, samples: int) -> list[Decimal]:
    """Amounts spaced geometrically, because fee structure is scale-driven."""
    if samples == 1:
        return [minimum]
    ratio = maximum / minimum
    return [
        _quantize(minimum * (ratio ** (Decimal(index) / Decimal(samples - 1))))
        for index in range(samples)
    ]


async def analyze(
    source_currency: str,
    target_currency: str,
    networks_factory,
    *,
    min_amount: Decimal,
    max_amount: Decimal,
    profile: DecisionProfile = DecisionProfile.BALANCED,
    samples: int = DEFAULT_SAMPLES,
    refine_steps: int = DEFAULT_REFINE_STEPS,
) -> BreakevenReport:
    """Locate the amounts where the winning route changes.

    ``samples`` sets the coarse scan; ``refine_steps`` bisections are then
    spent on each boundary found. Provider load is
    ``samples + boundaries * refine_steps`` graph builds, not one per unit of
    precision.
    """
    if min_amount <= 0 or max_amount <= 0:
        raise ValueError("amounts must be greater than zero")
    if min_amount >= max_amount:
        raise ValueError("min_amount must be below max_amount")
    if samples < 2:
        raise ValueError("samples must be at least 2")
    if refine_steps < 0:
        raise ValueError("refine_steps cannot be negative")

    builds = 0

    async def winner_at(amount: Decimal) -> Route | None:
        nonlocal builds
        builds += 1
        session = await build_session(
            source_currency,
            target_currency,
            str(amount),
            networks=networks_factory(),
        )
        return select_route_for_profile(
            session.router,
            session.source_currency,
            session.target_currency,
            session.amount,
            profile,
        )

    scanned: list[tuple[Decimal, Route | None]] = []
    for amount in _log_spaced(min_amount, max_amount, samples):
        scanned.append((amount, await winner_at(amount)))

    crossovers: list[Crossover] = []
    for (low_amount, low_route), (high_amount, high_route) in zip(
        scanned, scanned[1:], strict=False
    ):
        if low_route is None or high_route is None:
            continue
        if route_signature(low_route) == route_signature(high_route):
            continue
        crossovers.append(
            await _bisect(
                low_amount,
                low_route,
                high_amount,
                high_route,
                winner_at,
                refine_steps,
            )
        )

    regions = _regions_from(scanned, crossovers, min_amount, max_amount)
    return BreakevenReport(
        source_currency=source_currency.strip().upper(),
        target_currency=target_currency.strip().upper(),
        profile=profile,
        min_amount=min_amount,
        max_amount=max_amount,
        regions=tuple(regions),
        crossovers=tuple(crossovers),
        builds=builds,
        caveats=_caveats_for(regions, crossovers, scanned),
    )


async def _bisect(
    low_amount: Decimal,
    low_route: Route,
    high_amount: Decimal,
    high_route: Route,
    winner_at,
    refine_steps: int,
) -> Crossover:
    """Narrow the bracket that contains a change of winner."""
    below = route_signature(low_route)
    above = route_signature(high_route)
    low, high = low_amount, high_amount

    for _ in range(refine_steps):
        midpoint = _quantize((low + high) / 2)
        if midpoint <= low or midpoint >= high:
            break  # the bracket is already narrower than a cent
        route = await winner_at(midpoint)
        if route is None:
            break  # no route at the midpoint: the bracket cannot be narrowed honestly
        if route_signature(route) == below:
            low = midpoint
        else:
            above = route_signature(route)
            high = midpoint

    return Crossover(
        amount=high,
        bracket_low=low,
        bracket_high=high,
        below=below,
        above=above,
    )


def _regions_from(
    scanned: list[tuple[Decimal, Route | None]],
    crossovers: list[Crossover],
    min_amount: Decimal,
    max_amount: Decimal,
) -> list[AmountRegion]:
    routed = [(amount, route) for amount, route in scanned if route is not None]
    if not routed:
        return []

    boundaries = [min_amount, *(crossover.amount for crossover in crossovers), max_amount]
    regions: list[AmountRegion] = []
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        if start >= end:
            continue
        # Represent the region with a sample that actually falls inside it.
        inside = [route for amount, route in routed if start <= amount < end]
        representative = inside[0] if inside else routed[-1][1]
        regions.append(AmountRegion(amount_start=start, amount_end=end, route=representative))

    merged: list[AmountRegion] = []
    for region in regions:
        if merged and merged[-1].signature == region.signature:
            merged[-1] = AmountRegion(
                amount_start=merged[-1].amount_start,
                amount_end=region.amount_end,
                route=merged[-1].route,
            )
        else:
            merged.append(region)
    return merged


def _caveats_for(
    regions: list[AmountRegion],
    crossovers: list[Crossover],
    scanned: list[tuple[Decimal, Route | None]],
) -> tuple[str, ...]:
    caveats: list[str] = []

    if crossovers:
        widest = max(crossovers, key=lambda crossover: crossover.bracket_width)
        caveats.append(
            "A crossover is a bracket, not an exact figure: the widest one here "
            f"is only known to within {_quantize(widest.bracket_width)} "
            "(between "
            f"{_quantize(widest.bracket_low)} and {_quantize(widest.bracket_high)}). "
            "Bisection narrows it; it never resolves it to a single amount."
        )
    else:
        caveats.append(
            "No crossover was found in this range. One may still exist outside "
            "it, or between two sampled amounts if the winner changes and "
            "changes back within a single step."
        )

    if any(
        hop.fee_data_source is DataSource.ESTIMATED
        for region in regions
        for hop in region.route.hops
    ):
        caveats.append(
            "Some fees on these routes are scenario assumptions, so the "
            "crossover they produce is a property of the model, not a "
            "measured market boundary."
        )

    caveats.append(
        "Each sampled amount is quoted independently. A live provider can "
        "differ between samples for reasons unrelated to the amount, and any "
        "pricing tier the quote does not expose is invisible here."
    )

    unroutable = [amount for amount, route in scanned if route is None]
    if unroutable:
        caveats.append(
            f"{len(unroutable)} of {len(scanned)} sampled amounts had no route "
            "at all and were skipped; the smallest was "
            f"{_quantize(min(unroutable))}."
        )

    return tuple(caveats)
