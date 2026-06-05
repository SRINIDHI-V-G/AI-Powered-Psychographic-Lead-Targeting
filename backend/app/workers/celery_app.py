"""
Celery application instance.

Broker and result backend are resolved from settings:
  settings.celery_broker()  → CELERY_BROKER_URL or REDIS_URL or localhost fallback
  settings.celery_backend() → CELERY_RESULT_BACKEND or REDIS_URL or localhost fallback

To start the worker:
  celery -A app.workers.celery_app worker --loglevel=info \
    --queues=pipeline,discovery,nlp,scoring,matching,handles,similarity

Queue routing:
  pipeline    — motivation generation, product OCEAN
  discovery   — user discovery + content collection
  nlp         — NLP batch processing
  scoring     — OCEAN scoring (Ollama-heavy, slow)
  matching    — matching engine + lead ranking
  handles     — handle discovery (bio extraction + LLM generation)
  similarity  — similar product discovery
"""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "psycholead",
    broker=settings.celery_broker(),
    backend=settings.celery_backend(),
    include=[
        "app.workers.tasks.product_tasks",
        "app.workers.tasks.product_ocean_tasks",
        "app.workers.tasks.similarity_tasks",
        "app.workers.tasks.discovery_tasks",
        "app.workers.tasks.nlp_tasks",
        "app.workers.tasks.scoring_tasks",
        "app.workers.tasks.matching_tasks",
        "app.workers.tasks.handle_tasks",
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behaviour
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Retry policy defaults (individual tasks override as needed)
    task_max_retries=3,

    # Result expiry
    result_expires=86400,

    # Queue routing
    task_routes={
        "app.workers.tasks.product_tasks.*":       {"queue": "pipeline"},
        "app.workers.tasks.product_ocean_tasks.*": {"queue": "pipeline"},
        "app.workers.tasks.similarity_tasks.*":    {"queue": "similarity"},
        "app.workers.tasks.discovery_tasks.*":     {"queue": "discovery"},
        "app.workers.tasks.nlp_tasks.*":           {"queue": "nlp"},
        "app.workers.tasks.scoring_tasks.*":       {"queue": "scoring"},
        "app.workers.tasks.matching_tasks.*":      {"queue": "matching"},
        "app.workers.tasks.handle_tasks.*":        {"queue": "handles"},
    },

    # Beat schedule (reserved for future scheduled jobs)
    beat_schedule={},
)
