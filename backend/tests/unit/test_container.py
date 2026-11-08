"""Wiring checks that build no models and make no network calls."""

import pytest

from study_assistant.domain.entities import Chunk, ChunkMetadata, EmbeddedChunk
from study_assistant.infrastructure.config import Settings
from study_assistant.main import Container
from tests.fakes import FakeEmbedder, FakeReranker, InMemoryVectorStore


@pytest.mark.parametrize("enabled", [True, False])
def test_rerank_setting_controls_reranking_and_model_loading(enabled: bool) -> None:
    container = Container(Settings(_env_file=None, rerank_enabled=enabled))  # type: ignore[call-arg]
    embedder, store, reranker = FakeEmbedder(), InMemoryVectorStore(), FakeReranker()
    text = "the stages of change"
    chunk = Chunk(Chunk.make_id("ttm.pdf", 0), text, ChunkMetadata("ttm.pdf", 1, 0))
    store.upsert([EmbeddedChunk(chunk, embedder.embed_query(text))])
    # Put fakes where the cached adapters would go, so nothing real is built.
    container.__dict__.update(embedder=embedder, store=store, reranker=reranker)
    container.load_models()
    container.retrieve().execute("stages of change")
    assert len(reranker.calls) == (2 if enabled else 0)
