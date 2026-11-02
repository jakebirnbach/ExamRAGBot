"""Claude on Amazon Bedrock via the Anthropic SDK's Bedrock client (``AnthropicBedrockMantle``).

Current Claude models think adaptively by default, so a response can start with ``thinking``
blocks; text is read by block type. ``effort`` (low/medium/high/...) controls how much the
model thinks. Sampling parameters such as temperature are rejected by these models.
"""

from collections.abc import Sequence
from typing import Any

import anthropic
from anthropic.types import AssistantMessageParam, MessageParam, UserMessageParam

from study_assistant.domain.errors import LLMError, LLMRefusalError
from study_assistant.domain.ports import Message


class BedrockClaudeLLM:
    def __init__(
        self,
        *,
        model_id: str,
        region: str,
        aws_profile: str | None = None,
        effort: str = "low",
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        client: Any = None,
    ) -> None:
        """``client`` injects a stand-in for tests; otherwise one is built on first use."""
        self._model_id = model_id
        self._region = region
        self._aws_profile = aws_profile
        self._effort = effort
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._client: Any = client

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int = 4096,
    ) -> str:
        params = [_to_param(m) for m in messages]
        try:
            response = self._get_client().messages.create(
                model=self._model_id,
                max_tokens=max_tokens,
                system=system,
                messages=params,
                output_config={"effort": self._effort},
            )
        except anthropic.NotFoundError as exc:
            raise LLMError(
                f"Bedrock model {self._model_id!r} not found in {self._region} "
                f"(check BEDROCK_MODEL_ID and model access): {exc.message}"
            ) from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise LLMError(
                f"AWS credentials were rejected (profile {self._aws_profile or 'default chain'}); "
                f"check the IAM permissions and Bedrock model access: {exc.message}"
            ) from exc
        except anthropic.RateLimitError as exc:
            raise LLMError(f"Bedrock rate limit hit after retries: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Bedrock returned HTTP {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"could not reach Bedrock in {self._region}: {exc}") from exc

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMRefusalError(getattr(details, "category", None))

        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            if response.stop_reason == "max_tokens":
                raise LLMError(f"hit max_tokens={max_tokens} before writing an answer")
            raise LLMError(f"model returned no text (stop_reason={response.stop_reason})")
        return text

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                self._client = anthropic.AnthropicBedrockMantle(
                    aws_region=self._region,
                    aws_profile=self._aws_profile,
                    timeout=self._timeout,
                    max_retries=self._max_retries,
                )
            except Exception as exc:  # missing/invalid AWS config surfaces here
                raise LLMError(f"could not create the Bedrock client: {exc}") from exc
        return self._client


def _to_param(message: Message) -> MessageParam:
    if message.role == "assistant":
        return AssistantMessageParam(role="assistant", content=message.content)
    return UserMessageParam(role="user", content=message.content)
