from pathlib import Path

from study_assistant.domain.entities import Document
from study_assistant.domain.errors import DocumentParsingError


class FakeDocumentParser:
    """Returns pre-registered documents keyed by file name."""

    def __init__(self, documents: dict[str, Document] | None = None) -> None:
        self._documents = dict(documents or {})

    def supports(self, path: Path) -> bool:
        return path.name in self._documents

    def parse(self, path: Path) -> Document:
        try:
            return self._documents[path.name]
        except KeyError as exc:
            raise DocumentParsingError(f"no fake document registered for {path.name}") from exc
