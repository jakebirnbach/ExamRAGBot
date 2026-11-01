"""Normalise raw PDF text before chunking."""

import re
import unicodedata

# Private-use / symbol-font glyphs that PDFs emit for bullets.
_BULLET_GLYPHS = re.compile("[▪●■•➢]")
_PAGE_FOOTER = re.compile(r"^\s*\d+\s*\|\s*P\s*a\s*g\s*e\s*$", re.IGNORECASE)
_BOILERPLATE_LINES = frozenset({"video transcript"})
_BLANK_RUNS = re.compile(r"\n{3,}")


def clean_page_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # ligatures: "ﬁ" -> "fi"
    text = _BULLET_GLYPHS.sub("•", text)
    lines: list[str] = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if _PAGE_FOOTER.match(line) or line.lower() in _BOILERPLATE_LINES:
            continue
        lines.append(line)
    # Whitespace-only lines from the PDF become blank lines; keep at most one in a row.
    return _BLANK_RUNS.sub("\n\n", "\n".join(lines)).strip()
