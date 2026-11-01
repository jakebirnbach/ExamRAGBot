from pathlib import Path
from typing import Protocol

from study_assistant.domain.entities import Document


class DocumentParser(Protocol):
    def supports(self, path: Path) -> bool:
        """Whether this parser can handle the file (usually by extension)."""
        ...

    def parse(self, path: Path) -> Document:
        """Extract per-page text. Raises ``DocumentParsingError`` on failure."""
        ...
