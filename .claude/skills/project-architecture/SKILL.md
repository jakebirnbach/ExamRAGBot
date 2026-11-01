---
name: project-architecture
description: Use when adding or changing any code in the study assistant backend - a new port, adapter, use case, CLI command, API endpoint, setting, or test. Covers the Clean Architecture layer rules as they are actually enforced (import-linter contracts), the Container composition root, the fake-per-port testing pattern, the ruff/mypy strict conventions and their sanctioned exceptions, and the checks to run before calling work done. Triggers - "add an adapter", "new use case", "add a CLI command", "wire this up", "where does this code go", "mypy is failing", "import-linter broken", "how do I test this", "start phase 4/5".
---

# Study assistant: architecture and conventions

CLAUDE.md has the rules. This skill is how they are applied in the code that exists.

## Layout (backend/)

```
src/study_assistant/
  domain/entities/      frozen stdlib dataclasses (Document, Page, Chunk, ChunkMetadata, ScoredChunk,
                        Embedding, SparseVector, EmbeddedChunk, MetadataFilter, Citation, Answer, Quiz*)
  domain/ports/         typing.Protocol interfaces: DocumentParser, Chunker, Embedder, VectorStore,
                        Reranker, LLM (+ Message, Role)
  domain/errors.py      StudyAssistantError > DocumentParsingError, EmbeddingError, RerankingError,
                        VectorStoreError, LLMError
  application/dto.py    plain dataclasses (IngestReport, IngestedFile, SkippedFile, FailedFile)
  application/use_cases/ ingest_documents.py (+ discover_files), retrieve_context.py
                        (+ limit_per_source), list_topics.py
  infrastructure/       parsing/, chunking/, embedding/, reranking/, vectorstore/, llm/ (empty until
                        phase 4), config.py (pydantic-settings)
  interfaces/cli/app.py typer app built by build_app(CliDependencies)
  main.py               Container (composition root) + cli() entry point
tests/fakes/            one in-memory fake per port
tests/unit/             domain/, application/, infrastructure/ (pure-logic adapters), interfaces/
tests/integration/      real BGE-M3 (RUN_MODEL_TESTS=1) and real Pinecone (needs PINECONE_API_KEY)
eval/                   retrieval eval (see the retrieval-eval skill)
```

## Layer rules (enforced by `uv run lint-imports`, contracts in pyproject.toml)

1. Layers: main > interfaces > infrastructure > application > domain. Only inward imports.
2. `interfaces` must never import `infrastructure`.
3. `domain` and `application` must not import pydantic, pydantic_settings, fastapi, typer, boto3,
   botocore, pinecone, torch, sentence_transformers, FlagEmbedding, fitz or pymupdf. Use stdlib
   dataclasses. A new SDK that only infrastructure may touch should be added to that list.

These contracts are tested: a deliberate bad import makes them fail. Never "fix" a broken contract
by loosening it; move the code.

## Adding things

**A new port:** a Protocol in `domain/ports/<name>.py`, export it from `domain/ports/__init__.py`,
add a fake in `tests/fakes/` and export it, and add a conformance line to
`tests/unit/test_fakes_conform_to_ports.py` (`x: Port = Fake()`). mypy is the conformance check.

**A new adapter:** `infrastructure/<area>/<name>.py`. Conventions:
- Load heavy SDKs and models lazily, on first use, inside the method:
  `from FlagEmbedding import X  # noqa: PLC0415 - heavy import, deferred`. This keeps
  `--help`, dry runs and unit tests fast, and keeps CI from loading torch.
- Constructor config is keyword-only (`def __init__(self, model, *, batch_size=...)`).
  PLR0913 is ignored project-wide for this reason.
- Catch SDK exceptions at the boundary and re-raise the matching domain error
  (`raise VectorStoreError(...) from exc`). Use cases only catch domain errors.
- Untyped SDKs: add a `[[tool.mypy.overrides]] ignore_missing_imports` entry (FlagEmbedding and
  transformers have one), or `untyped_calls_exclude` (pymupdf has one). Never use blanket
  `# type: ignore`.

**A new use case:** `application/use_cases/<verb_noun>.py`. Ports come in through the constructor.
Unit-test it with the fakes only (no network, no models), following `test_ingest_documents.py`
and `test_retrieve_context.py`.

**Wiring:** add a `cached_property` adapter and/or a use-case factory method on `Container` in
`main.py`. Adapters are built once per process; that matters because each model takes tens of
seconds to load. `Container.vector_store(alpha=...)` exists so the eval can vary the hybrid weight.

**A CLI command:** in `interfaces/cli/app.py` inside `build_app`. It receives use-case *factories*
through `CliDependencies` (never adapters), so nothing heavy is built until a command runs. Add the
factory field to `CliDependencies` and pass it in `main.cli()`. Test with `typer.testing.CliRunner`
and fakes (`tests/unit/interfaces/test_cli.py`, `make_deps`).

**A setting:** a field on `Settings` in `infrastructure/config.py`, plus a commented example in
`backend/.env.example`. Relative paths are resolved against `backend/` by a validator, so
`RAW_DATA_DIR=../data/raw` works from any working directory.

## Definition of done (run from backend/)

```
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports && uv run pytest -q
```

CI (`.github/workflows/ci.yml`) runs the same commands, with unit tests only. mypy covers `src`,
`tests` and `eval`. The suite takes about 3 s; if it gets slow, something is loading a model.

## Git

- The repo is `jakebirnbach/ExamRAGBot` (private). The repo-local git identity is
  `jakebirnbach <jakebirnbach@gmail.com>`, because the global identity is the user's work account.
  Don't change either.
- Commit and push only when the user asks. Before committing, confirm nothing from `backend/.env`
  or `data/raw/` is staged.

## Phase 4 notes (generation, not built yet)

- `BEDROCK_MODEL_ID` is set in `.env`; the code default is `None` on purpose. Load the claude-api
  skill before writing the Bedrock adapter, and don't guess model IDs.
- Use the Converse API via boto3 (`bedrock-runtime`). Add `boto3` and `botocore` only to
  infrastructure; they are already in the forbidden list for domain and application.
- `answer_question` should build on `RetrieveContext.execute()` (returns at most 5 ScoredChunks)
  and produce `Answer(text, citations, grounded)`. `Citation` already supports `page_end` for
  slide ranges.
