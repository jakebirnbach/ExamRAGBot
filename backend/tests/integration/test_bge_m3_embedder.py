"""Runs the real BGE-M3 model (~2.3 GB download on first run). Opt in with RUN_MODEL_TESTS=1."""

import math
import os

import pytest

from study_assistant.infrastructure.embedding.bge_m3_embedder import BgeM3Embedder

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MODEL_TESTS") != "1", reason="set RUN_MODEL_TESTS=1 to run model tests"
)


def test_dense_and_sparse_output() -> None:
    embedder = BgeM3Embedder()
    docs = embedder.embed_documents(
        ["Self-efficacy is belief in one's ability to succeed.", "Protein supports muscle repair."]
    )
    query = embedder.embed_query("What is self-efficacy?")

    assert all(len(d.dense) == embedder.dimension == 1024 for d in docs)
    assert math.isclose(sum(x * x for x in docs[0].dense), 1.0, rel_tol=1e-3)  # normalised
    assert docs[0].sparse.indices and all(v > 0 for v in docs[0].sparse.values)

    def dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert dot(query.dense, docs[0].dense) > dot(query.dense, docs[1].dense)
