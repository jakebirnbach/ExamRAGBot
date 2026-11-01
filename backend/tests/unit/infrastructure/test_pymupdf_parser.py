from pathlib import Path

import pymupdf
import pytest

from study_assistant.domain.errors import DocumentParsingError
from study_assistant.infrastructure.parsing.course_catalog import CourseCatalog
from study_assistant.infrastructure.parsing.pymupdf_parser import PyMuPdfParser


def write_pdf(path: Path, pages: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as pdf:
        for text in pages:
            pdf.new_page().insert_text((72, 72), text)
        pdf.save(path)


def test_parses_pages_with_metadata(tmp_path: Path) -> None:
    pdf = tmp_path / "Module 3 Video Transcripts" / "M3 L1 Video 7 - Self-Efficacy.pdf"
    write_pdf(pdf, ["Self-efficacy is belief.", "1 | P a g e\nMastery experiences."])
    parser = PyMuPdfParser(tmp_path, CourseCatalog.from_directory(tmp_path))

    doc = parser.parse(pdf)

    assert parser.supports(pdf) and not parser.supports(tmp_path / "x.zip")
    assert doc.source == "Module 3 Video Transcripts/M3 L1 Video 7 - Self-Efficacy.pdf"
    assert doc.title == "M3 L1 Video 7 - Self-Efficacy"
    assert [p.number for p in doc.pages] == [1, 2]
    assert doc.pages[1].text == "Mastery experiences."
    assert (doc.module, doc.lesson) == ("M3", "L1")
    assert len(doc.checksum) == 64


def test_corrupt_pdf_raises_domain_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(DocumentParsingError):
        PyMuPdfParser(tmp_path, CourseCatalog({})).parse(bad)
