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

from payment_router.analysis import CaveatTemplate, RouteSignature, route_signature
from payment_router.core.models import DataSource, Route
from payment_router.decision import DecisionProfile
from payment_router.service import (
    BuildWarning,
    RoutingRequestError,
    build_session,
    merge_warnings,
    select_route_for_profile,
)

DEFAULT_SAMPLES = 12
DEFAULT_REFINE_STEPS = 6
_CENT = Decimal("0.01")

_BRACKET = CaveatTemplate(
    "breakeven.bracket",
    "A crossover is a bracket, not an exact figure: the widest one here is only "
    "known to within {width} (between {low} and {high}). Bisection narrows it; "
    "it never resolves it to a single amount.",
)
_NO_CROSSOVER = CaveatTemplate(
    "breakeven.no_crossover",
    "No crossover was found in this range. One may still exist outside it, or "
    "between two sampled amounts if the winner changes and changes back within "
    "a single step.",
)
_ESTIMATED_FEES = CaveatTemplate(
    "breakeven.estimated_fees",
    "Some fees on these routes are scenario assumptions, so the crossover they "
    "produce is a property of the model, not a measured market boundary.",
)
_INDEPENDENT_QUOTES = CaveatTemplate(
    "breakeven.independent_quotes",
    "Each sampled amount is quoted independently. A live provider can differ "
    "between samples for reasons unrelated to the amount, and any pricing tier "
    "the quote does not expose is invisible here.",
)
_UNROUTABLE = CaveatTemplate(
    "breakeven.unroutable",
    "{count} of {total} sampled amounts had no route at all and were skipped; "
    "the smallest was {smallest}. Regions cover only amounts where a route was "
    "observed and never extend across those samples.",
)


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
    # Provider failures from every build, reported once each. A provider that
    # failed changes which route can win, so it must not vanish from a scan.
    warnings: tuple[BuildWarning, ...] = ()


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
        raise RoutingRequestError(
            f"The scan range's minimum ({min_amount}) must be below its maximum ({max_amount}).",
            code="range_order",
            min=min_amount,
            max=max_amount,
        )
    if samples < 2:
        raise ValueError("samples must be at least 2")
    if refine_steps < 0:
        raise ValueError("refine_steps cannot be negative")

    builds = 0
    warnings: list[tuple[BuildWarning, ...]] = []

    async def winner_at(amount: Decimal) -> Route | None:
        nonlocal builds
        builds += 1
        session = await build_session(
            source_currency,
            target_currency,
            str(amount),
            networks=networks_factory(),
        )
        warnings.append(session.warnings)
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
    # Bisection midpoints are observations too: a region is represented by a
    # sample that fell inside it, which may be one that bisection found.
    observed: list[tuple[Decimal, Route | None]] = list(scanned)
    for (low_amount, low_route), (high_amount, high_route) in zip(
        scanned, scanned[1:], strict=False
    ):
        if low_route is None or high_route is None:
            continue
        if route_signature(low_route) == route_signature(high_route):
            continue
        found, midpoints = await _bisect(
            low_amount,
            route_signature(low_route),
            high_amount,
            route_signature(high_route),
            winner_at,
            refine_steps,
        )
        crossovers.extend(found)
        observed.extend(midpoints)
    observed.sort(key=lambda sample: sample[0])

    regions = _regions_from(observed, crossovers, min_amount, max_amount)
    return BreakevenReport(
        source_currency=source_currency.strip().upper(),
        target_currency=target_currency.strip().upper(),
        profile=profile,
        min_amount=min_amount,
        max_amount=max_amount,
        regions=tuple(regions),
        crossovers=tuple(crossovers),
        builds=builds,
        caveats=_caveats_for(regions, crossovers, observed),
        warnings=merge_warnings(*warnings),
    )


async def _bisect(
    low_amount: Decimal,
    below: RouteSignature,
    high_amount: Decimal,
    above: RouteSignature,
    winner_at,
    refine_steps: int,
) -> tuple[list[Crossover], list[tuple[Decimal, Route | None]]]:
    """Bracket every change of winner between two routed samples.

    Returns the crossovers found and every midpoint observed on the way. A
    midpoint won by a third route proves the interval holds at least two
    changes of winner, so each half is located separately with the budget
    that remains; treating the first change as the only one would drop the
    second and label the third route's amounts with the wrong winner.
    """
    low, high = low_amount, high_amount
    observed: list[tuple[Decimal, Route | None]] = []

    for step in range(refine_steps):
        midpoint = _quantize((low + high) / 2)
        if midpoint <= low or midpoint >= high:
            break  # the bracket is already narrower than a cent
        route = await winner_at(midpoint)
        observed.append((midpoint, route))
        if route is None:
            break  # no route at the midpoint: the bracket cannot be narrowed honestly
        signature = route_signature(route)
        if signature == below:
            low = midpoint
        elif signature == above:
            high = midpoint
        else:
            remaining = refine_steps - step - 1
            left, left_observed = await _bisect(
                low, below, midpoint, signature, winner_at, remaining
            )
            right, right_observed = await _bisect(
                midpoint, signature, high, above, winner_at, remaining
            )
            return left + right, observed + left_observed + right_observed

    crossover = Crossover(
        amount=high,
        bracket_low=low,
        bracket_high=high,
        below=below,
        above=above,
    )
    return [crossover], observed


def _routed_runs(
    observed: list[tuple[Decimal, Route | None]],
) -> list[list[tuple[Decimal, Route]]]:
    """Split sorted samples into maximal runs of consecutive routable ones."""
    runs: list[list[tuple[Decimal, Route]]] = []
    current: list[tuple[Decimal, Route]] = []
    for amount, route in observed:
        if route is None:
            if current:
                runs.append(current)
            current = []
        else:
            current.append((amount, route))
    if current:
        runs.append(current)
    return runs


def _regions_from(
    observed: list[tuple[Decimal, Route | None]],
    crossovers: list[Crossover],
    min_amount: Decimal,
    max_amount: Decimal,
) -> list[AmountRegion]:
    """Build regions only across amounts where a route was actually observed.

    A sample with no route interrupts coverage: nothing is known about which
    route wins across it, so no region extends over it. The outer regions
    therefore start at the first routable sample and end at the last one,
    rather than claiming the requested bounds for amounts that never routed.
    """
    regions: list[AmountRegion] = []
    for run in _routed_runs(observed):
        run_start, run_end = run[0][0], run[-1][0]
        # The requested bounds only differ from the first and last samples by
        # cent rounding, so they are kept wherever those samples routed.
        start_bound = min_amount if run_start == observed[0][0] else run_start
        end_bound = max_amount if run_end == observed[-1][0] else run_end
        inner = [
            crossover.amount for crossover in crossovers if run_start < crossover.amount <= run_end
        ]
        boundaries = [start_bound, *inner, end_bound]

        run_regions: list[AmountRegion] = []
        pairs = list(zip(boundaries, boundaries[1:], strict=False))
        for index, (start, end) in enumerate(pairs):
            # The last region includes the run's final sample, so it may be a
            # single observed amount: a lone routable sample, or a crossover
            # that bisection could not move below that sample. Both are real
            # observations and must not be dropped for having zero width.
            if start > end or (start == end and index < len(pairs) - 1):
                continue
            # A crossover sits at or below the next sample, so the first
            # sample at or above a region's start is inside that region.
            representative = next(
                (route for amount, route in run if amount >= start),
                run[-1][1],
            )
            region = AmountRegion(amount_start=start, amount_end=end, route=representative)
            if run_regions and run_regions[-1].signature == region.signature:
                run_regions[-1] = AmountRegion(
                    amount_start=run_regions[-1].amount_start,
                    amount_end=end,
                    route=run_regions[-1].route,
                )
            else:
                run_regions.append(region)
        # Runs are never merged with each other: the unroutable sample between
        # them was observed, and bridging it would claim coverage it lacks.
        regions.extend(run_regions)
    return regions


def _caveats_for(
    regions: list[AmountRegion],
    crossovers: list[Crossover],
    observed: list[tuple[Decimal, Route | None]],
) -> tuple[str, ...]:
    caveats: list[str] = []

    if crossovers:
        widest = max(crossovers, key=lambda crossover: crossover.bracket_width)
        caveats.append(
            _BRACKET(
                width=_quantize(widest.bracket_width),
                low=_quantize(widest.bracket_low),
                high=_quantize(widest.bracket_high),
            )
        )
    else:
        caveats.append(_NO_CROSSOVER())

    if any(
        hop.fee_data_source is DataSource.ESTIMATED
        for region in regions
        for hop in region.route.hops
    ):
        caveats.append(_ESTIMATED_FEES())

    caveats.append(_INDEPENDENT_QUOTES())

    unroutable = [amount for amount, route in observed if route is None]
    if unroutable:
        caveats.append(
            _UNROUTABLE(
                count=len(unroutable),
                total=len(observed),
                smallest=_quantize(min(unroutable)),
            )
        )

    return tuple(caveats)
