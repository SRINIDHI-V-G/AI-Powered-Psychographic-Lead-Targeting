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
                # num_predict caps output tokens; 1500 covers 5 JSON categories.
                # 700 tokens safely fits 5 compact JSON motivation categories.
                "num_predict": 700,
                # 2048 context is ample; avoids the overhead of a larger KV cache.
                "num_ctx": 2048,
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
