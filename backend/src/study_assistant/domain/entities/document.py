from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Page:
    """One page of extracted text. ``number`` is 1-based, as printed in the material."""

    number: int
    text: str

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"page number must be >= 1, got {self.number}")


@dataclass(frozen=True, slots=True)
class Document:
    """A parsed course-material file."""

    source: str
    """Path relative to the raw-data directory, e.g. ``Module 3 .../M3 L1 ....pdf``."""
    pages: tuple[Page, ...]
    title: str = ""
    """Human-readable title (usually the file stem); prepended to chunks as context."""
    topic: str | None = None
    """Topic label used for filtering, e.g. ``M3 · Health Behavior Change Theory``."""
    module: str | None = None
    """Course module, e.g. ``M3``."""
    lesson: str | None = None
    """Lesson within the module, e.g. ``L1``."""
    checksum: str = ""
    """Content hash of the source file; used to skip exact duplicates."""

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("document source must not be empty")
