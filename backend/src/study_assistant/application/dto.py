"""Input/output models for use cases (plain dataclasses; no pydantic in this layer)."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class IngestedFile:
    source: str
    pages: int
    chunks: int
    topic: str | None


@dataclass(frozen=True, slots=True)
class SkippedFile:
    """A file deliberately not indexed (unsupported, duplicate, no text)."""

    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class FailedFile:
    """A file that should have been indexed but errored."""

    path: str
    error: str


FileOutcome = IngestedFile | SkippedFile | FailedFile


@dataclass(slots=True)
class IngestReport:
    ingested: list[IngestedFile] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)
    failed: list[FailedFile] = field(default_factory=list)

    def add(self, outcome: FileOutcome) -> None:
        match outcome:
            case IngestedFile():
                self.ingested.append(outcome)
            case SkippedFile():
                self.skipped.append(outcome)
            case FailedFile():
                self.failed.append(outcome)

    @property
    def total_chunks(self) -> int:
        return sum(f.chunks for f in self.ingested)
