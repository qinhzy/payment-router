from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from enum import StrEnum
from importlib.metadata import version as distribution_version
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from payment_router import service
from payment_router.core import fx
from payment_router.decision import (
    DecisionProfile,
    RouteDecision,
    build_decision_board,
    summarize_tradeoff,
)
from payment_router.networks.base import PaymentNetwork
from payment_router.provenance import PROVENANCE_RECORDS
from payment_router.router import PaymentRouter
from payment_router.service import BuildWarning, RoutingRequestError
from payment_router.visualizer import format_hours, route_to_mermaid, routes_to_comparison_table

app = typer.Typer(
    help="Teaching-oriented CLI simulator for cross-border payment routing.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
console = Console()
error_console = Console(stderr=True)


class FxMode(StrEnum):
    FROZEN = "frozen"
    LIVE = "live"


_FX_OPTION = typer.Option(
    "--fx",
    help="FX rate source: 'frozen' teaching table (default) or 'live' ECB reference rates.",
    case_sensitive=False,
)


def _activate_fx(fx_mode: FxMode | None) -> None:
    requested = (
        fx_mode.value
        if fx_mode is not None
        else os.environ.get(fx.FX_MODE_ENV_VAR, "frozen").strip().lower()
    )
    if requested not in {"frozen", "live"}:
        _print_error(f"Unknown FX mode: {requested}. Use 'frozen' or 'live'.")
        raise typer.Exit(code=1)

    status = fx.activate(requested)
    if status.fallback:
        console.print(Panel(status.detail, title="FX fallback", border_style="yellow"))
    elif status.mode == "live":
        line = f"FX: {status.label} · {status.rate_date} ({status.classification.value})"
        if status.stale:
            line += " · cached snapshot (refresh failed)"
        console.print(line, style="dim")


def _read_version() -> str:
    return distribution_version("payment-router")


def _version_callback(value: bool) -> None:
    if not value:
        return
    console.print(_read_version())
    raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed payment-router version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """remit command line entrypoint."""


@app.command("route")
def route_command(
    from_currency: Annotated[str, typer.Argument(help="Source currency code.")],
    to_currency: Annotated[str, typer.Argument(help="Target currency code.")],
    amount: Annotated[str, typer.Argument(help="Amount to send.")],
    prefer: Annotated[
        DecisionProfile,
        typer.Option(
            "--prefer",
            help="Route preference: cheapest, fastest, or balanced.",
            case_sensitive=False,
        ),
    ] = DecisionProfile.BALANCED,
    top_n: Annotated[
        int,
        typer.Option("--top-n", min=1, help="Number of candidate routes to display."),
    ] = 1,
    fx_mode: Annotated[FxMode | None, _FX_OPTION] = None,
) -> None:
    _activate_fx(fx_mode)
    source_currency, target_currency, parsed_amount, router = _prepare_router(
        from_currency,
        to_currency,
        amount,
    )
    if top_n == 1:
        route = service.select_route_for_profile(
            router,
            source_currency,
            target_currency,
            parsed_amount,
            prefer,
        )
        if route is None:
            _print_error(service.no_route_message(source_currency, target_currency, parsed_amount))
            raise typer.Exit(code=1)
        _render_route(route)
        return

    routes = router.find_all_routes(
        source_currency,
        target_currency,
        parsed_amount,
        service.preference_for_profile(prefer),
        top_n=top_n,
    )
    if not routes:
        _print_error(service.no_route_message(source_currency, target_currency, parsed_amount))
        raise typer.Exit(code=1)

    _render_route_comparison(routes, prefer)


@app.command("decide")
def decide_command(
    from_currency: Annotated[str, typer.Argument(help="Source currency code.")],
    to_currency: Annotated[str, typer.Argument(help="Target currency code.")],
    amount: Annotated[str, typer.Argument(help="Amount to send.")],
    show_diagrams: Annotated[
        bool,
        typer.Option("--show-diagrams", help="Render Mermaid diagrams for unique recommendations."),
    ] = False,
    fx_mode: Annotated[FxMode | None, _FX_OPTION] = None,
) -> None:
    """Compare cheapest, fastest, and balanced recommendations in one decision board."""
    _activate_fx(fx_mode)
    source_currency, target_currency, parsed_amount, router = _prepare_router(
        from_currency,
        to_currency,
        amount,
    )
    decisions = build_decision_board(
        router,
        source_currency,
        target_currency,
        parsed_amount,
    )
    if not decisions:
        _print_error(service.no_route_message(source_currency, target_currency, parsed_amount))
        raise typer.Exit(code=1)
    _render_decision_board(decisions, parsed_amount, show_diagrams=show_diagrams)


@app.command("networks")
def networks_command() -> None:
    networks = _instantiate_networks()
    table = Table(title="Available Networks", header_style="bold white")
    table.add_column("Network", style="bold cyan")
    table.add_column("Supported Currencies", style="white")

    for network in networks:
        currencies = ", ".join(sorted(network.supported_currencies()))
        table.add_row(_network_display_name(network), currencies)

    console.print(table)


@app.command("sources")
def sources_command() -> None:
    """Show the auditable source and assumption registry."""
    table = Table(title="Data Provenance Registry", header_style="bold white")
    table.add_column("Evidence ID", style="cyan", no_wrap=True)
    table.add_column("Network")
    table.add_column("Class")
    table.add_column("Checked")

    for record in PROVENANCE_RECORDS:
        table.add_row(
            record.evidence_id,
            record.network,
            record.classification.value,
            record.checked_on,
        )

    console.print(table)
    console.print(
        "References and caveats: "
        "https://github.com/qinhzy/payment-router/blob/main/docs/DATA_SOURCES.md"
    )


@app.command("serve")
def serve_command(
    host: Annotated[str, typer.Option("--host", help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535, help="Port to bind.")] = 8000,
    open_browser: Annotated[
        bool,
        typer.Option("--open/--no-open", help="Open the console in a browser after starting."),
    ] = False,
    fx_mode: Annotated[FxMode | None, _FX_OPTION] = None,
) -> None:
    """Launch the local web console (requires the 'web' extra)."""
    _activate_fx(fx_mode)
    try:
        import uvicorn

        from payment_router.web.app import create_app
    except ModuleNotFoundError:
        _print_error(
            "The web console requires the optional 'web' dependencies. "
            "Install them with: uv sync --extra web "
            "(or: pip install 'payment-router[web]')."
        )
        raise typer.Exit(code=1) from None

    url = f"http://{host}:{port}"
    console.print(f"Serving the payment-router console at {url}")
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


def _instantiate_networks() -> list[PaymentNetwork]:
    return service.default_networks()


def _prepare_router(
    from_currency: str,
    to_currency: str,
    amount: str,
) -> tuple[str, str, Decimal, PaymentRouter]:
    try:
        session = asyncio.run(
            service.build_session(
                from_currency,
                to_currency,
                amount,
                networks=_instantiate_networks(),
            )
        )
    except RoutingRequestError as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from None

    if session.warnings:
        _print_build_warnings(session.warnings)
    return session.source_currency, session.target_currency, session.amount, session.router


def _render_route(route) -> None:
    path_text = " -> ".join([route.source_currency, *[hop.to_node for hop in route.hops]])
    summary = Text()
    summary.append(f"Path: {path_text}\n", style="bold")
    summary.append("Total fee: ", style="white")
    summary.append(
        f"${route.total_fee_usd.quantize(Decimal('0.01')):.2f}\n",
        style=_fee_style(route.total_fee_usd),
    )
    summary.append("Total time: ", style="white")
    summary.append(f"{format_hours(route.total_time_hours)} hours\n", style="bright_blue")
    summary.append("Final amount: ", style="white")
    summary.append(
        f"{route.final_amount.quantize(Decimal('0.01')):.2f} {route.target_currency}",
        style="bold white",
    )
    console.print(Panel(summary, title="Selected Route", border_style="cyan"))

    if route.hops:
        hop_table = Table(title="Hop Breakdown", header_style="bold white")
        hop_table.add_column("Hop")
        hop_table.add_column("Network", style="cyan")
        hop_table.add_column("Pair")
        hop_table.add_column("Fee (USD)")
        hop_table.add_column("Time (h)", style="bright_blue")
        for index, hop in enumerate(route.hops, start=1):
            hop_table.add_row(
                str(index),
                hop.network_name,
                f"{hop.currency_in}->{hop.currency_out}",
                f"${hop.fee_usd.quantize(Decimal('0.01')):.2f}",
                format_hours(hop.time_hours),
            )
        console.print(hop_table)

    console.print(
        Panel(
            Syntax(route_to_mermaid(route), "mermaid"),
            title="Mermaid",
            border_style="blue",
        )
    )


def _render_route_comparison(routes, prefer: DecisionProfile) -> None:
    console.print(
        Panel(
            f"Showing top {len(routes)} routes for preference: {prefer.value}.",
            title="Route Comparison",
            border_style="cyan",
        )
    )
    console.print(routes_to_comparison_table(routes))
    for index, route in enumerate(routes, start=1):
        path = " -> ".join([route.source_currency, *[hop.to_node for hop in route.hops]])
        title = f"Route {index}: {path}"
        console.print(
            Panel(
                Syntax(route_to_mermaid(route), "mermaid"),
                title=title,
                border_style="blue",
            )
        )


def _render_decision_board(
    decisions: list[RouteDecision],
    amount: Decimal,
    *,
    show_diagrams: bool,
) -> None:
    first_route = decisions[0].route
    table = Table(
        title=(
            f"Decision Board · {amount} {first_route.source_currency}"
            f" → {first_route.target_currency}"
        ),
        header_style="bold white",
        show_lines=False,
    )
    table.add_column("Profile", style="bold")
    table.add_column("Path", style="cyan")
    table.add_column("Fee", justify="right")
    table.add_column("ETA", justify="right")
    table.add_column("Recipient gets", justify="right")
    table.add_column("Evidence")

    for decision in decisions:
        route = decision.route
        profile = decision.profile.value.title()
        if decision.profile is DecisionProfile.BALANCED:
            profile = f"★ {profile}"
        table.add_row(
            profile,
            " → ".join(decision.path),
            f"${route.total_fee_usd.quantize(Decimal('0.01')):.2f}",
            f"{format_hours(route.total_time_hours)}h",
            f"{route.final_amount.quantize(Decimal('0.01')):.2f} {route.target_currency}",
            decision.evidence,
            style="bold" if decision.profile is DecisionProfile.BALANCED else None,
        )
    console.print(table)

    tradeoff = summarize_tradeoff(decisions)
    if tradeoff is not None:
        if tradeoff.same_route_for_all_profiles:
            explanation = "One route wins on cost, speed, and the balanced profile."
        else:
            explanation = (
                "Balanced vs cheapest: "
                f"fee {tradeoff.balanced_fee_delta_usd:+.2f} USD, "
                f"time saved {tradeoff.balanced_hours_saved_vs_cheapest:+.3f}h, "
                f"recipient amount {tradeoff.balanced_receive_delta:+.2f} "
                f"{first_route.target_currency}."
            )
        console.print(Panel(explanation, title="Decision note", border_style="green"))

    if show_diagrams:
        rendered_signatures: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        for decision in decisions:
            if decision.signature in rendered_signatures:
                continue
            rendered_signatures.add(decision.signature)
            console.print(
                Panel(
                    Syntax(route_to_mermaid(decision.route), "mermaid"),
                    title=f"{decision.profile.value.title()} route",
                    border_style="blue",
                )
            )


def _network_display_name(network: PaymentNetwork) -> str:
    return service.network_display_name(network)


def _print_error(message: str) -> None:
    error_console.print(Panel(message, title="Error", border_style="red"))


def _print_build_warnings(build_warnings: tuple[BuildWarning, ...]) -> None:
    warning_table = Table(title="Provider Warnings", header_style="bold yellow")
    warning_table.add_column("Network")
    warning_table.add_column("Pair")
    warning_table.add_column("Reason")

    for warning in build_warnings:
        warning_table.add_row(
            warning.network,
            f"{warning.from_currency}->{warning.to_currency}",
            warning.reason,
        )

    console.print(warning_table)


def _fee_style(fee_usd: Decimal) -> str:
    if fee_usd <= Decimal("10"):
        return "green3"
    if fee_usd <= Decimal("50"):
        return "spring_green3"
    if fee_usd <= Decimal("100"):
        return "yellow3"
    return "red3"
