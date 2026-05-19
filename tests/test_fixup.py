from claude2openai_gateway.fixup import (
    build_backend_target_url,
    build_responses_json_from_sse,
    decode_sse_bytes,
    resolve_backend_authorization,
    sanitize_responses_payload,
)


def test_build_responses_json_from_sse_extracts_text_model_and_usage():
    sse_body = """
event: response.created
data: {"type":"response.created","response":{"id":"resp_123","model":"gpt-5.4"}}

event: response.output_item.done
data: {"type":"response.output_item.done","item":{"id":"msg_123","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"你好！有什么我可以帮你的吗？"}]}}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_123","model":"gpt-5.4","status":"completed","usage":{"input_tokens":7,"output_tokens":13,"total_tokens":20}}}
""".strip()

    response = build_responses_json_from_sse(sse_body)

    assert response["id"] == "resp_123"
    assert response["model"] == "gpt-5.4"
    assert response["status"] == "completed"
    assert response["usage"] == {
        "input_tokens": 7,
        "output_tokens": 13,
        "total_tokens": 20,
    }
    assert response["output"] == [
        {
            "id": "msg_123",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "你好！有什么我可以帮你的吗？",
                }
            ],
        }
    ]


def test_decode_sse_bytes_uses_utf8():
    assert decode_sse_bytes("你好".encode("utf-8")) == "你好"


def test_resolve_backend_authorization_ignores_incoming_gateway_token():
    assert (
        resolve_backend_authorization(
            backend_api_key="real-key",
            incoming_authorization="Bearer local-gateway-key",
        )
        == "Bearer real-key"
    )


def test_sanitize_responses_payload_removes_user_field():
    assert sanitize_responses_payload({"model": "gpt-5.5", "user": "opaque", "stream": True}) == {
        "model": "gpt-5.5",
        "stream": True,
    }


def test_build_backend_target_url_appends_path_to_backend_root():
    assert (
        build_backend_target_url("http://127.0.0.1:8327/v1/", "responses")
        == "http://127.0.0.1:8327/v1/responses"
    )
