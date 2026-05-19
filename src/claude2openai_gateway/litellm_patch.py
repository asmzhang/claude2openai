from __future__ import annotations

from typing import Any

from litellm.litellm_core_utils.litellm_logging import Logging
from litellm.types.llms.openai import ResponsesAPIResponse

_PATCH_FLAG = "_claude2openai_anthropic_logging_patch_applied"


def normalize_anthropic_logging_result(result: Any) -> Any:
    if isinstance(result, ResponsesAPIResponse):
        return result

    response = getattr(result, "response", None)
    if isinstance(response, ResponsesAPIResponse):
        return response

    return result


def apply_litellm_patch() -> None:
    if getattr(Logging, _PATCH_FLAG, False):
        return

    original = Logging._handle_anthropic_messages_response_logging

    def patched(self: Logging, result: Any) -> Any:
        normalized = normalize_anthropic_logging_result(result)
        if isinstance(result, ResponsesAPIResponse) or normalized is not result:
            return normalized
        return original(self, result)

    Logging._handle_anthropic_messages_response_logging = patched
    setattr(Logging, _PATCH_FLAG, True)
