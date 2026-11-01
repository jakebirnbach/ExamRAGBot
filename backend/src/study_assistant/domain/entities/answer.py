from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Citation:
    source: str
    page: int

    def __str__(self) -> str:
        return f"{self.source}, p. {self.page}"


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    citations: tuple[Citation, ...]
    grounded: bool
    """False when the retrieved materials did not cover the question."""
