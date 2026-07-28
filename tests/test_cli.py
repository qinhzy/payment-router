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
            {"USD", "EUR", "GBP", "CNY", "HKD", "SGD"},
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
            {"USD", "GBP", "CNY", "HKD", "SGD"},
            {
                ("USD", "CNY"): make_quote("SWIFT", "20", "30", "6.8"),
                ("USD", "GBP"): make_quote("SWIFT GBP", "4", "2", "0.7"),
                ("GBP", "CNY"): make_quote("SWIFT CNY", "4", "2", "10.0"),
            },
        ),
        FakeNetwork(
            "CIPS",
            {"USD", "EUR", "GBP", "CNY", "HKD", "SGD"},
            {
                ("HKD", "CNY"): make_quote(
                    "CIPS",
                    "18.56",
                    "12",
                    "0.91",
                    time_min_hours="2",
                    time_max_hours="24",
                ),
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
    assert "CIPS" in result.output


def test_default_networks_include_standard_and_instant_sepa() -> None:
    names = [_network_display_name(network) for network in _instantiate_networks()]

    assert names == ["Wise", "SEPA", "SEPA Instant", "SWIFT", "CIPS"]


def test_version_option_prints_project_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "0.7.0" in result.output


def test_sources_command_lists_verified_and_estimated_evidence() -> None:
    result = runner.invoke(app, ["sources"])

    assert result.exit_code == 0
    assert "Data Provenance Registry" in result.output
    assert "wise-live-quote" in result.output
    assert "swift-model-parameters" in result.output
    assert "cips-topology" in result.output
    assert "cips-model-parameters" in result.output
    assert "VERIFIED" in result.output
    assert "ESTIMATED" in result.output


def test_route_command_rejects_non_finite_amount(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["route", "USD", "CNY", "NaN"])

    assert result.exit_code != 0
    assert "valid decimal number" in result.output


def test_sensitivity_command_outputs_sweep_and_stability(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["sensitivity", "USD", "CNY", "100", "--steps", "40"])

    assert result.exit_code == 0
    assert "Preference sweep" in result.output
    assert "Stability" in result.output
    assert "0.00" in result.output


def test_sensitivity_stability_panel_names_the_winning_route(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["sensitivity", "USD", "CNY", "100", "--steps", "10"])

    assert result.exit_code == 0
    output = " ".join(result.output.split())
    assert "The balanced (0.50) choice" in output
    assert "via" in output
    assert "USD" in output and "CNY" in output


def test_route_command_supports_hkd_to_cny_cips_corridor(monkeypatch) -> None:
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _stub_networks)

    result = runner.invoke(app, ["route", "HKD", "CNY", "10000"])

    assert result.exit_code == 0
    assert "CIPS" in result.output
    assert "Time range" in result.output


def test_compare_command_rejects_a_malformed_date() -> None:
    result = runner.invoke(app, ["compare", "USD", "CNY", "1000", "--on", "nope"])

    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output


def _rate_linked_networks() -> list[PaymentNetwork]:
    """Scenario rails whose quoted rate tracks the active FX table."""
    from decimal import Decimal

    from payment_router.core import fx as fx_module
    from payment_router.core.models import NetworkQuote

    class Scenario(PaymentNetwork):
        def display_name(self) -> str:
            return "SWIFT"

        def supported_currencies(self) -> set[str]:
            return {"USD", "CNY"}

        def get_quote(self, amount, source, target):
            if source == target:
                return None
            return NetworkQuote(
                network_name="SWIFT",
                fee_usd=Decimal("20"),
                time_hours=Decimal("30"),
                fx_rate=fx_module.get_mid_rate(source, target) * Decimal("0.99"),
                data_source=DataSource.ESTIMATED,
            )

    class LiveQuoting(Scenario):
        def display_name(self) -> str:
            return "Wise"

        def quotes_at_request_time(self) -> bool:
            return True

    return [LiveQuoting(), Scenario()]


def test_compare_command_renders_both_dates_deltas_and_caveats(
    monkeypatch,
    tmp_path,
    httpx_mock,
) -> None:
    from payment_router.core import fx as fx_module

    monkeypatch.setenv(fx_module.CACHE_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _rate_linked_networks)
    january = {
        "amount": 1.0,
        "base": "USD",
        "date": "2024-01-02",
        "rates": {"CNY": 7.1, "EUR": 0.906, "GBP": 0.784, "HKD": 7.81, "SGD": 1.32},
    }
    httpx_mock.add_response(
        json={**january, "date": "2024-06-03", "rates": {**january["rates"], "CNY": 7.6}}
    )
    httpx_mock.add_response(json=january)

    try:
        result = runner.invoke(
            app,
            ["compare", "USD", "CNY", "1000", "--on", "2024-01-02", "--against", "2024-06-03"],
        )
    finally:
        fx_module.activate("frozen")

    assert result.exit_code == 0
    output = " ".join(result.output.split())
    assert "2024-06-03" in output and "2024-01-02" in output
    assert "Mid-rate" in output
    assert "Recipient gets" in output
    # Only the FX table moves, so the fee cannot differ between the sides.
    assert "+0.00 USD" in output
    assert "Only the FX table differs" in output
    # The live-quoting rail is dropped from both sides, not just the historical one.
    assert "Excluded from both sides: Wise" in output
    assert "SWIFT" in output


def test_compare_command_reports_a_weekend_rate_date_resolution(
    monkeypatch,
    tmp_path,
    httpx_mock,
) -> None:
    from payment_router.core import fx as fx_module

    monkeypatch.setenv(fx_module.CACHE_DIR_ENV_VAR, str(tmp_path))
    # Pin the width: at 80 columns Rich wraps the rate-date cell, which would
    # make this assertion depend on the terminal rather than on the behaviour.
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr("payment_router.cli._instantiate_networks", _rate_linked_networks)
    base = {
        "amount": 1.0,
        "base": "USD",
        "rates": {"CNY": 7.1, "EUR": 0.906, "GBP": 0.784, "HKD": 7.81, "SGD": 1.32},
    }
    httpx_mock.add_response(json={**base, "date": "2024-06-03"})
    httpx_mock.add_response(json={**base, "date": "2024-01-05"})

    try:
        result = runner.invoke(
            app,
            ["compare", "USD", "CNY", "1000", "--on", "2024-01-06", "--against", "2024-06-03"],
        )
    finally:
        fx_module.activate("frozen")

    assert result.exit_code == 0
    output = " ".join(result.output.split())
    assert "asked 2024-01-06" in output
    assert "no published ECB fixing" in output
