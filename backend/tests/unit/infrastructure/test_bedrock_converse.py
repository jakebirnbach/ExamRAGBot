"""Request/response handling of the Converse adapter, with a stand-in client (no AWS calls)."""

from typing import Any

import pytest
from botocore.exceptions import ClientError

from study_assistant.domain.errors import LLMError, LLMRefusalError
from study_assistant.domain.ports import Message
from study_assistant.infrastructure.llm.bedrock_converse import BedrockConverseLLM

MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


class StubRuntime:
    def __init__(self, response: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.response = response or {}
        self.error = error
        self.kwargs: dict[str, Any] = {}

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.kwargs = kwargs
        if self.error:
            raise ClientError({"Error": {"Code": self.error, "Message": "nope"}}, "Converse")
        return self.response


def reply(stop: str, *blocks: dict[str, Any]) -> dict[str, Any]:
    return {
        "stopReason": stop,
        "output": {"message": {"role": "assistant", "content": list(blocks)}},
    }


def make(stub: StubRuntime) -> BedrockConverseLLM:
    return BedrockConverseLLM(model_id=MODEL, region="us-east-1", client=stub)


def test_sends_converse_request_and_joins_text_blocks() -> None:
    stub = StubRuntime(
        reply("end_turn", {"reasoningContent": {}}, {"text": "A "}, {"text": "[1]."})
    )
    out = make(stub).complete("sys", [Message("user", "q")], max_tokens=300)
    assert out == "A [1]."
    assert stub.kwargs == {
        "modelId": MODEL,
        "system": [{"text": "sys"}],
        "messages": [{"role": "user", "content": [{"text": "q"}]}],
        "inferenceConfig": {"maxTokens": 300},
    }


@pytest.mark.parametrize("stop", ["content_filtered", "guardrail_intervened"])
def test_safety_stops_are_refusals(stop: str) -> None:
    with pytest.raises(LLMRefusalError):
        make(StubRuntime(reply(stop))).complete("sys", [Message("user", "q")])


def test_empty_at_max_tokens() -> None:
    with pytest.raises(LLMError, match="max_tokens"):
        make(StubRuntime(reply("max_tokens"))).complete("sys", [Message("user", "q")])


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("AccessDeniedException", "no access"),
        ("ThrottlingException", "rate limit"),
        ("ValidationException", "rejected model"),
        ("InternalServerException", "Bedrock Internal"),
    ],
)
def test_client_errors_map_to_llm_error(code: str, message: str) -> None:
    with pytest.raises(LLMError, match=message):
        make(StubRuntime(error=code)).complete("sys", [Message("user", "q")])
