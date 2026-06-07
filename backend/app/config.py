import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    DATABASE_URL: str
    ENVIRONMENT: str = "development"

    # ── Redis (optional — required for Celery + persistent rate-limiting) ─────
    # Leave blank in dev; the health check reports "not_configured" cleanly.
    REDIS_URL: str = ""

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Explicit allowlist of origins. Must be set before production deployment.
    # Development default permits localhost only.
    # Production example:
    #   CORS_ORIGINS=https://app.example.com,https://staging.example.com
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # ── Ollama / LLM ──────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_TIMEOUT: float = 300.0
    USE_MOCK_LLM: bool = False
    FALLBACK_TO_MOCK_ON_ERROR: bool = False

    # ── Reddit Discovery ──────────────────────────────────────────────────────
    # Obtain credentials at https://reddit.com/prefs/apps (type: script).
    # Leave blank to fall back to MockDiscoveryProvider automatically.
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "python:PsychographicLeads:1.0 (by u/project_owner)"

    # ── YouTube Discovery ─────────────────────────────────────────────────────
    # Obtain a key at https://console.cloud.google.com → enable YouTube Data API v3.
    # Leave blank to fall back to MockDiscoveryProvider for YouTube jobs.
    # Free quota: 10,000 units/day. Search costs 100 units; comments cost 1 unit.
    YOUTUBE_API_KEY: str = ""

    # ── Instagram Discovery ───────────────────────────────────────────────────
    # Uses instagrapi (Instagram private API). Provide a dedicated account —
    # do NOT use your personal account to avoid lockouts.
    # Leave blank to disable Instagram discovery.
    INSTAGRAM_USERNAME: str = ""
    INSTAGRAM_PASSWORD: str = ""
    # Browser session-ID login (alternative to username+password).
    # Get it from DevTools → Application → Cookies → instagram.com → sessionid.
    # When set, instagrapi skips the password flow and avoids challenge issues.
    INSTAGRAM_SESSION_ID: str = ""
    # Path to persist the Instagram session (cookies + device fingerprint).
    # In Docker: mount a persistent volume so the session survives restarts.
    INSTAGRAM_SESSION_FILE: str = "instagram_session.json"
    # Discovery limits — lower values reduce API load but may reduce user coverage.
    INSTAGRAM_MAX_POSTS_PER_HASHTAG: int = 20
    INSTAGRAM_MAX_COMMENTS_PER_POST: int = 30

    # ── Discovery Behaviour ───────────────────────────────────────────────────
    # When True, always use MockDiscoveryProvider regardless of credentials.
    MOCK_DISCOVERY: bool = False

    DISCOVERY_MAX_USERS: int = 150
    DISCOVERY_CONTENT_PER_USER: int = 15
    DISCOVERY_CONTENT_BATCH_SIZE: int = 20

    # YouTube-specific discovery limits
    # Videos searched per keyword × max_results_per_video × comment density = user volume.
    YOUTUBE_MAX_VIDEOS_PER_KEYWORD: int = 10
    YOUTUBE_MAX_COMMENTS_PER_VIDEO: int = 50

    # ── Similar Product Discovery ─────────────────────────────────────────────
    # Maximum number of similar products to keep after filtering by similarity
    # threshold. The LLM is asked for 8 candidates; only the top SIMILAR_PRODUCTS_MAX
    # that exceed the threshold are persisted.
    SIMILAR_PRODUCTS_MAX: int = 5

    # Minimum cosine similarity (0.0-1.0) between a candidate's OCEAN profile
    # and the source product's OCEAN profile for the candidate to be kept.
    # Raise this value to get fewer but more personality-aligned similar products.
    SIMILAR_PRODUCT_SIMILARITY_THRESHOLD: float = 0.65

    # Timeout in seconds for the similar products LLM call.
    # Separate from OLLAMA_TIMEOUT so the two pipelines can be tuned independently.
    SIMILAR_PRODUCTS_LLM_TIMEOUT: float = 120.0

    # ── Demo mode ─────────────────────────────────────────────────────────────
    # DISABLED by default. Set ENABLE_DEMO=true only in development/staging.
    # NEVER enable in production — demo endpoints create API keys without auth.
    # DEMO_SECRET: a bearer token callers must supply to reach demo endpoints.
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    ENABLE_DEMO: bool = False
    DEMO_SECRET: str = ""

    # ── Celery / background task dispatch ────────────────────────────────────
    # Set USE_CELERY=True + configure REDIS_URL to enable Celery task queue.
    # When False (default), all pipeline stages run as asyncio background tasks
    # inside the Uvicorn process — suitable for single-server dev/staging.
    USE_CELERY: bool = False
    # Celery broker and result backend derive from REDIS_URL when not overridden.
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── Derived helpers ───────────────────────────────────────────────────────

    def reddit_credentials_configured(self) -> bool:
        # All three fields are mandatory for Application-Only OAuth.
        # USER_AGENT is checked because Reddit rejects "python-requests" (PRAW default).
        return bool(
            self.REDDIT_CLIENT_ID
            and self.REDDIT_CLIENT_SECRET
            and self.REDDIT_USER_AGENT
            and "project_owner" not in self.REDDIT_USER_AGENT  # reject unconfigured default
        )

    def youtube_credentials_configured(self) -> bool:
        return bool(self.YOUTUBE_API_KEY)

    def instagram_credentials_configured(self) -> bool:
        session_id_ok = bool(self.INSTAGRAM_SESSION_ID and self.INSTAGRAM_USERNAME)
        password_ok = bool(self.INSTAGRAM_USERNAME and self.INSTAGRAM_PASSWORD)
        return session_id_ok or password_ok

    def use_mock_discovery(self) -> bool:
        """True → use MockDiscoveryProvider for all discovery jobs."""
        return self.MOCK_DISCOVERY or not (
            self.reddit_credentials_configured()
            or self.youtube_credentials_configured()
            or self.instagram_credentials_configured()
        )

    def celery_broker(self) -> str:
        """Resolve broker URL: explicit override → REDIS_URL → localhost fallback."""
        if self.CELERY_BROKER_URL:
            return self.CELERY_BROKER_URL
        if self.REDIS_URL:
            return self.REDIS_URL
        return "redis://localhost:6379/0"

    def celery_backend(self) -> str:
        if self.CELERY_RESULT_BACKEND:
            return self.CELERY_RESULT_BACKEND
        if self.REDIS_URL:
            return self.REDIS_URL
        return "redis://localhost:6379/0"

    def celery_enabled(self) -> bool:
        return self.USE_CELERY and bool(self.REDIS_URL or self.CELERY_BROKER_URL)


settings = Settings()


def warn_missing_credentials() -> None:
    """Log startup warnings for unconfigured external credentials."""

    # ── Production safety checks (hard errors on misconfiguration) ───────────
    is_prod = settings.ENVIRONMENT.lower() == "production"

    if is_prod and "*" in settings.CORS_ORIGINS:
        raise RuntimeError(
            "FATAL: CORS_ORIGINS contains '*' in a production environment. "
            "Set CORS_ORIGINS to your frontend domain(s) before starting the server. "
            "Example: CORS_ORIGINS=https://app.example.com"
        )

    if is_prod and settings.ENABLE_DEMO:
        raise RuntimeError(
            "FATAL: ENABLE_DEMO=true is not allowed in a production environment. "
            "Demo endpoints create API keys without authentication. "
            "Remove ENABLE_DEMO from your production .env file."
        )

    if settings.ENABLE_DEMO and not settings.DEMO_SECRET:
        raise RuntimeError(
            "ENABLE_DEMO=true requires DEMO_SECRET to be set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    # ── Origin summary ───────────────────────────────────────────────────────
    if "*" in settings.CORS_ORIGINS:
        logger.warning(
            "⚠️  CORS_ORIGINS is '*' — all origins are allowed. "
            "Acceptable in development only. Set explicit origins before deploying."
        )
    else:
        logger.info("✓ CORS restricted to: %s", settings.CORS_ORIGINS)

    # ── Demo mode ────────────────────────────────────────────────────────────
    if settings.ENABLE_DEMO:
        logger.warning(
            "⚠️  Demo mode ENABLED. Demo endpoints are active. "
            "Never enable in production."
        )

    # ── Discovery credentials ────────────────────────────────────────────────
    if not settings.reddit_credentials_configured():
        logger.warning(
            "⚠️  Reddit credentials not configured. "
            "Discovery will use MockDiscoveryProvider. "
            "Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT in .env."
        )
    else:
        logger.info("✓ Reddit credentials configured (client_id=%s...)", settings.REDDIT_CLIENT_ID[:6])

    if not settings.youtube_credentials_configured():
        logger.warning(
            "⚠️  YouTube API key not configured. "
            "YouTube discovery will use MockDiscoveryProvider. "
            "Set YOUTUBE_API_KEY in .env to enable real YouTube discovery."
        )
    else:
        logger.info("✓ YouTube API key configured.")

    if not settings.instagram_credentials_configured():
        logger.warning(
            "⚠️  Instagram credentials not configured. "
            "Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in .env to enable Instagram discovery."
        )
    else:
        logger.info(
            "✓ Instagram credentials configured (account=%s)", settings.INSTAGRAM_USERNAME
        )

    if settings.celery_enabled():
        logger.info("✓ Celery enabled (broker=%s)", settings.celery_broker()[:30])
    else:
        logger.info("ℹ  Celery disabled — pipeline runs as async background tasks.")
