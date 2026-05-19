from claude2openai_gateway.smoke import build_anthropic_messages_payload, extract_text


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
