from litellm.litellm_core_utils.litellm_logging import Logging
from litellm.types.llms.openai import ResponseCompletedEvent, ResponsesAPIResponse

from claude2openai_gateway.litellm_patch import (
    apply_litellm_patch,
    normalize_anthropic_logging_result,
)


def test_normalize_anthropic_logging_result_keeps_responses_api_response():
    response = ResponsesAPIResponse(
        id="resp_123",
        created_at=1,
        model="gpt-5.5",
        object="response",
        output=[],
        usage=None,
    )

    assert normalize_anthropic_logging_result(response) is response


def test_normalize_anthropic_logging_result_unwraps_response_events():
    response = ResponsesAPIResponse(
        id="resp_123",
        created_at=1,
        model="gpt-5.5",
        object="response",
        output=[],
        usage=None,
    )
    event = ResponseCompletedEvent(
        type="response.completed",
        response=response,
    )

    assert normalize_anthropic_logging_result(event) is response


def test_apply_litellm_patch_short_circuits_responses_api_result():
    response = ResponsesAPIResponse(
        id="resp_123",
        created_at=1,
        model="gpt-5.5",
        object="response",
        output=[],
        usage=None,
    )

    apply_litellm_patch()

    assert Logging._handle_anthropic_messages_response_logging(object(), response) is response
