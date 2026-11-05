"""Exercise the installed Anthropic SDK with only its HTTP transport intercepted."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from payment_router.web.ai import DEFAULT_MODEL, SYSTEM_PROMPT, AIExplainer
from payment_router.web.app import create_app

from .test_ai import _events
from .test_api import _stub_networks


@pytest.fixture
def isolated_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    # Never load a developer's real credentials, profile, or gateway settings.
    for name in tuple(os.environ):
        if name.startswith("ANTHROPIC_"):
            monkeypatch.delenv(name)
    monkeypatch.delenv("PAYMENT_ROUTER_AI_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://sdk-test.invalid")
    return tmp_path


@pytest.fixture
def sdk_transport(monkeypatch: pytest.MonkeyPatch):
    def install(handler: Callable[[httpx2.Request], httpx2.Response]) -> None:
        sdk_client = anthropic.AsyncAnthropic

        def create_client() -> anthropic.AsyncAnthropic:
            return sdk_client(
                http_client=anthropic.DefaultAsyncHttpxClient(
                    transport=httpx2.MockTransport(handler), trust_env=False
                )
            )

        # Only transport is mocked; keep SDK construction, auth, and SSE parsing real.
        # The test must not depend on the host's proxy configuration.
        monkeypatch.setattr(anthropic, "AsyncAnthropic", create_client)

    return install


def _sse(*events: dict[str, object]) -> bytes:
    return "".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
    ).encode()


def _message_start() -> dict[str, object]:
    return {
        "type": "message_start",
        "message": {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": DEFAULT_MODEL,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 8, "output_tokens": 1},
        },
    }


@pytest.mark.parametrize("source", ["api_key", "auth_token", "profile", "both"])
def test_sdk_resolves_credentials_and_streams_text(
    source: str,
    isolated_credentials: Path,
    monkeypatch: pytest.MonkeyPatch,
    sdk_transport,
) -> None:
    if source in {"api_key", "both"}:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    if source in {"auth_token", "both"}:
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-auth-token")
    if source == "profile":
        configs = isolated_credentials / "configs"
        credentials = isolated_credentials / "credentials"
        configs.mkdir()
        credentials.mkdir()
        (configs / "default.json").write_text(
            json.dumps({"authentication": {"type": "user_oauth"}})
        )
        token_file = credentials / "default.json"
        token_file.write_text(
            json.dumps({"type": "oauth_token", "access_token": "test-profile-token"})
        )
        token_file.chmod(0o600)

    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                _message_start(),
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "text",
                        "text": "",
                    },
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "text_delta",
                        "text": "Synthetic ",
                    },
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "text_delta",
                        "text": "explanation.",
                    },
                },
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": "end_turn",
                        "stop_sequence": None,
                    },
                    "usage": {"output_tokens": 4},
                },
                {"type": "message_stop"},
            ),
        )

    sdk_transport(respond)
    explainer = AIExplainer.try_create()
    assert explainer is not None, "SDK initialization must not silently disable AI"

    async def collect() -> list[str]:
        async with explainer._client:
            return [
                chunk
                async for chunk in explainer.stream_explanation(
                    "route", {"routes": [], "caveats": ["synthetic test"]}, "zh-CN"
                )
            ]

    assert asyncio.run(collect()) == ["Synthetic ", "explanation."]
    assert explainer._client.is_closed()
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://sdk-test.invalid/v1/messages"
    sdk_v2 = int(anthropic.__version__.split(".")[0]) >= 2
    assert request.headers["anthropic-version"] == ("2026-10-21" if sdk_v2 else "2023-06-01")
    if sdk_v2:
        assert "x-api-key" not in request.headers
    if source in {"api_key", "both"}:
        if sdk_v2:
            assert request.headers["authorization"] == "Bearer test-api-key"
        else:
            assert request.headers["x-api-key"] == "test-api-key"
    if source == "auth_token" or (source == "both" and not sdk_v2):
        assert request.headers["authorization"] == "Bearer test-auth-token"
    if source == "profile":
        assert request.headers["authorization"] == "Bearer test-profile-token"

    body = json.loads(request.content)
    assert body["stream"] is True
    assert body["model"] == DEFAULT_MODEL
    assert body["system"] == SYSTEM_PROMPT
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"] == {"effort": "low"}
    assert body["max_tokens"] == 1500
    assert body["messages"][0]["role"] == "user"
    assert "Response language: zh-CN" in body["messages"][0]["content"]
    assert '"caveats": ["synthetic test"]' in body["messages"][0]["content"]


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(401, "authentication_error"), (429, "rate_limit_error"), (200, "overloaded_error")],
)
def test_sdk_errors_are_reported_without_a_done_event(
    status: int,
    error_type: str,
    isolated_credentials: Path,
    monkeypatch: pytest.MonkeyPatch,
    sdk_transport,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    error = {"type": "error", "error": {"type": error_type, "message": "synthetic failure"}}

    def respond(request: httpx2.Request) -> httpx2.Response:
        if status == 200:
            return httpx2.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse(_message_start(), error),
            )
        return httpx2.Response(status, json=error)

    sdk_transport(respond)
    explainer = AIExplainer()
    explainer._client.max_retries = 0
    try:
        with TestClient(
            create_app(networks_factory=_stub_networks, explainer_factory=lambda: explainer)
        ) as client:
            assert client.get("/api/meta").json()["ai"]["enabled"] is True
            response = client.post("/api/explain", json={"kind": "route", "data": {}})
        assert response.status_code == 200
        events = _events(response.text)
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "synthetic failure" in events[0]["message"]
    finally:
        asyncio.run(explainer._client.close())


def test_missing_sdk_credentials_disable_ai(isolated_credentials: Path, sdk_transport) -> None:
    def unexpected_request(request: httpx2.Request) -> httpx2.Response:
        pytest.fail("No request should be sent without credentials")

    sdk_transport(unexpected_request)
    assert AIExplainer.try_create() is None
    with TestClient(create_app(networks_factory=_stub_networks)) as client:
        assert client.get("/api/meta").json()["ai"] == {"enabled": False, "model": None}
        assert client.post("/api/explain", json={"kind": "route", "data": {}}).status_code == 503
