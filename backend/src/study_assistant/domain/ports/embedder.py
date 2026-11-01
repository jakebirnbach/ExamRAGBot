from collections.abc import Sequence
from typing import Protocol

from study_assistant.domain.entities import Embedding


class Embedder(Protocol):
    @property
    def dimension(self) -> int:
        """Length of the dense vectors this embedder produces."""
        ...

    def embed_documents(self, texts: Sequence[str]) -> list[Embedding]:
        """Embed passages for indexing (batched)."""
        ...

    def embed_query(self, text: str) -> Embedding:
        """Embed a single search query."""
        ...
