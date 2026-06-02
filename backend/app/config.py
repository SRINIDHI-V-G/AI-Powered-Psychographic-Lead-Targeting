from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"

    # How long (seconds) to wait for a single Ollama /api/generate response.
    # 180 s is generous for llama3.1:8b on consumer hardware.
    OLLAMA_TIMEOUT: float = 300.0

    # Set to True to skip Ollama entirely and persist hardcoded fallback
    # categories.  Useful for offline demos or CI where Ollama is absent.
    USE_MOCK_LLM: bool = False

    # If True, a failed Ollama call (connection error, timeout, parse failure)
    # stores fallback categories instead of marking the product as "failed".
    # The product still reaches motivations_generated so the dashboard works.
    FALLBACK_TO_MOCK_ON_ERROR: bool = True

    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
