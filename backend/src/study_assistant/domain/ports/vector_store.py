from collections.abc import Sequence
from typing import Protocol

from study_assistant.domain.entities import EmbeddedChunk, Embedding, MetadataFilter, ScoredChunk


class VectorStore(Protocol):
    def upsert(self, items: Sequence[EmbeddedChunk]) -> None:
        """Insert or overwrite chunks by id."""
        ...

    def search(
        self,
        query: Embedding,
        top_k: int,
        metadata_filter: MetadataFilter | None = None,
    ) -> list[ScoredChunk]:
        """Hybrid (dense + sparse) search, best match first."""
        ...

    def list_topics(self) -> list[str]:
        """Distinct topic labels present in the index, sorted."""
        ...
