import pytest

from study_assistant.domain.entities import (
    Chunk,
    ChunkMetadata,
    Citation,
    Document,
    MetadataFilter,
    Page,
    QuizGrade,
    SparseVector,
)


def test_page_numbers_are_one_based() -> None:
    with pytest.raises(ValueError, match="page number"):
        Page(0, "x")


def test_document_requires_source() -> None:
    with pytest.raises(ValueError, match="source"):
        Document(source="", pages=())


def test_chunk_metadata_validation() -> None:
    with pytest.raises(ValueError, match="page"):
        ChunkMetadata(source="a.pdf", page=0, chunk_index=0)
    with pytest.raises(ValueError, match="chunk_index"):
        ChunkMetadata(source="a.pdf", page=1, chunk_index=-1)


def test_chunk_id_is_deterministic() -> None:
    assert Chunk.make_id("a.pdf", 3) == Chunk.make_id("a.pdf", 3)
    assert Chunk.make_id("a.pdf", 3).startswith(Chunk.id_prefix("a.pdf"))
    assert Chunk.id_prefix("a.pdf") != Chunk.id_prefix("b.pdf")
    assert Chunk.make_id("Modül 1/ü.pdf", 0).isascii()


def test_sparse_vector_lengths_must_match() -> None:
    with pytest.raises(ValueError, match="same length"):
        SparseVector(indices=(1, 2), values=(0.5,))


def test_citation_str() -> None:
    assert str(Citation("lecture-01.pdf", 4)) == "lecture-01.pdf, p. 4"


def test_quiz_grade_score_bounds() -> None:
    with pytest.raises(ValueError, match="score"):
        QuizGrade(correct=True, feedback="", score=1.5)


@pytest.mark.parametrize(
    ("flt", "topic", "source", "expected"),
    [
        (MetadataFilter(), None, "a.pdf", True),
        (MetadataFilter(topics=("sleep",)), "sleep", "a.pdf", True),
        (MetadataFilter(topics=("sleep",)), None, "a.pdf", False),
        (MetadataFilter(sources=("b.pdf",)), "sleep", "a.pdf", False),
        (MetadataFilter(topics=("sleep",), sources=("a.pdf",)), "sleep", "a.pdf", True),
    ],
)
def test_metadata_filter(
    flt: MetadataFilter, topic: str | None, source: str, expected: bool
) -> None:
    assert flt.matches(topic, source) is expected


def test_page_range_metadata() -> None:
    meta = ChunkMetadata(source="deck.pdf", page=3, chunk_index=0, page_end=5)
    assert meta.last_page == 5
    assert ChunkMetadata(source="a.pdf", page=3, chunk_index=0).last_page == 3
    with pytest.raises(ValueError, match="page_end"):
        ChunkMetadata(source="a.pdf", page=3, chunk_index=0, page_end=3)


def test_citation_page_range_str() -> None:
    assert str(Citation("deck.pdf", 3, 5)) == "deck.pdf, pp. 3-5"
