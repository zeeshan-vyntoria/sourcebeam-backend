from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Sourcebeam AI API"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg_async://postgres:postgres@localhost:5432/ai_backend"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_models: str = "gemini-3.5-flash,gemini-3.6-flash"
    embedding_model: str = "gemini-embedding-2"
    embedding_dimensions: int = Field(default=768, ge=128, le=3072)

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "sourcebeam-api"
    jwt_audience: str = "sourcebeam-web"
    jwt_access_token_minutes: int = Field(default=60, ge=5, le=1440)
    auth_cookie_name: str = "sourcebeam_session"

    allowed_origins_csv: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="ALLOWED_ORIGINS",
    )
    conversation_context_messages: int = Field(default=20, ge=2, le=100)
    conversation_context_characters: int = Field(default=40_000, ge=4_000, le=500_000)
    auth_rate_limit_requests: int = Field(default=8, ge=1, le=100)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    ai_rate_limit_requests: int = Field(default=10, ge=1, le=1000)
    ai_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    ai_max_concurrency: int = Field(default=4, ge=1, le=32)
    ai_request_timeout_seconds: float = Field(default=45, ge=5, le=300)
    rag_max_pdf_bytes: int = Field(default=15 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    rag_max_pdf_pages: int = Field(default=250, ge=1, le=1000)
    rag_max_extracted_characters: int = Field(default=1_000_000, ge=10_000, le=5_000_000)
    rag_chunk_characters: int = Field(default=2400, ge=400, le=8000)
    rag_chunk_overlap_characters: int = Field(default=320, ge=0, le=2000)
    rag_retrieval_top_k: int = Field(default=6, ge=1, le=20)
    rag_candidate_pool: int = Field(default=24, ge=4, le=100)
    rag_min_similarity: float = Field(default=0.20, ge=-1, le=1)
    rag_hybrid_enabled: bool = True
    rag_rerank_enabled: bool = True
    rag_rerank_candidates: int = Field(default=12, ge=2, le=30)
    ocr_enabled: bool = True
    ocr_min_page_characters: int = Field(default=40, ge=0, le=1000)
    ocr_render_dpi: int = Field(default=200, ge=100, le=400)
    ingestion_poll_seconds: float = Field(default=1.0, ge=0.2, le=30)
    ingestion_max_attempts: int = Field(default=3, ge=1, le=10)
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = ".sourcebeam-storage"
    s3_endpoint_url: str = ""
    s3_bucket: str = "sourcebeam"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    public_daily_ai_messages: int = Field(default=50, ge=1, le=10000)
    public_daily_uploads: int = Field(default=20, ge=1, le=1000)
    public_user_storage_bytes: int = Field(default=250 * 1024 * 1024, ge=1024)
    image_max_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    image_max_pixels: int = Field(default=20_000_000, ge=100_000, le=50_000_000)
    image_max_dimension: int = Field(default=8192, ge=256, le=16384)
    image_max_per_message: int = Field(default=3, ge=1, le=10)
    image_context_max_bytes: int = Field(
        default=16 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024
    )

    @field_validator("database_url")
    @classmethod
    def use_async_psycopg_driver(cls, value: str) -> str:
        # Smoothly upgrade the URL used by the earlier synchronous tutorial app.
        return value.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)

    @model_validator(mode="after")
    def validate_security_settings(self):
        secret = self.jwt_secret_key.strip()
        normalized = "".join(character for character in secret.lower() if character.isalnum())
        placeholder_words = (
            "secret",
            "password",
            "changeme",
            "replacewith",
            "development",
            "example",
        )
        if (
            secret != self.jwt_secret_key
            or len(secret) < 43
            or len(set(secret)) < 12
            or any(word in normalized for word in placeholder_words)
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be a random value with at least 43 characters"
            )
        if "*" in self.allowed_origins:
            raise ValueError("ALLOWED_ORIGINS cannot contain '*' when cookies are enabled")
        if self.environment == "production":
            if not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required in production")
        if self.embedding_dimensions != 768:
            raise ValueError("EMBEDDING_DIMENSIONS is fixed at 768; changing it needs a migration")
        if self.rag_chunk_overlap_characters >= self.rag_chunk_characters:
            raise ValueError("RAG chunk overlap must be smaller than the chunk size")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins_csv.split(",") if origin.strip()]

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"

    @property
    def fallback_models(self) -> list[str]:
        return [model.strip() for model in self.gemini_fallback_models.split(",") if model.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
