"""The console's interface text: both catalogs stay complete and consistent.

A translation that drifts is worse than none: it can state a different limit
than the result actually has. These tests tie every Chinese caveat and error
to the backend code that selects it, with the same parameters, and every
interface string to a key the console really uses.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from helpers import FakeNetwork, make_quote

import payment_router.breakeven
import payment_router.comparison
import payment_router.regime
import payment_router.sensitivity
import payment_router.service
import payment_router.web.app
from payment_router.analysis import caveat_templates
from payment_router.web.app import DISCLAIMER, STATIC_DIR, create_app

CATALOG_DIR = STATIC_DIR / "i18n"
# Backend statements are rendered from their code only when translating;
# English shows the backend's own sentence, so these live in zh-CN alone.
TRANSLATION_ONLY = ("caveat.", "error.", "warning.")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
CODE_ASSIGNMENT = re.compile(r'code="([a-z_]+)"')


def _catalog(name: str) -> dict[str, str]:
    return json.loads((CATALOG_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


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


def test_every_error_and_warning_code_has_a_chinese_message() -> None:
    chinese = _catalog("zh-CN")
    sources = "\n".join(
        Path(module.__file__).read_text(encoding="utf-8")
        for module in (
            payment_router.service,
            payment_router.comparison,
            payment_router.web.app,
        )
    )
    codes = set(CODE_ASSIGNMENT.findall(sources))

    assert {"no_route", "amount_invalid", "historical_excluded"} <= codes
    missing = [
        code
        for code in codes
        if f"error.{code}" not in chinese and f"warning.{code}" not in chinese
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
    ]

    seen = set()
    for response in responses:
        payload = response.json()
        code = payload["code"]
        seen.add(code)
        template = chinese[f"error.{code}"]
        assert _placeholders(template) <= set(payload["params"]), code
    assert seen == {
        "amount_invalid",
        "amount_not_positive",
        "unsupported_currency",
        "no_route",
        "breakeven_no_route",
        "regime_no_route",
        "ai_not_configured",
    }


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


def test_english_disclaimer_is_the_one_the_api_publishes() -> None:
    assert _catalog("en")["disclaimer"] == DISCLAIMER


def test_catalogs_are_served_with_the_console() -> None:
    client = TestClient(create_app(networks_factory=list))

    response = client.get("/i18n/zh-CN.json")

    assert response.status_code == 200
    assert response.json()["meta.title"] == _catalog("zh-CN")["meta.title"]
