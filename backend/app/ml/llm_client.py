import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.timeout = settings.OLLAMA_TIMEOUT

    # ── Main generation call ──────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system: str,
        model: str | None = None,
        temperature: float = 0.3,
        num_predict: int = 700,
        num_ctx: int = 2048,
    ) -> str:
        """
        Send a prompt to Ollama and return the raw response string.

        Raises:
            ConnectionError  – Ollama is not reachable.
            TimeoutError     – Ollama did not respond within OLLAMA_TIMEOUT seconds.
            RuntimeError     – Ollama returned a non-2xx HTTP status.
        """
        resolved_model = model or settings.OLLAMA_MODEL
        payload = {
            "model": resolved_model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "num_ctx": num_ctx,
            },
        }
        url = f"{self.base_url}/api/generate"
        logger.debug("Ollama request → model=%s url=%s", resolved_model, url)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                text = response.json()["response"]
                logger.debug(
                    "Ollama response ← %d chars (model=%s)", len(text), resolved_model
                )
                return text

        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot reach Ollama at {self.base_url}. "
                "Start it with: ollama serve"
            ) from exc

        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"Ollama timed out after {self.timeout}s "
                f"(model={resolved_model}). "
                "Try: ollama run " + resolved_model
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama HTTP {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            ) from exc

    # ── Health check ──────────────────────────────────────────────────────────

    async def health_check(self) -> dict:
        """
        Ping Ollama and return a status dict:
          {"reachable": True,  "models": [...], "error": None}
          {"reachable": False, "models": [],    "error": "<reason>"}
        """
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                r.raise_for_status()
                models = [m["name"] for m in r.json().get("models", [])]
                configured = settings.OLLAMA_MODEL
                return {
                    "reachable": True,
                    "base_url": self.base_url,
                    "configured_model": configured,
                    "model_available": configured in models,
                    "available_models": models,
                    "error": None,
                }
        except Exception as exc:
            return {
                "reachable": False,
                "base_url": self.base_url,
                "configured_model": settings.OLLAMA_MODEL,
                "model_available": False,
                "available_models": [],
                "error": str(exc),
            }


class GroqClient:
    """
    Drop-in replacement for OllamaClient using Groq's OpenAI-compatible API.
    ~800 tokens/sec vs Ollama's ~15-20 tokens/sec — ~40x faster for LLM steps.
    Active when GROQ_API_KEY is set in .env; falls back to OllamaClient otherwise.
    """

    _API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self) -> None:
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.timeout = 60.0

    async def generate(
        self,
        prompt: str,
        system: str,
        model: str | None = None,
        temperature: float = 0.3,
        num_predict: int = 700,
        num_ctx: int = 2048,  # ignored by Groq API — accepted for interface compat
    ) -> str:
        """
        Send a chat completion request to Groq and return the response text.
        Interface is identical to OllamaClient.generate().

        Raises:
            ConnectionError – Groq API is not reachable.
            TimeoutError    – Request exceeded timeout.
            RuntimeError    – Groq returned a non-2xx HTTP status or rate limit.
        """
        resolved_model = model or self.model
        payload = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": num_predict,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        logger.debug("Groq request → model=%s", resolved_model)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self._API_URL, json=payload, headers=headers
                )
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"]
                logger.debug("Groq response ← %d chars", len(text))
                return text

        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Cannot reach Groq API at {self._API_URL}."
            ) from exc

        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"Groq timed out after {self.timeout}s (model={resolved_model})."
            ) from exc

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = exc.response.text[:300]
            if status == 429:
                raise RuntimeError(f"Groq rate limit hit: {body}") from exc
            raise RuntimeError(f"Groq HTTP {status}: {body}") from exc

    async def health_check(self) -> dict:
        """Ping Groq by listing available models."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                r.raise_for_status()
                models = [m["id"] for m in r.json().get("data", [])]
                return {
                    "reachable": True,
                    "provider": "groq",
                    "configured_model": self.model,
                    "model_available": self.model in models,
                    "available_models": models,
                    "error": None,
                }
        except Exception as exc:
            return {
                "reachable": False,
                "provider": "groq",
                "configured_model": self.model,
                "model_available": False,
                "available_models": [],
                "error": str(exc),
            }


def get_llm_client() -> OllamaClient | GroqClient:
    """
    Return the active LLM client.
    Groq is used when GROQ_API_KEY is set; otherwise falls back to Ollama.
    """
    if settings.GROQ_API_KEY:
        logger.debug("LLM backend: Groq (model=%s)", settings.GROQ_MODEL)
        return GroqClient()
    logger.debug("LLM backend: Ollama (model=%s)", settings.OLLAMA_MODEL)
    return OllamaClient()
