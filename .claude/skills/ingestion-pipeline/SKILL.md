---
name: ingestion-pipeline
description: Use when ingesting, re-ingesting or changing how course materials are parsed, cleaned, classified into topics, or chunked - or when debugging a file that was skipped, failed, mis-topiced, or chunked badly. Covers the parse -> clean -> classify -> chunk -> embed -> replace flow, the per-document chunking rules (page-bounded prose vs merged slide ranges), the course catalog title matching, dedup/exclusion rules, timings, and how to verify changes with a dry run. Triggers - "ingest", "re-index", "add new course material", "why was X skipped", "wrong topic", "chunk size", "page ranges", "dry run", "re-ingest one file".
---

# Ingestion pipeline

## Commands (run from backend/)

```
uv run study-assistant ingest --dry-run           # parse + chunk only: no model, no Pinecone, about 11 s
uv run study-assistant ingest                     # everything in data/raw: about 18 min on CPU
uv run study-assistant ingest "../data/raw/X.pdf" # one file or folder; replaces only its chunks
```

Each file prints `ok`, `skip` or `FAIL`; the exit code is 1 if anything failed. Always run a
**dry run first** after changing parsing, cleaning, catalog or chunking code, and read the output:
topic per file, chunk counts, skip reasons.

Current corpus result: 227 files → 220 ingested, **2,871 chunks**, 7 skipped (2 zips, 1 png,
2 exact duplicates, 2 image-only PDFs), 0 failed.

## Flow (`application/use_cases/ingest_documents.py`)

Per file:
1. `parser.supports(path)`, otherwise skip "unsupported file type".
2. Parse. `DocumentParsingError` → FailedFile; the run continues.
3. Content-hash dedup: a later file with the same SHA-256 is skipped "duplicate of …".
   `discover_files` sorts files ending in ` (1)` last, so the clean name is kept.
4. Chunk. No chunks → skip "no extractable text".
5. Embed in batches, **then** `store.delete_source(source)`, then upsert. Embedding happens first
   so a failure leaves the old chunks intact.

Exclusions: `data/ingest_exclude.txt` (tracked in git; one file name or relative path per line,
`#` comments allowed). It currently excludes the 48-page `Health and Wellness Coaching - Study
Guide.pdf`, because the Full 138pp edition supersedes it.

## Parsing and cleaning (`infrastructure/parsing/`)

- `pymupdf_parser.py`: `source` is the path relative to `data/raw` (POSIX), `title` is the file
  stem, and `checksum` is the SHA-256 of the bytes.
- `text_cleaning.py`: NFKC normalisation (ligatures `ﬁ` → `fi`), private-use bullet glyphs such as
  `` → `•`, drops `N | P a g e` footers and `Video Transcript` header lines, collapses
  whitespace.
- **Known, not yet fixed:** transcripts are speech-to-text exports with spaces before hyphens
  everywhere (`pre -contemplation`, `client -centered`, `check -in`) and misheard names. See the
  course-materials skill. Normalising ` -` → `-` would help keyword matching. If you do it, re-run
  the dry run, then a full ingest and the eval.

## Topic classification (`parsing/course_catalog.py`)

- `M3 L1 Video 7 - Title.pdf` → module M3, lesson L1, topic `M3 · Health Behavior Change Theory`.
- A file inside a `Module N …` folder → module only.
- Otherwise the title is matched against all lesson titles: normalised
  (lowercase, strip `Video Slides Handout - `, trailing ` (1)` or ` 2`, leading `the `, non-alphanumerics),
  then exact match → containment (shorter title ≥ 10 chars) → fuzzy match (difflib ratio ≥ 0.88).
- If candidates span **more than one module**, the topic is `General / Reference`. This is
  deliberate: "Follow-Up Session" and "Final Closing Session" exist in both M2 and M4.
- `MODULE_NAMES` is hard-coded from the study guide's cover page.

## Chunking (`chunking/token_chunker.py`)

- Token counts come from BGE-M3's own tokenizer (`hf_token_counter.py`).
- A **per-document** decision: if the median page has fewer than `SPARSE_PAGE_TOKENS` (150) tokens,
  the document is a slide deck and pages merge across boundaries, at most **6 pages** per chunk,
  with `page_end` set. Otherwise (prose) a chunk **never crosses a page boundary**, so citations are
  single pages. The user explicitly wants single-page citations for transcripts and the study guide;
  don't change this without asking.
- Splitting: paragraph → sentence → line → word, at the coarsest level that fits; then greedy
  packing up to `CHUNK_MAX_TOKENS` (450) with about `CHUNK_OVERLAP_TOKENS` (50) of overlap.
  450 tokens keeps query + chunk inside the reranker's 512-token window.
- Every chunk's text starts with `"{document title}\n"` (a contextual header). The CLI `search`
  output strips that first line.
- Documents with fewer than 40 body tokens produce no chunks (image-only PDFs).

## Chunk ids and re-ingestion

`Chunk.make_id(source, i)` = `sha256(source)[:16] + "#" + i`. Ids are ASCII, which Pinecone
requires, and prefix-listable per file. Serverless Pinecone can't delete by metadata filter, so
`delete_source` lists the prefix and deletes those ids. **Renaming a file in data/raw changes its
id prefix**: the old chunks stay until you delete them (see the pinecone-index skill).

## Metadata stored per chunk

`text, source, page, chunk_index` always; `page_end, topic, module, lesson` only when set, because
Pinecone rejects null values.
