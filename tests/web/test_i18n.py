"""The console's interface text: both catalogs stay complete and consistent.

A translation that drifts is worse than none: it can state a different limit
than the result actually has. These tests tie every Chinese caveat and error
to the backend code that selects it, with the same parameters, and every
interface string to a key the console really uses.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import FakeNetwork, make_quote

import payment_router.breakeven
import payment_router.comparison
import payment_router.core.fx
import payment_router.core.graph
import payment_router.networks.wise
import payment_router.regime
import payment_router.sensitivity
import payment_router.service
import payment_router.web.app
from payment_router.analysis import caveat_templates
from payment_router.core import fx
from payment_router.core.graph import QuoteTimeoutError
from payment_router.networks.wise import WiseAPIError, WiseNetwork
from payment_router.provenance import PROVENANCE_RECORDS
from payment_router.web.app import DISCLAIMER, STATIC_DIR, create_app

CATALOG_DIR = STATIC_DIR / "i18n"
# Backend statements are rendered from their code only when translating;
# English shows the backend's own sentence, so these live in zh-CN alone.
TRANSLATION_ONLY = ("caveat.", "error.", "warning.", "reason.", "fxstatus.", "evidence.")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
FIGURE = re.compile(r"\d+(?:\.\d+)?")
CODE_ASSIGNMENT = re.compile(r'\bcode\s*=\s*"([a-z_]+)"')
CODED_MODULES = (
    payment_router.service,
    payment_router.comparison,
    payment_router.breakeven,
    payment_router.regime,
    payment_router.web.app,
    payment_router.networks.wise,
    payment_router.core.graph,
    payment_router.core.fx,
)
FRANKFURTER_JSON = {
    "amount": 1.0,
    "base": "USD",
    "date": "2024-01-02",
    "rates": {"CNY": 7.1, "EUR": 0.906, "GBP": 0.784, "HKD": 7.81, "SGD": 1.32},
}


def _catalog(name: str) -> dict[str, str]:
    return json.loads((CATALOG_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def _codes(chinese: dict[str, str], namespace: str) -> set[str]:
    return {key.split(".", 1)[1] for key in chinese if key.startswith(f"{namespace}.")}


def _assert_translatable(
    chinese: dict[str, str], namespace: str, code: str | None, params: dict[str, str]
) -> None:
    """The Chinese template exists and quotes only parameters that were sent.

    A statement that quotes a failure carries it flattened (``reason_code``
    and ``reason_*``); that failure's own template is checked the same way.
    """
    assert code is not None
    template = chinese[f"{namespace}.{code}"]
    assert _placeholders(template) <= set(params), (namespace, code, params)
    if "reason_code" in params:
        quoted = {
            name.removeprefix("reason_")
            for name in params
            if name.startswith("reason_") and name != "reason_code"
        }
        assert _placeholders(chinese[f"reason.{params['reason_code']}"]) <= quoted


def _html_keys() -> set[str]:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    keys = set(re.findall(r'data-i18n="([^"]+)"', html))
    for attributes in re.findall(r'data-i18n-attr="([^"]+)"', html):
        keys.update(entry.split("=", 1)[1].strip() for entry in attributes.split(";"))
    return keys


def test_both_catalogs_cover_the_same_interface_keys() -> None:
    english, chinese = _catalog("en"), _catalog("zh-CN")

    assert not [key for key in english if key.startswith(TRANSLATION_ONLY)]
    assert set(english) == {key for key in chinese if not key.startswith(TRANSLATION_ONLY)}


def test_translations_keep_every_placeholder() -> None:
    english, chinese = _catalog("en"), _catalog("zh-CN")

    mismatched = {
        key: (sorted(_placeholders(text)), sorted(_placeholders(chinese[key])))
        for key, text in english.items()
        if _placeholders(text) != _placeholders(chinese[key])
    }
    assert mismatched == {}


def test_every_backend_caveat_has_a_chinese_template_with_its_parameters() -> None:
    chinese = _catalog("zh-CN")
    templates = caveat_templates()

    # Importing the analysis modules registers their caveats.
    assert {code.split(".")[0] for code in templates} == {
        "breakeven",
        "compare",
        "regime",
        "sensitivity",
    }
    for code, text in templates.items():
        key = f"caveat.{code}"
        assert key in chinese, key
        assert _placeholders(chinese[key]) == _placeholders(text), key
    assert {key for key in chinese if key.startswith("caveat.")} == {
        f"caveat.{code}" for code in templates
    }


def test_every_code_the_backend_assigns_has_a_chinese_message() -> None:
    chinese = _catalog("zh-CN")
    sources = "\n".join(
        Path(module.__file__).read_text(encoding="utf-8") for module in CODED_MODULES
    )
    codes = set(CODE_ASSIGNMENT.findall(sources))

    assert {
        "no_route",
        "amount_invalid",
        "historical_excluded",
        "provider_timeout",
        "quote_timeout",
        "fx_request_failed",
        "fallback",
        "date_too_early",
        "range_order",
    } <= codes
    missing = [
        code
        for code in codes
        if not any(
            f"{namespace}.{code}" in chinese
            for namespace in ("error", "warning", "reason", "fxstatus")
        )
    ]
    assert missing == []


def test_error_templates_only_use_parameters_the_api_sends() -> None:
    chinese = _catalog("zh-CN")

    def networks():
        return [
            FakeNetwork("Rail", {"USD", "CNY"}, {("USD", "CNY"): make_quote("Rail", "5", "1")}),
            FakeNetwork(
                "Unaffordable",
                {"GBP", "SGD"},
                {("GBP", "SGD"): make_quote("Unaffordable", "1e9", "1")},
            ),
        ]

    client = TestClient(create_app(networks_factory=networks))
    responses = [
        client.get("/api/route", params={"source": "USD", "target": "CNY", "amount": "abc"}),
        client.get("/api/route", params={"source": "USD", "target": "CNY", "amount": "0"}),
        client.get("/api/route", params={"source": "USD", "target": "JPY", "amount": "5"}),
        client.get("/api/route", params={"source": "GBP", "target": "SGD", "amount": "5"}),
        client.get("/api/breakeven", params={"source": "GBP", "target": "SGD", "samples": 3}),
        client.get(
            "/api/regime",
            params={"source": "GBP", "target": "SGD", "amount_samples": 2, "weight_steps": 10},
        ),
        client.post("/api/explain", json={"kind": "route", "data": {}}),
        client.get(
            "/api/breakeven", params={"source": "USD", "target": "CNY", "min": "500", "max": "100"}
        ),
        client.get(
            "/api/regime", params={"source": "USD", "target": "CNY", "min": "500", "max": "100"}
        ),
        # Dates are checked before any rate is fetched, so these stay offline.
        *(
            client.get(
                "/api/compare",
                params={"source": "USD", "target": "CNY", "amount": "5", "on": on},
            )
            for on in ("15/03/2024", "2999-01-01", "1998-06-01")
        ),
    ]

    seen = set()
    for response in responses:
        payload = response.json()
        code = payload["code"]
        seen.add(code)
        _assert_translatable(chinese, "error", code, payload["params"])
    assert seen == {
        "amount_invalid",
        "amount_not_positive",
        "unsupported_currency",
        "no_route",
        "breakeven_no_route",
        "regime_no_route",
        "ai_not_configured",
        "range_order",
        "date_format",
        "date_future",
        "date_too_early",
    }


@pytest.fixture
def fx_cache_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv(fx.CACHE_DIR_ENV_VAR, str(tmp_path))
    yield tmp_path
    fx.activate("frozen")


def test_rate_failures_translate_with_the_parameters_they_send(fx_cache_dir, httpx_mock) -> None:
    chinese = _catalog("zh-CN")
    client = TestClient(create_app(networks_factory=list))
    compare = {"source": "USD", "target": "CNY", "amount": "5", "on": "2024-01-02"}

    httpx_mock.add_exception(httpx.ConnectError("offline"))
    baseline = client.get("/api/compare", params=compare).json()
    httpx_mock.add_exception(httpx.ConnectError("offline"))
    historical = client.get("/api/compare", params={**compare, "against": "2024-01-03"}).json()

    for payload in (baseline, historical):
        _assert_translatable(chinese, "error", payload["code"], payload["params"])
    assert baseline["code"] == "compare_baseline_unavailable"
    assert historical["code"] == "historical_unavailable"
    assert baseline["params"]["reason_code"] == historical["params"]["reason_code"]

    # Each way a rate fetch can fail. A failed fetch writes no snapshot, so
    # every date below is fetched afresh.
    seen = set()
    for on_date, response in (
        ("2024-02-01", {"exception": httpx.ConnectError("offline")}),
        ("2024-02-02", {"json": {"date": "2024-02-02"}}),
        (
            "2024-02-05",
            {"json": {**FRANKFURTER_JSON, "rates": {**FRANKFURTER_JSON["rates"], "CNY": 0}}},
        ),
        ("2024-02-06", {"json": {**FRANKFURTER_JSON, "rates": {"CNY": 7.1}}}),
    ):
        if "exception" in response:
            httpx_mock.add_exception(response["exception"])
        else:
            httpx_mock.add_response(json=response["json"])
        with pytest.raises(fx.FxLiveUnavailableError) as failure:
            fx.historical_source(on_date)
        seen.add(failure.value.code)
        _assert_translatable(chinese, "reason", failure.value.code, failure.value.params)
    assert seen == _codes(chinese, "reason")


def test_rate_statuses_translate_with_the_parameters_they_send(fx_cache_dir, httpx_mock) -> None:
    chinese = _catalog("zh-CN")
    statuses = [fx.activate("frozen")]

    # No snapshot yet: a failed fetch falls back to the frozen table.
    httpx_mock.add_exception(httpx.ConnectError("offline"))
    statuses.append(fx.activate("live"))
    # An older snapshot survives a failed fetch as a stale live source.
    (fx_cache_dir / "fx_snapshot.json").write_text(
        json.dumps(
            {
                "rate_date": "2024-01-02",
                "fetched_on": "2024-01-02",
                "usd_rates": {
                    "USD": "1.0",
                    "EUR": "1.07",
                    "GBP": "1.25",
                    "CNY": "0.139",
                    "HKD": "0.128",
                    "SGD": "0.74",
                },
            }
        )
    )
    httpx_mock.add_exception(httpx.ConnectError("offline"))
    statuses.append(fx.activate("live"))
    httpx_mock.add_response(json=FRANKFURTER_JSON)
    statuses.append(fx.activate("live"))
    httpx_mock.add_response(json=FRANKFURTER_JSON)
    statuses.append(fx.activate("historical", on_date="2024-01-02"))
    # A Saturday resolves to the preceding Friday's publication.
    httpx_mock.add_response(json={**FRANKFURTER_JSON, "date": "2024-01-05"})
    statuses.append(fx.activate("historical", on_date="2024-01-06"))

    for status in statuses:
        _assert_translatable(chinese, "fxstatus", status.code, dict(status.params))
    assert [status.code for status in statuses] == [
        "frozen",
        "fallback",
        "live_stale",
        "live",
        "historical",
        "historical_substituted",
    ]
    assert {status.code for status in statuses} == _codes(chinese, "fxstatus")


@pytest.mark.anyio
async def test_provider_failures_translate_with_the_parameters_they_send(httpx_mock) -> None:
    chinese = _catalog("zh-CN")
    failures = []
    for response in (
        {"exception": httpx.ReadTimeout("slow")},
        {"exception": httpx.ConnectError("down")},
        {"status_code": 500, "text": "internal error"},
        {"text": "<html>gateway</html>"},
        {"json": [1, 2, 3]},
        {"json": {"rate": 7.1}},
    ):
        if "exception" in response:
            httpx_mock.add_exception(response["exception"])
        else:
            httpx_mock.add_response(**response)
        with pytest.raises(WiseAPIError) as failure:
            await WiseNetwork().get_quote(Decimal("1000"), "GBP", "CNY")
        failures.append(failure.value)
    failures.append(QuoteTimeoutError(2.5))

    for failure in failures:
        code, params = payment_router.service.error_code(failure)
        _assert_translatable(chinese, "warning", code, params)
    assert {failure.code for failure in failures} | {"historical_excluded"} == _codes(
        chinese, "warning"
    )


def test_every_key_the_console_uses_exists() -> None:
    english = _catalog("en")
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    namespaces = {key.split(".")[0] for key in english if "." in key}
    literals = {
        literal
        for literal in re.findall(r'"([a-z][A-Za-z]*\.[A-Za-z0-9_.]+)"', javascript)
        if literal.split(".")[0] in namespaces
    }

    missing = [
        key for key in literals | _html_keys() if key not in english and f"{key}.one" not in english
    ]
    assert missing == []


def test_every_interface_key_is_used() -> None:
    javascript = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html_keys = _html_keys()

    unused = [
        key
        for key in _catalog("en")
        if key not in html_keys
        and f'"{key}"' not in javascript
        and f'"{key.removesuffix(".one").removesuffix(".other")}"' not in javascript
    ]
    assert unused == []


def test_every_registry_entry_is_translated_with_the_same_figures() -> None:
    chinese = _catalog("zh-CN")
    records = {record.evidence_id: record for record in PROVENANCE_RECORDS}
    translated = {key for key in chinese if key.startswith("evidence.")}

    # No translation outlives its entry, and only these fields translate.
    assert {key.split(".")[1] for key in translated} == set(records)
    assert {key.split(".")[2] for key in translated} <= {"network", "metric", "value", "caveat"}
    for evidence_id, record in records.items():
        for field in ("metric", "value", "caveat"):
            english = getattr(record, field)
            text = chinese[f"evidence.{evidence_id}.{field}"]
            # The English entry is authoritative: a translation restates
            # every figure it gives, and no other.
            assert sorted(FIGURE.findall(text)) == sorted(FIGURE.findall(english)), (
                evidence_id,
                field,
            )
        network = chinese.get(f"evidence.{evidence_id}.network")
        assert network is None or FIGURE.findall(network) == FIGURE.findall(record.network)


def test_english_disclaimer_is_the_one_the_api_publishes() -> None:
    assert _catalog("en")["disclaimer"] == DISCLAIMER


def test_catalogs_are_served_with_the_console() -> None:
    client = TestClient(create_app(networks_factory=list))

    response = client.get("/i18n/zh-CN.json")

    assert response.status_code == 200
    assert response.json()["meta.title"] == _catalog("zh-CN")["meta.title"]
