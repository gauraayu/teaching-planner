"""Application configuration, loaded from environment variables.

Nothing in here is a secret by default; real values come from the
environment (see `.env.example`).
"""
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Academic Teaching Plan Portal"
    environment: str = Field(default="development", description="development | staging | production")

    # MongoDB Atlas connection string: mongodb+srv://user:password@cluster0.xxxxx.mongodb.net/
    mongodb_uri: str = ""
    # Database name inside the cluster. It is created on first write.
    mongodb_db: str = "teaching_portal"

    # Signs session tokens.
    secret_key: str = "change-me-in-every-environment"
    session_ttl_hours: int = 12

    # true: /api/auth/config tells the sign-in page about the seeded demo accounts. Set false for real use.
    demo_auth_enabled: bool = True

    # Only needed when the browser calls the API directly (Next.js proxies /api by default).
    # Comma-separated in .env: CORS_ORIGINS=http://localhost:3000,https://app.example.edu
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Institution timezone decides what "today" means for a professor.
    institution_timezone: str = "Asia/Kolkata"

    # A professor entering later than this many minutes after the scheduled start is "Delayed"
    # and the Operations Manager must record a reason.
    entry_delay_tolerance_minutes: int = 5

    # Leaving more than this many minutes before the scheduled end needs a reason from the OM.
    exit_early_tolerance_minutes: int = 10
    # How long before the scheduled start the "class starting soon" alert appears.
    class_alert_lead_minutes: int = 5

    # Indian academic sheets write 01/10/2026 for 1 October.
    import_date_dayfirst: bool = True
    import_max_rows: int = 2000
    import_max_file_mb: int = 10

    # Fuzzy-mapping confidence thresholds (RapidFuzz scores, 0-100).
    mapping_fuzzy_suggest_threshold: int = 86
    mapping_fuzzy_hint_threshold: int = 65

    # Object storage (S3-compatible). Empty bucket => URL-only mode.
    storage_bucket: str = ""
    storage_endpoint_url: str = ""
    storage_public_base_url: str = ""
    # Class photos: with no bucket configured they are written to this folder and served from /api/uploads.
    local_upload_dir: str = "uploads"
    evidence_max_mb: int = 5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def signing_key(self) -> str:
        """The key that signs session tokens. A placeholder SECRET_KEY is never used to sign.

        Production refuses to start without a real key. Elsewhere a random key is generated once and
        kept in `.secret_key` (git-ignored), so local sessions survive restarts without a guessable key.
        """
        return _signing_key(self.secret_key, self.is_production)

    @property
    def show_demo_accounts(self) -> bool:
        """The sign-in page may list the seeded demo accounts - never in production."""
        return self.demo_auth_enabled and not self.is_production

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.institution_timezone)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


PLACEHOLDER_KEYS = {"", "change-me-in-every-environment", "generate-a-long-random-string", "changeme", "secret"}


@lru_cache
def _signing_key(configured: str, production: bool) -> str:
    if configured.strip() not in PLACEHOLDER_KEYS and len(configured.strip()) >= 16:
        return configured
    if production:
        raise RuntimeError("SECRET_KEY is missing or a placeholder. Set a long random SECRET_KEY before starting in production.")
    path = Path(__file__).resolve().parents[2] / ".secret_key"
    try:
        if path.exists() and len(path.read_text().strip()) >= 32:
            return path.read_text().strip()
        key = secrets.token_urlsafe(48)
        path.write_text(key)
        return key
    except OSError:
        return secrets.token_urlsafe(48)  # read-only filesystem: sessions last until the process restarts


@lru_cache
def get_settings() -> Settings:
    return Settings()
