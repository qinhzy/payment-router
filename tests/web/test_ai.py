from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from payment_router.web.app import create_app

from .test_api import _stub_networks


class FakeExplainer:
    def __init__(self, chunks: list[str] | None = None, error: Exception | None = None) -> None:
        self.chunks = chunks or []
        self.error = error
        self.requests: list[tuple[str, dict[str, object], str]] = []

    @property
    def model(self) -> str:
        return "fake-model"

    async def stream_explanation(
        self,
        kind: str,
        payload: dict[str, object],
        lang: str,
    ) -> AsyncIterator[str]:
        self.requests.append((kind, payload, lang))
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk


def _client(explainer: FakeExplainer | None) -> TestClient:
    return TestClient(
        create_app(
            networks_factory=_stub_networks,
            explainer_factory=lambda: explainer,
        )
    )


def _events(text: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def test_meta_reports_ai_disabled_without_explainer() -> None:
    response = _client(None).get("/api/meta")

    assert response.json()["ai"] == {"enabled": False, "model": None}


def test_meta_reports_ai_enabled_with_model() -> None:
    response = _client(FakeExplainer()).get("/api/meta")

    assert response.json()["ai"] == {"enabled": True, "model": "fake-model"}


def test_explain_streams_deltas_and_done_event() -> None:
    explainer = FakeExplainer(chunks=["The balanced ", "route wins."])
    response = _client(explainer).post(
        "/api/explain",
        json={"kind": "decide", "data": {"decisions": []}, "lang": "zh-CN"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert events == [
        {"type": "delta", "text": "The balanced "},
        {"type": "delta", "text": "route wins."},
        {"type": "done", "model": "fake-model"},
    ]
    assert explainer.requests == [("decide", {"decisions": []}, "zh-CN")]


def test_explain_reports_stream_errors_as_sse_events() -> None:
    explainer = FakeExplainer(error=RuntimeError("model unavailable"))
    response = _client(explainer).post(
        "/api/explain",
        json={"kind": "route", "data": {"routes": []}},
    )

    assert response.status_code == 200
    events = _events(response.text)
    assert events == [{"type": "error", "message": "model unavailable"}]


def test_explain_returns_503_when_ai_not_configured() -> None:
    response = _client(None).post(
        "/api/explain",
        json={"kind": "route", "data": {}},
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_explain_rejects_unknown_kind() -> None:
    response = _client(FakeExplainer()).post(
        "/api/explain",
        json={"kind": "forecast", "data": {}},
    )

    assert response.status_code == 422
