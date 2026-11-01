"""Token-budgeted chunking that keeps page provenance.

* Dense documents (prose: transcripts, study guide) are chunked page by page; a chunk
  never crosses a page boundary, so every citation is a single page.
* Sparse documents (slide decks, whose median page is tiny) are packed across pages,
  at most ``max_pages_per_chunk`` pages per chunk; those chunks carry a page range.
* Documents with almost no text (image-only PDFs) produce no chunks.

Each chunk is prefixed with the document title, so short passages ("Today's topic...")
still embed with their subject attached.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import median

from study_assistant.domain.entities import Chunk, ChunkMetadata, Document

TokenCounter = Callable[[str], int]

# Coarsest first: paragraphs, sentences, lines, words.
_SEPARATORS = (
    re.compile(r"\n\s*\n"),
    re.compile(r"(?<=[.!?])\s+"),
    re.compile(r"\n"),
    re.compile(r"\s+"),
)


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    page: int
    tokens: int


class TokenChunker:
    def __init__(
        self,
        count_tokens: TokenCounter,
        *,
        max_tokens: int = 450,
        overlap_tokens: int = 50,
        sparse_page_tokens: int = 150,
        max_pages_per_chunk: int = 6,
        min_document_tokens: int = 40,
    ) -> None:
        if not 0 <= overlap_tokens < max_tokens:
            raise ValueError("overlap_tokens must be >= 0 and < max_tokens")
        self._count = count_tokens
        self._max = max_tokens
        self._overlap = overlap_tokens
        self._sparse_page_tokens = sparse_page_tokens
        self._max_pages = max_pages_per_chunk
        self._min_document_tokens = min_document_tokens

    def chunk(self, document: Document) -> list[Chunk]:
        pages = [p for p in document.pages if p.text.strip()]
        if not pages:
            return []
        header = f"{document.title}\n" if document.title else ""
        budget = max(self._max - self._count(header), self._max // 2)

        page_units = [self._split(p.text, p.number, budget) for p in pages]
        page_tokens = [sum(u.tokens for u in units) for units in page_units]
        if sum(page_tokens) < self._min_document_tokens:
            return []  # e.g. an image-only PDF whose only text is a title and page numbers
        if median(page_tokens) < self._sparse_page_tokens:
            groups = self._pack([u for units in page_units for u in units], budget)
        else:
            groups = [g for units in page_units for g in self._pack(units, budget)]

        chunks: list[Chunk] = []
        for index, group in enumerate(groups):
            first, last = group[0].page, max(u.page for u in group)
            chunks.append(
                Chunk(
                    id=Chunk.make_id(document.source, index),
                    text=header + "\n".join(u.text for u in group),
                    metadata=ChunkMetadata(
                        source=document.source,
                        page=first,
                        page_end=last if last != first else None,
                        chunk_index=index,
                        topic=document.topic,
                        module=document.module,
                        lesson=document.lesson,
                    ),
                )
            )
        return chunks

    def _split(self, text: str, page: int, budget: int, level: int = 0) -> list[_Unit]:
        """Break ``text`` at the coarsest separator that yields pieces within ``budget``."""
        text = text.strip()
        if not text:
            return []
        tokens = self._count(text)
        if tokens <= budget or level == len(_SEPARATORS):
            return [_Unit(text, page, tokens)]  # an over-long single word is left to truncation
        units: list[_Unit] = []
        for part in _SEPARATORS[level].split(text):
            units.extend(self._split(part, page, budget, level + 1))
        return units

    def _pack(self, units: Sequence[_Unit], budget: int) -> list[list[_Unit]]:
        """Greedily fill chunks up to ``budget`` tokens, repeating ~overlap tokens of tail
        units at the start of the next chunk."""
        groups: list[list[_Unit]] = []
        current: list[_Unit] = []
        size = 0
        for unit in units:
            too_many_pages = current and unit.page - current[0].page >= self._max_pages
            if current and (size + unit.tokens > budget or too_many_pages):
                groups.append(current)
                current = self._tail(current, budget - unit.tokens)
                size = sum(u.tokens for u in current)
            current.append(unit)
            size += unit.tokens
        if current:
            groups.append(current)
        return groups

    def _tail(self, units: list[_Unit], room: int) -> list[_Unit]:
        tail: list[_Unit] = []
        size = 0
        for unit in reversed(units):
            if size + unit.tokens > min(self._overlap, room):
                break
            tail.insert(0, unit)
            size += unit.tokens
        return tail
