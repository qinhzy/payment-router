"""FastAPI application serving the routing API and the static web console."""

from __future__ import annotations

import asyncio
import json
import time
from asyncio import Lock
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Annotated, Literal, Protocol

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from payment_router import breakeven, comparison, regime, sensitivity, service
from payment_router.core import fx
from payment_router.decision import DecisionProfile, build_decision_board, summarize_tradeoff
from payment_router.networks.base import PaymentNetwork
from payment_router.provenance import PROVENANCE_RECORDS
from payment_router.web import schemas

NetworksFactory = Callable[[], list[PaymentNetwork]]

STATIC_DIR = Path(__file__).parent / "static"

DISCLAIMER = (
    "Teaching and research simulator. Quotes are illustrative and must never "
    "be used to initiate or promise a real payment."
)

DEFAULT_QUOTE_TTL_SECONDS = 60.0
DEFAULT_FX_REFRESH_SECONDS = 30 * 60.0
"""How often a long-running console re-checks the live ECB source.

ECB publishes once per business day, so this only needs to be frequent
enough to notice a new publication within the working day, not to track a
market. A refresh is skipped entirely unless the active source is live and
was fetched before today.
"""

_CurrencyParam = Annotated[str, Query(min_length=3, max_length=3)]
_AmountParam = Annotated[str, Query(description="Amount to send, as a decimal string.")]

_CacheKey = tuple[str, str, str, int]


class Explainer(Protocol):
    """The AI explainer surface the app depends on (see ``web.ai``)."""

    @property
    def model(self) -> str: ...

    def stream_explanation(
        self,
        kind: str,
        payload: dict[str, object],
        lang: str,
    ) -> AsyncIterator[str]: ...


ExplainerFactory = Callable[[], "Explainer | None"]


def _default_explainer() -> Explainer | None:
    from payment_router.web.ai import AIExplainer

    return AIExplainer.try_create()


class ExplainRequest(BaseModel):
    kind: Literal["route", "decide", "sensitivity", "compare", "breakeven", "regime"]
    data: dict[str, object]
    lang: str = Field(default="en", max_length=35)


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    session: service.RoutingSession
    built_monotonic: float
    quoted_at: datetime


class _SessionCache:
    """Short-lived cache of built routing sessions.

    Switching preference or top-N in the console re-queries the same corridor;
    reusing the freshly built graph avoids hammering live providers. Only
    successful builds are cached, and a TTL of zero disables caching entirely.
    """

    def __init__(self, ttl_seconds: float, max_entries: int = 8) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[_CacheKey, _CacheEntry] = {}
        self._locks: dict[_CacheKey, Lock] = {}

    def _fresh_entry(self, key: _CacheKey) -> _CacheEntry | None:
        if self._ttl_seconds <= 0:
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.built_monotonic >= self._ttl_seconds:
            return None
        return entry

    @staticmethod
    def _build_entry(session: service.RoutingSession) -> _CacheEntry:
        return _CacheEntry(
            session=session,
            built_monotonic=time.monotonic(),
            quoted_at=datetime.now(UTC),
        )

    async def get(
        self,
        key: _CacheKey,
        builder: Callable[[], Awaitable[service.RoutingSession]],
    ) -> tuple[_CacheEntry, bool]:
        if self._ttl_seconds <= 0:
            return self._build_entry(await builder()), False

        entry = self._fresh_entry(key)
        if entry is not None:
            return entry, True

        lock = self._locks.setdefault(key, Lock())
        try:
            async with lock:
                entry = self._fresh_entry(key)
                if entry is not None:
                    return entry, True

                entry = self._build_entry(await builder())
                self._entries[key] = entry
                while len(self._entries) > self._max_entries:
                    oldest_key = min(
                        self._entries,
                        key=lambda cached: self._entries[cached].built_monotonic,
                    )
                    del self._entries[oldest_key]
                    if oldest_key != key:
                        self._locks.pop(oldest_key, None)
                return entry, False
        finally:
            # Failed builds never cache; drop their lock so keys that can
            # never succeed do not accumulate entries in the lock table.
            if key not in self._entries:
                self._locks.pop(key, None)


async def refresh_live_fx_once() -> bool:
    """Re-fetch the live ECB source when its snapshot predates today.

    Returns whether a refresh was attempted. ``fx.refresh_live`` will not
    replace the active source with anything worse, so a failed attempt leaves
    the console exactly as it was and the next tick tries again.
    """
    async with comparison.FX_SWITCH_LOCK:
        if fx.snapshot_is_current():
            return False
        await asyncio.to_thread(fx.refresh_live)
        return True


async def _fx_refresh_loop(interval_seconds: float) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await refresh_live_fx_once()
        except Exception:
            # A refresh is best-effort; never take the console down for it.
            continue


def create_app(
    networks_factory: NetworksFactory = service.default_networks,
    quote_ttl_seconds: float = DEFAULT_QUOTE_TTL_SECONDS,
    explainer_factory: ExplainerFactory = _default_explainer,
    fx_refresh_seconds: float = DEFAULT_FX_REFRESH_SECONDS,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Only a live source can go out of date: the frozen table has no date
        # and a historical fixing never changes.
        refresher = (
            asyncio.create_task(_fx_refresh_loop(fx_refresh_seconds))
            if fx_refresh_seconds > 0 and fx.current_status().mode == "live"
            else None
        )
        try:
            yield
        finally:
            if refresher is not None:
                refresher.cancel()
                with suppress(asyncio.CancelledError):
                    await refresher

    application = FastAPI(
        title="payment-router console",
        version=distribution_version("payment-router"),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    cache = _SessionCache(ttl_seconds=quote_ttl_seconds)
    explainer = explainer_factory()

    async def build_session(
        source: str,
        target: str,
        amount: str,
    ) -> tuple[service.RoutingSession, dict[str, object]]:
        try:
            # Validate up front so invalid amounts never reach the cache, and
            # normalize the scale so equivalent spellings ("100", "100.0",
            # "100.00") share one key instead of re-quoting every provider.
            canonical_amount = service.parse_amount(amount).normalize()
            normalized_source = source.strip().upper()
            normalized_target = target.strip().upper()
            while True:
                fx_generation = fx.generation()
                key = (
                    normalized_source,
                    normalized_target,
                    str(canonical_amount),
                    fx_generation,
                )
                entry, from_cache = await cache.get(
                    key,
                    lambda: service.build_session(
                        source,
                        target,
                        amount,
                        networks=networks_factory(),
                    ),
                )
                # A live refresh can finish while providers are quoting. Such
                # a graph may contain values derived from two FX generations;
                # discard it and coalesce a rebuild under the current one.
                if fx.generation() == fx_generation:
                    break
        except service.RoutingRequestError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        quotes_meta: dict[str, object] = {
            "quoted_at": entry.quoted_at.isoformat(timespec="seconds"),
            "from_cache": from_cache,
            "ttl_seconds": quote_ttl_seconds,
        }
        return entry.session, quotes_meta

    def no_route_error(session: service.RoutingSession) -> HTTPException:
        return HTTPException(
            status_code=404,
            detail=service.no_route_message(
                session.source_currency,
                session.target_currency,
                session.amount,
            ),
        )

    # The network roster cannot change over the app's lifetime; build it once.
    networks_snapshot = networks_factory()
    static_meta: dict[str, object] = {
        "version": application.version,
        "disclaimer": DISCLAIMER,
        "currencies": sorted(service.supported_currencies(networks_snapshot)),
        "networks": [
            {
                "name": network.display_name(),
                "currencies": sorted(network.supported_currencies()),
            }
            for network in networks_snapshot
        ],
        "profiles": [profile.value for profile in DecisionProfile],
        "ai": {
            "enabled": explainer is not None,
            "model": explainer.model if explainer is not None else None,
        },
    }
    sources_payload: dict[str, object] = {
        "records": [schemas.provenance_to_json(record) for record in PROVENANCE_RECORDS],
    }

    @application.get("/api/meta")
    async def meta() -> dict[str, object]:
        # The FX block is read per request, not snapshotted: the active source
        # is process state that a re-activation can change, and a disclosure
        # the console shows must not be able to drift from what routing uses.
        fx_status = fx.current_status()
        return {
            **static_meta,
            "fx": {
                "mode": fx_status.mode,
                "requested_mode": fx_status.requested_mode,
                "label": fx_status.label,
                "classification": fx_status.classification.value,
                "rate_date": fx_status.rate_date,
                "stale": fx_status.stale,
                "fallback": fx_status.fallback,
                "detail": fx_status.detail,
            },
        }

    @application.get("/api/route")
    async def route(
        source: _CurrencyParam,
        target: _CurrencyParam,
        amount: _AmountParam,
        profile: DecisionProfile = DecisionProfile.BALANCED,
        top_n: Annotated[int, Query(ge=1, le=10)] = 1,
    ) -> dict[str, object]:
        session, quotes_meta = await build_session(source, target, amount)
        if top_n == 1:
            selected = service.select_route_for_profile(
                session.router,
                session.source_currency,
                session.target_currency,
                session.amount,
                profile,
            )
            routes = [selected] if selected is not None else []
        else:
            routes = session.router.find_all_routes(
                session.source_currency,
                session.target_currency,
                session.amount,
                service.preference_for_profile(profile),
                top_n=top_n,
            )
        if not routes:
            raise no_route_error(session)
        return {
            "request": {
                "source": session.source_currency,
                "target": session.target_currency,
                "amount": str(session.amount),
                "profile": profile.value,
                "top_n": top_n,
            },
            "quotes": quotes_meta,
            "routes": [schemas.route_to_json(route) for route in routes],
            "warnings": [schemas.warning_to_json(warning) for warning in session.warnings],
        }

    @application.get("/api/decide")
    async def decide(
        source: _CurrencyParam,
        target: _CurrencyParam,
        amount: _AmountParam,
    ) -> dict[str, object]:
        session, quotes_meta = await build_session(source, target, amount)
        decisions = build_decision_board(
            session.router,
            session.source_currency,
            session.target_currency,
            session.amount,
        )
        if not decisions:
            raise no_route_error(session)
        tradeoff = summarize_tradeoff(decisions)
        return {
            "request": {
                "source": session.source_currency,
                "target": session.target_currency,
                "amount": str(session.amount),
            },
            "quotes": quotes_meta,
            "decisions": [schemas.decision_to_json(decision) for decision in decisions],
            "tradeoff": schemas.tradeoff_to_json(tradeoff) if tradeoff is not None else None,
            "warnings": [schemas.warning_to_json(warning) for warning in session.warnings],
        }

    @application.get("/api/sensitivity")
    async def sensitivity_endpoint(
        source: _CurrencyParam,
        target: _CurrencyParam,
        amount: _AmountParam,
        steps: Annotated[int, Query(ge=10, le=400)] = 100,
    ) -> dict[str, object]:
        session, quotes_meta = await build_session(source, target, amount)
        # A sweep runs `steps + 1` full route selections back to back. That is
        # CPU-bound work with no awaits, so running it inline would stall every
        # other request on the event loop for the whole sweep. The router and
        # its graph are read-only here, which makes the offload safe.
        report = await asyncio.to_thread(
            sensitivity.analyze,
            session.router,
            session.source_currency,
            session.target_currency,
            session.amount,
            steps=steps,
        )
        if not report.regions:
            raise no_route_error(session)
        return {
            "request": {
                "source": session.source_currency,
                "target": session.target_currency,
                "amount": str(session.amount),
                "steps": steps,
            },
            "quotes": quotes_meta,
            **schemas.sensitivity_to_json(report),
            "warnings": [schemas.warning_to_json(warning) for warning in session.warnings],
        }

    @application.get("/api/compare")
    async def compare(
        source: _CurrencyParam,
        target: _CurrencyParam,
        amount: _AmountParam,
        on: Annotated[str, Query(description="Rate date to price at (YYYY-MM-DD).")],
        against: Annotated[str | None, Query(description="Baseline rate date.")] = None,
        profile: DecisionProfile = DecisionProfile.BALANCED,
    ) -> dict[str, object]:
        # This switches the process-wide FX source while it runs, so it does
        # not share the session cache: those entries were built under whatever
        # source was active at the time and are not comparable across dates.
        try:
            report = await comparison.compare_dates(
                source,
                target,
                amount,
                networks_factory,
                on_date=on,
                against_date=against,
                profile=profile,
            )
        except service.RoutingRequestError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except fx.FxLiveUnavailableError as error:
            raise HTTPException(
                status_code=503,
                detail=f"Historical rates unavailable: {error}",
            ) from None

        if report.baseline.route is None or report.candidate.route is None:
            raise HTTPException(
                status_code=404,
                detail=service.no_route_message(
                    report.source_currency,
                    report.target_currency,
                    report.amount,
                ),
            )
        return schemas.comparison_to_json(report)

    @application.get("/api/breakeven")
    async def breakeven_endpoint(
        source: _CurrencyParam,
        target: _CurrencyParam,
        min_amount: Annotated[str, Query(alias="min", description="Smallest amount.")] = "10",
        max_amount: Annotated[str, Query(alias="max", description="Largest amount.")] = "100000",
        samples: Annotated[int, Query(ge=2, le=40)] = breakeven.DEFAULT_SAMPLES,
        refine: Annotated[int, Query(ge=0, le=20)] = breakeven.DEFAULT_REFINE_STEPS,
        profile: DecisionProfile = DecisionProfile.BALANCED,
    ) -> dict[str, object]:
        # Deliberately not cached: every sampled amount needs its own graph,
        # and the session cache is keyed by amount, so there is nothing to reuse.
        try:
            report = await breakeven.analyze(
                source,
                target,
                networks_factory,
                min_amount=service.parse_amount(min_amount),
                max_amount=service.parse_amount(max_amount),
                profile=profile,
                samples=samples,
                refine_steps=refine,
            )
        except service.RoutingRequestError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None

        if not report.regions:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No route found from {report.source_currency} to "
                    f"{report.target_currency} at any tested amount."
                ),
            )
        return schemas.breakeven_to_json(report)

    @application.get("/api/regime")
    async def regime_endpoint(
        source: _CurrencyParam,
        target: _CurrencyParam,
        min_amount: Annotated[str, Query(alias="min", description="Smallest amount.")] = "10",
        max_amount: Annotated[str, Query(alias="max", description="Largest amount.")] = "100000",
        amount_samples: Annotated[int, Query(ge=2, le=40)] = regime.DEFAULT_AMOUNT_SAMPLES,
        weight_steps: Annotated[int, Query(ge=10, le=400)] = regime.DEFAULT_WEIGHT_STEPS,
    ) -> dict[str, object]:
        # The amount loop performs asynchronous graph builds, while the nested
        # weight sweep is CPU-bound. Run the complete private event loop in a
        # worker so neither part can monopolize FastAPI's serving loop.
        def run_analysis() -> regime.RegimeMap:
            return asyncio.run(
                regime.analyze(
                    source,
                    target,
                    networks_factory,
                    min_amount=service.parse_amount(min_amount),
                    max_amount=service.parse_amount(max_amount),
                    amount_samples=amount_samples,
                    weight_steps=weight_steps,
                )
            )

        try:
            report = await asyncio.to_thread(run_analysis)
        except service.RoutingRequestError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None

        if not report.winners:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No route found from {report.source_currency} to "
                    f"{report.target_currency} in any sampled cell."
                ),
            )
        return schemas.regime_to_json(report)

    @application.post("/api/explain")
    async def explain(request: ExplainRequest) -> StreamingResponse:
        if explainer is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "AI explanations are not configured. Set ANTHROPIC_API_KEY "
                    "(or sign in with `ant auth login`) and restart the console."
                ),
            )

        def sse_event(event: dict[str, object]) -> str:
            return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        async def event_stream() -> AsyncIterator[str]:
            try:
                async for text in explainer.stream_explanation(
                    request.kind,
                    request.data,
                    request.lang,
                ):
                    yield sse_event({"type": "delta", "text": text})
                yield sse_event({"type": "done", "model": explainer.model})
            except Exception as error:
                yield sse_event({"type": "error", "message": str(error)[:500]})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @application.get("/api/sources")
    async def sources() -> dict[str, object]:
        return sources_payload

    application.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="console")
    return application
