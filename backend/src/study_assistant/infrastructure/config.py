from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (and ``backend/.env``)."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Data
    raw_data_dir: Path = REPO_ROOT / "data" / "raw"
    ingest_exclude_file: Path = REPO_ROOT / "data" / "ingest_exclude.txt"

    # Embedding + chunking (local models)
    embedding_model: str = "BAAI/bge-m3"
    embedding_batch_size: int = Field(default=16, ge=1)
    embedding_device: str = "cpu"
    chunk_max_tokens: int = Field(default=450, ge=50)
    """Kept under 512 so query + chunk fits the reranker's input window."""
    chunk_overlap_tokens: int = Field(default=50, ge=0)
    sparse_page_tokens: int = Field(default=150, ge=0)
    """Documents whose median page is below this are treated as slide decks."""

    # Reranking
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_batch_size: int = Field(default=16, ge=1)

    # Retrieval
    retrieval_top_k: int = Field(default=20, ge=1)
    rerank_top_n: int = Field(default=5, ge=1)
    max_chunks_per_source: int = Field(default=2, ge=1)
    """Diversity cap applied to the final top-N."""
    hybrid_alpha: float = Field(default=0.5, ge=0.0, le=1.0)
    """Dense weight in hybrid search (1.0 = dense only)."""

    # Pinecone
    pinecone_api_key: SecretStr | None = None
    pinecone_index_name: str = "study-assistant"
    pinecone_namespace: str = "default"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # AWS Bedrock (Claude via the Anthropic SDK's Bedrock client)
    bedrock_region: str = "us-east-1"
    bedrock_api: Literal["messages", "converse"] = "converse"
    """``converse`` (default): AWS Converse API via boto3, for Claude Haiku 4.5 - the model this
    AWS account can use. ``messages``: Anthropic SDK Bedrock client, for current models such as
    Haiku 5.5 (``anthropic.claude-haiku-5-5``), which AWS hasn't enabled on this account.
    ``llm_effort`` applies to ``messages`` only."""
    bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_aws_profile: str | None = None
    """Named profile from ~/.aws (e.g. ``exam-rag-bot``). This and ``bedrock_region`` are
    deliberately not ``AWS_PROFILE`` / ``AWS_REGION``: shell-exported AWS variables override
    .env and would silently switch the credentials or region the app uses."""
    llm_effort: str = "low"
    """How much the model thinks before answering: low / medium / high."""
    llm_max_tokens: int = Field(default=4096, ge=256)
    """Covers thinking plus the answer."""

    # API
    api_password: SecretStr | None = None
    """Required by the API server, which won't start without it."""
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_max_failed_logins: int = Field(default=10, ge=1)
    """Wrong passwords allowed from one client within the window before it's locked out."""
    api_lockout_seconds: int = Field(default=900, ge=1)
    """The window starts at a client's first wrong password; a lockout lasts until it ends."""

    @field_validator("bedrock_model_id", "bedrock_aws_profile", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object, info: ValidationInfo) -> object:
        """A blank ``KEY=`` line in .env means "use the default", not an empty string."""
        if isinstance(value, str) and not value.strip() and info.field_name:
            return cls.model_fields[info.field_name].default
        return value

    @field_validator("raw_data_dir", "ingest_exclude_file")
    @classmethod
    def _relative_to_backend(cls, path: Path) -> Path:
        """Relative paths (e.g. ``RAW_DATA_DIR=../data/raw``) are relative to ``backend/``,
        where ``.env`` lives, so commands work from any working directory."""
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()

    def ingest_exclusions(self) -> frozenset[str]:
        """File names / relative paths listed in the exclude file (``#`` comments allowed)."""
        if not self.ingest_exclude_file.is_file():
            return frozenset()
        lines = self.ingest_exclude_file.read_text(encoding="utf-8").splitlines()
        return frozenset(s for line in lines if (s := line.split("#", 1)[0].strip()))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
