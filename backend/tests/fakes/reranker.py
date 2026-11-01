from collections.abc import Sequence

from study_assistant.domain.entities import ScoredChunk
from tests.fakes.text import tokenize


class FakeReranker:
    """Scores by the fraction of query tokens present in the chunk."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []  # (query, n_candidates, top_n)

    def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        self.calls.append((query, len(candidates), top_n))
        q = set(tokenize(query))
        rescored = [
            ScoredChunk(
                chunk=c.chunk,
                score=len(q & set(tokenize(c.chunk.text))) / len(q) if q else 0.0,
            )
            for c in candidates
        ]
        rescored.sort(key=lambda s: s.score, reverse=True)
        return rescored[:top_n]
