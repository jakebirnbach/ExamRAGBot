"""``study-assistant`` command line. Receives use-case factories from the composition root."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from study_assistant.application.dto import FailedFile, FileOutcome, IngestedFile, SkippedFile
from study_assistant.application.use_cases.ingest_documents import IngestDocuments, discover_files


@dataclass(frozen=True, slots=True)
class CliDependencies:
    ingest: Callable[[], IngestDocuments]
    """Factory, so heavy adapters are only built when a command needs them."""
    raw_data_dir: Path
    ingest_exclusions: frozenset[str]


def _describe(outcome: FileOutcome) -> str:
    match outcome:
        case IngestedFile(source, pages, chunks, topic):
            return f"  ok    {source}  [{topic}]  {pages} pages -> {chunks} chunks"
        case SkippedFile(path, reason):
            return f"  skip  {path}  ({reason})"
        case FailedFile(path, error):
            return f"  FAIL  {path}  ({error})"


def build_app(deps: CliDependencies) -> typer.Typer:
    app = typer.Typer(no_args_is_help=True, add_completion=False)

    @app.command()
    def ingest(
        paths: Annotated[
            list[Path] | None,
            typer.Argument(help="Files or folders to ingest. Defaults to the raw-data directory."),
        ] = None,
        dry_run: Annotated[
            bool, typer.Option("--dry-run", help="Parse and chunk only; embed and write nothing.")
        ] = False,
    ) -> None:
        """Parse, chunk, embed and index course materials."""
        files: list[Path] = []
        for target in paths or [deps.raw_data_dir]:
            if target.is_dir():
                files.extend(discover_files(target, deps.ingest_exclusions))
            elif target.is_file():
                files.append(target)
            else:
                raise typer.BadParameter(f"not found: {target}")

        mode = "dry run: parse + chunk only" if dry_run else "indexing"
        typer.echo(f"{len(files)} files ({mode})")
        report = deps.ingest().execute(
            files, dry_run=dry_run, on_file_done=lambda o: typer.echo(_describe(o))
        )
        typer.echo(
            f"\n{len(report.ingested)} ingested ({report.total_chunks} chunks), "
            f"{len(report.skipped)} skipped, {len(report.failed)} failed"
        )
        if report.failed:
            raise typer.Exit(code=1)

    @app.callback()
    def main() -> None:
        """Study assistant: RAG over course materials."""

    return app
