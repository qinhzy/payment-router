from __future__ import annotations

from decimal import Decimal

from typer.testing import CliRunner

from payment_router.cli import app
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork

runner = CliRunner()


def _quote(
    network_name: str,
    fee_usd: str,
    time_hours: str,
    fx_rate: str,
    data_source: DataSource = DataSource.INDUSTRY_AVERAGE,
) -> NetworkQuote:
    return NetworkQuote(
        network_name=network_name,
        fee_usd=Decimal(fee_usd),
        time_hours=Decimal(time_hours),
        fx_rate=Decimal(fx_rate),
        data_source=data_source,
    )


class FakeNetwork(PaymentNetwork):
    def __init__(
        self,
        name: str,
        supported: set[str],
        quotes: dict[tuple[str, str], NetworkQuote | None | Exception],
    ) -> None:
        self._name = name
        self._supported = supported
        self._quotes = quotes

    async def get_quote(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        _ = amount
        result = self._quotes.get((from_currency, to_currency))
        if isinstance(result, Exception):
            raise result
        return result

    def supported_currencies(self) -> set[str]:
        return self._supported


def _stub_networks() -> list[PaymentNetwork]:
    return [
        FakeNetwork(
            "Wise",
            {"USD", "EUR", "GBP", "CNY"},
            {
                ("USD", "CNY"): _quote("Wise", "5", "1", "7.0", DataSource.VERIFIED),
                ("USD", "EUR"): _quote("Wise EUR", "2", "1", "0.8", DataSource.VERIFIED),
            },
        ),
        FakeNetwork(
            "SEPA",
            {"USD", "EUR", "CNY"},
            {
                ("EUR", "CNY"): _quote("SEPA Bridge", "3", "2", "9.0"),
            },
        ),
        FakeNetwork(
            "SWIFT",
            {"USD", "GBP", "CNY"},
            {
                ("USD", "CNY"): _quote("SWIFT", "20", "30", "6.8"),
                ("USD", "GBP"): _quote("SWIFT GBP", "4", "2", "0.7"),
                ("GBP", "CNY"): _quote("SWIFT CNY", "4", "2", "10.0"),
            },
        ),
    ]


def test_route_command_outputs_selected_route(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["route", "USD", "CNY", "100"])

    assert result.exit_code == 0
    assert "Selected Route" in result.output
    assert "Wise" in result.output
    assert "flowchart LR" in result.output


def test_route_command_cheapest_prefers_lower_fee_path(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["route", "USD", "CNY", "100", "--prefer=cheapest"])

    assert result.exit_code == 0
    assert "Wise" in result.output
    assert "SWIFT" not in result.output


def test_route_command_top_n_outputs_comparison_table(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["route", "USD", "CNY", "100", "--top-n=3"])

    assert result.exit_code == 0
    assert "| Route | Total Fee (USD) | Total Time (hours) | Final Amount | Path |" in result.output
    assert "Route 1" in result.output
    assert result.output.count("flowchart LR") == 3


def test_route_command_rejects_unsupported_currency(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["route", "USD", "XYZ", "100"])

    assert result.exit_code != 0
    assert "Unsupported currency code(s): XYZ" in result.output


def test_networks_command_lists_available_networks(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["networks"])

    assert result.exit_code == 0
    assert "Wise" in result.output
    assert "SEPA" in result.output
    assert "SWIFT" in result.output


def test_version_option_prints_project_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.output
