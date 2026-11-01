from collections.abc import Sequence

from study_assistant.domain.entities import (
    EmbeddedChunk,
    Embedding,
    MetadataFilter,
    ScoredChunk,
    SparseVector,
)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _sparse_dot(a: SparseVector, b: SparseVector) -> float:
    weights = dict(zip(a.indices, a.values, strict=True))
    return sum(weights.get(i, 0.0) * v for i, v in zip(b.indices, b.values, strict=True))


class InMemoryVectorStore:
    """Brute-force hybrid search: ``alpha * dense_dot + (1 - alpha) * sparse_dot``."""

    def __init__(self, alpha: float = 0.5) -> None:
        self._alpha = alpha
        self.items: dict[str, EmbeddedChunk] = {}
        self.deleted_sources: list[str] = []

    def upsert(self, items: Sequence[EmbeddedChunk]) -> None:
        for item in items:
            self.items[item.chunk.id] = item

    def delete_source(self, source: str) -> int:
        doomed = [cid for cid, item in self.items.items() if item.chunk.metadata.source == source]
        for cid in doomed:
            del self.items[cid]
        self.deleted_sources.append(source)
        return len(doomed)

    def search(
        self,
        query: Embedding,
        top_k: int,
        metadata_filter: MetadataFilter | None = None,
    ) -> list[ScoredChunk]:
        scored: list[ScoredChunk] = []
        for item in self.items.values():
            meta = item.chunk.metadata
            if metadata_filter and not metadata_filter.matches(meta.topic, meta.source):
                continue
            score = self._alpha * _dot(query.dense, item.embedding.dense) + (
                1 - self._alpha
            ) * _sparse_dot(query.sparse, item.embedding.sparse)
            scored.append(ScoredChunk(chunk=item.chunk, score=score))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]

    def list_topics(self) -> list[str]:
        return sorted({t for i in self.items.values() if (t := i.chunk.metadata.topic)})
