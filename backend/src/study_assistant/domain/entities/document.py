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
    """File name relative to the raw-data directory, e.g. ``lecture-03-nutrition.pdf``."""
    pages: tuple[Page, ...]
    topic: str | None = None
    """Lecture/topic label, when it can be derived from the file name or folder."""

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("document source must not be empty")
