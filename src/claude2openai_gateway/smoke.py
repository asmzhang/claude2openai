from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections.abc import Callable
from typing import Any

import httpx

from .fixup import build_responses_json_from_sse, decode_sse_bytes


def build_anthropic_messages_payload(
    model: str, prompt: str, max_tokens: int = 64
) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }


def extract_text(response: dict[str, Any]) -> str:
    content = response.get("content")
    if isinstance(content, list):
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        joined = "".join(texts).strip()
        if joined:
            return joined

    output = response.get("output")
    if isinstance(output, list):
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            for block in item.get("content", []):
                if isinstance(block, dict) and block.get("type") == "output_text":
                    texts.append(block.get("text", ""))
        joined = "".join(texts).strip()
        if joined:
            return joined

    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        text = message.get("content")
        if isinstance(text, str) and text.strip():
            return text.strip()

    raise ValueError("No assistant text found in response payload")


def _gateway_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return root
    return f"{root}/v1"


def _post_json_with_client(
    client: httpx.Client, url: str, headers: dict[str, str], payload: dict[str, Any]
) -> dict[str, Any]:
    response = client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        return build_responses_json_from_sse(decode_sse_bytes(response.content))
    return response.json()


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        return _post_json_with_client(client, url, headers, payload)


def _backend_request_args(
    base_url: str, api_key: str, model: str, prompt: str, max_output_tokens: int
) -> tuple[str, dict[str, str], dict[str, Any]]:
    return (
        f"{_gateway_root(base_url)}/responses",
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        {
            "model": model,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
            "stream": True,
        },
    )


def _gateway_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def _gateway_count_tokens_request_args(
    base_url: str, api_key: str, model: str, prompt: str
) -> tuple[str, dict[str, str], dict[str, Any]]:
    root = _gateway_root(base_url)
    return (
        f"{root}/messages/count_tokens",
        _gateway_headers(api_key),
        {"model": model, "messages": [{"role": "user", "content": prompt}]},
    )


def _gateway_message_request_args(
    base_url: str, api_key: str, model: str, prompt: str, max_tokens: int
) -> tuple[str, dict[str, str], dict[str, Any]]:
    root = _gateway_root(base_url)
    return (
        f"{root}/messages",
        _gateway_headers(api_key),
        build_anthropic_messages_payload(model, prompt, max_tokens=max_tokens),
    )


def _measure_ms(func: Callable[[], dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    result = func()
    return (time.perf_counter() - started) * 1000, result


def summarize_latency_ms(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        raise ValueError("At least one latency sample is required")

    ordered = sorted(samples)
    p95_index = max(math.ceil(len(ordered) * 0.95) - 1, 0)
    return {
        "count": len(ordered),
        "min_ms": round(ordered[0], 2),
        "avg_ms": round(sum(ordered) / len(ordered), 2),
        "p50_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[p95_index], 2),
        "max_ms": round(ordered[-1], 2),
    }


def _validate_benchmark_iterations(repeats: int, warmup: int) -> None:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if warmup < 0:
        raise ValueError("warmup must be 0 or greater")


def run_backend_smoke(
    base_url: str, api_key: str, model: str, prompt: str, max_output_tokens: int = 64
) -> dict[str, Any]:
    url, headers, payload = _backend_request_args(base_url, api_key, model, prompt, max_output_tokens)
    data = _post_json(url, headers, payload)
    return {
        "target": "backend",
        "endpoint": url,
        "requested_model": model,
        "returned_model": data.get("model"),
        "text": extract_text(data),
    }


def run_gateway_smoke(
    base_url: str, api_key: str, model: str, prompt: str, max_tokens: int = 64
) -> dict[str, Any]:
    count_url, headers, count_payload = _gateway_count_tokens_request_args(base_url, api_key, model, prompt)
    message_url, _, message_payload = _gateway_message_request_args(
        base_url, api_key, model, prompt, max_tokens
    )
    count_data = _post_json(count_url, headers, count_payload)
    message_data = _post_json(message_url, headers, message_payload)
    return {
        "target": "gateway",
        "endpoint": message_url,
        "requested_model": model,
        "returned_model": message_data.get("model"),
        "input_tokens": count_data.get("input_tokens"),
        "text": extract_text(message_data),
    }


def run_backend_benchmark(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    *,
    repeats: int = 5,
    warmup: int = 1,
    max_output_tokens: int = 64,
    target: str = "backend",
) -> dict[str, Any]:
    _validate_benchmark_iterations(repeats, warmup)
    url, headers, payload = _backend_request_args(base_url, api_key, model, prompt, max_output_tokens)

    with httpx.Client(timeout=30.0) as client:
        last_data: dict[str, Any] | None = None
        for _ in range(warmup):
            last_data = _post_json_with_client(client, url, headers, payload)

        samples: list[float] = []
        for _ in range(repeats):
            duration_ms, last_data = _measure_ms(
                lambda: _post_json_with_client(client, url, headers, payload)
            )
            samples.append(duration_ms)

    assert last_data is not None
    return {
        "target": target,
        "endpoint": url,
        "requested_model": model,
        "returned_model": last_data.get("model"),
        "latency_ms": summarize_latency_ms(samples),
        "usage": last_data.get("usage"),
        "text": extract_text(last_data),
    }


def run_gateway_benchmark(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    *,
    repeats: int = 5,
    warmup: int = 1,
    max_tokens: int = 64,
) -> dict[str, Any]:
    _validate_benchmark_iterations(repeats, warmup)
    count_url, headers, count_payload = _gateway_count_tokens_request_args(base_url, api_key, model, prompt)
    message_url, _, message_payload = _gateway_message_request_args(
        base_url, api_key, model, prompt, max_tokens
    )

    with httpx.Client(timeout=30.0) as client:
        count_data: dict[str, Any] | None = None
        message_data: dict[str, Any] | None = None
        for _ in range(warmup):
            count_data = _post_json_with_client(client, count_url, headers, count_payload)
            message_data = _post_json_with_client(client, message_url, headers, message_payload)

        count_samples: list[float] = []
        message_samples: list[float] = []
        total_samples: list[float] = []
        for _ in range(repeats):
            count_ms, count_data = _measure_ms(
                lambda: _post_json_with_client(client, count_url, headers, count_payload)
            )
            message_ms, message_data = _measure_ms(
                lambda: _post_json_with_client(client, message_url, headers, message_payload)
            )
            count_samples.append(count_ms)
            message_samples.append(message_ms)
            total_samples.append(count_ms + message_ms)

    assert count_data is not None
    assert message_data is not None
    return {
        "target": "gateway",
        "count_tokens_endpoint": count_url,
        "endpoint": message_url,
        "requested_model": model,
        "returned_model": message_data.get("model"),
        "latency_ms": {
            "count_tokens": summarize_latency_ms(count_samples),
            "messages": summarize_latency_ms(message_samples),
            "total": summarize_latency_ms(total_samples),
        },
        "input_tokens": count_data.get("input_tokens"),
        "usage": message_data.get("usage"),
        "text": extract_text(message_data),
    }


def run_benchmark(
    *,
    backend_base_url: str,
    fixup_base_url: str,
    gateway_base_url: str,
    backend_api_key: str,
    gateway_api_key: str,
    model: str,
    prompt: str,
    repeats: int = 5,
    warmup: int = 1,
) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "repeats": repeats,
        "warmup": warmup,
        "results": [
            run_backend_benchmark(
                backend_base_url,
                backend_api_key,
                model,
                prompt,
                repeats=repeats,
                warmup=warmup,
                target="backend",
            ),
            run_backend_benchmark(
                fixup_base_url,
                backend_api_key,
                model,
                prompt,
                repeats=repeats,
                warmup=warmup,
                target="fixup",
            ),
            run_gateway_benchmark(
                gateway_base_url,
                gateway_api_key,
                model,
                prompt,
                repeats=repeats,
                warmup=warmup,
            ),
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke tests for backend and gateway")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("backend", "gateway"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--base-url", required=True)
        subparser.add_argument("--api-key", required=True)
        subparser.add_argument("--model", required=True)
        subparser.add_argument("--prompt", default="你好")

    benchmark_parser = subparsers.add_parser("bench")
    benchmark_parser.add_argument("--backend-base-url", default="http://127.0.0.1:8327/v1")
    benchmark_parser.add_argument("--fixup-base-url", default="http://127.0.0.1:8328/v1")
    benchmark_parser.add_argument("--gateway-base-url", default="http://127.0.0.1:4000")
    benchmark_parser.add_argument("--backend-api-key", required=True)
    benchmark_parser.add_argument("--gateway-api-key", required=True)
    benchmark_parser.add_argument("--model", required=True)
    benchmark_parser.add_argument("--prompt", default="你好")
    benchmark_parser.add_argument("--repeats", type=int, default=5)
    benchmark_parser.add_argument("--warmup", type=int, default=1)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "backend":
        result = run_backend_smoke(args.base_url, args.api_key, args.model, args.prompt)
    elif args.command == "gateway":
        result = run_gateway_smoke(args.base_url, args.api_key, args.model, args.prompt)
    else:
        result = run_benchmark(
            backend_base_url=args.backend_base_url,
            fixup_base_url=args.fixup_base_url,
            gateway_base_url=args.gateway_base_url,
            backend_api_key=args.backend_api_key,
            gateway_api_key=args.gateway_api_key,
            model=args.model,
            prompt=args.prompt,
            repeats=args.repeats,
            warmup=args.warmup,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
