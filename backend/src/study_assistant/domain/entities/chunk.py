import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    """Provenance stored alongside every chunk; used for citations and filtering."""

    source: str
    page: int
    """First page the chunk's text comes from (1-based)."""
    chunk_index: int
    """Position of the chunk within its source document (0-based)."""
    topic: str | None = None
    page_end: int | None = None
    """Last page, when the chunk spans several (merged slides). ``None`` means single page."""
    module: str | None = None
    lesson: str | None = None

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError(f"page must be >= 1, got {self.page}")
        if self.chunk_index < 0:
            raise ValueError(f"chunk_index must be >= 0, got {self.chunk_index}")
        if self.page_end is not None and self.page_end <= self.page:
            raise ValueError(f"page_end must be > page when set, got {self.page}-{self.page_end}")

    @property
    def last_page(self) -> int:
        return self.page_end or self.page


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    """``<source-hash>#<chunk_index>``: deterministic, ASCII, and prefix-listable per source."""
    text: str
    metadata: ChunkMetadata

    @staticmethod
    def id_prefix(source: str) -> str:
        """Prefix shared by every chunk id of one source file (used to delete a file's chunks)."""
        return hashlib.sha256(source.encode()).hexdigest()[:16] + "#"

    @staticmethod
    def make_id(source: str, chunk_index: int) -> str:
        return f"{Chunk.id_prefix(source)}{chunk_index}"


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A chunk returned by retrieval or reranking, with its relevance score."""

    chunk: Chunk
    score: float
