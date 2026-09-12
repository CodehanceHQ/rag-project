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
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
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
