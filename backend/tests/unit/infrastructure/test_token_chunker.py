from study_assistant.domain.entities import Document, Page
from study_assistant.infrastructure.chunking.token_chunker import TokenChunker


def words(text: str) -> int:
    return len(text.split())


def sentences(n: int, start: int = 0) -> str:
    return " ".join(f"Sentence number {i} has six words." for i in range(start, start + n))


def make(**kw: int) -> TokenChunker:
    opts = {
        "max_tokens": 40,
        "overlap_tokens": 8,
        "sparse_page_tokens": 20,
        "min_document_tokens": 5,
    }
    opts.update(kw)
    return TokenChunker(words, **opts)


def test_dense_pages_never_cross_page_boundaries() -> None:
    doc = Document(
        source="t.pdf",
        title="Transcript",
        pages=(Page(1, sentences(12)), Page(2, sentences(12, 12))),
    )
    chunks = make().chunk(doc)
    assert len(chunks) > 2
    assert all(c.metadata.page_end is None for c in chunks)
    assert {c.metadata.page for c in chunks} == {1, 2}
    assert all(words(c.text) <= 40 for c in chunks)
    assert [c.metadata.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.text.startswith("Transcript\n") for c in chunks)


def test_overlap_repeats_tail_sentences() -> None:
    doc = Document(source="t.pdf", pages=(Page(1, sentences(12)),))
    first, second = make().chunk(doc)[:2]
    last_sentence_of_first = first.text.splitlines()[-1]
    assert second.text.splitlines()[0] == last_sentence_of_first


def test_sparse_documents_merge_pages_into_ranges() -> None:
    slides = tuple(Page(i, f"Slide {i} title • bullet one • bullet two") for i in range(1, 11))
    chunks = make(max_pages_per_chunk=4).chunk(Document(source="deck.pdf", pages=slides))
    assert len(chunks) < len(slides)
    assert all(c.metadata.page_end is not None for c in chunks)
    assert all(c.metadata.last_page - c.metadata.page < 4 for c in chunks)
    assert chunks[0].metadata.page == 1 and chunks[-1].metadata.last_page == 10


def test_oversized_paragraph_is_split() -> None:
    doc = Document(source="t.pdf", pages=(Page(1, "word " * 200),))
    chunks = make(overlap_tokens=0).chunk(doc)
    assert len(chunks) == 5 and all(words(c.text) <= 40 for c in chunks)


def test_textless_documents_produce_no_chunks() -> None:
    assert make().chunk(Document(source="s.pdf", pages=(Page(1, "  "),))) == []
    title_only = Document(source="s.pdf", pages=(Page(1, "Title"), Page(2, "2")))
    assert make(min_document_tokens=5).chunk(title_only) == []


def test_metadata_is_carried_through() -> None:
    doc = Document(
        source="m.pdf",
        topic="M3 · Theory",
        module="M3",
        lesson="L1",
        pages=(Page(4, sentences(2)),),
    )
    (chunk,) = make().chunk(doc)
    m = chunk.metadata
    assert (m.source, m.page, m.topic, m.module, m.lesson) == (
        "m.pdf",
        4,
        "M3 · Theory",
        "M3",
        "L1",
    )
