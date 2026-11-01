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
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        """Return the model's text reply. Raises ``LLMError`` on failure."""
        ...
