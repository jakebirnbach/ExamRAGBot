from collections.abc import Sequence
from typing import Any

from study_assistant.domain.entities import ScoredChunk
from study_assistant.domain.errors import RerankingError


class BgeReranker:
    """BAAI/bge-reranker-v2-m3 cross-encoder: reads question and chunk *together* and scores
    relevance (0-1 after sigmoid). Slower than vector search, much more precise, so it only
    re-orders the shortlist the hybrid search returns. The model loads on first use."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        *,
        batch_size: int = 16,
        max_length: int = 512,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._batch_size = batch_size
        self._max_length = max_length
        self._device = device
        self._model: Any = None

    def rerank(
        self, query: str, candidates: Sequence[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        if not candidates:
            return []
        pairs = [(query, c.chunk.text) for c in candidates]
        try:
            scores = self._get_model().compute_score(pairs, batch_size=self._batch_size)
        except Exception as exc:  # torch/transformers raise a wide variety of errors
            raise RerankingError(f"reranking failed: {exc}") from exc
        if isinstance(scores, float):  # FlagEmbedding unwraps single-pair results
            scores = [scores]
        rescored = [
            ScoredChunk(chunk=c.chunk, score=float(s))
            for c, s in zip(candidates, scores, strict=True)
        ]
        rescored.sort(key=lambda s: s.score, reverse=True)
        return rescored[:top_n]

    def _get_model(self) -> Any:
        if self._model is None:
            from FlagEmbedding import FlagReranker  # noqa: PLC0415 - heavy import, deferred

            self._model = FlagReranker(
                self._model_name,
                use_fp16=False,
                devices=self._device,
                normalize=True,
                max_length=self._max_length,
            )
        return self._model
