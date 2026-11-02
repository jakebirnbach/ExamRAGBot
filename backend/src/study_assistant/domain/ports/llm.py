from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


class LLM(Protocol):
    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int = 4096,
    ) -> str:
        """Return the model's text reply.

        Raises ``LLMRefusalError`` when the model's safety system declines the request and
        ``LLMError`` for any other failure. (No sampling parameters: current Claude models
        reject ``temperature``/``top_p``.)"""
        ...
