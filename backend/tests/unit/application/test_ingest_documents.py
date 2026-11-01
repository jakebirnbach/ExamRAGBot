from pathlib import Path

from study_assistant.application.dto import FailedFile, FileOutcome, IngestedFile, SkippedFile
from study_assistant.application.use_cases.ingest_documents import IngestDocuments, discover_files
from study_assistant.domain.entities import Document, Page
from tests.fakes import FakeChunker, FakeDocumentParser, FakeEmbedder, InMemoryVectorStore

SLEEP = Document(
    source="sleep.pdf",
    topic="M6",
    checksum="aaa",
    pages=(Page(1, "Sleep hygiene improves recovery."), Page(2, "Light regulates melatonin.")),
)
SLEEP_COPY = Document(source="sleep (1).pdf", pages=SLEEP.pages, checksum="aaa")
SCANNED = Document(source="scan.pdf", checksum="bbb", pages=(Page(1, "   "),))
NUTRITION = Document(source="nutrition.pdf", checksum="ccc", pages=(Page(1, "Protein matters."),))


def make(
    *docs: Document, embedder: FakeEmbedder | None = None
) -> tuple[IngestDocuments, InMemoryVectorStore, FakeEmbedder]:
    store = InMemoryVectorStore()
    emb = embedder or FakeEmbedder()
    parser = FakeDocumentParser({d.source: d for d in docs})
    use_case = IngestDocuments(
        parser, FakeChunker(words_per_chunk=3), emb, store, embed_batch_size=2
    )
    return use_case, store, emb


def test_ingests_chunks_with_metadata() -> None:
    use_case, store, _ = make(SLEEP)
    report = use_case.execute([Path("sleep.pdf")])

    assert report.ingested == [IngestedFile("sleep.pdf", pages=2, chunks=3, topic="M6")]
    assert report.total_chunks == 3 == len(store.items)
    assert {i.chunk.metadata.page for i in store.items.values()} == {1, 2}
    assert all(i.chunk.metadata.topic == "M6" for i in store.items.values())


def test_embeds_in_batches() -> None:
    use_case, _, emb = make(SLEEP)
    use_case.execute([Path("sleep.pdf")])
    assert [len(c) for c in emb.calls] == [2, 1]


def test_skips_unsupported_duplicates_and_textless() -> None:
    use_case, store, _ = make(SLEEP, SLEEP_COPY, SCANNED)
    report = use_case.execute(
        [Path("sleep.pdf"), Path("sleep (1).pdf"), Path("scan.pdf"), Path("notes.zip")]
    )
    reasons = {s.path: s.reason for s in report.skipped}
    assert reasons["sleep (1).pdf"] == "duplicate of sleep.pdf"
    assert "no extractable text" in reasons["scan.pdf"]
    assert reasons["notes.zip"] == "unsupported file type"
    assert {i.chunk.metadata.source for i in store.items.values()} == {"sleep.pdf"}


def test_reingest_replaces_old_chunks() -> None:
    use_case, store, _ = make(SLEEP)
    use_case.execute([Path("sleep.pdf")])
    shorter = Document(source="sleep.pdf", checksum="new", pages=(Page(1, "Sleep."),))
    use_case2 = IngestDocuments(
        FakeDocumentParser({"sleep.pdf": shorter}), FakeChunker(3), FakeEmbedder(), store
    )
    use_case2.execute([Path("sleep.pdf")])
    assert [i.chunk.text for i in store.items.values()] == ["Sleep."]


def test_embedding_failure_is_reported_and_keeps_old_chunks() -> None:
    emb = FakeEmbedder()
    use_case, store, _ = make(SLEEP, NUTRITION, embedder=emb)
    use_case.execute([Path("sleep.pdf")])
    before = dict(store.items)

    emb.fail_on = "Sleep"
    report = use_case.execute([Path("sleep.pdf"), Path("nutrition.pdf")])

    assert [f.path for f in report.failed] == ["sleep.pdf"]
    assert [f.source for f in report.ingested] == [
        "nutrition.pdf"
    ]  # one failure doesn't stop the run
    assert "sleep.pdf" not in store.deleted_sources[1:]
    assert all(store.items[k] == v for k, v in before.items())


def test_dry_run_writes_nothing() -> None:
    use_case, store, emb = make(SLEEP)
    report = use_case.execute([Path("sleep.pdf")], dry_run=True)
    assert report.total_chunks == 3
    assert store.items == {} and emb.calls == []


def test_progress_callback_sees_every_file() -> None:
    use_case, _, _ = make(SLEEP)
    seen: list[FileOutcome] = []
    use_case.execute([Path("sleep.pdf"), Path("missing.pdf")], on_file_done=seen.append)
    assert isinstance(seen[0], IngestedFile)
    assert isinstance(seen[1], SkippedFile)  # fake parser doesn't "support" unknown names


def test_parse_errors_become_failures() -> None:
    class ExplodingParser(FakeDocumentParser):
        def supports(self, path: Path) -> bool:
            return True

    use_case = IngestDocuments(
        ExplodingParser(), FakeChunker(), FakeEmbedder(), InMemoryVectorStore()
    )
    report = use_case.execute([Path("broken.pdf")])
    assert isinstance(report.failed[0], FailedFile)


def test_discover_files(tmp_path: Path) -> None:
    for rel in ["b.pdf", "a (1).pdf", "a.pdf", "Module 1/c.pdf", ".DS_Store", "skip me.pdf"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(b"x")
    found = [p.relative_to(tmp_path).as_posix() for p in discover_files(tmp_path, {"skip me.pdf"})]
    assert found == ["Module 1/c.pdf", "a.pdf", "b.pdf", "a (1).pdf"]
