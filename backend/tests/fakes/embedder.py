import math
import zlib
from collections import Counter
from collections.abc import Sequence

from study_assistant.domain.entities import Embedding, SparseVector
from study_assistant.domain.errors import EmbeddingError
from tests.fakes.text import tokenize


def _bucket(token: str, size: int) -> int:
    return zlib.crc32(token.encode()) % size


class FakeEmbedder:
    """Hashed bag-of-words: deterministic, and texts sharing words land close together."""

    def __init__(self, dimension: int = 64, vocab_size: int = 10_000) -> None:
        self._dimension = dimension
        self._vocab_size = vocab_size
        self.calls: list[Sequence[str]] = []
        self.fail_on: str | None = None
        """Raise ``EmbeddingError`` for any batch containing this substring."""

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> list[Embedding]:
        self.calls.append(list(texts))
        if self.fail_on and any(self.fail_on in t for t in texts):
            raise EmbeddingError(f"fake failure on {self.fail_on!r}")
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> Embedding:
        return self._embed(text)

    def _embed(self, text: str) -> Embedding:
        counts = Counter(tokenize(text))
        dense = [0.0] * self._dimension
        for token, n in counts.items():
            dense[_bucket(token, self._dimension)] += n
        norm = math.sqrt(sum(x * x for x in dense)) or 1.0

        sparse: dict[int, float] = {}
        for token, n in counts.items():
            idx = _bucket(token, self._vocab_size)
            sparse[idx] = sparse.get(idx, 0.0) + float(n)
        indices = tuple(sorted(sparse))
        return Embedding(
            dense=tuple(x / norm for x in dense),
            sparse=SparseVector(indices=indices, values=tuple(sparse[i] for i in indices)),
        )
