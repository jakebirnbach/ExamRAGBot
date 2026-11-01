from pathlib import Path

from study_assistant.infrastructure.config import BACKEND_DIR, Settings


def test_relative_paths_resolve_against_backend_dir() -> None:
    s = Settings(_env_file=None, raw_data_dir=Path("../data/raw"))  # type: ignore[call-arg]
    assert s.raw_data_dir == (BACKEND_DIR / "../data/raw").resolve()


def test_ingest_exclusions_ignores_comments(tmp_path: Path) -> None:
    f = tmp_path / "exclude.txt"
    f.write_text("# comment\nA.pdf  # why\n\n  B.pdf\n")
    s = Settings(_env_file=None, ingest_exclude_file=f)  # type: ignore[call-arg]
    assert s.ingest_exclusions() == frozenset({"A.pdf", "B.pdf"})
