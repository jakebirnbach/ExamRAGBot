from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from study_assistant.domain.errors import LLMError
from study_assistant.domain.ports import Message


@dataclass(frozen=True, slots=True)
class LLMCall:
    system: str
    messages: tuple[Message, ...]
    max_tokens: int
    temperature: float


class FakeLLM:
    """Returns scripted replies in order and records every call for assertions."""

    def __init__(self, replies: Iterable[str] = ()) -> None:
        self._replies: deque[str] = deque(replies)
        self.calls: list[LLMCall] = []

    def queue(self, *replies: str) -> None:
        self._replies.extend(replies)

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        self.calls.append(LLMCall(system, tuple(messages), max_tokens, temperature))
        if not self._replies:
            raise LLMError("FakeLLM has no scripted reply left")
        return self._replies.popleft()
