"""Hits a real Pinecone index. Skipped unless PINECONE_API_KEY is set.
Uses a throwaway namespace and deletes it afterwards."""

import os
import time
import uuid
from collections.abc import Iterator

import pytest

from study_assistant.domain.entities import (
    Chunk,
    ChunkMetadata,
    EmbeddedChunk,
    Embedding,
    MetadataFilter,
    SparseVector,
)
from study_assistant.infrastructure.config import get_settings
from study_assistant.infrastructure.vectorstore.pinecone_store import PineconeVectorStore

API_KEY = os.environ.get("PINECONE_API_KEY") or (
    s.get_secret_value() if (s := get_settings().pinecone_api_key) else None
)
pytestmark = pytest.mark.skipif(not API_KEY, reason="PINECONE_API_KEY not set")
DIM = 1024


def unit(i: int) -> tuple[float, ...]:
    v = [0.0] * DIM
    v[i] = 1.0
    return tuple(v)


def item(
    source: str, idx: int, axis: int, topic: str, page_end: int | None = None
) -> EmbeddedChunk:
    chunk = Chunk(
        id=Chunk.make_id(source, idx),
        text=f"{source} chunk {idx}",
        metadata=ChunkMetadata(
            source=source, page=1, chunk_index=idx, topic=topic, page_end=page_end
        ),
    )
    return EmbeddedChunk(chunk, Embedding(unit(axis), SparseVector((axis,), (1.0,))))


@pytest.fixture
def store() -> Iterator[PineconeVectorStore]:
    settings = get_settings()
    s = PineconeVectorStore(
        api_key=API_KEY,
        index_name=settings.pinecone_index_name,
        namespace=f"test-{uuid.uuid4().hex[:8]}",
        dimension=DIM,
        cloud=settings.pinecone_cloud,
        region=settings.pinecone_region,
    )
    yield s
    index = s._get_index()
    for ns in (s._namespace, s._meta_namespace):
        index.delete(delete_all=True, namespace=ns)


def wait_for(predicate: object, timeout: float = 30.0) -> None:
    """Pinecone serverless is eventually consistent; poll until writes are visible."""
    assert callable(predicate)
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail("timed out waiting for Pinecone to reflect writes")
        time.sleep(1)


def test_roundtrip_filter_delete_topics(store: PineconeVectorStore) -> None:
    store.upsert(
        [
            item("a.pdf", 0, 0, "M1", page_end=3),
            item("a.pdf", 1, 1, "M1"),
            item("b.pdf", 0, 2, "M2"),
        ]
    )
    wait_for(lambda: len(store.search(Embedding(unit(0)), top_k=10)) == 3)

    best = store.search(Embedding(unit(0), SparseVector((0,), (1.0,))), top_k=1)[0]
    assert best.chunk.id == Chunk.make_id("a.pdf", 0)
    assert best.chunk.metadata.page_end == 3 and best.chunk.metadata.topic == "M1"

    only_m2 = store.search(
        Embedding(unit(0)), top_k=10, metadata_filter=MetadataFilter(topics=("M2",))
    )
    assert [r.chunk.metadata.source for r in only_m2] == ["b.pdf"]
    assert store.list_topics() == ["M1", "M2"]

    sampled = store.sample(5, MetadataFilter(topics=("M1",)))
    assert {c.metadata.source for c in sampled} == {"a.pdf"} and len(sampled) == 2

    removed = 0

    def delete_a() -> bool:  # the list endpoint can lag behind query; retry until both seen
        nonlocal removed
        removed += store.delete_source("a.pdf")
        return removed == 2

    wait_for(delete_a)
    wait_for(
        lambda: (
            {r.chunk.metadata.source for r in store.search(Embedding(unit(0)), top_k=10)}
            == {"b.pdf"}
        )
    )
