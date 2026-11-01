from collections.abc import Sequence
from typing import Protocol

from study_assistant.domain.entities import ScoredChunk


class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        """Re-score candidates against the query; return the best ``top_n``, best first.
        Returned scores are the reranker's, not the retriever's."""
        ...
