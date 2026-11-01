from collections.abc import Mapping, Sequence
from typing import Any

from study_assistant.domain.entities import Embedding, SparseVector
from study_assistant.domain.errors import EmbeddingError


class BgeM3Embedder:
    """BAAI/bge-m3 on CPU: one forward pass yields the dense vector and the lexical
    (sparse) weights used for hybrid search. The model loads on first use."""

    DIMENSION = 1024

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        batch_size: int = 16,
        max_length: int = 1024,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._batch_size = batch_size
        self._max_length = max_length
        self._device = device
        self._model: Any = None

    @property
    def dimension(self) -> int:
        return self.DIMENSION

    def embed_documents(self, texts: Sequence[str]) -> list[Embedding]:
        if not texts:
            return []
        try:
            out = self._get_model().encode(
                list(texts),
                batch_size=self._batch_size,
                max_length=self._max_length,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )
        except Exception as exc:  # torch/transformers raise a wide variety of errors
            raise EmbeddingError(f"BGE-M3 encoding failed: {exc}") from exc
        return [
            Embedding(dense=tuple(float(x) for x in dense), sparse=_to_sparse(weights))
            for dense, weights in zip(out["dense_vecs"], out["lexical_weights"], strict=True)
        ]

    def embed_query(self, text: str) -> Embedding:
        return self.embed_documents([text])[0]

    def _get_model(self) -> Any:
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel  # noqa: PLC0415 - heavy import, deferred

            self._model = BGEM3FlagModel(self._model_name, use_fp16=False, devices=self._device)
        return self._model


def _to_sparse(weights: Mapping[str, Any]) -> SparseVector:
    pairs = sorted((int(token), float(w)) for token, w in weights.items() if float(w) > 0)
    return SparseVector(indices=tuple(i for i, _ in pairs), values=tuple(w for _, w in pairs))
