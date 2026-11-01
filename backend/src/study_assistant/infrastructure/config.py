from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
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
    pinecone_namespace: str = "course"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # AWS Bedrock
    aws_region: str = "us-east-1"
    bedrock_model_id: str | None = None
    """Claude Haiku model / inference-profile id; set via BEDROCK_MODEL_ID."""

    # API
    api_password: SecretStr | None = None

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
