from dataclasses import dataclass, field

from study_assistant.domain.entities.chunk import Chunk


@dataclass(frozen=True, slots=True)
class SparseVector:
    """Lexical weights (BGE-M3 sparse output): parallel token-id / weight arrays."""

    indices: tuple[int, ...] = ()
    values: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if len(self.indices) != len(self.values):
            raise ValueError("sparse indices and values must have the same length")


@dataclass(frozen=True, slots=True)
class Embedding:
    """Hybrid embedding: a dense vector plus an optional sparse (lexical) vector."""

    dense: tuple[float, ...]
    sparse: SparseVector = field(default_factory=SparseVector)


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """A chunk paired with its embedding, ready to upsert."""

    chunk: Chunk
    embedding: Embedding
