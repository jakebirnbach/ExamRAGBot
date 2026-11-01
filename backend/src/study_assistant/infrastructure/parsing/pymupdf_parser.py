import hashlib
from pathlib import Path

import pymupdf

from study_assistant.domain.entities import Document, Page
from study_assistant.domain.errors import DocumentParsingError
from study_assistant.infrastructure.parsing.course_catalog import CourseCatalog
from study_assistant.infrastructure.parsing.text_cleaning import clean_page_text


class PyMuPdfParser:
    """PDF -> per-page cleaned text, with source relative to ``root`` and course metadata."""

    def __init__(self, root: Path, catalog: CourseCatalog) -> None:
        self._root = root.resolve()
        self._catalog = catalog

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> Document:
        resolved = path.resolve()
        relative = (
            resolved.relative_to(self._root)
            if resolved.is_relative_to(self._root)
            else Path(path.name)
        )
        try:
            data = resolved.read_bytes()
            with pymupdf.open(stream=data, filetype="pdf") as pdf:
                pages = tuple(
                    Page(number=i + 1, text=clean_page_text(page.get_text()))
                    for i, page in enumerate(pdf)
                )
        except (OSError, RuntimeError, ValueError) as exc:
            raise DocumentParsingError(f"{relative}: {exc}") from exc

        classification = self._catalog.classify(relative)
        return Document(
            source=relative.as_posix(),
            pages=pages,
            title=relative.stem,
            topic=classification.topic,
            module=classification.module,
            lesson=classification.lesson,
            checksum=hashlib.sha256(data).hexdigest(),
        )
