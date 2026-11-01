---
name: local-models
description: Use when working with the local ML models - BGE-M3 embeddings (dense + sparse) and the bge-reranker-v2-m3 cross-encoder - or with torch/transformers/FlagEmbedding dependencies, model load time, CPU speed, tokenization, or the Linux CPU-only torch setup for CI/Docker. Covers verified library APIs (FlagEmbedding 1.4 on transformers 5), output formats, performance numbers, the 250k multilingual vocabulary, and dependency gotchas. Triggers - "embedding", "BGE", "reranker", "torch", "model download", "slow", "tokenizer", "sparse vector", "CUDA in CI", "Docker image size".
---

# Local models

Both run on CPU via FlagEmbedding (1.4.x), on transformers 5.x and torch 2.15. They're cached in
the Hugging Face cache (`~/.cache/huggingface`), about 2.3 GB each.

## BGE-M3 (`infrastructure/embedding/bge_m3_embedder.py`)

- `BGEM3FlagModel(name, use_fp16=False, devices="cpu")`. fp16 is for GPUs.
- `model.encode(texts, batch_size=, max_length=, return_dense=True, return_sparse=True, return_colbert_vecs=False)`
  returns a dict: `dense_vecs` (np.ndarray N×1024, float32, already L2-normalised) and
  `lexical_weights` (a list of `{token_id_str: weight}`). The adapter converts these to `Embedding`
  with int sparse indices sorted, dropping weights ≤ 0.
- One pass gives both vectors; that's the reason for choosing it (hybrid search without a separate
  BM25 index). Queries and documents use the same encode call.
- Speed: a full corpus embed (2,871 chunks of about 400 tokens) takes about 18 min on the dev Mac.
  First load including download took about 107 s; cached loads are much faster but still several
  seconds.

## Tokenizer / vocabulary

- XLM-RoBERTa SentencePiece, **250,002 tokens**, multilingual. Sparse indices are positions in
  this vocabulary; `▁` marks the start of a word.
- Words split into pieces: `OARS` → `▁O` + `ARS`; `HbA1c` → 5 single characters (weak for keyword
  matching, so it relies on dense). Capitalised variants are separate tokens.
- The chunker counts tokens with the same tokenizer (`HuggingFaceTokenCounter`,
  `add_special_tokens=False`, `model_max_length` raised to silence warnings).
- Switching embedding models means **re-ingesting everything**: the dense dimension and the sparse
  index space are model-specific.

## Reranker (`infrastructure/reranking/bge_reranker.py`)

- `FlagReranker(name, use_fp16=False, devices="cpu", normalize=True, max_length=512)`;
  `compute_score(list_of_(query, passage), batch_size=)` returns a list of floats in 0–1 (sigmoid).
  **A single pair returns a bare float**, which the adapter handles.
- Max input is 512 tokens for query + passage, which is why chunks are capped at 450 tokens.
- Speed: about 3.5 s to rerank 20 candidates on CPU; first load including download about 55 s.

## Loading strategy

Both adapters load lazily on first use (deferred imports with `# noqa: PLC0415`). `Container`
caches one instance per process. A fresh `study-assistant search` pays the model loads each time
(about 8 s without reranking, about 15 s with). A long-running API server (phase 5) should warm both
models at startup and needs about 3–5 GB of RAM.

## Dependency setup (backend/pyproject.toml)

- On Linux, torch comes from the **CPU-only** index (`[tool.uv.sources]` + `[[tool.uv.index]]
  pytorch-cpu`, `explicit = true`). That gives a 200 MB wheel instead of about 3 GB of CUDA.
- **uv sources only apply to direct dependencies**: torch is listed explicitly in
  `dependencies` even though only FlagEmbedding needs it. Don't remove it.
- Verify after relocking: `grep -c nvidia uv.lock` should be 0, and the lock should contain
  `torch-2.15.0+cpu-…-manylinux_2_28_x86_64.whl`.
- mypy: `FlagEmbedding.*` and `transformers.*` have `ignore_missing_imports`.

## Integration test

`RUN_MODEL_TESTS=1 uv run pytest tests/integration/test_bge_m3_embedder.py` checks 1024-dim
normalised dense vectors, positive sparse weights, and that the query is nearer the relevant text.
