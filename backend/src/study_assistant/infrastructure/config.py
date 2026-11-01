from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (and ``.env`` locally)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Data
    raw_data_dir: Path = Path("../data/raw")

    # Embeddings / reranking (local models)
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64

    # Retrieval
    retrieval_top_k: int = Field(default=20, ge=1)
    rerank_top_n: int = Field(default=5, ge=1)

    # Pinecone
    pinecone_api_key: SecretStr | None = None
    pinecone_index_name: str = "study-assistant"
    pinecone_namespace: str = "default"

    # AWS Bedrock
    aws_region: str = "us-east-1"
    bedrock_model_id: str | None = None
    """Claude Haiku model / inference-profile id; set via BEDROCK_MODEL_ID."""

    # API
    api_password: SecretStr | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
