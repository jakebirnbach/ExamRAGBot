"""Static conformance: mypy fails here if a fake drifts from its port.
The runtime assertions exercise each fake once so the fakes themselves are trustworthy."""

from pathlib import Path

import pytest

from study_assistant.domain.entities import Document, EmbeddedChunk, MetadataFilter, Page
from study_assistant.domain.errors import DocumentParsingError, LLMError
from study_assistant.domain.ports import (
    LLM,
    Chunker,
    DocumentParser,
    Embedder,
    Message,
    Reranker,
    VectorStore,
)
from tests.fakes import (
    FakeChunker,
    FakeDocumentParser,
    FakeEmbedder,
    FakeLLM,
    FakeReranker,
    InMemoryVectorStore,
)

DOC = Document(
    source="lecture-01-sleep.pdf",
    topic="sleep",
    pages=(
        Page(1, "Sleep hygiene improves recovery and cognitive performance."),
        Page(2, "Circadian rhythm is regulated by light exposure and melatonin."),
    ),
)
OTHER = Document(
    source="lecture-02-nutrition.pdf",
    topic="nutrition",
    pages=(Page(1, "Protein intake supports muscle protein synthesis after exercise."),),
)


def _indexed_store(embedder: Embedder, chunker: Chunker) -> VectorStore:
    store: VectorStore = InMemoryVectorStore()
    for doc in (DOC, OTHER):
        chunks = chunker.chunk(doc)
        vectors = embedder.embed_documents([c.text for c in chunks])
        store.upsert([EmbeddedChunk(c, e) for c, e in zip(chunks, vectors, strict=True)])
    return store


def test_parser() -> None:
    parser: DocumentParser = FakeDocumentParser({DOC.source: DOC})
    assert parser.supports(Path(DOC.source))
    assert parser.parse(Path("data/raw") / DOC.source) == DOC
    with pytest.raises(DocumentParsingError):
        parser.parse(Path("missing.pdf"))


def test_chunker_keeps_provenance() -> None:
    chunker: Chunker = FakeChunker(words_per_chunk=4)
    chunks = chunker.chunk(DOC)
    assert [c.metadata.chunk_index for c in chunks] == list(range(len(chunks)))
    assert {c.metadata.page for c in chunks} == {1, 2}
    assert all(c.metadata.source == DOC.source and c.metadata.topic == "sleep" for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


def test_hybrid_search_and_topic_filter() -> None:
    embedder: Embedder = FakeEmbedder()
    store = _indexed_store(embedder, FakeChunker())
    query = embedder.embed_query("how does light affect circadian rhythm")

    top = store.search(query, top_k=1)
    assert top[0].chunk.metadata.page == 2

    filtered = store.search(query, top_k=5, metadata_filter=MetadataFilter(topics=("nutrition",)))
    assert filtered and all(s.chunk.metadata.topic == "nutrition" for s in filtered)
    assert store.list_topics() == ["nutrition", "sleep"]


def test_reranker_orders_by_overlap() -> None:
    embedder = FakeEmbedder()
    store = _indexed_store(embedder, FakeChunker())
    candidates = store.search(embedder.embed_query("protein"), top_k=10)
    reranker: Reranker = FakeReranker()
    best = reranker.rerank("protein synthesis", candidates, top_n=1)
    assert best[0].chunk.metadata.source == OTHER.source
    assert best[0].score == 1.0


def test_llm_scripted_replies() -> None:
    fake = FakeLLM(["first"])
    llm: LLM = fake
    assert llm.complete("sys", [Message("user", "hi")]) == "first"
    assert fake.calls[0].messages == (Message("user", "hi"),)
    with pytest.raises(LLMError):
        llm.complete("sys", [Message("user", "again")])


def test_sample_respects_filter_and_count() -> None:
    store = _indexed_store(FakeEmbedder(), FakeChunker())
    picked = store.sample(1, MetadataFilter(topics=("nutrition",)))
    assert [c.metadata.topic for c in picked] == ["nutrition"]
    assert len(store.sample(100)) > 1
    assert store.sample(5, MetadataFilter(topics=("absent",))) == []
