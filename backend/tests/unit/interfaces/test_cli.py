from pathlib import Path

from typer.testing import CliRunner

from study_assistant.application.use_cases.ingest_documents import IngestDocuments
from study_assistant.domain.entities import Document, Page
from study_assistant.interfaces.cli.app import CliDependencies, build_app
from tests.fakes import FakeChunker, FakeDocumentParser, FakeEmbedder, InMemoryVectorStore


def test_ingest_command(tmp_path: Path) -> None:
    for name in ["a.pdf", "excluded.pdf"]:
        (tmp_path / name).write_bytes(b"x")
    doc = Document(source="a.pdf", topic="M1", pages=(Page(1, "hello world"),))
    store = InMemoryVectorStore()
    parser = FakeDocumentParser({"a.pdf": doc, "excluded.pdf": doc})
    app = build_app(
        CliDependencies(
            ingest=lambda: IngestDocuments(parser, FakeChunker(), FakeEmbedder(), store),
            raw_data_dir=tmp_path,
            ingest_exclusions=frozenset({"excluded.pdf"}),
        )
    )

    result = CliRunner().invoke(app, ["ingest"])

    assert result.exit_code == 0, result.output
    assert "1 files" in result.output
    assert "ok    a.pdf  [M1]  1 pages -> 1 chunks" in result.output
    assert len(store.items) == 1


def test_ingest_dry_run_and_failure_exit_code(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"x")

    class AlwaysSupports(FakeDocumentParser):
        def supports(self, path: Path) -> bool:
            return True

    app = build_app(
        CliDependencies(
            ingest=lambda: IngestDocuments(
                AlwaysSupports(), FakeChunker(), FakeEmbedder(), InMemoryVectorStore()
            ),
            raw_data_dir=tmp_path,
            ingest_exclusions=frozenset(),
        )
    )
    result = CliRunner().invoke(app, ["ingest", "--dry-run"])
    assert "dry run" in result.output
    assert "FAIL" in result.output and result.exit_code == 1
