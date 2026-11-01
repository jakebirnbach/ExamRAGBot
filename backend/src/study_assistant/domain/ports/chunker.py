from typing import Protocol

from study_assistant.domain.entities import Chunk, Document


class Chunker(Protocol):
    def chunk(self, document: Document) -> list[Chunk]:
        """Split a document into chunks. Every chunk carries source/page/topic/index metadata."""
        ...
