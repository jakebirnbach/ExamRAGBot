---
name: pinecone-index
description: Use when touching the Pinecone index or the pinecone_store adapter - inspecting what's stored, debugging empty or odd search results, deleting stale chunks, creating or recreating the index, changing namespaces, or working with sparse vectors. Covers the live index config and namespaces, Pinecone SDK v10 API specifics, hybrid scoring, the topics meta record, eventual consistency, and ready-to-run inspection snippets. Triggers - "pinecone", "index", "namespace", "vectors", "sparse values", "search returns nothing", "delete chunks", "describe index", "create a new index".
---

# Pinecone index

## The live index

- Name `study-assistant` (from `.env` `PINECONE_INDEX_NAME`), serverless AWS `us-east-1`,
  **dimension 1024, metric `dotproduct`, vector type dense**, with optional sparse values per record.
  It was created by the adapter, not the console.
- **Namespaces:** chunks live in **`default`** (2,871 records). Distinct topics live in a single
  record with id `topics` in **`default--meta`**.
- `Settings.pinecone_namespace` defaults to `"default"`, matching the data (and `.env`). If
  someone changes `PINECONE_NAMESPACE`, every search silently hits an empty namespace until a
  re-ingest. When search returns nothing, check `describe_index_stats()` first.

## Index requirements

- Hybrid search needs `dotproduct`; cosine won't combine dense and sparse correctly.
- Don't create indexes with the console's integrated-embedding ("chunk text / title" field map)
  option. We bring our own BGE-M3 vectors.
- If the index is missing, `PineconeVectorStore._get_index()` creates it; `create_index` blocks
  until ready by default. The free plan limits the number of indexes, so delete unused ones.

## Adapter behaviour (`infrastructure/vectorstore/pinecone_store.py`)

- Hybrid weighting is client-side: the query dense vector is scaled by `alpha`, sparse values by
  `1 - alpha`. `HYBRID_ALPHA=0.5` was chosen by the eval (see the retrieval-eval skill).
- Upserts go in batches of 100, then the topic set is merged into the `topics` record.
- `delete_source` lists ids by the `sha256(source)[:16]#` prefix, then deletes in batches of 1,000.
- Metadata numbers come back as floats, so `_from_metadata` casts with `int(...)`.
- Every SDK call is wrapped in `except PineconeError` → `VectorStoreError`.

## SDK v10 specifics (pinecone==10.2.0)

- `index.list(prefix=, namespace=)` yields **`ListResponse` pages**; ids are in
  `page.vectors[i].id`. Older SDKs yielded plain id lists.
- `index.fetch(ids=, namespace=)` → `.vectors: dict[str, Vector]`; `Vector.metadata`,
  `Vector.sparse_values.indices/.values`.
- `index.query(top_k=, vector=, sparse_vector={"indices","values"}, filter=, include_metadata=True, namespace=)` → `.matches[i].id/.score/.metadata`.
- `upsert(..., show_progress=False)`, otherwise it prints progress bars.
- The base exception is `pinecone.errors.PineconeError`.
- Serverless is **eventually consistent**: a read right after an upsert or delete can be stale.
  Integration tests poll (`wait_for`). The list endpoint can lag behind query.

## Inspection snippets (run from backend/)

```python
# uv run python - <<'EOF' ... EOF
from study_assistant.main import Container
from study_assistant.infrastructure.config import get_settings
c = Container(get_settings())
index = c.store._get_index()
print(index.describe_index_stats())          # per-namespace vector counts
print(c.store.list_topics())
```

Decode a chunk's sparse vector into tokens:

```python
from transformers import AutoTokenizer
from study_assistant.domain.entities import Chunk
tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")
cid = Chunk.make_id("The Microskills of Motivational Interviewing.pdf", 0)
v = index.fetch(ids=[cid], namespace="default").vectors[cid]
for i, w in sorted(zip(v.sparse_values.indices, v.sparse_values.values), key=lambda p: -p[1])[:10]:
    print(i, round(w, 3), tok.convert_ids_to_tokens(i))
```

Delete stale chunks for a renamed or removed file: `c.store.delete_source("<old relative path>")`.

## Integration test

`tests/integration/test_pinecone_store.py` runs automatically whenever `PINECONE_API_KEY` is set
(including via `.env`). It writes to a random `test-xxxxxxxx` namespace in the real index and
deletes it afterwards. It never touches `default`.
