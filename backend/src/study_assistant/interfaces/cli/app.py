"""``study-assistant`` command line. Receives use-case factories from the composition root."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from study_assistant.application.dto import FailedFile, FileOutcome, IngestedFile, SkippedFile
from study_assistant.application.use_cases.ingest_documents import IngestDocuments, discover_files
from study_assistant.application.use_cases.list_topics import ListTopics
from study_assistant.application.use_cases.retrieve_context import RetrieveContext
from study_assistant.domain.entities import MetadataFilter, ScoredChunk


@dataclass(frozen=True, slots=True)
class CliDependencies:
    ingest: Callable[[], IngestDocuments]
    """Factory, so heavy adapters are only built when a command needs them."""
    retrieve: Callable[[], RetrieveContext]
    list_topics: Callable[[], ListTopics]
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


def _resolve_topics(wanted: list[str], available: list[str]) -> tuple[str, ...]:
    """Match each ``--topic`` value case-insensitively against topic labels, so ``M3``
    selects ``M3 · Health Behavior Change Theory``."""
    resolved: list[str] = []
    for w in wanted:
        hits = [t for t in available if t.lower().startswith(w.lower()) or w.lower() in t.lower()]
        if not hits:
            raise typer.BadParameter(f"no topic matches {w!r}; run `topics` to list them")
        resolved.extend(hits)
    return tuple(dict.fromkeys(resolved))


def _format_hit(rank: int, hit: ScoredChunk, snippet_chars: int) -> str:
    m = hit.chunk.metadata
    pages = f"pp. {m.page}-{m.page_end}" if m.page_end else f"p. {m.page}"
    body = hit.chunk.text.split("\n", 1)[-1]  # drop the title header line
    snippet = " ".join(body.split())[:snippet_chars]
    return f"{rank}. [{hit.score:.3f}] {m.source}, {pages}  ({m.topic})\n   {snippet}..."


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

    @app.command()
    def search(
        question: Annotated[str, typer.Argument(help="Question to retrieve context for.")],
        topic: Annotated[
            list[str] | None,
            typer.Option("--topic", "-t", help="Restrict to a topic, e.g. M3 (repeatable)."),
        ] = None,
        no_rerank: Annotated[
            bool, typer.Option("--no-rerank", help="Show raw hybrid-search order.")
        ] = False,
        snippet: Annotated[int, typer.Option(help="Characters of each chunk to show.")] = 240,
    ) -> None:
        """Show the chunks retrieval returns for a question (no LLM involved)."""
        flt = None
        if topic:
            flt = MetadataFilter(topics=_resolve_topics(topic, deps.list_topics().execute()))
            typer.echo(f"topics: {', '.join(flt.topics or ())}")
        hits = deps.retrieve().execute(question, flt, rerank=not no_rerank)
        if not hits:
            typer.echo("no results")
        for rank, hit in enumerate(hits, 1):
            typer.echo(_format_hit(rank, hit, snippet))

    @app.command()
    def topics() -> None:
        """List the topics available for filtering."""
        for t in deps.list_topics().execute():
            typer.echo(t)

    @app.callback()
    def main() -> None:
        """Study assistant: RAG over course materials."""

    return app
