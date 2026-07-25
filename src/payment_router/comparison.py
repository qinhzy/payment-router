"""Compare one corridor across two FX rate dates.

The question this answers is narrow on purpose: *how much of a route's cost
is the exchange-rate regime, rather than the fees and rails?* Only the FX
layer moves between the two runs. Scheme rules and scenario parameters are
date-independent assumptions, so they are identical on both sides, and
live-quoting providers are excluded from a historical run entirely (see
:func:`payment_router.service.networks_for_active_fx`) rather than
contributing today's prices to a past date.

That boundary is what keeps this a comparison of rate regimes and not a
reconstruction of what a transfer would actually have cost on a past day.
The simulator has no evidence for the latter and does not claim it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from payment_router.core import fx
from payment_router.core.models import Route
from payment_router.decision import DecisionProfile
from payment_router.service import (
    BuildWarning,
    RoutingRequestError,
    build_session,
    parse_amount,
    select_route_for_profile,
)


@dataclass(frozen=True, slots=True)
class ComparisonSide:
    """One corridor run under one rate source."""

    label: str
    mode: str
    rate_date: str | None
    requested_date: str | None
    detail: str
    route: Route | None
    warnings: tuple[BuildWarning, ...]
    mid_rate: Decimal | None


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    source_currency: str
    target_currency: str
    amount: Decimal
    profile: DecisionProfile
    baseline: ComparisonSide
    candidate: ComparisonSide
    caveats: tuple[str, ...]

    @property
    def fee_delta_usd(self) -> Decimal | None:
        return _delta(self.candidate.route, self.baseline.route, "total_fee_usd")

    @property
    def receive_delta(self) -> Decimal | None:
        return _delta(self.candidate.route, self.baseline.route, "final_amount")

    @property
    def time_delta_hours(self) -> Decimal | None:
        return _delta(self.candidate.route, self.baseline.route, "total_time_hours")

    @property
    def mid_rate_delta(self) -> Decimal | None:
        if self.baseline.mid_rate is None or self.candidate.mid_rate is None:
            return None
        return self.candidate.mid_rate - self.baseline.mid_rate

    @property
    def route_changed(self) -> bool:
        return _signature(self.baseline.route) != _signature(self.candidate.route)


def _delta(candidate: Route | None, baseline: Route | None, field: str) -> Decimal | None:
    if candidate is None or baseline is None:
        return None
    return getattr(candidate, field) - getattr(baseline, field)


def _signature(route: Route | None) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    if route is None:
        return None
    path = (route.source_currency, *(hop.to_node for hop in route.hops))
    return path, tuple(hop.network_name for hop in route.hops)


async def _run_side(
    label: str,
    source_currency: str,
    target_currency: str,
    raw_amount: str,
    networks_factory,
    profile: DecisionProfile,
) -> ComparisonSide:
    """Route the corridor against whatever FX source is currently active."""
    status = fx.current_status()
    try:
        mid_rate = fx.get_mid_rate(source_currency, target_currency)
    except fx.UnsupportedCurrencyError:
        mid_rate = None

    session = await build_session(
        source_currency,
        target_currency,
        raw_amount,
        networks=networks_factory(),
    )
    route = select_route_for_profile(
        session.router,
        session.source_currency,
        session.target_currency,
        session.amount,
        profile,
    )
    return ComparisonSide(
        label=label,
        mode=status.mode,
        rate_date=status.rate_date,
        requested_date=status.requested_date,
        detail=status.detail,
        route=route,
        warnings=session.warnings,
        mid_rate=mid_rate,
    )


async def compare_dates(
    source_currency: str,
    target_currency: str,
    raw_amount: str,
    networks_factory,
    *,
    on_date: str,
    against_date: str | None = None,
    profile: DecisionProfile = DecisionProfile.BALANCED,
    timeout_seconds: float = 10.0,
) -> ComparisonReport:
    """Route the corridor on ``on_date`` and against a baseline.

    ``against_date`` defaults to the latest published fixing. Both sides are
    routed with the same networks and the same profile, so every difference
    between them comes from the rate table.

    The active FX source is process state, so this restores whatever was
    active before it ran.
    """
    # Validate both dates before any network work: a malformed or future date
    # should fail immediately, not after fetching a baseline it will discard.
    fx.validate_date(on_date)
    if against_date is not None:
        fx.validate_date(against_date)

    # One side is always historical, so live-quoting providers cannot appear on
    # it. They must therefore be dropped from *both* sides: leaving them on the
    # baseline would let a provider-set difference masquerade as a rate effect
    # in the deltas.
    eligible_factory, excluded_networks = _comparable_networks(networks_factory)

    previous_status = fx.current_status()

    try:
        if against_date is None:
            baseline_status = fx.activate("live", timeout_seconds=timeout_seconds)
            if baseline_status.fallback:
                raise RoutingRequestError(
                    "A comparison baseline needs published rates, but live rates "
                    f"are unavailable: {baseline_status.detail}"
                )
            baseline_label = "latest"
        else:
            fx.activate("historical", on_date=against_date, timeout_seconds=timeout_seconds)
            baseline_label = against_date
        baseline = await _run_side(
            baseline_label,
            source_currency,
            target_currency,
            raw_amount,
            eligible_factory,
            profile,
        )

        fx.activate("historical", on_date=on_date, timeout_seconds=timeout_seconds)
        candidate = await _run_side(
            on_date,
            source_currency,
            target_currency,
            raw_amount,
            eligible_factory,
            profile,
        )
    finally:
        _restore(previous_status, timeout_seconds)

    return ComparisonReport(
        source_currency=source_currency.strip().upper(),
        target_currency=target_currency.strip().upper(),
        amount=parse_amount(raw_amount),
        profile=profile,
        baseline=baseline,
        candidate=candidate,
        caveats=_caveats_for(baseline, candidate, excluded_networks),
    )


def _comparable_networks(networks_factory):
    """Restrict both sides to providers that can answer for either date."""
    excluded = tuple(
        sorted(
            network.display_name()
            for network in networks_factory()
            if network.quotes_at_request_time()
        )
    )

    def factory():
        return [network for network in networks_factory() if not network.quotes_at_request_time()]

    return factory, excluded


def _restore(status: fx.FxStatus, timeout_seconds: float) -> None:
    if status.mode == "historical" and status.requested_date is not None:
        fx.activate("historical", on_date=status.requested_date, timeout_seconds=timeout_seconds)
    elif status.mode == "live":
        fx.activate("live", timeout_seconds=timeout_seconds)
    else:
        fx.activate("frozen")


def _caveats_for(
    baseline: ComparisonSide,
    candidate: ComparisonSide,
    excluded_networks: tuple[str, ...],
) -> tuple[str, ...]:
    caveats: list[str] = [
        "Only the FX table differs between the two runs. Fees, scheme rules, "
        "and scenario timings are date-independent assumptions, so this shows "
        "the effect of the rate regime, not what a transfer actually cost on "
        "that date."
    ]

    if excluded_networks:
        caveats.append(
            f"Excluded from both sides: {', '.join(excluded_networks)}. These "
            "providers quote at request time and have no rate for a past date. "
            "Dropping them from the baseline too keeps the two sides "
            "comparable, so the deltas reflect the rate regime rather than a "
            "difference in which providers were available."
        )

    for side in (baseline, candidate):
        if side.requested_date is not None and side.rate_date != side.requested_date:
            caveats.append(
                f"{side.requested_date} has no published ECB fixing "
                f"(weekend or holiday); {side.rate_date} is used instead."
            )

    return tuple(caveats)
