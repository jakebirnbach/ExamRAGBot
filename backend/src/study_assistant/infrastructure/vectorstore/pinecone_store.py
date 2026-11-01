"""Pinecone serverless index with hybrid (dense + sparse) vectors.

Hybrid search on Pinecone needs the ``dotproduct`` metric; dense and sparse query parts
are weighted client-side with ``alpha`` (1.0 = dense only, 0.0 = sparse only).
"""

from collections.abc import Sequence
from itertools import batched
from typing import Any

from pinecone import Pinecone, ServerlessSpec
from pinecone.errors import PineconeError

from study_assistant.domain.entities import (
    Chunk,
    ChunkMetadata,
    EmbeddedChunk,
    Embedding,
    MetadataFilter,
    ScoredChunk,
)
from study_assistant.domain.errors import VectorStoreError

_TOPICS_RECORD_ID = "topics"


class PineconeVectorStore:
    def __init__(
        self,
        *,
        api_key: str | None,
        index_name: str,
        namespace: str,
        dimension: int,
        cloud: str = "aws",
        region: str = "us-east-1",
        alpha: float = 0.5,
        upsert_batch_size: int = 100,
    ) -> None:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be within [0, 1]")
        self._api_key = api_key
        self._index_name = index_name
        self._namespace = namespace
        self._meta_namespace = f"{namespace}--meta"
        self._dimension = dimension
        self._spec = ServerlessSpec(cloud=cloud, region=region)
        self._alpha = alpha
        self._batch = upsert_batch_size
        self._index: Any = None

    # ------------------------------------------------------------------ port methods
    def upsert(self, items: Sequence[EmbeddedChunk]) -> None:
        if not items:
            return
        index = self._get_index()
        try:
            for batch in batched(items, self._batch):
                index.upsert(
                    vectors=[_to_record(item) for item in batch],
                    namespace=self._namespace,
                    show_progress=False,
                )
            self._register_topics({t for i in items if (t := i.chunk.metadata.topic)})
        except PineconeError as exc:
            raise VectorStoreError(f"Pinecone upsert failed: {exc}") from exc

    def delete_source(self, source: str) -> int:
        index = self._get_index()
        try:
            ids = [
                item.id
                for page in index.list(prefix=Chunk.id_prefix(source), namespace=self._namespace)
                for item in page.vectors
                if item.id
            ]
            for batch in batched(ids, 1000):
                index.delete(ids=list(batch), namespace=self._namespace)
        except PineconeError as exc:
            raise VectorStoreError(f"Pinecone delete failed for {source}: {exc}") from exc
        return len(ids)

    def search(
        self,
        query: Embedding,
        top_k: int,
        metadata_filter: MetadataFilter | None = None,
    ) -> list[ScoredChunk]:
        sparse = None
        if query.sparse.indices and self._alpha < 1.0:
            sparse = {
                "indices": list(query.sparse.indices),
                "values": [v * (1 - self._alpha) for v in query.sparse.values],
            }
        try:
            response = self._get_index().query(
                top_k=top_k,
                vector=[v * self._alpha for v in query.dense],
                sparse_vector=sparse,
                filter=_to_filter(metadata_filter),
                include_metadata=True,
                namespace=self._namespace,
            )
        except PineconeError as exc:
            raise VectorStoreError(f"Pinecone query failed: {exc}") from exc
        return [
            ScoredChunk(chunk=_from_metadata(m.id, m.metadata or {}), score=m.score)
            for m in response.matches
        ]

    def list_topics(self) -> list[str]:
        return sorted(self._stored_topics())

    # ------------------------------------------------------------------ internals
    def _get_index(self) -> Any:
        if self._index is None:
            if not self._api_key:
                raise VectorStoreError("PINECONE_API_KEY is not set")
            try:
                pc = Pinecone(api_key=self._api_key)
                if not pc.has_index(self._index_name):
                    pc.create_index(
                        name=self._index_name,
                        dimension=self._dimension,
                        metric="dotproduct",
                        spec=self._spec,
                    )
                self._index = pc.Index(self._index_name)
            except PineconeError as exc:
                raise VectorStoreError(f"Pinecone index setup failed: {exc}") from exc
        return self._index

    def _stored_topics(self) -> set[str]:
        """Pinecone cannot list distinct metadata values, so topics are kept in one record
        in a side namespace and merged on every upsert."""
        try:
            fetched = self._get_index().fetch(
                ids=[_TOPICS_RECORD_ID], namespace=self._meta_namespace
            )
        except PineconeError as exc:
            raise VectorStoreError(f"Pinecone fetch failed: {exc}") from exc
        record = fetched.vectors.get(_TOPICS_RECORD_ID)
        return set((record.metadata or {}).get("topics", [])) if record else set()

    def _register_topics(self, topics: set[str]) -> None:
        known = self._stored_topics()
        if topics <= known:
            return
        placeholder = [0.0] * self._dimension
        placeholder[0] = 1.0  # dense values must not be all zero
        self._get_index().upsert(
            vectors=[
                {
                    "id": _TOPICS_RECORD_ID,
                    "values": placeholder,
                    "metadata": {"topics": sorted(known | topics)},
                }
            ],
            namespace=self._meta_namespace,
            show_progress=False,
        )


def _to_record(item: EmbeddedChunk) -> dict[str, Any]:
    meta = item.chunk.metadata
    metadata: dict[str, Any] = {
        "text": item.chunk.text,
        "source": meta.source,
        "page": meta.page,
        "chunk_index": meta.chunk_index,
    }
    # Pinecone rejects null metadata values, so optional fields are omitted when unset.
    optional = {
        "page_end": meta.page_end,
        "topic": meta.topic,
        "module": meta.module,
        "lesson": meta.lesson,
    }
    metadata.update({k: v for k, v in optional.items() if v is not None})
    record: dict[str, Any] = {
        "id": item.chunk.id,
        "values": list(item.embedding.dense),
        "metadata": metadata,
    }
    if item.embedding.sparse.indices:
        record["sparse_values"] = {
            "indices": list(item.embedding.sparse.indices),
            "values": list(item.embedding.sparse.values),
        }
    return record


def _from_metadata(chunk_id: str, m: dict[str, Any]) -> Chunk:
    def opt_int(key: str) -> int | None:
        return int(m[key]) if key in m else None

    return Chunk(
        id=chunk_id,
        text=str(m.get("text", "")),
        metadata=ChunkMetadata(
            source=str(m["source"]),
            page=int(m["page"]),  # Pinecone returns numbers as floats
            chunk_index=int(m["chunk_index"]),
            page_end=opt_int("page_end"),
            topic=m.get("topic"),
            module=m.get("module"),
            lesson=m.get("lesson"),
        ),
    )


def _to_filter(flt: MetadataFilter | None) -> dict[str, Any] | None:
    if flt is None:
        return None
    clauses: dict[str, Any] = {}
    if flt.topics is not None:
        clauses["topic"] = {"$in": list(flt.topics)}
    if flt.sources is not None:
        clauses["source"] = {"$in": list(flt.sources)}
    return clauses or None
