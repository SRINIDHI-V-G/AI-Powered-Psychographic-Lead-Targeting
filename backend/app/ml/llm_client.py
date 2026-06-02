import httpx
from app.config import settings


class OllamaClient:
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.timeout = 600.0

    async def generate(
        self,
        prompt: str,
        system: str,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> str:
        payload = {
            "model": model or settings.OLLAMA_MODEL,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 1200,
            },
        }
        url = f"{self.base_url}/api/generate"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()["response"]
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Make sure Ollama is running: open a terminal and run 'ollama serve'"
            )
        except httpx.TimeoutException:
            raise TimeoutError(
                f"Ollama request timed out after {self.timeout}s. "
                "The model may be too slow or not loaded. "
                f"Try running: ollama run {payload['model']}"
            )
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Ollama returned HTTP {e.response.status_code}. "
                f"Body: {e.response.text[:300]}"
            )
