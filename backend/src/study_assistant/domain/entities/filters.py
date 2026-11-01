from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetadataFilter:
    """Restricts retrieval to a subset of chunks. ``None`` fields are unconstrained;
    non-empty tuples mean "any of"."""

    topics: tuple[str, ...] | None = None
    sources: tuple[str, ...] | None = None

    def matches(self, topic: str | None, source: str) -> bool:
        if self.topics is not None and topic not in self.topics:
            return False
        return self.sources is None or source in self.sources
