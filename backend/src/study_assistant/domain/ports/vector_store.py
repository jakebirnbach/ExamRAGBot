from collections.abc import Sequence
from typing import Protocol

from study_assistant.domain.entities import (
    Chunk,
    EmbeddedChunk,
    Embedding,
    MetadataFilter,
    ScoredChunk,
)


class VectorStore(Protocol):
    def upsert(self, items: Sequence[EmbeddedChunk]) -> None:
        """Insert or overwrite chunks by id."""
        ...

    def delete_source(self, source: str) -> int:
        """Remove every chunk of one source file; returns how many were removed."""
        ...

    def search(
        self,
        query: Embedding,
        top_k: int,
        metadata_filter: MetadataFilter | None = None,
    ) -> list[ScoredChunk]:
        """Hybrid (dense + sparse) search, best match first."""
        ...

    def sample(self, count: int, metadata_filter: MetadataFilter | None = None) -> list[Chunk]:
        """Up to ``count`` chunks picked at random from those matching the filter."""
        ...

    def list_topics(self) -> list[str]:
        """Distinct topic labels present in the index, sorted."""
        ...
