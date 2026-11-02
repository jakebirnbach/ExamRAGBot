"""Response handling of the Bedrock adapter, with a stand-in client (no AWS calls)."""

from types import SimpleNamespace
from typing import Any

import pytest

from study_assistant.domain.errors import LLMError, LLMRefusalError
from study_assistant.domain.ports import Message
from study_assistant.infrastructure.llm.bedrock_claude import BedrockClaudeLLM


class StubMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


def make(
    stop_reason: str, *blocks: Any, details: Any = None
) -> tuple[BedrockClaudeLLM, StubMessages]:
    response = SimpleNamespace(content=list(blocks), stop_reason=stop_reason, stop_details=details)
    messages = StubMessages(response)
    llm = BedrockClaudeLLM(
        model_id="anthropic.claude-haiku-5-5",
        region="us-east-1",
        effort="low",
        client=SimpleNamespace(messages=messages),
    )
    return llm, messages


def text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


THINKING = SimpleNamespace(type="thinking", thinking="", signature="sig")


def test_reads_text_blocks_after_thinking_and_sends_expected_request() -> None:
    llm, messages = make("end_turn", THINKING, text("Answer "), text("[1]."))
    assert llm.complete("sys", [Message("user", "q")], max_tokens=500) == "Answer [1]."
    assert messages.kwargs == {
        "model": "anthropic.claude-haiku-5-5",
        "max_tokens": 500,
        "system": "sys",
        "messages": [{"role": "user", "content": "q"}],
        "output_config": {"effort": "low"},
    }


def test_refusal_raises_with_category() -> None:
    llm, _ = make("refusal", details=SimpleNamespace(category="bio"))
    with pytest.raises(LLMRefusalError) as info:
        llm.complete("sys", [Message("user", "q")])
    assert info.value.category == "bio"


def test_thinking_only_at_max_tokens_is_an_error() -> None:
    llm, _ = make("max_tokens", THINKING)
    with pytest.raises(LLMError, match="max_tokens=4096"):
        llm.complete("sys", [Message("user", "q")])


def test_empty_reply_is_an_error() -> None:
    llm, _ = make("end_turn", text("   "))
    with pytest.raises(LLMError, match="no text"):
        llm.complete("sys", [Message("user", "q")])
