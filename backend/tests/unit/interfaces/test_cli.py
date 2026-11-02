from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from study_assistant.application.use_cases.answer_question import AnswerQuestion
from study_assistant.application.use_cases.ingest_documents import IngestDocuments
from study_assistant.application.use_cases.list_topics import ListTopics
from study_assistant.application.use_cases.retrieve_context import RetrieveContext
from study_assistant.domain.entities import (
    Chunk,
    ChunkMetadata,
    Document,
    EmbeddedChunk,
    Page,
)
from study_assistant.domain.ports import DocumentParser
from study_assistant.interfaces.cli.app import CliDependencies, build_app
from tests.fakes import (
    FakeChunker,
    FakeDocumentParser,
    FakeEmbedder,
    FakeLLM,
    InMemoryVectorStore,
)

runner = CliRunner()


def make_deps(
    root: Path,
    parser: DocumentParser | None = None,
    store: InMemoryVectorStore | None = None,
    exclusions: Sequence[str] = (),
    llm: FakeLLM | None = None,
) -> CliDependencies:
    emb, st = FakeEmbedder(), store if store is not None else InMemoryVectorStore()
    return CliDependencies(
        ingest=lambda: IngestDocuments(parser or FakeDocumentParser(), FakeChunker(), emb, st),
        retrieve=lambda: RetrieveContext(emb, st, top_k=5, top_n=2),
        answer=lambda: AnswerQuestion(RetrieveContext(emb, st, top_k=5, top_n=2), llm or FakeLLM()),
        list_topics=lambda: ListTopics(st),
        raw_data_dir=root,
        ingest_exclusions=frozenset(exclusions),
    )


@pytest.fixture
def indexed_store() -> InMemoryVectorStore:
    emb, store = FakeEmbedder(), InMemoryVectorStore()
    rows = [
        ("ttm.pdf", 3, None, "M3 · Behavior Change", "TTM\nStages of change: precontemplation"),
        ("deck.pdf", 10, 12, "General / Reference", "Deck\nOARS skills reflections"),
    ]
    for source, page, page_end, topic, text in rows:
        meta = ChunkMetadata(source, page, 0, topic=topic, page_end=page_end)
        chunk = Chunk(Chunk.make_id(source, 0), text, meta)
        store.upsert([EmbeddedChunk(chunk, emb.embed_query(text))])
    return store


def test_ingest_command(tmp_path: Path) -> None:
    for name in ["a.pdf", "excluded.pdf"]:
        (tmp_path / name).write_bytes(b"x")
    doc = Document(source="a.pdf", topic="M1", pages=(Page(1, "hello world"),))
    store = InMemoryVectorStore()
    parser = FakeDocumentParser({"a.pdf": doc, "excluded.pdf": doc})
    app = build_app(make_deps(tmp_path, parser, store, ["excluded.pdf"]))

    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 0, result.output
    assert "1 files" in result.output
    assert "ok    a.pdf  [M1]  1 pages -> 1 chunks" in result.output
    assert len(store.items) == 1


def test_ingest_dry_run_and_failure_exit_code(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"x")

    class AlwaysSupports(FakeDocumentParser):
        def supports(self, path: Path) -> bool:
            return True

    result = runner.invoke(
        build_app(make_deps(tmp_path, AlwaysSupports())), ["ingest", "--dry-run"]
    )
    assert "dry run" in result.output
    assert "FAIL" in result.output and result.exit_code == 1


def test_search_shows_citations(tmp_path: Path, indexed_store: InMemoryVectorStore) -> None:
    app = build_app(make_deps(tmp_path, store=indexed_store))
    result = runner.invoke(app, ["search", "OARS reflections"])
    assert result.exit_code == 0, result.output
    first = result.output.splitlines()[0]
    assert "deck.pdf, pp. 10-12" in first
    assert "OARS skills reflections" in result.output and "Deck" not in result.output


def test_search_topic_filter_by_prefix(tmp_path: Path, indexed_store: InMemoryVectorStore) -> None:
    app = build_app(make_deps(tmp_path, store=indexed_store))
    result = runner.invoke(app, ["search", "OARS reflections", "--topic", "m3"])
    assert result.exit_code == 0, result.output
    assert "topics: M3 · Behavior Change" in result.output
    assert "deck.pdf" not in result.output and "ttm.pdf, p. 3" in result.output

    bad = runner.invoke(app, ["search", "x", "--topic", "M9"])
    assert bad.exit_code != 0


def test_topics_command(tmp_path: Path, indexed_store: InMemoryVectorStore) -> None:
    result = runner.invoke(build_app(make_deps(tmp_path, store=indexed_store)), ["topics"])
    assert result.output.splitlines() == ["General / Reference", "M3 · Behavior Change"]


def test_ask_prints_answer_and_sources(tmp_path: Path, indexed_store: InMemoryVectorStore) -> None:
    llm = FakeLLM(["OARS covers reflections [1]."])
    app = build_app(make_deps(tmp_path, store=indexed_store, llm=llm))
    result = runner.invoke(app, ["ask", "What is OARS?"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == "OARS covers reflections [1]."
    assert "Sources:\n  [1] deck.pdf, pp. 10-12" in result.output


def test_ask_not_covered(tmp_path: Path, indexed_store: InMemoryVectorStore) -> None:
    llm = FakeLLM(["NOT_IN_MATERIALS\nThe excerpts cover TTM and OARS."])
    result = runner.invoke(
        build_app(make_deps(tmp_path, store=indexed_store, llm=llm)), ["ask", "x"]
    )
    assert "course materials don't cover this" in result.output
    assert "(No sources cited.)" in result.output
