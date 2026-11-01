from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    """Provenance stored alongside every chunk; used for citations and filtering."""

    source: str
    page: int
    chunk_index: int
    """Position of the chunk within its source document (0-based)."""
    topic: str | None = None

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError(f"page must be >= 1, got {self.page}")
        if self.chunk_index < 0:
            raise ValueError(f"chunk_index must be >= 0, got {self.chunk_index}")


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    """Stable, deterministic id (e.g. ``<source>::<chunk_index>``) so re-ingestion upserts."""
    text: str
    metadata: ChunkMetadata

    @staticmethod
    def make_id(source: str, chunk_index: int) -> str:
        return f"{source}::{chunk_index}"


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A chunk returned by retrieval or reranking, with its relevance score."""

    chunk: Chunk
    score: float
