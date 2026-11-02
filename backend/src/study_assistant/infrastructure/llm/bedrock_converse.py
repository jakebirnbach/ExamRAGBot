"""Claude on Amazon Bedrock via AWS's model-agnostic Converse API (boto3 ``bedrock-runtime``).

Used for models the Anthropic SDK's Bedrock client can't reach, such as Claude Haiku 4.5,
which Bedrock serves only through its legacy runtime. Select it with ``BEDROCK_API=converse``.
"""

from collections.abc import Sequence
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from study_assistant.domain.errors import LLMError, LLMRefusalError
from study_assistant.domain.ports import Message

# Converse stop reasons meaning a safety system blocked the output.
_REFUSAL_STOP_REASONS = frozenset({"content_filtered", "guardrail_intervened"})


class BedrockConverseLLM:
    def __init__(
        self,
        *,
        model_id: str,
        region: str,
        aws_profile: str | None = None,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        client: Any = None,
    ) -> None:
        """``client`` injects a stand-in for tests; otherwise one is built on first use."""
        self._model_id = model_id
        self._region = region
        self._aws_profile = aws_profile
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._client: Any = client

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int = 4096,
    ) -> str:
        try:
            response = self._get_client().converse(
                modelId=self._model_id,
                system=[{"text": system}],
                messages=[{"role": m.role, "content": [{"text": m.content}]} for m in messages],
                inferenceConfig={"maxTokens": max_tokens},
            )
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code, detail = error.get("Code", "Unknown"), error.get("Message", str(exc))
            if code == "AccessDeniedException":
                raise LLMError(
                    f"no access to {self._model_id!r} (profile "
                    f"{self._aws_profile or 'default chain'}): {detail}"
                ) from exc
            if code in {"ResourceNotFoundException", "ValidationException"}:
                raise LLMError(f"Bedrock rejected model {self._model_id!r}: {detail}") from exc
            if code == "ThrottlingException":
                raise LLMError(f"Bedrock rate limit hit after retries: {detail}") from exc
            raise LLMError(f"Bedrock {code}: {detail}") from exc
        except BotoCoreError as exc:  # credentials, profile, network
            raise LLMError(f"could not call Bedrock in {self._region}: {exc}") from exc

        stop_reason = response.get("stopReason")
        if stop_reason in _REFUSAL_STOP_REASONS:
            raise LLMRefusalError(stop_reason)
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(block["text"] for block in blocks if "text" in block).strip()
        if not text:
            if stop_reason == "max_tokens":
                raise LLMError(f"hit max_tokens={max_tokens} before writing an answer")
            raise LLMError(f"model returned no text (stopReason={stop_reason})")
        return text

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                session = boto3.Session(profile_name=self._aws_profile, region_name=self._region)
                self._client = session.client(
                    "bedrock-runtime",
                    config=Config(
                        read_timeout=self._timeout,
                        retries={"max_attempts": self._max_retries + 1, "mode": "standard"},
                    ),
                )
            except BotoCoreError as exc:  # e.g. the named profile doesn't exist
                raise LLMError(f"could not create the Bedrock client: {exc}") from exc
        return self._client
