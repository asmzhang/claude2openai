from __future__ import annotations

from collections.abc import Iterator
import json
from typing import Any


def decode_sse_bytes(raw_bytes: bytes) -> str:
    return raw_bytes.decode("utf-8", errors="replace")


def build_backend_target_url(backend_api_base: str, path: str) -> str:
    return f"{backend_api_base.rstrip('/')}/{path}"


def resolve_backend_authorization(
    backend_api_key: str | None, incoming_authorization: str | None = None
) -> str:
    del incoming_authorization
    if not backend_api_key:
        raise ValueError("BACKEND_API_KEY is not set")
    return f"Bearer {backend_api_key}"


def sanitize_responses_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "user" not in payload:
        return payload
    return {key: value for key, value in payload.items() if key != "user"}


def _parse_sse_events(sse_body: str) -> Iterator[dict[str, Any]]:
    for chunk in sse_body.split("\n\n"):
        lines = [line for line in chunk.splitlines() if line.strip()]
        data_lines = [line[5:].strip() for line in lines if line.startswith("data:")]
        if not data_lines:
            continue
        yield json.loads("\n".join(data_lines))


def build_responses_json_from_sse(sse_body: str) -> dict[str, Any]:
    created: dict[str, Any] = {}
    completed: dict[str, Any] = {}
    output_items: list[dict[str, Any]] = []

    for payload in _parse_sse_events(sse_body):
        payload_type = payload.get("type")
        if payload_type == "response.created":
            created = payload.get("response", {})
        elif payload_type == "response.output_item.done":
            item = payload.get("item")
            if isinstance(item, dict):
                output_items.append(item)
        elif payload_type == "response.completed":
            completed = payload.get("response", {})

    response = dict(created)
    response.update(completed)
    response.setdefault("object", "response")
    response.setdefault("status", "completed")
    response["output"] = output_items
    return response
