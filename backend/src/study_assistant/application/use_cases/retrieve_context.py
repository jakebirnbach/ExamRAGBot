"""Question -> the few chunks most likely to contain the answer."""

from collections import Counter
from collections.abc import Sequence

from study_assistant.domain.entities import MetadataFilter, ScoredChunk
from study_assistant.domain.ports import Embedder, Reranker, VectorStore


def limit_per_source(
    ranked: Sequence[ScoredChunk], top_n: int, max_per_source: int
) -> list[ScoredChunk]:
    """Keep ranking order but allow at most ``max_per_source`` chunks from any one file, so
    the final context isn't five overlapping chunks of the same transcript."""
    kept: list[ScoredChunk] = []
    per_source: Counter[str] = Counter()
    for item in ranked:
        source = item.chunk.metadata.source
        if per_source[source] < max_per_source:
            kept.append(item)
            per_source[source] += 1
            if len(kept) == top_n:
                break
    return kept


class RetrieveContext:
    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        reranker: Reranker | None = None,
        *,
        top_k: int = 20,
        top_n: int = 5,
        max_per_source: int = 2,
    ) -> None:
        if top_n > top_k:
            raise ValueError("top_n must be <= top_k")
        self._embedder = embedder
        self._store = store
        self._reranker = reranker
        self._top_k = top_k
        self._top_n = top_n
        self._max_per_source = max_per_source

    def execute(
        self,
        question: str,
        metadata_filter: MetadataFilter | None = None,
        *,
        rerank: bool = True,
    ) -> list[ScoredChunk]:
        """Hybrid search for ``top_k`` candidates, optionally rerank them all, then return
        the best ``top_n`` with at most ``max_per_source`` per file."""
        if not question.strip():
            raise ValueError("question must not be empty")
        candidates = self._store.search(
            self._embedder.embed_query(question), self._top_k, metadata_filter
        )
        if rerank and self._reranker is not None and candidates:
            candidates = self._reranker.rerank(question, candidates, top_n=len(candidates))
        return limit_per_source(candidates, self._top_n, self._max_per_source)
