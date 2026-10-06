from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8", extra="ignore", case_sensitive=False,
    )
    database_url: str
    jwt_secret: SecretStr
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"
    cookie_secure: bool = False
    pdf_storage_path: Path = REPO_ROOT / ".local" / "pdfs"
    model_artifact_path: Path = REPO_ROOT / 'ml' / 'artifacts' / 'current'
    chat_provider: str = 'gemini'
    gemini_api_key: SecretStr | None = None
    gemini_model: str = Field(default='gemini-3.5-flash-lite', pattern=r'^[A-Za-z0-9._-]+$')
    embedding_model_path: Path = REPO_ROOT / '.local' / 'embedding'
    chat_timeout_seconds: int = Field(default=45, ge=5, le=55)
    auth_rate_limit: int = Field(default=20, ge=1, le=1000)
    auth_rate_window_seconds: int = Field(default=60, ge=1, le=3600)

    @field_validator('embedding_model_path')
    @classmethod
    def absolute_embedding_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @field_validator('chat_provider')
    @classmethod
    def validate_chat_provider(cls, value: str) -> str:
        if value not in {'disabled', 'gemini'}:
            raise ValueError('CHAT_PROVIDER must be disabled or gemini')
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, value: str) -> str:
        origins = [item.strip() for item in value.split(",") if item.strip()]
        if not origins:
            raise ValueError("ALLOWED_ORIGINS must not be empty")
        for origin in origins:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
                raise ValueError("ALLOWED_ORIGINS must contain exact HTTP(S) origins without paths")
        return ",".join(origins)

    @property
    def origin_set(self) -> set[str]:
        return set(self.allowed_origins.split(","))


@lru_cache
def get_settings() -> Settings:
    return Settings()
