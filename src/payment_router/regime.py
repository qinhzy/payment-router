"""Map the winning route across amount and cost/time preference.

The two axes have deliberately different costs. Quotes depend on the amount,
so every amount column gets one freshly built graph. Cost/time preference does
not affect quotes, so all weights in that column reuse the same router. A map
with ``N`` amount samples therefore performs exactly ``N`` graph builds, not
one build per grid cell.

Cells are observations at the requested sample coordinates. Connected regions
use four-neighbour adjacency and are never interpolated or smoothed.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from payment_router.analysis import RouteSignature, route_signature
from payment_router.breakeven import _log_spaced
from payment_router.core.models import DataSource, Route
from payment_router.router import RoutingPreference
from payment_router.service import build_session

DEFAULT_AMOUNT_SAMPLES = 12
DEFAULT_WEIGHT_STEPS = 60


@dataclass(frozen=True, slots=True)
class RegimeWinner:
    """One distinct route signature observed anywhere in the grid."""

    signature: RouteSignature
    route: Route


@dataclass(frozen=True, slots=True)
class ConnectedRegion:
    """A four-neighbour connected component of cells with one signature."""

    region_id: int
    signature: RouteSignature
    cell_count: int
    amount_index_start: int
    amount_index_end: int
    weight_index_start: int
    weight_index_end: int


@dataclass(frozen=True, slots=True)
class RegimeMap:
    source_currency: str
    target_currency: str
    min_amount: Decimal
    max_amount: Decimal
    amounts: tuple[Decimal, ...]
    cost_weights: tuple[float, ...]
    # Weight-major rows, amount-major columns. ``None`` means no route won.
    grid: tuple[tuple[RouteSignature | None, ...], ...]
    # Same shape as ``grid``; IDs point into ``regions``.
    region_grid: tuple[tuple[int | None, ...], ...]
    winners: tuple[RegimeWinner, ...]
    regions: tuple[ConnectedRegion, ...]
    amount_samples: int
    weight_steps: int
    builds: int
    caveats: tuple[str, ...]


async def analyze(
    source_currency: str,
    target_currency: str,
    networks_factory,
    *,
    min_amount: Decimal,
    max_amount: Decimal,
    amount_samples: int = DEFAULT_AMOUNT_SAMPLES,
    weight_steps: int = DEFAULT_WEIGHT_STEPS,
) -> RegimeMap:
    """Sample the amount/weight plane without rebuilding along the weight axis."""
    if not min_amount.is_finite() or not max_amount.is_finite():
        raise ValueError("amounts must be finite")
    if min_amount <= 0 or max_amount <= 0:
        raise ValueError("amounts must be greater than zero")
    if min_amount >= max_amount:
        raise ValueError("min_amount must be below max_amount")
    if amount_samples < 2:
        raise ValueError("amount_samples must be at least 2")
    if weight_steps < 1:
        raise ValueError("weight_steps must be a positive integer")

    amounts = tuple(_log_spaced(min_amount, max_amount, amount_samples))
    cost_weights = tuple(index / weight_steps for index in range(weight_steps + 1))
    columns: list[list[Route | None]] = []
    winners_by_signature: dict[RouteSignature, Route] = {}

    # This loop order is the provider-load contract: one graph per amount,
    # followed by a free, in-memory preference sweep on that same router.
    for amount in amounts:
        session = await build_session(
            source_currency,
            target_currency,
            str(amount),
            networks=networks_factory(),
        )
        column: list[Route | None] = []
        for cost_weight in cost_weights:
            route = session.router.find_route(
                session.source_currency,
                session.target_currency,
                session.amount,
                RoutingPreference(
                    cost_weight=cost_weight,
                    time_weight=1.0 - cost_weight,
                ),
            )
            column.append(route)
            if route is not None:
                signature = route_signature(route)
                winners_by_signature.setdefault(signature, route)
        columns.append(column)

    grid = tuple(
        tuple(
            route_signature(columns[amount_index][weight_index])
            if columns[amount_index][weight_index] is not None
            else None
            for amount_index in range(len(amounts))
        )
        for weight_index in range(len(cost_weights))
    )
    regions, region_grid = _connected_regions(grid)
    winners = tuple(
        RegimeWinner(signature=signature, route=route)
        for signature, route in winners_by_signature.items()
    )

    return RegimeMap(
        source_currency=source_currency.strip().upper(),
        target_currency=target_currency.strip().upper(),
        min_amount=min_amount,
        max_amount=max_amount,
        amounts=amounts,
        cost_weights=cost_weights,
        grid=grid,
        region_grid=region_grid,
        winners=winners,
        regions=regions,
        amount_samples=amount_samples,
        weight_steps=weight_steps,
        builds=len(amounts),
        caveats=_caveats_for(grid, winners),
    )


def _connected_regions(
    grid: tuple[tuple[RouteSignature | None, ...], ...],
) -> tuple[tuple[ConnectedRegion, ...], tuple[tuple[int | None, ...], ...]]:
    """Label four-neighbour components without joining diagonal cells."""
    if not grid:
        return (), ()

    height = len(grid)
    width = len(grid[0])
    labels: list[list[int | None]] = [[None] * width for _ in range(height)]
    regions: list[ConnectedRegion] = []

    for weight_index in range(height):
        for amount_index in range(width):
            signature = grid[weight_index][amount_index]
            if signature is None or labels[weight_index][amount_index] is not None:
                continue

            region_id = len(regions)
            queue = deque([(weight_index, amount_index)])
            labels[weight_index][amount_index] = region_id
            cells: list[tuple[int, int]] = []

            while queue:
                current_weight, current_amount = queue.popleft()
                cells.append((current_weight, current_amount))
                for next_weight, next_amount in (
                    (current_weight - 1, current_amount),
                    (current_weight + 1, current_amount),
                    (current_weight, current_amount - 1),
                    (current_weight, current_amount + 1),
                ):
                    if not (0 <= next_weight < height and 0 <= next_amount < width):
                        continue
                    if labels[next_weight][next_amount] is not None:
                        continue
                    if grid[next_weight][next_amount] != signature:
                        continue
                    labels[next_weight][next_amount] = region_id
                    queue.append((next_weight, next_amount))

            weight_indices = [cell[0] for cell in cells]
            amount_indices = [cell[1] for cell in cells]
            regions.append(
                ConnectedRegion(
                    region_id=region_id,
                    signature=signature,
                    cell_count=len(cells),
                    amount_index_start=min(amount_indices),
                    amount_index_end=max(amount_indices),
                    weight_index_start=min(weight_indices),
                    weight_index_end=max(weight_indices),
                )
            )

    return tuple(regions), tuple(tuple(row) for row in labels)


def _caveats_for(
    grid: tuple[tuple[RouteSignature | None, ...], ...],
    winners: tuple[RegimeWinner, ...],
) -> tuple[str, ...]:
    caveats = [
        (
            "Region boundaries are sampled, not exact: along the amount axis a "
            "boundary is only known to lie between neighbouring quoted amounts, "
            "and along the preference axis between neighbouring cost weights. "
            "The map does not interpolate or smooth unsampled cells."
        )
    ]

    if any(
        hop.fee_data_source is DataSource.ESTIMATED
        for winner in winners
        for hop in winner.route.hops
    ):
        caveats.append(
            "Some fees on these routes are scenario assumptions, so the region "
            "boundaries they produce are properties of the model, not measured "
            "market boundaries."
        )

    caveats.append(
        "Each amount column is quoted independently. A live provider can differ "
        "between columns for reasons unrelated to the amount, and any pricing "
        "tier the quote does not expose is invisible here."
    )

    total_cells = sum(len(row) for row in grid)
    unroutable_cells = sum(cell is None for row in grid for cell in row)
    if unroutable_cells:
        caveats.append(
            f"{unroutable_cells} of {total_cells} sampled cells had no route and "
            "remain blank; they were not filled from neighbouring cells."
        )
    return tuple(caveats)
