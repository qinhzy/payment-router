from __future__ import annotations

from helpers import FakeNetwork, make_quote
from typer.testing import CliRunner

from payment_router.cli import _instantiate_networks, _network_display_name, app
from payment_router.core.models import DataSource
from payment_router.networks.base import PaymentNetwork

runner = CliRunner()


def _stub_networks() -> list[PaymentNetwork]:
    return [
        FakeNetwork(
            "Wise",
            {"USD", "EUR", "GBP", "CNY"},
            {
                ("USD", "CNY"): make_quote("Wise", "5", "1", "7.0", DataSource.VERIFIED),
                ("USD", "EUR"): make_quote("Wise EUR", "2", "1", "0.8", DataSource.VERIFIED),
            },
        ),
        FakeNetwork(
            "SEPA",
            {"USD", "EUR", "CNY"},
            {
                ("EUR", "CNY"): make_quote("SEPA Bridge", "3", "2", "9.0"),
            },
        ),
        FakeNetwork(
            "SWIFT",
            {"USD", "GBP", "CNY"},
            {
                ("USD", "CNY"): make_quote("SWIFT", "20", "30", "6.8"),
                ("USD", "GBP"): make_quote("SWIFT GBP", "4", "2", "0.7"),
                ("GBP", "CNY"): make_quote("SWIFT CNY", "4", "2", "10.0"),
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


def test_decide_command_outputs_all_profiles_and_tradeoff(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["decide", "USD", "CNY", "100"])

    assert result.exit_code == 0
    assert "Decision Board" in result.output
    assert "Cheapest" in result.output
    assert "Fastest" in result.output
    assert "Balanced" in result.output
    assert "Decision note" in result.output
    assert "VERIFIED" in result.output


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


def test_default_networks_include_standard_and_instant_sepa() -> None:
    names = [_network_display_name(network) for network in _instantiate_networks()]

    assert names == ["Wise", "SEPA", "SEPA Instant", "SWIFT"]


def test_version_option_prints_project_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "0.4.0" in result.output


def test_sources_command_lists_verified_and_estimated_evidence() -> None:
    result = runner.invoke(app, ["sources"])

    assert result.exit_code == 0
    assert "Data Provenance Registry" in result.output
    assert "wise-live-quote" in result.output
    assert "swift-model-parameters" in result.output
    assert "VERIFIED" in result.output
    assert "ESTIMATED" in result.output


def test_route_command_rejects_non_finite_amount(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["route", "USD", "CNY", "NaN"])

    assert result.exit_code != 0
    assert "valid decimal number" in result.output
