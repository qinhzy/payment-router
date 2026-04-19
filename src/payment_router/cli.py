from __future__ import annotations

import asyncio
import tomllib
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from payment_router.core.graph import PaymentGraph
from payment_router.networks.base import PaymentNetwork
from payment_router.networks.sepa import SEPANetwork
from payment_router.networks.swift import SWIFTNetwork
from payment_router.networks.wise import WiseNetwork
from payment_router.router import PaymentRouter, RoutingPreference
from payment_router.visualizer import route_to_mermaid, routes_to_comparison_table

app = typer.Typer(
    help="Teaching-oriented CLI simulator for cross-border payment routing.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
console = Console()
error_console = Console(stderr=True)


class PreferenceName(StrEnum):
    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    BALANCED = "balanced"


def _read_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject_path.open("rb") as file:
        project_data = tomllib.load(file)
    return str(project_data["project"]["version"])


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
        PreferenceName,
        typer.Option(
            "--prefer",
            help="Route preference: cheapest, fastest, or balanced.",
            case_sensitive=False,
        ),
    ] = PreferenceName.BALANCED,
    top_n: Annotated[
        int,
        typer.Option("--top-n", min=1, help="Number of candidate routes to display."),
    ] = 1,
) -> None:
    source_currency = from_currency.strip().upper()
    target_currency = to_currency.strip().upper()
    parsed_amount = _parse_amount(amount)

    if parsed_amount is None:
        _print_error("Amount must be a valid decimal number.")
        raise typer.Exit(code=1)

    if parsed_amount <= 0:
        _print_error("Amount must be greater than zero.")
        raise typer.Exit(code=1)

    networks = _instantiate_networks()
    supported = _supported_currencies(networks)
    unsupported = [
        currency for currency in (source_currency, target_currency) if currency not in supported
    ]
    if unsupported:
        supported_list = ", ".join(sorted(supported))
        _print_error(
            "Unsupported currency code(s): "
            f"{', '.join(unsupported)}. Supported currencies: {supported_list}."
        )
        raise typer.Exit(code=1)

    graph = PaymentGraph(networks=networks, currencies=sorted(supported), amount=parsed_amount)
    asyncio.run(graph.build())

    if graph._build_errors:
        _print_build_warnings(graph._build_errors)

    router = PaymentRouter(graph)
    preference = _preference_from_name(prefer)

    if top_n == 1:
        route = _select_single_route(
            router,
            source_currency,
            target_currency,
            parsed_amount,
            prefer,
            preference,
        )
        if route is None:
            _print_error(
                f"No route found from {source_currency} to {target_currency} for {parsed_amount}."
            )
            raise typer.Exit(code=1)
        _render_route(route)
        return

    routes = router.find_all_routes(
        source_currency,
        target_currency,
        parsed_amount,
        preference,
        top_n=top_n,
    )
    if not routes:
        _print_error(
            f"No route found from {source_currency} to {target_currency} for {parsed_amount}."
        )
        raise typer.Exit(code=1)

    _render_route_comparison(routes, prefer)


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


def _instantiate_networks() -> list[PaymentNetwork]:
    return [WiseNetwork(), SEPANetwork(), SWIFTNetwork()]


def _supported_currencies(networks: list[PaymentNetwork]) -> set[str]:
    supported: set[str] = set()
    for network in networks:
        supported.update(currency.strip().upper() for currency in network.supported_currencies())
    return supported


def _parse_amount(raw_amount: str) -> Decimal | None:
    try:
        return Decimal(raw_amount)
    except InvalidOperation:
        return None


def _preference_from_name(prefer: PreferenceName) -> RoutingPreference:
    if prefer is PreferenceName.CHEAPEST:
        return RoutingPreference(cost_weight=1.0, time_weight=0.0)
    if prefer is PreferenceName.FASTEST:
        return RoutingPreference(cost_weight=0.0, time_weight=1.0)
    return RoutingPreference(cost_weight=0.5, time_weight=0.5)


def _select_single_route(
    router: PaymentRouter,
    source_currency: str,
    target_currency: str,
    amount: Decimal,
    prefer: PreferenceName,
    preference: RoutingPreference,
):
    if prefer is PreferenceName.CHEAPEST:
        return router.find_cheapest(source_currency, target_currency, amount)
    if prefer is PreferenceName.FASTEST:
        return router.find_fastest(source_currency, target_currency, amount)
    return router.find_route(source_currency, target_currency, amount, preference)


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
    summary.append(f"{_format_hours(route.total_time_hours)} hours\n", style="bright_blue")
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
                _format_hours(hop.time_hours),
            )
        console.print(hop_table)

    console.print(
        Panel(
            Syntax(route_to_mermaid(route), "mermaid"),
            title="Mermaid",
            border_style="blue",
        )
    )


def _render_route_comparison(routes, prefer: PreferenceName) -> None:
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


def _network_display_name(network: PaymentNetwork) -> str:
    explicit_name = getattr(network, "_name", None)
    if explicit_name:
        return str(explicit_name)

    class_name = type(network).__name__
    return class_name.removesuffix("Network") or class_name


def _print_error(message: str) -> None:
    error_console.print(Panel(message, title="Error", border_style="red"))


def _print_build_warnings(build_errors: list[tuple[str, str, str, Exception]]) -> None:
    warning_table = Table(title="Provider Warnings", header_style="bold yellow")
    warning_table.add_column("Network")
    warning_table.add_column("Pair")
    warning_table.add_column("Reason")

    for network_name, from_currency, to_currency, exception in build_errors:
        warning_table.add_row(network_name, f"{from_currency}->{to_currency}", str(exception))

    console.print(warning_table)


def _format_hours(hours: Decimal) -> str:
    normalized = format(hours.quantize(Decimal("0.001")).normalize(), "f")
    if "." not in normalized:
        return f"{normalized}.0"

    trimmed = normalized.rstrip("0").rstrip(".")
    return trimmed if "." in trimmed else f"{trimmed}.0"


def _fee_style(fee_usd: Decimal) -> str:
    if fee_usd <= Decimal("10"):
        return "green3"
    if fee_usd <= Decimal("50"):
        return "spring_green3"
    if fee_usd <= Decimal("100"):
        return "yellow3"
    return "red3"
