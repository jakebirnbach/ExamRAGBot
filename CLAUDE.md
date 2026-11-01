# Study Assistant — RAG chatbot

A personal study assistant for a master's student in Health & Wellness. It answers questions and quizzes her using retrieval-augmented generation over her course materials. Single user, private deployment on AWS.

## Stack
- **Backend (Python 3.12):** FastAPI, Pydantic v2, `uv` for dependency management, pytest, ruff, mypy (strict)
- **Embeddings:** BAAI/bge-m3 (dense + sparse) via FlagEmbedding / sentence-transformers, run locally on CPU
- **Vector store:** Pinecone (serverless index, hybrid dense+sparse, metadata filtering)
- **Reranker:** BAAI/bge-reranker-v2-m3 (cross-encoder, local)
- **LLM:** Claude Haiku via AWS Bedrock (`boto3` bedrock-runtime, Converse API)
- **Parsing:** PyMuPDF for PDFs (add python-pptx / python-docx only if needed)
- **Frontend (TypeScript):** React + Vite, strict TS, talks to the FastAPI backend over JSON
- **Deployment (later phase):** Docker, AWS App Runner or EC2, secrets in env vars / Secrets Manager
- **No LangChain yet.** The pipeline is built by hand first; a LangChain version comes in a later phase.

## Architecture — Clean Architecture, dependencies point inward only

```
backend/
  src/study_assistant/
    domain/            # innermost: pure Python, no third-party imports except stdlib/pydantic-free dataclasses
      entities/        # Document, Chunk, ChunkMetadata, Citation, Answer, QuizQuestion
      ports/           # abstract interfaces (typing.Protocol / ABC):
                       #   DocumentParser, Chunker, Embedder, VectorStore, Reranker, LLM
      errors.py
    application/       # use cases; depends ONLY on domain
      use_cases/
        ingest_documents.py   # parse -> chunk -> embed -> upsert
        answer_question.py    # embed query -> hybrid search -> rerank -> LLM w/ citations
        generate_quiz.py      # sample chunks by topic -> generate question -> grade answer
      dto.py           # input/output models for use cases
    infrastructure/    # adapters implementing domain ports; depends on domain (and application DTOs if needed)
      parsing/pymupdf_parser.py
      chunking/token_chunker.py
      embedding/bge_m3_embedder.py
      vectorstore/pinecone_store.py
      reranking/bge_reranker.py
      llm/bedrock_llm.py
      config.py        # pydantic-settings; reads env vars
    interfaces/        # delivery layer
      api/             # FastAPI routers, request/response schemas
      cli/             # ingest + ask commands (typer)
    main.py            # composition root: wires infrastructure adapters into use cases (dependency injection)
  tests/
    unit/              # domain + application tested with in-memory fakes of every port
    integration/       # adapters against real services (marked, skipped without credentials)
  eval/
    questions.jsonl    # {question, expected_source, expected_page}
    run_eval.py        # retrieval hit@k, before/after reranking
frontend/
  src/                 # React + Vite + TS chat UI, quiz mode, topic filter
```

### Dependency rules (enforce these)
- `domain` imports nothing from `application`, `infrastructure`, or `interfaces`, and no SDKs (no boto3, pinecone, torch, fastapi).
- `application` imports only `domain`. Use cases receive ports via constructor injection.
- `infrastructure` implements domain ports. Only this layer touches SDKs.
- `interfaces` call application use cases; they never call infrastructure directly.
- Only `main.py` (composition root) knows about concrete adapters.
- Add `import-linter` contracts to CI to enforce the layering.

## Behavior requirements
- Every chunk stores metadata: source file, page, topic/lecture (if derivable), chunk index.
- Answers must cite sources (file + page), answer only from retrieved context, and say so explicitly when the materials don't cover the question.
- Retrieval: hybrid search top ~20, rerank to top ~5.
- Topic filtering via Pinecone metadata filters.
- Simple password gate on the API for the deployed version.

## Ingestion decisions (phase 2)
- **Chunking is per document.** Prose (transcripts, study guide, articles) is chunked within page boundaries, so citations are single pages. Slide decks (median page < `SPARSE_PAGE_TOKENS`) merge consecutive pages, at most 6 per chunk, and carry `page_end`. Chunks are ≤450 tokens (so query + chunk fits the reranker's 512 window) and are prefixed with the document title.
- **Topics** are course modules (`M3 · Health Behavior Change Theory`), derived from `Module N` folders and `M3 L1 Video 7 - …` file names; top-level handouts are matched to lessons by title. Ambiguous or unmatched files → `General / Reference`. `module` / `lesson` are stored separately too.
- **Chunk ids** are `<sha256(source)[:16]>#<index>`: serverless Pinecone can't delete by metadata, so re-ingesting a file lists that id prefix and deletes its old chunks first.
- **Skipped on purpose:** exact duplicates (by content hash, keeping the name without ` (1)`), image-only PDFs, non-PDFs, and anything in `data/ingest_exclude.txt` (e.g. the shorter Study Guide edition).
- Pinecone index uses `dotproduct` (required for hybrid); dense/sparse weighting is `HYBRID_ALPHA`. Distinct topics live in one record in the `<namespace>--meta` namespace.
- Linux installs CPU-only torch (`[tool.uv.sources]`); torch is a direct dependency only so that rule applies.

## Retrieval eval (phase 3)
- `eval/questions.jsonl`: `{id, question, expected_source, expected_page, also_accept: [{source, page}], answer_pattern}`. A hit is any retrieved chunk whose source matches and whose page range covers an accepted page; the same fact often lives in a transcript, handout, study guide and deck, so all are accepted.
- Gold pages come from `answer_pattern` (regex over every indexed page) via `eval/label_questions.py` on `eval/questions_draft.jsonl`. Patterns must match answer-bearing text, not mere mentions; check the page counts it prints.
- `eval/run_eval.py` reports hit@1, hit@5, MRR@5 and recall@top_k per hybrid alpha, with and without reranking, using the app's per-source cap.

## Build phases
1. **Scaffold** the folder structure, tooling (uv, ruff, mypy, pytest, import-linter), domain entities and ports, and in-memory fakes for tests.
2. **Ingestion**: parser, chunker, BGE-M3 embedder, Pinecone adapter, `ingest` CLI command.
3. **Retrieval + eval**: hybrid query, reranker, `eval/run_eval.py` reporting hit@5 with and without reranking.
4. **Generation**: Bedrock adapter, `answer_question` use case, `ask` CLI command.
5. **API + frontend**: FastAPI endpoints (`/ask`, `/quiz`, `/topics`), React chat UI, quiz mode, password gate.
6. **Deploy**: Dockerfiles, docker-compose for local dev, AWS deployment.
7. **LangChain rebuild** (later): reimplement the pipeline with LangChain behind the same ports and compare on the eval set.

## Conventions
- Type hints everywhere; mypy strict must pass.
- Unit tests for every use case using fakes; no network in unit tests.
- Secrets only via environment variables (`.env` for local, gitignored). Provide `.env.example`.
- Course materials live in `data/raw/` and are gitignored; they are not to be redistributed.
