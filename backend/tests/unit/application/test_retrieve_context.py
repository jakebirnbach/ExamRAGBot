import pytest

from study_assistant.application.use_cases.list_topics import ListTopics
from study_assistant.application.use_cases.retrieve_context import (
    RetrieveContext,
    limit_per_source,
)
from study_assistant.domain.entities import (
    Chunk,
    ChunkMetadata,
    EmbeddedChunk,
    MetadataFilter,
    ScoredChunk,
)
from tests.fakes import FakeEmbedder, FakeReranker, InMemoryVectorStore

TEXTS = {
    ("ttm.pdf", "M3"): [
        "The transtheoretical model has six stages of change",
        "Precontemplation contemplation preparation action maintenance termination",
        "Decisional balance weighs pros and cons of change",
    ],
    ("oars.pdf", "M4"): ["OARS means open questions affirmations reflections summaries"],
    ("sleep.pdf", "M6"): ["Adults need seven or more hours of sleep"],
}


def scored(source: str, i: int, score: float) -> ScoredChunk:
    return ScoredChunk(Chunk(f"{source}#{i}", "t", ChunkMetadata(source, 1, i)), score)


@pytest.fixture
def setup() -> tuple[FakeEmbedder, InMemoryVectorStore]:
    emb, store = FakeEmbedder(), InMemoryVectorStore()
    for (source, topic), texts in TEXTS.items():
        chunks = [
            Chunk(Chunk.make_id(source, i), t, ChunkMetadata(source, 1, i, topic=topic))
            for i, t in enumerate(texts)
        ]
        vecs = emb.embed_documents([c.text for c in chunks])
        store.upsert([EmbeddedChunk(c, v) for c, v in zip(chunks, vecs, strict=True)])
    return emb, store


def test_limit_per_source_keeps_order_and_caps() -> None:
    ranked = [scored("a", 0, 0.9), scored("a", 1, 0.8), scored("a", 2, 0.7), scored("b", 0, 0.6)]
    kept = limit_per_source(ranked, top_n=3, max_per_source=2)
    assert [(k.chunk.metadata.source, k.score) for k in kept] == [
        ("a", 0.9),
        ("a", 0.8),
        ("b", 0.6),
    ]


def test_retrieves_reranks_and_caps(setup: tuple[FakeEmbedder, InMemoryVectorStore]) -> None:
    emb, store = setup
    reranker = FakeReranker()
    retrieve = RetrieveContext(emb, store, reranker, top_k=5, top_n=3, max_per_source=2)

    hits = retrieve.execute("stages of change in the transtheoretical model")

    assert reranker.calls == [("stages of change in the transtheoretical model", 5, 5)]
    assert hits[0].chunk.metadata.source == "ttm.pdf"
    assert sum(h.chunk.metadata.source == "ttm.pdf" for h in hits) == 2
    assert len(hits) == 3


def test_rerank_can_be_disabled(setup: tuple[FakeEmbedder, InMemoryVectorStore]) -> None:
    emb, store = setup
    reranker = FakeReranker()
    RetrieveContext(emb, store, reranker, top_k=5, top_n=3).execute("sleep", rerank=False)
    assert reranker.calls == []


def test_topic_filter(setup: tuple[FakeEmbedder, InMemoryVectorStore]) -> None:
    emb, store = setup
    hits = RetrieveContext(emb, store).execute("change", MetadataFilter(topics=("M6",)))
    assert {h.chunk.metadata.topic for h in hits} == {"M6"}


def test_validation(setup: tuple[FakeEmbedder, InMemoryVectorStore]) -> None:
    emb, store = setup
    with pytest.raises(ValueError, match="top_n"):
        RetrieveContext(emb, store, top_k=3, top_n=5)
    with pytest.raises(ValueError, match="empty"):
        RetrieveContext(emb, store).execute("   ")


def test_list_topics(setup: tuple[FakeEmbedder, InMemoryVectorStore]) -> None:
    assert ListTopics(setup[1]).execute() == ["M3", "M4", "M6"]
