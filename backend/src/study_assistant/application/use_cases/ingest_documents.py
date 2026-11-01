"""Parse -> chunk -> embed -> upsert, one file at a time."""

import re
from collections.abc import Callable, Collection, Iterator, Sequence
from itertools import batched
from pathlib import Path

from study_assistant.application.dto import (
    FailedFile,
    FileOutcome,
    IngestedFile,
    IngestReport,
    SkippedFile,
)
from study_assistant.domain.entities import EmbeddedChunk, Embedding
from study_assistant.domain.errors import DocumentParsingError, StudyAssistantError
from study_assistant.domain.ports import Chunker, DocumentParser, Embedder, VectorStore

_COPY_SUFFIX = re.compile(r"\s\(\d+\)$")  # "Notes (1).pdf" - a browser re-download


def _discovery_order(path: Path) -> tuple[bool, str]:
    # Originals before " (1)" copies, so duplicate detection keeps the clean file name.
    return bool(_COPY_SUFFIX.search(path.stem)), path.as_posix()


def discover_files(root: Path, exclude: Collection[str] = ()) -> list[Path]:
    """Every non-hidden file under ``root``. ``exclude`` entries match either the file name
    or the path relative to ``root``. Unsupported types are left to the parser to reject,
    so they show up in the report instead of vanishing silently."""
    found: list[Path] = []
    for path in sorted(root.rglob("*"), key=_discovery_order):
        rel = path.relative_to(root)
        if not path.is_file() or any(part.startswith(".") for part in rel.parts):
            continue
        if path.name in exclude or rel.as_posix() in exclude:
            continue
        found.append(path)
    return found


class IngestDocuments:
    def __init__(
        self,
        parser: DocumentParser,
        chunker: Chunker,
        embedder: Embedder,
        store: VectorStore,
        embed_batch_size: int = 32,
    ) -> None:
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._batch_size = embed_batch_size

    def execute(
        self,
        paths: Sequence[Path],
        *,
        dry_run: bool = False,
        on_file_done: Callable[[FileOutcome], None] | None = None,
    ) -> IngestReport:
        """Index ``paths``. With ``dry_run`` the files are parsed and chunked only:
        nothing is embedded or written."""
        report = IngestReport()
        seen_checksums: dict[str, str] = {}
        for path in paths:
            outcome = self._ingest_one(path, seen_checksums, dry_run)
            report.add(outcome)
            if on_file_done:
                on_file_done(outcome)
        return report

    def _ingest_one(self, path: Path, seen: dict[str, str], dry_run: bool) -> FileOutcome:
        if not self._parser.supports(path):
            return SkippedFile(str(path), "unsupported file type")
        try:
            document = self._parser.parse(path)
        except DocumentParsingError as exc:
            return FailedFile(str(path), str(exc))

        if document.checksum:
            if original := seen.get(document.checksum):
                return SkippedFile(document.source, f"duplicate of {original}")
            seen[document.checksum] = document.source

        chunks = self._chunker.chunk(document)
        if not chunks:
            return SkippedFile(document.source, "no extractable text (scanned or image-only?)")

        if not dry_run:
            try:
                embeddings = list(self._embed([c.text for c in chunks]))
                # Embed first, then replace: a failure above leaves the old chunks intact.
                self._store.delete_source(document.source)
                self._store.upsert(
                    [EmbeddedChunk(c, e) for c, e in zip(chunks, embeddings, strict=True)]
                )
            except StudyAssistantError as exc:
                return FailedFile(document.source, str(exc))

        return IngestedFile(document.source, len(document.pages), len(chunks), document.topic)

    def _embed(self, texts: list[str]) -> Iterator[Embedding]:
        for batch in batched(texts, self._batch_size):
            yield from self._embedder.embed_documents(batch)
