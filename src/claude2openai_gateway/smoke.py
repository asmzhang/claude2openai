from __future__ import annotations

import argparse
import json
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


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return build_responses_json_from_sse(decode_sse_bytes(response.content))
        return response.json()


def run_backend_smoke(
    base_url: str, api_key: str, model: str, prompt: str, max_output_tokens: int = 64
) -> dict[str, Any]:
    url = f"{_gateway_root(base_url)}/responses"
    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
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
    root = _gateway_root(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    count_payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    count_data = _post_json(f"{root}/messages/count_tokens", headers, count_payload)
    message_data = _post_json(
        f"{root}/messages",
        headers,
        build_anthropic_messages_payload(model, prompt, max_tokens=max_tokens),
    )
    return {
        "target": "gateway",
        "endpoint": f"{root}/messages",
        "requested_model": model,
        "returned_model": message_data.get("model"),
        "input_tokens": count_data.get("input_tokens"),
        "text": extract_text(message_data),
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "backend":
        result = run_backend_smoke(args.base_url, args.api_key, args.model, args.prompt)
    else:
        result = run_gateway_smoke(args.base_url, args.api_key, args.model, args.prompt)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
