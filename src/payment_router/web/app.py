"""FastAPI application serving the routing API and the static web console."""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from payment_router import service
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

_CurrencyParam = Annotated[str, Query(min_length=3, max_length=3)]
_AmountParam = Annotated[str, Query(description="Amount to send, as a decimal string.")]


def create_app(networks_factory: NetworksFactory = service.default_networks) -> FastAPI:
    application = FastAPI(
        title="payment-router console",
        version=distribution_version("payment-router"),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    async def build_session(source: str, target: str, amount: str) -> service.RoutingSession:
        try:
            return await service.build_session(
                source,
                target,
                amount,
                networks=networks_factory(),
            )
        except service.RoutingRequestError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None

    def no_route_error(session: service.RoutingSession) -> HTTPException:
        return HTTPException(
            status_code=404,
            detail=(
                f"No route found from {session.source_currency} "
                f"to {session.target_currency} for {session.amount}."
            ),
        )

    @application.get("/api/meta")
    async def meta() -> dict[str, object]:
        networks = networks_factory()
        return {
            "version": application.version,
            "disclaimer": DISCLAIMER,
            "currencies": sorted(service.supported_currencies(networks)),
            "networks": [
                {
                    "name": service.network_display_name(network),
                    "currencies": sorted(network.supported_currencies()),
                }
                for network in networks
            ],
            "profiles": [profile.value for profile in DecisionProfile],
        }

    @application.get("/api/route")
    async def route(
        source: _CurrencyParam,
        target: _CurrencyParam,
        amount: _AmountParam,
        profile: DecisionProfile = DecisionProfile.BALANCED,
        top_n: Annotated[int, Query(ge=1, le=10)] = 1,
    ) -> dict[str, object]:
        session = await build_session(source, target, amount)
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
            "routes": [schemas.route_to_json(route) for route in routes],
            "warnings": [schemas.warning_to_json(warning) for warning in session.warnings],
        }

    @application.get("/api/decide")
    async def decide(
        source: _CurrencyParam,
        target: _CurrencyParam,
        amount: _AmountParam,
    ) -> dict[str, object]:
        session = await build_session(source, target, amount)
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
            "decisions": [schemas.decision_to_json(decision) for decision in decisions],
            "tradeoff": schemas.tradeoff_to_json(tradeoff) if tradeoff is not None else None,
            "warnings": [schemas.warning_to_json(warning) for warning in session.warnings],
        }

    @application.get("/api/sources")
    async def sources() -> dict[str, object]:
        return {
            "records": [schemas.provenance_to_json(record) for record in PROVENANCE_RECORDS],
        }

    application.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="console")
    return application
