from pathlib import Path, PurePath

import pytest

from study_assistant.infrastructure.parsing.course_catalog import (
    GENERAL_TOPIC,
    CourseCatalog,
    normalize_title,
)

FILES = [
    "Module 3 Video Transcripts/M3 L1 Video 7 - Self-Efficacy.pdf",
    "Module 3 Video Transcripts/M3 L1 Video 4 -Self-Determination Theory.pdf",
    "Module 2 Video Transcripts/M2 L3 Video 10 - S.M.A.R.T. Goals.pdf",
    "Module 2 Video Transcripts/M2 L4 Video 3 - Follow-up Session.pdf",
    "Module 4 Video Transcripts/M4 L2 Video 1 - Follow-Up Session 1.pdf",
    "Module 6 Video Transcripts/M6 L4 Video 8 - Spritual Wellness.pdf",
]


@pytest.fixture
def catalog(tmp_path: Path) -> CourseCatalog:
    for rel in FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"")
    return CourseCatalog.from_directory(tmp_path)


@pytest.mark.parametrize(
    ("path", "module", "lesson"),
    [
        (FILES[0], "M3", "L1"),
        ("Module 5 Video Transcripts/notes.pdf", "M5", None),  # folder only
        ("Video Slides Handout - Self-Efficacy.pdf", "M3", "L1"),  # exact title
        ("SMART Goals.pdf", "M2", "L3"),  # punctuation-insensitive
        ("Video Slides Handout - Spiritual Wellness.pdf", "M6", "L4"),  # typo, fuzzy
        ("Self-Determination Theory.pdf", "M3", "L1"),
        ("Video Slides Handout - The Follow-Up Session.pdf", None, None),  # ambiguous M2/M4
        ("The Science of Nature Exposure.pdf", None, None),  # unrelated
    ],
)
def test_classify(
    catalog: CourseCatalog, path: str, module: str | None, lesson: str | None
) -> None:
    c = catalog.classify(PurePath(path))
    assert (c.module, c.lesson) == (module, lesson)
    assert (c.topic == GENERAL_TOPIC) is (module is None)
    if module:
        assert c.topic.startswith(f"{module} · ")


def test_normalize_title() -> None:
    assert normalize_title("Video Slides Handout - The Wellness Vision (1)") == "wellnessvision"
    assert normalize_title("Transtheoretical Model 2") == "transtheoreticalmodel"
