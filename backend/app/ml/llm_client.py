import httpx
from app.config import settings


class OllamaClient:
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.timeout = 180.0

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
                "num_predict": 1500,
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            return response.json()["response"]
