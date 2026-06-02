import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    DATABASE_URL: str
    ENVIRONMENT: str = "development"

    # ── Ollama / LLM ──────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_TIMEOUT: float = 300.0
    USE_MOCK_LLM: bool = False
    FALLBACK_TO_MOCK_ON_ERROR: bool = True

    # ── Reddit Discovery ──────────────────────────────────────────────────────
    # ⚠️  PENDING EXTERNAL CREDENTIALS — see backend/CREDENTIALS_REQUIRED.md
    #
    # These must be supplied by the project owner/team before Reddit discovery
    # can function. They are obtained by creating a Reddit developer application
    # at https://reddit.com/prefs/apps (select type "script", free, ~5 minutes).
    #
    # Do NOT use personal/intern accounts. Use a shared project account.
    #
    # Leave blank (default "") during development. The system will warn at
    # startup and fall back to MockDiscoveryProvider automatically.
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    # Format: "python:AppName:1.0 (by u/YourRedditUsername)"
    REDDIT_USER_AGENT: str = "python:PsychographicLeads:1.0 (by u/project_owner)"

    # ── Discovery Behaviour ───────────────────────────────────────────────────
    # When True, always use MockDiscoveryProvider regardless of credentials.
    # Automatically set to True if Reddit credentials are absent.
    MOCK_DISCOVERY: bool = False

    # Default maximum users to discover per job.
    # Analysis: 150 users × 15 content items = 2,250 API calls at 60 req/min
    # ≈ 37 minutes. 300 users ≈ 75 minutes. 150 is the MVP sweet spot.
    DISCOVERY_MAX_USERS: int = 150

    # Maximum content items fetched per user.
    # Analysis: OCEAN prompt uses 8 items. NLP benefits level off after ~15.
    # 15 gives >95% of signal value at 60% of the API cost vs. 25.
    DISCOVERY_CONTENT_PER_USER: int = 15

    # Batch size for content collection background processing.
    DISCOVERY_CONTENT_BATCH_SIZE: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    def reddit_credentials_configured(self) -> bool:
        return bool(self.REDDIT_CLIENT_ID and self.REDDIT_CLIENT_SECRET)

    def use_mock_discovery(self) -> bool:
        """Returns True if MockDiscoveryProvider should be used."""
        return self.MOCK_DISCOVERY or not self.reddit_credentials_configured()


settings = Settings()


def warn_missing_credentials() -> None:
    """
    Log startup warnings for any unconfigured external credentials.
    Called once from main.py lifespan so operators see warnings immediately.
    """
    if not settings.reddit_credentials_configured():
        logger.warning(
            "⚠️  Reddit credentials not configured. "
            "Discovery will use MockDiscoveryProvider. "
            "Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT "
            "in .env to enable real Reddit discovery. "
            "See backend/CREDENTIALS_REQUIRED.md for setup instructions."
        )
    else:
        logger.info(
            "✓ Reddit credentials configured (client_id=%s...)",
            settings.REDDIT_CLIENT_ID[:6],
        )
