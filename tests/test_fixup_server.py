from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claude2openai_gateway import fixup_server


class FakeUpstreamResponse:
    def __init__(
        self,
        *,
        content: bytes = b"",
        chunks: list[bytes] | None = None,
        content_type: str = "application/json",
        status_code: int = 200,
    ):
        self.content = content
        self._chunks = chunks or []
        self.headers = {"content-type": content_type}
        self.status_code = status_code
        self.is_error = status_code >= 400
        self.closed = False

    async def aread(self) -> bytes:
        return self.content or b"".join(self._chunks)

    async def aiter_raw(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class FakeAsyncClient:
    instances: list["FakeAsyncClient"] = []

    def __init__(self, *args: Any, **kwargs: Any):
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.closed = False
        FakeAsyncClient.instances.append(self)

    def build_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]) -> dict[str, Any]:
        return {
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
        }

    async def get(self, url: str, headers: dict[str, str]) -> FakeUpstreamResponse:
        self.calls.append(("get", url, None))
        return FakeUpstreamResponse(content=b'{"ok":true}')

    async def post(
        self,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
        content: bytes | None = None,
    ) -> FakeUpstreamResponse:
        self.calls.append(("post", url, json if json is not None else content))
        return FakeUpstreamResponse(content=b'{"ok":true}')

    async def send(self, request: dict[str, Any], *, stream: bool = False) -> FakeUpstreamResponse:
        self.calls.append(("send", request["url"], request["json"]))
        self.last_stream_flag = stream
        return FakeUpstreamResponse(
            chunks=[b"data: first\n\n", b"data: second\n\n"],
            content_type="text/event-stream",
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def cleanup_backend_client_state() -> None:
    if hasattr(fixup_server.app.state, "backend_client"):
        delattr(fixup_server.app.state, "backend_client")
    FakeAsyncClient.instances.clear()
    yield
    if hasattr(fixup_server.app.state, "backend_client"):
        delattr(fixup_server.app.state, "backend_client")
    FakeAsyncClient.instances.clear()


def test_fixup_server_reuses_backend_client_across_requests(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BACKEND_API_KEY", "real-key")
    monkeypatch.setattr(fixup_server.httpx, "AsyncClient", FakeAsyncClient)

    with TestClient(fixup_server.app) as client:
        first = client.get("/v1/models")
        second = client.get("/v1/models")

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(FakeAsyncClient.instances) == 1
    assert FakeAsyncClient.instances[0].calls == [
        ("get", "http://127.0.0.1:8327/v1/models", None),
        ("get", "http://127.0.0.1:8327/v1/models", None),
    ]
    assert FakeAsyncClient.instances[0].closed is True


def test_fixup_server_streams_responses_without_buffering(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BACKEND_API_KEY", "real-key")
    fake_client = FakeAsyncClient()

    async def fake_backend_client() -> FakeAsyncClient:
        return fake_client

    monkeypatch.setattr(fixup_server, "_backend_client", fake_backend_client)

    with TestClient(fixup_server.app) as client:
        with client.stream(
            "POST",
            "/v1/responses",
            json={"model": "gpt-5.5", "stream": True, "user": "opaque"},
        ) as response:
            body = b"".join(response.iter_bytes())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert body == b"data: first\n\ndata: second\n\n"
    assert fake_client.calls == [
        ("send", "http://127.0.0.1:8327/v1/responses", {"model": "gpt-5.5", "stream": True})
    ]
    assert fake_client.last_stream_flag is True


def test_fixup_server_passthrough_post_forwards_raw_body(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BACKEND_API_KEY", "real-key")
    fake_client = FakeAsyncClient()

    async def fake_backend_client() -> FakeAsyncClient:
        return fake_client

    monkeypatch.setattr(fixup_server, "_backend_client", fake_backend_client)

    raw_body = b'{"model":"gpt-5.5","input":[{"role":"user","content":[{"type":"input_image","image_url":"data:image/png;base64,AAA="}]}]}'

    with TestClient(fixup_server.app) as client:
        response = client.post(
            "/v1/chat/completions",
            content=raw_body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert fake_client.calls == [
        ("post", "http://127.0.0.1:8327/v1/chat/completions", raw_body)
    ]
