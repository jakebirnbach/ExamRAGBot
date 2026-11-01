"""Composition root: the only module that knows about concrete adapters.

Builds infrastructure adapters from ``Settings`` and injects them into use cases.
"""

from study_assistant.application.use_cases.ingest_documents import IngestDocuments
from study_assistant.infrastructure.chunking.hf_token_counter import HuggingFaceTokenCounter
from study_assistant.infrastructure.chunking.token_chunker import TokenChunker
from study_assistant.infrastructure.config import Settings, get_settings
from study_assistant.infrastructure.embedding.bge_m3_embedder import BgeM3Embedder
from study_assistant.infrastructure.parsing.course_catalog import CourseCatalog
from study_assistant.infrastructure.parsing.pymupdf_parser import PyMuPdfParser
from study_assistant.infrastructure.vectorstore.pinecone_store import PineconeVectorStore
from study_assistant.interfaces.cli.app import CliDependencies, build_app


def build_ingest(settings: Settings) -> IngestDocuments:
    root = settings.raw_data_dir
    embedder = BgeM3Embedder(
        model_name=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
        device=settings.embedding_device,
    )
    api_key = settings.pinecone_api_key
    return IngestDocuments(
        parser=PyMuPdfParser(root, CourseCatalog.from_directory(root)),
        chunker=TokenChunker(
            HuggingFaceTokenCounter(settings.embedding_model),
            max_tokens=settings.chunk_max_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
            sparse_page_tokens=settings.sparse_page_tokens,
        ),
        embedder=embedder,
        store=PineconeVectorStore(
            api_key=api_key.get_secret_value() if api_key else None,
            index_name=settings.pinecone_index_name,
            namespace=settings.pinecone_namespace,
            dimension=embedder.dimension,
            cloud=settings.pinecone_cloud,
            region=settings.pinecone_region,
            alpha=settings.hybrid_alpha,
        ),
        embed_batch_size=settings.embedding_batch_size * 4,
    )


def cli() -> None:
    settings = get_settings()
    app = build_app(
        CliDependencies(
            ingest=lambda: build_ingest(settings),
            raw_data_dir=settings.raw_data_dir,
            ingest_exclusions=settings.ingest_exclusions(),
        )
    )
    app()


if __name__ == "__main__":
    cli()
