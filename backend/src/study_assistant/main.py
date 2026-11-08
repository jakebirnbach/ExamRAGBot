"""Composition root: the only module that knows about concrete adapters.

``Container`` builds each adapter once, on first use, and wires adapters into use cases.
The CLI, the eval script and the API all go through it.
"""

from functools import cached_property

from study_assistant.application.use_cases.answer_question import AnswerQuestion
from study_assistant.application.use_cases.generate_quiz import GenerateQuiz, GradeAnswer
from study_assistant.application.use_cases.ingest_documents import IngestDocuments
from study_assistant.application.use_cases.list_topics import ListTopics
from study_assistant.application.use_cases.retrieve_context import RetrieveContext
from study_assistant.domain.entities import Chunk, ChunkMetadata, ScoredChunk
from study_assistant.infrastructure.chunking.hf_token_counter import HuggingFaceTokenCounter
from study_assistant.infrastructure.chunking.token_chunker import TokenChunker
from study_assistant.infrastructure.config import Settings, get_settings
from study_assistant.infrastructure.embedding.bge_m3_embedder import BgeM3Embedder
from study_assistant.infrastructure.llm.bedrock_claude import BedrockClaudeLLM
from study_assistant.infrastructure.llm.bedrock_converse import BedrockConverseLLM
from study_assistant.infrastructure.parsing.course_catalog import CourseCatalog
from study_assistant.infrastructure.parsing.pymupdf_parser import PyMuPdfParser
from study_assistant.infrastructure.reranking.bge_reranker import BgeReranker
from study_assistant.infrastructure.vectorstore.pinecone_store import PineconeVectorStore
from study_assistant.interfaces.api.app import ApiDependencies, build_api
from study_assistant.interfaces.cli.app import CliDependencies, build_app


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------ adapters
    @cached_property
    def embedder(self) -> BgeM3Embedder:
        s = self.settings
        return BgeM3Embedder(
            model_name=s.embedding_model,
            batch_size=s.embedding_batch_size,
            device=s.embedding_device,
        )

    @cached_property
    def reranker(self) -> BgeReranker:
        s = self.settings
        return BgeReranker(
            s.reranker_model, batch_size=s.reranker_batch_size, device=s.embedding_device
        )

    def vector_store(self, alpha: float | None = None) -> PineconeVectorStore:
        """A store client; ``alpha`` overrides the configured hybrid weight (used by eval)."""
        s = self.settings
        api_key = s.pinecone_api_key
        return PineconeVectorStore(
            api_key=api_key.get_secret_value() if api_key else None,
            index_name=s.pinecone_index_name,
            namespace=s.pinecone_namespace,
            dimension=BgeM3Embedder.DIMENSION,
            cloud=s.pinecone_cloud,
            region=s.pinecone_region,
            alpha=s.hybrid_alpha if alpha is None else alpha,
        )

    @cached_property
    def store(self) -> PineconeVectorStore:
        return self.vector_store()

    @cached_property
    def llm(self) -> BedrockClaudeLLM | BedrockConverseLLM:
        s = self.settings
        if s.bedrock_api == "converse":
            return BedrockConverseLLM(
                model_id=s.bedrock_model_id,
                region=s.bedrock_region,
                aws_profile=s.bedrock_aws_profile,
            )
        return BedrockClaudeLLM(
            model_id=s.bedrock_model_id,
            region=s.bedrock_region,
            aws_profile=s.bedrock_aws_profile,
            effort=s.llm_effort,
        )

    # ------------------------------------------------------------------ use cases
    def ingest(self) -> IngestDocuments:
        s = self.settings
        root = s.raw_data_dir
        return IngestDocuments(
            parser=PyMuPdfParser(root, CourseCatalog.from_directory(root)),
            chunker=TokenChunker(
                HuggingFaceTokenCounter(s.embedding_model),
                max_tokens=s.chunk_max_tokens,
                overlap_tokens=s.chunk_overlap_tokens,
                sparse_page_tokens=s.sparse_page_tokens,
            ),
            embedder=self.embedder,
            store=self.store,
            embed_batch_size=s.embedding_batch_size * 4,
        )

    def retrieve(self) -> RetrieveContext:
        s = self.settings
        return RetrieveContext(
            self.embedder,
            self.store,
            self.reranker if s.rerank_enabled else None,
            top_k=s.retrieval_top_k,
            top_n=s.rerank_top_n,
            max_per_source=s.max_chunks_per_source,
        )

    def answer(self) -> AnswerQuestion:
        return AnswerQuestion(
            self.retrieve(),
            self.llm,
            list_topics=self.list_topics(),
            max_tokens=self.settings.llm_max_tokens,
        )

    def list_topics(self) -> ListTopics:
        return ListTopics(self.store)

    def generate_quiz(self) -> GenerateQuiz:
        return GenerateQuiz(self.store, self.llm)

    def grade_answer(self) -> GradeAnswer:
        return GradeAnswer(self.llm)

    def load_models(self) -> None:
        """Load the local models, downloading them if needed. The Docker build uses this to put
        exactly the files the app reads into the image; the build leaves reranking on, so the
        image always has the reranker and turning it back on is a config change."""
        self.embedder.embed_query("warm up")
        if self.settings.rerank_enabled:
            sample = ScoredChunk(Chunk("warm-up", "warm up", ChunkMetadata("warm-up", 1, 0)), 0.0)
            self.reranker.rerank("warm up", [sample], top_n=1)

    def warm_up(self) -> None:
        """Load both models and open the index, so a server's first request isn't slow. No LLM
        call. Running this before serving also means the threads never race to build an adapter."""
        self.load_models()
        self.store.list_topics()
        _ = self.llm


def cli() -> None:
    container = Container(get_settings())
    app = build_app(
        CliDependencies(
            ingest=container.ingest,
            retrieve=container.retrieve,
            answer=container.answer,
            list_topics=container.list_topics,
            raw_data_dir=container.settings.raw_data_dir,
            ingest_exclusions=container.settings.ingest_exclusions(),
        )
    )
    app()


def api() -> None:
    import uvicorn  # noqa: PLC0415 - only the server needs it

    container = Container(get_settings())
    s = container.settings
    password = s.api_password.get_secret_value() if s.api_password else ""
    if not password.strip():
        raise SystemExit("API_PASSWORD is not set. Add it to backend/.env, then start again.")
    app = build_api(
        ApiDependencies(
            answer=container.answer,
            list_topics=container.list_topics,
            generate_quiz=container.generate_quiz,
            grade_answer=container.grade_answer,
            warm_up=container.warm_up,
            password=password,
            max_failed_logins=s.api_max_failed_logins,
            lockout_seconds=s.api_lockout_seconds,
        )
    )
    uvicorn.run(app, host=s.api_host, port=s.api_port)


if __name__ == "__main__":
    cli()
