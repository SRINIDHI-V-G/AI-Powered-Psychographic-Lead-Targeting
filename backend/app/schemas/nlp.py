"""Pydantic schemas for the NLP pipeline API."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NlpStatusResponse(BaseModel):
    """Pipeline NLP status for a product — returned by the status poll endpoint."""
    product_id: UUID
    total_users: int
    nlp_processed: int
    nlp_pending: int
    nlp_failed: int
    progress_pct: float


class UserEmbeddingResponse(BaseModel):
    id: UUID
    user_id: UUID
    embedding_type: str
    model_used: str
    token_count: int | None
    # Embedding vector is intentionally excluded from API responses
    # (384 floats = ~3KB per user; clients don't need raw vectors)
    created_at: datetime

    model_config = {"from_attributes": True}


class UserNlpFeaturesResponse(BaseModel):
    id: UUID
    user_id: UUID
    empath_scores: dict
    bertopic_topics: list
    spacy_entities: list
    interest_tags: list[str]
    keyword_frequency: dict
    vocabulary_richness: float | None
    avg_sentence_length: float | None
    total_tokens: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
