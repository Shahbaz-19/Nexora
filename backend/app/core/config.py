import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret_key: str
    groq_api_key: str
    groq_model: str
    cors_origins: tuple[str, ...]
    cors_origin_regex: str | None
    cookie_secure: bool
    cookie_samesite: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    groq_timeout_seconds: float
    max_upload_bytes: int
    stale_processing_minutes: int
    database_pool_size: int
    database_max_overflow: int
    database_pool_recycle_seconds: int
    embedding_provider: str
    gemini_api_key: str | None
    gemini_embedding_model: str
    embedding_request_timeout_seconds: float
    embedding_batch_size: int
    reranker_provider: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    required = {
        "DATABASE_URL": os.getenv("DATABASE_URL"),
        "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY"),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
        "GROQ_MODEL": os.getenv("GROQ_MODEL"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required settings: {', '.join(missing)}")
    if len(required["JWT_SECRET_KEY"] or "") < 32:
        raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters.")

    same_site = os.getenv("COOKIE_SAMESITE", "lax").lower()
    if same_site not in {"lax", "strict", "none"}:
        raise RuntimeError("COOKIE_SAMESITE must be lax, strict, or none.")
    secure = _bool("COOKIE_SECURE", False)
    if same_site == "none" and not secure:
        raise RuntimeError("COOKIE_SECURE must be true when COOKIE_SAMESITE=none.")

    origins = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    )
    if not origins or "*" in origins:
        raise RuntimeError("CORS_ORIGINS must contain explicit origins.")

    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()
    if embedding_provider not in {"gemini", "nomic_local"}:
        raise RuntimeError("EMBEDDING_PROVIDER must be gemini or nomic_local.")
    gemini_api_key = os.getenv("GEMINI_API_KEY") or None
    if embedding_provider == "gemini" and not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini.")
    reranker_provider = os.getenv("RERANKER_PROVIDER", "none").lower()
    if reranker_provider not in {"none", "local"}:
        raise RuntimeError("RERANKER_PROVIDER must be none or local.")

    settings_value = Settings(
        database_url=required["DATABASE_URL"] or "",
        jwt_secret_key=required["JWT_SECRET_KEY"] or "",
        groq_api_key=required["GROQ_API_KEY"] or "",
        groq_model=required["GROQ_MODEL"] or "",
        cors_origins=origins,
        cors_origin_regex=os.getenv("CORS_ORIGIN_REGEX") or None,
        cookie_secure=secure,
        cookie_samesite=same_site,
        access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")),
        refresh_token_expire_days=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")),
        groq_timeout_seconds=float(os.getenv("GROQ_TIMEOUT_SECONDS", "45")),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        stale_processing_minutes=int(os.getenv("STALE_PROCESSING_MINUTES", "30")),
        database_pool_size=int(os.getenv("DATABASE_POOL_SIZE", "3")),
        database_max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "2")),
        database_pool_recycle_seconds=int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "300")),
        embedding_provider=embedding_provider,
        gemini_api_key=gemini_api_key,
        gemini_embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        embedding_request_timeout_seconds=float(
            os.getenv("EMBEDDING_REQUEST_TIMEOUT_SECONDS", "30")
        ),
        embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "50")),
        reranker_provider=reranker_provider,
    )
    if settings_value.access_token_expire_minutes <= 0 or settings_value.refresh_token_expire_days <= 0:
        raise RuntimeError("Token expiration settings must be positive.")
    if settings_value.groq_timeout_seconds <= 0 or settings_value.max_upload_bytes <= 0:
        raise RuntimeError("Timeout and upload limit settings must be positive.")
    if settings_value.database_pool_size <= 0 or settings_value.database_max_overflow < 0:
        raise RuntimeError("Database pool size must be positive and max overflow cannot be negative.")
    if settings_value.database_pool_recycle_seconds <= 0:
        raise RuntimeError("DATABASE_POOL_RECYCLE_SECONDS must be positive.")
    if settings_value.embedding_request_timeout_seconds <= 0:
        raise RuntimeError("EMBEDDING_REQUEST_TIMEOUT_SECONDS must be positive.")
    if not 1 <= settings_value.embedding_batch_size <= 100:
        raise RuntimeError("EMBEDDING_BATCH_SIZE must be between 1 and 100.")
    return settings_value


settings = get_settings()
