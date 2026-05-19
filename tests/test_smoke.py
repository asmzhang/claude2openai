from __future__ import annotations

from collections import deque
from typing import Any

import pytest

from claude2openai_gateway import smoke
from claude2openai_gateway.smoke import (
    build_anthropic_messages_payload,
    extract_text,
    run_backend_benchmark,
    run_gateway_benchmark,
    summarize_latency_ms,
)


def test_build_anthropic_messages_payload_uses_single_user_message():
    payload = build_anthropic_messages_payload("gpt-5.5", "你好", max_tokens=64)

    assert payload == {
        "model": "gpt-5.5",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "你好"}],
    }


def test_extract_text_reads_anthropic_message_content():
    response = {
        "id": "msg_123",
        "content": [
            {"type": "text", "text": "你好！有什么我可以帮你的吗？"},
        ],
    }

    assert extract_text(response) == "你好！有什么我可以帮你的吗？"


def test_extract_text_reads_openai_responses_output():
    response = {
        "id": "resp_123",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "你好！有什么我可以帮你的吗？",
                    }
                ],
            }
        ],
    }

    assert extract_text(response) == "你好！有什么我可以帮你的吗？"


def test_extract_text_reads_chat_completions_message():
    response = {
        "id": "chatcmpl_123",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "你好！有什么我可以帮你的吗？",
                }
            }
        ],
    }

    assert extract_text(response) == "你好！有什么我可以帮你的吗？"


def test_summarize_latency_ms_reports_distribution():
    assert summarize_latency_ms([30.0, 10.0, 20.0, 40.0]) == {
        "count": 4,
        "min_ms": 10.0,
        "avg_ms": 25.0,
        "p50_ms": 25.0,
        "p95_ms": 40.0,
        "max_ms": 40.0,
    }


class FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload
        self.headers = {"content-type": "application/json"}
        self.content = b""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeClient:
    payloads: deque[dict[str, Any]] = deque()
    requests: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any):
        self.timeout = kwargs.get("timeout")

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
        FakeClient.requests.append((url, json))
        return FakeResponse(FakeClient.payloads.popleft())


def test_run_backend_benchmark_collects_latency_and_usage(monkeypatch: pytest.MonkeyPatch):
    FakeClient.payloads = deque(
        [
            {
                "model": "gpt-5.4",
                "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
                "output": [{"content": [{"type": "output_text", "text": "2"}]}],
            },
            {
                "model": "gpt-5.4",
                "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
                "output": [{"content": [{"type": "output_text", "text": "2"}]}],
            },
        ]
    )
    FakeClient.requests = []
    perf_counter_values = iter([0.0, 0.01, 0.01, 0.03])

    monkeypatch.setattr(smoke.httpx, "Client", FakeClient)
    monkeypatch.setattr(smoke.time, "perf_counter", lambda: next(perf_counter_values))

    result = run_backend_benchmark(
        "http://127.0.0.1:8328/v1",
        "proxy-key",
        "gpt-5.5",
        "1+1?",
        repeats=2,
        warmup=0,
    )

    assert result == {
        "target": "backend",
        "endpoint": "http://127.0.0.1:8328/v1/responses",
        "requested_model": "gpt-5.5",
        "returned_model": "gpt-5.4",
        "latency_ms": {
            "count": 2,
            "min_ms": 10.0,
            "avg_ms": 15.0,
            "p50_ms": 15.0,
            "p95_ms": 20.0,
            "max_ms": 20.0,
        },
        "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
        "text": "2",
    }
    assert FakeClient.requests == [
        (
            "http://127.0.0.1:8328/v1/responses",
            {
                "model": "gpt-5.5",
                "input": "1+1?",
                "max_output_tokens": 64,
                "stream": True,
            },
        ),
        (
            "http://127.0.0.1:8328/v1/responses",
            {
                "model": "gpt-5.5",
                "input": "1+1?",
                "max_output_tokens": 64,
                "stream": True,
            },
        ),
    ]


def test_run_gateway_benchmark_reports_count_message_and_total_latency(
    monkeypatch: pytest.MonkeyPatch,
):
    FakeClient.payloads = deque(
        [
            {"input_tokens": 42},
            {
                "model": "gpt-5.5",
                "usage": {"input_tokens": 42, "output_tokens": 5, "total_tokens": 47},
                "content": [{"type": "text", "text": "2"}],
            },
        ]
    )
    FakeClient.requests = []
    perf_counter_values = iter([0.0, 0.005, 0.005, 0.02])

    monkeypatch.setattr(smoke.httpx, "Client", FakeClient)
    monkeypatch.setattr(smoke.time, "perf_counter", lambda: next(perf_counter_values))

    result = run_gateway_benchmark(
        "http://127.0.0.1:4000",
        "local-gateway-key",
        "gpt-5.5",
        "1+1?",
        repeats=1,
        warmup=0,
    )

    assert result == {
        "target": "gateway",
        "count_tokens_endpoint": "http://127.0.0.1:4000/v1/messages/count_tokens",
        "endpoint": "http://127.0.0.1:4000/v1/messages",
        "requested_model": "gpt-5.5",
        "returned_model": "gpt-5.5",
        "latency_ms": {
            "count_tokens": {
                "count": 1,
                "min_ms": 5.0,
                "avg_ms": 5.0,
                "p50_ms": 5.0,
                "p95_ms": 5.0,
                "max_ms": 5.0,
            },
            "messages": {
                "count": 1,
                "min_ms": 15.0,
                "avg_ms": 15.0,
                "p50_ms": 15.0,
                "p95_ms": 15.0,
                "max_ms": 15.0,
            },
            "total": {
                "count": 1,
                "min_ms": 20.0,
                "avg_ms": 20.0,
                "p50_ms": 20.0,
                "p95_ms": 20.0,
                "max_ms": 20.0,
            },
        },
        "input_tokens": 42,
        "usage": {"input_tokens": 42, "output_tokens": 5, "total_tokens": 47},
        "text": "2",
    }
    assert FakeClient.requests == [
        (
            "http://127.0.0.1:4000/v1/messages/count_tokens",
            {"model": "gpt-5.5", "messages": [{"role": "user", "content": "1+1?"}]},
        ),
        (
            "http://127.0.0.1:4000/v1/messages",
            {"model": "gpt-5.5", "max_tokens": 64, "messages": [{"role": "user", "content": "1+1?"}]},
        ),
    ]
