from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .fixup import (
    build_backend_target_url,
    build_responses_json_from_sse,
    decode_sse_bytes,
    resolve_backend_authorization,
    sanitize_responses_payload,
)

logger = logging.getLogger("uvicorn.error")


def _backend_root() -> str:
    base_url = os.environ.get("BACKEND_API_BASE", "http://127.0.0.1:8327/v1")
    return base_url.rstrip("/")


def _backend_auth_headers(request: Request) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    try:
        headers["Authorization"] = resolve_backend_authorization(
            backend_api_key=os.environ.get("BACKEND_API_KEY"),
            incoming_authorization=request.headers.get("authorization"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return headers


def _create_backend_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=60.0)


async def _backend_client() -> httpx.AsyncClient:
    client = getattr(app.state, "backend_client", None)
    if client is None:
        client = _create_backend_client()
        app.state.backend_client = client
    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _backend_client()
    try:
        yield
    finally:
        client = getattr(app.state, "backend_client", None)
        if client is not None:
            await client.aclose()
            delattr(app.state, "backend_client")


app = FastAPI(title="claude2openai-fixup", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _stream_upstream_response(upstream: httpx.Response):
    try:
        async for chunk in upstream.aiter_raw():
            if chunk:
                yield chunk
    finally:
        await upstream.aclose()


async def _proxy_streaming_responses(
    client: httpx.AsyncClient,
    target_url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> Response:
    upstream_request = client.build_request("POST", target_url, headers=headers, json=payload)
    upstream = await client.send(upstream_request, stream=True)
    if upstream.is_error:
        content = await upstream.aread()
        await upstream.aclose()
        return Response(
            content=content,
            media_type=upstream.headers.get("content-type", "application/json"),
            status_code=upstream.status_code,
        )

    return StreamingResponse(
        _stream_upstream_response(upstream),
        media_type=upstream.headers.get("content-type", "text/event-stream"),
        status_code=upstream.status_code,
    )


@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def proxy_v1(path: str, request: Request) -> Response:
    target_url = build_backend_target_url(_backend_root(), path)
    logger.info("Proxying %s %s -> %s", request.method, request.url.path, target_url)
    headers = _backend_auth_headers(request)
    client = await _backend_client()

    if request.method == "GET":
        upstream = await client.get(target_url, headers=headers)
        return Response(
            content=upstream.content,
            media_type=upstream.headers.get("content-type"),
            status_code=upstream.status_code,
        )

    payload: dict[str, Any] = await request.json()
    if path == "responses":
        payload = sanitize_responses_payload(payload)
        stream_requested = bool(payload.get("stream"))
        if stream_requested:
            return await _proxy_streaming_responses(client, target_url, headers, payload)

        upstream_payload = dict(payload)
        upstream_payload["stream"] = True
        upstream = await client.post(target_url, headers=headers, json=upstream_payload)
        if upstream.is_error:
            return Response(
                content=upstream.content,
                media_type=upstream.headers.get("content-type", "application/json"),
                status_code=upstream.status_code,
            )
        return JSONResponse(build_responses_json_from_sse(decode_sse_bytes(upstream.content)))

    body = await request.body()
    upstream = await client.post(target_url, headers=headers, content=body)
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type"),
        status_code=upstream.status_code,
    )
