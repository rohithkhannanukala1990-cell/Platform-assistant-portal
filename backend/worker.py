"""
Celery application factory.
---------------------------------------
Import this module to get the configured Celery app:

    from worker import celery_app

Start the worker from the backend/ directory:

    celery -A worker.celery_app worker --loglevel=info --concurrency=2

Or via Docker Compose (see docker-compose.yml).
"""
import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

BROKER_URL      = os.getenv("CELERY_BROKER_URL",    "redis://localhost:6379/0")
RESULT_BACKEND  = os.getenv("CELERY_RESULT_BACKEND", BROKER_URL)

celery_app = Celery(
    "aiops",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    # Register task modules so the worker discovers them on startup
    include=["tasks"],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,               # ack only after the task finishes
    task_reject_on_worker_lost=True,   # requeue if the worker crashes mid-task
    worker_prefetch_multiplier=1,      # one task per worker slot (fair scheduling)

    # Visibility
    task_track_started=True,           # STARTED state visible in result backend

    # Result expiry – keep for 24 h then discard
    result_expires=86400,
)
