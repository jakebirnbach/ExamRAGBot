from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from study_assistant.domain.errors import LLMError, LLMRefusalError
from study_assistant.domain.ports import Message


@dataclass(frozen=True, slots=True)
class LLMCall:
    system: str
    messages: tuple[Message, ...]
    max_tokens: int


class FakeLLM:
    """Returns scripted replies in order (or computes one with ``responder``) and records
    every call for assertions. Queue ``FakeLLM.REFUSE`` to simulate a safety refusal."""

    REFUSE = "<<refuse>>"

    def __init__(
        self,
        replies: Iterable[str] = (),
        responder: Callable[[str, Sequence[Message]], str] | None = None,
    ) -> None:
        self._replies: deque[str] = deque(replies)
        self._responder = responder
        self.calls: list[LLMCall] = []

    def queue(self, *replies: str) -> None:
        self._replies.extend(replies)

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int = 4096,
    ) -> str:
        self.calls.append(LLMCall(system, tuple(messages), max_tokens))
        if self._replies:
            reply = self._replies.popleft()
        elif self._responder is not None:
            reply = self._responder(system, messages)
        else:
            raise LLMError("FakeLLM has no scripted reply left")
        if reply == self.REFUSE:
            raise LLMRefusalError("test")
        return reply
