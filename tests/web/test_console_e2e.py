"""Browser tests of the web console against a real server.

The static-asset tests can only check that a hook exists; these drive the
console in Chromium and check what a person actually sees and does. They
need Playwright's browser: ``uv run playwright install chromium``. Without
it they are skipped, unless ``PAYMENT_ROUTER_E2E=1`` asks for them to fail
instead (CI sets it, so a missing browser can never pass silently).
``PAYMENT_ROUTER_E2E_CHROMIUM`` may point at an existing Chromium binary.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Iterator
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip("playwright.sync_api")

import uvicorn  # noqa: E402
from playwright.sync_api import Browser, Page, sync_playwright  # noqa: E402

from payment_router.core import fx  # noqa: E402
from payment_router.core.models import DataSource, NetworkQuote  # noqa: E402
from payment_router.networks.base import PaymentNetwork  # noqa: E402
from payment_router.web.app import create_app  # noqa: E402

pytestmark = pytest.mark.e2e

CURRENCIES = {"USD", "EUR", "CNY"}
IDLE = """() => document.querySelector('#route-form').getAttribute('aria-busy') === 'false'
    && !document.querySelector('.skeleton')"""


class Rail(PaymentNetwork):
    """A teaching rail whose cost is a fixed fee plus an FX spread."""

    def __init__(self, name: str, fixed: str, spread: str, hours: str) -> None:
        self._name = name
        self._fixed = Decimal(fixed)
        self._spread = Decimal(spread)
        self._hours = Decimal(hours)

    def supported_currencies(self) -> set[str]:
        return CURRENCIES

    def get_quote(self, amount, source, target):
        if source == target:
            return None
        return NetworkQuote(
            network_name=self._name,
            fee_usd=self._fixed,
            time_hours=self._hours,
            fx_rate=fx.get_mid_rate(source, target) * (Decimal(1) - self._spread),
            data_source=DataSource.ESTIMATED,
        )


class Offline(PaymentNetwork):
    """Fails every corridor, as an unreachable live provider does."""

    _name = "Offline"

    def supported_currencies(self) -> set[str]:
        return CURRENCIES

    def get_quote(self, amount, source, target):
        raise RuntimeError("quote request failed")


def _networks() -> list[PaymentNetwork]:
    # A fixed fee against a spread: the cheaper rail changes near 2,200 USD.
    return [
        Rail("FlatFee", fixed="25", spread="0.001", hours="24"),
        Rail("SpreadHeavy", fixed="0.5", spread="0.012", hours="20"),
        Offline(),
    ]


@pytest.fixture(scope="module")
def console_url() -> Iterator[str]:
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(networks_factory=_networks, explainer_factory=lambda: None),
            host="127.0.0.1",
            port=0,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            pytest.fail("the console server did not start")
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch(
                executable_path=os.environ.get("PAYMENT_ROUTER_E2E_CHROMIUM") or None
            )
        except Exception as error:  # the browser binary is not installed
            if os.environ.get("PAYMENT_ROUTER_E2E") == "1":
                pytest.fail(f"Chromium is required for browser tests: {error}")
            pytest.skip("Chromium is not installed; run `uv run playwright install chromium`")
        yield launched
        launched.close()


def _page(browser: Browser, *, locale: str = "en-US", width: int = 1280) -> Page:
    context = browser.new_context(viewport={"width": width, "height": 900}, locale=locale)
    page = context.new_page()
    page.set_default_timeout(10_000)
    return page


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    opened = _page(browser)
    yield opened
    opened.context.close()


def _settle(page: Page) -> None:
    page.wait_for_function(IDLE)


def _ready(page: Page) -> None:
    """Wait until metadata has populated the form."""
    page.wait_for_selector("#source-select option", state="attached")


def _hold(page: Page, pattern: str) -> list:
    """Intercept matching requests and keep them pending until released.

    Holding a request is deterministic where a sleeping handler is not: with
    the sync API a handler only runs while the test is inside a Playwright
    call, so a sleep lands wherever that call happens to be.
    """
    held: list = []

    def keep(route) -> None:
        held.append(route)

    page.route(pattern, keep)
    return held


def _query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def test_hidden_parts_take_no_space_before_data_arrives(browser: Browser, console_url: str) -> None:
    page = _page(browser)
    held = _hold(page, "**/api/meta*")
    page.goto(console_url)
    page.wait_for_function("document.documentElement.lang === 'en'")
    assert held, "the metadata request should be pending"

    # Component rules used to override `hidden`: an empty "Recent" bar and a
    # blank disclaimer showed before any data had loaded.
    assert page.locator("#disclaimer").bounding_box() is None
    assert page.locator("#recents").bounding_box() is None
    held[0].continue_()
    page.wait_for_selector("#disclaimer:not([hidden])")
    assert "simulator" in page.locator("#disclaimer-text").inner_text()
    page.context.close()


def test_top_candidates_are_compared_and_each_row_opens_its_route(
    page: Page, console_url: str
) -> None:
    page.goto(f"{console_url}/?from=USD&to=CNY&amount=1000&profile=balanced&top_n=3")
    _settle(page)

    rows = page.locator(".candidate-row")
    assert rows.count() == page.locator(".route-card").count() >= 2
    assert "top ranked" in rows.nth(0).inner_text()
    assert "(" in rows.nth(1).locator(".candidate-delta").inner_text()
    # These rails model one delivery time, not a band; the tile says so
    # rather than repeating the headline figure.
    time_tile = page.locator(".route-card").first.locator(".stat-tile").nth(2)
    assert time_tile.locator(".stat-sub").inner_text() == "no range modelled"

    page.locator(".rank-button").nth(1).click()
    page.wait_for_timeout(300)
    focused_card = page.evaluate("document.activeElement.closest('.route-card')?.id")
    assert focused_card == "route-card-2"


def test_provider_failures_are_grouped_per_network_and_reason(page: Page, console_url: str) -> None:
    page.goto(f"{console_url}/?from=USD&to=CNY&amount=1000&profile=balanced&top_n=1")
    _settle(page)

    items = page.locator("#warnings li")
    assert items.count() == 1
    assert "Offline" in items.first.inner_text()
    assert "quote request failed" in items.first.inner_text()
    assert "corridors" in items.first.locator("summary").inner_text()


def test_breakeven_uses_the_selected_profile_and_follows_the_entered_amount(
    page: Page, console_url: str
) -> None:
    page.goto(console_url)
    _ready(page)
    page.check("input[name=profile][value=cheapest]", force=True)

    with page.expect_request("**/api/breakeven*") as request:
        page.click("#breakeven-button")
    _settle(page)

    assert _query(request.value.url)["profile"] == "cheapest"
    assert _query(page.url)["profile"] == "cheapest"
    assert page.locator(".breakeven-strip .regime-segment").count() >= 2
    assert page.locator(".scenario-marker").is_visible()

    # The marker and its note are client-side: no new scan for a new amount.
    requests: list[str] = []
    page.on("request", lambda sent: requests.append(sent.url))
    page.fill("#amount-input", "90000")
    assert "90,000 USD" in page.locator(".scenario-note").inner_text()
    assert page.locator("#results-context").is_hidden()
    assert not [url for url in requests if "/api/" in url]

    # The profile does change the scan, so changing it marks the result stale.
    page.check("input[name=profile][value=fastest]", force=True)
    assert page.locator("#results-context").is_visible()


def test_amounts_accept_grouping_but_reject_ambiguous_input(page: Page, console_url: str) -> None:
    page.goto(console_url)
    _ready(page)

    page.fill("#amount-input", "1,5")
    page.click("#route-button")
    assert page.locator("#amount-error").is_visible()
    assert page.evaluate("document.activeElement.id") == "amount-input"
    assert page.locator("#scenario-summary").inner_text().startswith("— USD")

    page.fill("#amount-input", "2,500")
    page.click("#route-button")
    _settle(page)
    assert _query(page.url)["amount"] == "2500"
    assert page.locator("[data-quick-amount='2500']").get_attribute("aria-pressed") == "true"


def test_scan_range_and_rate_date_validate_beside_their_inputs(
    page: Page, console_url: str
) -> None:
    page.goto(console_url)
    _ready(page)

    page.click("#compare-button")
    assert page.locator("#date-error").is_visible()
    assert page.evaluate("document.activeElement.id") == "on-date"

    page.fill("#range-min", "5000")
    page.fill("#range-max", "100")
    page.click("#regime-button")
    assert page.locator("#range-error").is_visible()
    assert page.evaluate("document.activeElement.id") == "range-max"
    assert page.locator("#alerts").is_hidden()


def test_a_rate_date_out_of_range_does_not_block_a_route_search(
    page: Page, console_url: str
) -> None:
    page.goto(console_url)
    _ready(page)

    # Below the picker's minimum. Only the rate-date comparison reads this
    # field; the browser's own validation used to stop every search with an
    # untranslated bubble until it was cleared.
    page.fill("#on-date", "1998-06-01")
    page.fill("#amount-input", "2000")
    with page.expect_request("**/api/route*"):
        page.click("#route-button")
    _settle(page)

    assert _query(page.url)["amount"] == "2000"
    assert page.locator("#date-error").is_hidden()


def test_cancelling_a_scan_restores_the_previous_view(page: Page, console_url: str) -> None:
    page.goto(f"{console_url}/?from=USD&to=CNY&amount=1000&profile=balanced&top_n=1")
    _settle(page)

    held = _hold(page, "**/api/regime*")
    page.click("#regime-button")
    page.wait_for_selector(".skeleton")
    assert held, "the scan should be pending"
    page.keyboard.press("Escape")
    _settle(page)

    assert page.locator(".route-card").count() == 1
    assert page.locator("#regime-button").inner_text() == "Regime map"
    assert page.evaluate("document.activeElement.id") == "regime-button"


def test_back_button_restores_the_previous_view(page: Page, console_url: str) -> None:
    page.goto(f"{console_url}/?from=USD&to=CNY&amount=1000&profile=balanced&top_n=1")
    _settle(page)
    page.click("#sensitivity-button")
    _settle(page)
    assert page.locator(".regime-marker").count() == 1

    page.go_back()
    _settle(page)
    assert page.locator(".route-card").count() == 1
    assert page.title().startswith("Route search · USD → CNY")


def test_quick_amounts_follow_the_source_currency(page: Page, console_url: str) -> None:
    page.goto(console_url)
    _ready(page)

    def ladder() -> list[str]:
        return page.locator("[data-quick-amount]").evaluate_all(
            "buttons => buttons.map((button) => button.dataset.quickAmount)"
        )

    assert ladder() == ["250", "500", "1000", "2500", "5000"]
    page.select_option("#source-select", "CNY")
    assert ladder() == ["2000", "5000", "10000", "20000", "50000"]
    assert page.locator("#range-currency").inner_text() == "CNY"


def test_the_interface_switches_to_chinese_in_place(page: Page, console_url: str) -> None:
    page.goto(f"{console_url}/?from=USD&to=CNY&amount=1000&view=breakeven")
    _settle(page)
    english_caveat = page.locator(".caveat-rows div").first.inner_text()

    page.click("#lang-toggle")
    page.wait_for_function("document.documentElement.lang === 'zh-CN'")

    assert page.locator("#route-button").inner_text() == "查找路由"
    assert page.locator(".panel-header h2").first.inner_text() == "按金额的盈亏平衡"
    chinese_caveat = page.locator(".caveat-rows div").first.inner_text()
    assert chinese_caveat != english_caveat
    assert "交叉点" in chinese_caveat
    # The translation quotes the same figures: they come from the caveat's
    # parameters, so no number is re-derived or reformatted on the way.
    figures = re.findall(r"\d+(?:\.\d+)?", english_caveat)
    assert figures
    assert all(figure in chinese_caveat for figure in figures)
    assert page.title().endswith("payment-router 控制台")
    # Evidence badges keep their label on one line in the narrow column.
    heights = page.locator(".registry-table .badge").evaluate_all(
        "(badges) => badges.map((badge) => badge.getBoundingClientRect().height)"
    )
    assert heights and max(heights) < 26

    page.reload()
    _settle(page)
    assert page.evaluate("document.documentElement.lang") == "zh-CN"

    page.click("#lang-toggle")
    page.wait_for_function("document.documentElement.lang === 'en'")
    assert page.locator(".caveat-rows div").first.inner_text() == english_caveat


def test_a_chinese_browser_starts_in_chinese(browser: Browser, console_url: str) -> None:
    page = _page(browser, locale="zh-CN")
    page.goto(console_url)
    page.wait_for_function("document.documentElement.lang === 'zh-CN'")

    assert page.locator("#route-button").inner_text() == "查找路由"
    assert page.locator("#lang-toggle").inner_text() == "English"
    page.context.close()


def test_phone_layout_fits_the_screen(browser: Browser, console_url: str) -> None:
    page = _page(browser, width=390)
    page.goto(f"{console_url}/?from=USD&to=CNY&amount=1000&profile=balanced&top_n=3")
    _settle(page)

    assert page.evaluate("document.documentElement.scrollWidth") == 390
    assert page.evaluate("document.querySelector('.topbar').offsetHeight") < 70
    flow = page.locator(".flow").first
    assert flow.evaluate("(node) => getComputedStyle(node).flexDirection") == "column"
    brand = page.locator(".brand-name").bounding_box()
    actions = page.locator(".topbar-actions").bounding_box()
    assert brand["x"] + brand["width"] <= actions["x"], "the top bar must not overlap"

    # An enormous figure wraps inside its own tile; the tile beside it keeps
    # its half of the row. The stub rails charge flat fees, so the response
    # is given a fee twelve digits long.
    def enlarge_fee(route) -> None:
        response = route.fetch()
        payload = response.json()
        payload["routes"][0]["total_fee_usd"] = "123456789012.34"
        route.fulfill(response=response, json=payload)

    page.route("**/api/route*", enlarge_fee)
    page.fill("#amount-input", "2000")
    page.click("#route-button")
    _settle(page)
    page.unroute("**/api/route*")
    tiles = page.locator(".route-card .stat-tile")
    # Figures count up to their value; measure once the fee has arrived.
    tiles.filter(has_text="123,456,789,012.34").wait_for()
    widths = tiles.evaluate_all(
        "(tiles) => tiles.map((tile) => tile.getBoundingClientRect().width)"
    )
    assert abs(widths[1] - widths[2]) <= 1
    assert tiles.evaluate_all(
        "(tiles) => tiles.every((tile) => tile.scrollWidth <= tile.clientWidth)"
    )
    assert page.evaluate("document.documentElement.scrollWidth") == 390

    # The widest preset ladder still fits on one line beside its label, in
    # either language.
    page.select_option("#source-select", "CNY")
    presets = page.locator("#quick-amounts")
    for language in ("en", "zh-CN"):
        if page.evaluate("document.documentElement.lang") != language:
            page.click("#lang-toggle")
            page.wait_for_function(f"document.documentElement.lang === '{language}'")
        assert presets.evaluate("(row) => row.scrollWidth <= row.clientWidth"), language
        label = presets.locator("span").first.bounding_box()
        button = presets.locator("button").first.bounding_box()
        assert label["height"] <= button["height"], f"the {language} preset label must not wrap"
    page.context.close()


def test_presets_shorten_rather_than_clip_on_a_narrow_phone(
    browser: Browser, console_url: str
) -> None:
    page = _page(browser, width=320)
    page.goto(f"{console_url}/?from=CNY&to=USD&amount=10000&profile=balanced&top_n=3")
    _settle(page)
    presets = page.locator("#quick-amounts")
    first = presets.locator("button").first

    assert presets.evaluate("(row) => row.scrollWidth <= row.clientWidth")
    assert first.inner_text() == "2K"
    assert first.get_attribute("data-quick-amount") == "2000"

    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_function("!document.querySelector('#quick-amounts.is-compact')")
    assert first.inner_text() == "2,000"
    page.context.close()
