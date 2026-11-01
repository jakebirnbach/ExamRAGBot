from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Citation:
    source: str
    page: int
    page_end: int | None = None

    def __str__(self) -> str:
        if self.page_end and self.page_end != self.page:
            return f"{self.source}, pp. {self.page}-{self.page_end}"
        return f"{self.source}, p. {self.page}"


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    citations: tuple[Citation, ...]
    grounded: bool
    """False when the retrieved materials did not cover the question."""
