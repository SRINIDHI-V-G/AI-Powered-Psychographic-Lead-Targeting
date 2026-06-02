"""
Ollama health / status endpoints.
These are unauthenticated so operators can check LLM readiness without an API key.
"""
from fastapi import APIRouter

from app.config import settings
from app.ml.llm_client import OllamaClient

router = APIRouter(prefix="/ollama", tags=["Ollama"])


@router.get(
    "/status",
    summary="Check Ollama connectivity and model availability",
    description=(
        "Pings the configured Ollama instance and reports whether it is reachable, "
        "which models are available, and whether the configured model is loaded. "
        "Does NOT require an API key."
    ),
)
async def ollama_status() -> dict:
    client = OllamaClient()
    info = await client.health_check()
    info["use_mock_llm"] = settings.USE_MOCK_LLM
    info["fallback_on_error"] = settings.FALLBACK_TO_MOCK_ON_ERROR
    return info
