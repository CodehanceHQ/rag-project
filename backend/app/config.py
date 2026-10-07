from functools import lru_cache
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    mongodb_uri: str = ""
    mongodb_root_username: str = "rag"
    mongodb_root_password: str = "rag-local-password"
    mongodb_database: str = "local_rag"
    mongodb_vector_index: str = "chunk_vector_index"
    mongodb_text_index: str = "chunk_text_index"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    retrieval_candidate_limit: int = 30
    rrf_rank_constant: int = 60
    minimum_relevance_score: float = 0.15
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4.1-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str = "http://localhost:3000"
    openrouter_app_name: str = "Local RAG Studio"
    openrouter_timeout_seconds: float = 30.0
    ambiguity_score_margin: float = 0.05
    ambiguity_max_candidates: int = 6
    frontend_origin: str = "http://localhost:3000"
    max_upload_mb: int = 50
    chunk_size: int = 1000
    chunk_overlap: int = 180

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def mongo_connection_uri(self) -> str:
        if self.mongodb_uri:
            return self.mongodb_uri
        username = quote_plus(self.mongodb_root_username)
        password = quote_plus(self.mongodb_root_password)
        return f"mongodb://{username}:{password}@localhost:27017/?authSource=admin&directConnection=true"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
