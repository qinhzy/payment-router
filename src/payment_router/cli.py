from __future__ import annotations

import asyncio
import ipaddress
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

from payment_router import breakeven, comparison, regime, sensitivity, service
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
from payment_router.visualizer import (
    format_amount,
    format_hours,
    route_to_mermaid,
    routes_to_comparison_table,
)

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


def _activate_fx(fx_mode: FxMode | None) -> fx.FxStatus | None:
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
    return status


def _is_loopback(host: str) -> bool:
    candidate = host.strip().strip("[]").lower()
    if candidate in {"localhost", ""}:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        # A hostname the CLI cannot resolve to a literal is not assumed local.
        return False


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


@app.command("sensitivity")
def sensitivity_command(
    from_currency: Annotated[str, typer.Argument(help="Source currency code.")],
    to_currency: Annotated[str, typer.Argument(help="Target currency code.")],
    amount: Annotated[str, typer.Argument(help="Amount to send.")],
    steps: Annotated[
        int,
        typer.Option("--steps", min=10, max=400, help="Sweep resolution across the weight axis."),
    ] = 100,
    fx_mode: Annotated[FxMode | None, _FX_OPTION] = None,
) -> None:
    """Sweep the cost/time preference and show where the best route flips."""
    _activate_fx(fx_mode)
    source_currency, target_currency, parsed_amount, router = _prepare_router(
        from_currency,
        to_currency,
        amount,
    )
    report = sensitivity.analyze(
        router,
        source_currency,
        target_currency,
        parsed_amount,
        steps=steps,
    )
    if not report.regions:
        _print_error(service.no_route_message(source_currency, target_currency, parsed_amount))
        raise typer.Exit(code=1)

    table = Table(
        title="Preference sweep · cost weight 0 (fastest) → 1 (cheapest)",
        header_style="bold white",
    )
    table.add_column("Cost weight", justify="right")
    table.add_column("Path", style="cyan")
    table.add_column("Networks")
    table.add_column("Fee", justify="right")
    table.add_column("ETA", justify="right")
    table.add_column("ETA range", justify="right", style="bright_blue")
    for region in report.regions:
        route = region.route
        path, networks = region.signature
        table.add_row(
            f"{region.cost_weight_start:.2f} – {region.cost_weight_end:.2f}",
            " → ".join(path),
            ", ".join(networks),
            f"${route.total_fee_usd.quantize(Decimal('0.01')):.2f}",
            f"{format_hours(route.total_time_hours)}h",
            f"{format_hours(route.total_time_min_hours)}–"
            f"{format_hours(route.total_time_max_hours)}h",
        )
    console.print(table)

    if report.balanced_region is not None:
        balanced_path, balanced_networks = report.balanced_region.signature
        console.print(
            Panel(
                f"The balanced (0.50) choice — {' → '.join(balanced_path)} via "
                f"{', '.join(dict.fromkeys(balanced_networks))} — holds for cost weights "
                f"{report.balanced_region.cost_weight_start:.2f}–"
                f"{report.balanced_region.cost_weight_end:.2f}.",
                title="Stability",
                border_style="green",
            )
        )
    if report.caveats:
        console.print(
            Panel(
                "\n".join(f"• {caveat}" for caveat in report.caveats),
                title="Timing caveats",
                border_style="yellow",
            ),
        )


@app.command("compare")
def compare_command(
    from_currency: Annotated[str, typer.Argument(help="Source currency code.")],
    to_currency: Annotated[str, typer.Argument(help="Target currency code.")],
    amount: Annotated[str, typer.Argument(help="Amount to send.")],
    on_date: Annotated[
        str,
        typer.Option("--on", help="Rate date to price the corridor at (YYYY-MM-DD)."),
    ],
    against: Annotated[
        str | None,
        typer.Option(
            "--against",
            help="Baseline rate date; defaults to the latest published fixing.",
        ),
    ] = None,
    prefer: Annotated[
        DecisionProfile,
        typer.Option("--prefer", help="Profile used on both sides of the comparison."),
    ] = DecisionProfile.BALANCED,
) -> None:
    """Compare one corridor across two ECB rate dates."""
    try:
        report = asyncio.run(
            comparison.compare_dates(
                from_currency,
                to_currency,
                amount,
                _instantiate_networks,
                on_date=on_date,
                against_date=against,
                profile=prefer,
            )
        )
    except (RoutingRequestError, ValueError) as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from None
    except fx.FxLiveUnavailableError as error:
        _print_error(f"Historical rates unavailable: {error}")
        raise typer.Exit(code=1) from None

    if report.baseline.route is None or report.candidate.route is None:
        _print_error(
            service.no_route_message(
                report.source_currency,
                report.target_currency,
                report.amount,
            )
        )
        raise typer.Exit(code=1)

    table = Table(
        title=(
            f"{report.source_currency} → {report.target_currency} "
            f"{format_amount(report.amount)} · {report.profile.value}"
        ),
        header_style="bold white",
    )
    table.add_column("Rate date")
    table.add_column("Mid-rate", justify="right")
    table.add_column("Route", style="cyan")
    table.add_column("Networks")
    table.add_column("Fee (USD)", justify="right")
    table.add_column("ETA", justify="right")
    table.add_column("Recipient gets", justify="right")

    for side in (report.baseline, report.candidate):
        route = side.route
        path = " → ".join([route.source_currency, *(hop.to_node for hop in route.hops)])
        networks = ", ".join(dict.fromkeys(hop.network_name for hop in route.hops))
        table.add_row(
            _rate_date_label(side),
            f"{side.mid_rate:.6f}" if side.mid_rate is not None else "—",
            path,
            networks,
            f"${route.total_fee_usd.quantize(Decimal('0.01')):.2f}",
            f"{format_hours(route.total_time_hours)}h",
            f"{format_amount(route.final_amount)} {route.target_currency}",
        )
    console.print(table)

    delta_lines = [
        f"Mid-rate: {_signed(report.mid_rate_delta, 6)}",
        f"Fee: {_signed(report.fee_delta_usd, 2)} USD",
        f"Recipient gets: {_signed(report.receive_delta, 2)} {report.target_currency}",
    ]
    if report.route_changed:
        delta_lines.append("The winning route differs between the two dates.")
    console.print(
        Panel(
            "\n".join(delta_lines),
            title=f"Change from {report.baseline.label} to {report.candidate.label}",
            border_style="green",
        )
    )
    console.print(
        Panel(
            "\n".join(f"• {caveat}" for caveat in report.caveats),
            title="What this does and does not show",
            border_style="yellow",
        )
    )


def _rate_date_label(side) -> str:
    if side.requested_date is not None and side.rate_date != side.requested_date:
        return f"{side.rate_date} (asked {side.requested_date})"
    return side.rate_date or side.label


def _signed(value, places: int) -> str:
    if value is None:
        return "—"
    quantum = Decimal(1).scaleb(-places)
    rounded = value.quantize(quantum)
    return f"+{rounded}" if rounded >= 0 else str(rounded)


@app.command("breakeven")
def breakeven_command(
    from_currency: Annotated[str, typer.Argument(help="Source currency code.")],
    to_currency: Annotated[str, typer.Argument(help="Target currency code.")],
    min_amount: Annotated[str, typer.Option("--min", help="Smallest amount to test.")] = "10",
    max_amount: Annotated[str, typer.Option("--max", help="Largest amount to test.")] = "100000",
    samples: Annotated[
        int,
        typer.Option("--samples", min=2, max=40, help="Coarse scan resolution."),
    ] = breakeven.DEFAULT_SAMPLES,
    refine: Annotated[
        int,
        typer.Option("--refine", min=0, max=20, help="Bisection steps per boundary."),
    ] = breakeven.DEFAULT_REFINE_STEPS,
    prefer: Annotated[
        DecisionProfile,
        typer.Option("--prefer", help="Profile applied at every amount."),
    ] = DecisionProfile.BALANCED,
    fx_mode: Annotated[FxMode | None, _FX_OPTION] = None,
) -> None:
    """Find the amounts at which the best route changes."""
    _activate_fx(fx_mode)
    try:
        low = service.parse_amount(min_amount)
        high = service.parse_amount(max_amount)
        report = asyncio.run(
            breakeven.analyze(
                from_currency,
                to_currency,
                _instantiate_networks,
                min_amount=low,
                max_amount=high,
                profile=prefer,
                samples=samples,
                refine_steps=refine,
            )
        )
    except (RoutingRequestError, ValueError) as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from None

    if not report.regions:
        _print_error(
            f"No route found from {report.source_currency} to "
            f"{report.target_currency} at any tested amount."
        )
        raise typer.Exit(code=1)

    table = Table(
        title=(
            f"{report.source_currency} → {report.target_currency} · "
            f"{report.profile.value} · best route by amount"
        ),
        header_style="bold white",
    )
    table.add_column("Amount range", justify="right")
    table.add_column("Best route", style="cyan")
    table.add_column("Networks")
    for region in report.regions:
        path, networks = region.signature
        table.add_row(
            f"{format_amount(region.amount_start)} – {format_amount(region.amount_end)}",
            " → ".join(path),
            ", ".join(dict.fromkeys(networks)),
        )
    console.print(table)

    if report.crossovers:
        lines = []
        for crossover in report.crossovers:
            below = ", ".join(dict.fromkeys(crossover.below[1]))
            above = ", ".join(dict.fromkeys(crossover.above[1]))
            lines.append(
                f"{below} → {above} somewhere in "
                f"{format_amount(crossover.bracket_low)}–"
                f"{format_amount(crossover.bracket_high)} "
                f"{report.source_currency}"
            )
        console.print(
            Panel(
                "\n".join(lines),
                title="Crossovers",
                border_style="green",
            )
        )

    console.print(
        Panel(
            "\n".join(f"• {caveat}" for caveat in report.caveats),
            title=f"What this does and does not show ({report.builds} quote rounds)",
            border_style="yellow",
        )
    )


@app.command("regime")
def regime_command(
    from_currency: Annotated[str, typer.Argument(help="Source currency code.")],
    to_currency: Annotated[str, typer.Argument(help="Target currency code.")],
    min_amount: Annotated[str, typer.Option("--min", help="Smallest amount to test.")] = "10",
    max_amount: Annotated[str, typer.Option("--max", help="Largest amount to test.")] = "100000",
    amount_samples: Annotated[
        int,
        typer.Option(
            "--amount-samples",
            min=2,
            max=40,
            help="Geometrically spaced amount columns.",
        ),
    ] = regime.DEFAULT_AMOUNT_SAMPLES,
    weight_steps: Annotated[
        int,
        typer.Option(
            "--weight-steps",
            min=10,
            max=400,
            help="Intervals across the cost/time weight axis.",
        ),
    ] = regime.DEFAULT_WEIGHT_STEPS,
    fx_mode: Annotated[FxMode | None, _FX_OPTION] = None,
) -> None:
    """Map the winning route across amount and cost/time preference."""
    _activate_fx(fx_mode)
    try:
        report = asyncio.run(
            regime.analyze(
                from_currency,
                to_currency,
                _instantiate_networks,
                min_amount=service.parse_amount(min_amount),
                max_amount=service.parse_amount(max_amount),
                amount_samples=amount_samples,
                weight_steps=weight_steps,
            )
        )
    except (RoutingRequestError, ValueError) as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from None

    if not report.winners:
        _print_error(
            f"No route found from {report.source_currency} to "
            f"{report.target_currency} in any sampled cell."
        )
        raise typer.Exit(code=1)

    symbols = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    colors = (
        "cyan",
        "green",
        "magenta",
        "yellow",
        "bright_green",
        "bright_red",
        "bright_blue",
        "red",
    )
    winner_styles = {
        winner.signature: (
            symbols[index] if index < len(symbols) else "?",
            colors[index] if index < len(colors) else "white",
        )
        for index, winner in enumerate(report.winners)
    }

    table = Table(
        title=(
            f"Regime map · {report.source_currency} → {report.target_currency} · "
            "x = amount (log), y = cost weight"
        ),
        header_style="bold white",
        show_lines=False,
    )
    table.add_column("α", justify="right", no_wrap=True)
    for index in range(len(report.amounts)):
        table.add_column(str(index + 1), justify="center", no_wrap=True)

    # Collapse consecutive weights that produce an identical row. The default
    # 60 steps would otherwise print 61 near-identical lines for a map whose
    # entire content is often a single region, which scrolls off any terminal.
    # `sensitivity` and `breakeven` compress their axes the same way. Every
    # weight is still sampled; only the display is merged.
    runs: list[tuple[int, int]] = []
    for weight_index in range(len(report.cost_weights) - 1, -1, -1):
        if runs and report.grid[runs[-1][1]] == report.grid[weight_index]:
            runs[-1] = (runs[-1][0], weight_index)
        else:
            runs.append((weight_index, weight_index))

    for high_index, low_index in runs:
        high = report.cost_weights[high_index]
        low = report.cost_weights[low_index]
        label = f"{high:.2f}" if high_index == low_index else f"{low:.2f}–{high:.2f}"
        cells: list[Text | str] = [label]
        for signature in report.grid[high_index]:
            if signature is None:
                cells.append(Text("·", style="dim"))
                continue
            symbol, color = winner_styles[signature]
            cells.append(Text(symbol, style=f"bold {color}"))
        table.add_row(*cells)
    console.print(table)
    console.print(
        f"{len(report.cost_weights)} sampled cost weights, "
        f"shown as {len(runs)} distinct row{'' if len(runs) == 1 else 's'}; "
        "identical neighbours are merged.",
        style="dim",
    )

    amount_key = " · ".join(
        f"{index + 1}={format_amount(amount)}" for index, amount in enumerate(report.amounts)
    )
    console.print(
        Panel(
            amount_key,
            title=f"Amount samples ({report.source_currency}, logarithmic spacing)",
            border_style="blue",
        )
    )

    legend = Table(
        title=f"Legend · {len(report.regions)} connected regions",
        header_style="bold white",
    )
    legend.add_column("Key", justify="center")
    legend.add_column("Path", style="cyan")
    legend.add_column("Networks")
    for winner in report.winners:
        symbol, color = winner_styles[winner.signature]
        path, networks = winner.signature
        legend.add_row(
            Text(symbol, style=f"bold {color}"),
            " → ".join(path),
            ", ".join(dict.fromkeys(networks)),
        )
    console.print(legend)

    console.print(
        Panel(
            "\n".join(f"• {caveat}" for caveat in report.caveats),
            title=f"Sampling caveats ({report.builds} graph builds)",
            border_style="yellow",
        )
    )


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
    fx_refresh_minutes: Annotated[
        float,
        typer.Option(
            "--fx-refresh-minutes",
            min=0,
            help=(
                "How often to re-check live ECB rates while serving. "
                "0 disables refreshing. Ignored unless --fx live is active."
            ),
        ),
    ] = 30.0,
) -> None:
    """Launch the local web console (requires the 'web' extra)."""
    status = _activate_fx(fx_mode)
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
    if not _is_loopback(host):
        console.print(
            Panel(
                f"Binding {host} exposes this console beyond your machine. It has no "
                "authentication, it issues outbound provider requests on behalf of "
                "whoever reaches it, and — when Anthropic credentials are present — "
                "it will spend them for anyone who opens the AI panel. It is built "
                "as a local tool, not a deployment target.",
                title="Non-local bind",
                border_style="yellow",
            )
        )
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    if status is not None and status.mode == "live" and fx_refresh_minutes > 0:
        console.print(f"Re-checking ECB rates every {fx_refresh_minutes:g} min", style="dim")
    uvicorn.run(
        create_app(fx_refresh_seconds=fx_refresh_minutes * 60.0),
        host=host,
        port=port,
        log_level="info",
    )


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
    if route.total_time_min_hours != route.total_time_max_hours:
        summary.append("Time range: ", style="white")
        summary.append(
            f"{format_hours(route.total_time_min_hours)}–"
            f"{format_hours(route.total_time_max_hours)} hours\n",
            style="bright_blue",
        )
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
