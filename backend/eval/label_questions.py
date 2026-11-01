"""Fill in the gold pages for eval questions from their answer patterns.

Each line of ``questions_draft.jsonl`` is ``{"question", "answer_pattern", "prefer"?}``.
``answer_pattern`` is a case-insensitive regex that matches text *containing the answer*.
Every indexed page matching it becomes an acceptable location; ``prefer`` (a substring of
a source path) picks which one is the primary ``expected_source`` / ``expected_page``.

    uv run python eval/label_questions.py eval/questions_draft.jsonl > eval/questions.jsonl

Review the output: a pattern that matches dozens of pages is too loose; zero means too strict.
"""

import json
import re
import sys
from pathlib import Path

from study_assistant.application.use_cases.ingest_documents import discover_files
from study_assistant.infrastructure.config import get_settings
from study_assistant.infrastructure.parsing.course_catalog import CourseCatalog
from study_assistant.infrastructure.parsing.pymupdf_parser import PyMuPdfParser


def load_pages() -> list[tuple[str, int, str]]:
    settings = get_settings()
    root = settings.raw_data_dir
    parser = PyMuPdfParser(root, CourseCatalog.from_directory(root))
    pages: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for path in discover_files(root, settings.ingest_exclusions()):
        if not parser.supports(path):
            continue
        doc = parser.parse(path)
        if doc.checksum in seen:  # same duplicate rule as ingestion
            continue
        seen.add(doc.checksum)
        pages.extend((doc.source, p.number, " ".join(p.text.split())) for p in doc.pages)
    return pages


def main() -> None:
    drafts = [
        json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()
    ]
    pages = load_pages()
    for i, d in enumerate(drafts, 1):
        rx = re.compile(d["answer_pattern"], re.IGNORECASE)
        hits = [(s, n) for s, n, text in pages if rx.search(text)]
        preferred = [h for h in hits if d.get("prefer", "") in h[0]] or hits
        sources = {s for s, _ in hits}
        print(
            f"q{i:02d} {len(hits):3d} pages / {len(sources):2d} files  {d['question'][:70]}",
            file=sys.stderr,
        )
        if not hits:
            print("     !! no matches", file=sys.stderr)
            continue
        primary = preferred[0]
        print(
            json.dumps(
                {
                    "id": f"q{i:02d}",
                    "question": d["question"],
                    "expected_source": primary[0],
                    "expected_page": primary[1],
                    "also_accept": [{"source": s, "page": n} for s, n in hits if (s, n) != primary],
                    "answer_pattern": d["answer_pattern"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
