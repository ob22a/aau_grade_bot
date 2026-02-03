import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery requires 'ssl_cert_reqs' parameter for 'rediss://' (SSL) URLs.
# Without this, it raises a ValueError.
if REDIS_URL.startswith("rediss://") and "ssl_cert_reqs" not in REDIS_URL:
    separator = "&" if "?" in REDIS_URL else "?"
    REDIS_URL = f"{REDIS_URL}{separator}ssl_cert_reqs=none"

celery_app = Celery(
    "aau_grade_bot",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Concurrency limit per requirement (5-10 concurrent scrapes)
    # This is usually set in the worker command: celery -A ... worker --concurrency=8
    # Windows stability settings
    worker_concurrency=4, 
    worker_max_tasks_per_child=100,
    worker_pool_restarts=True,
    task_track_started=True,
    # Central Scheduler (Celery Beat) configuration
    beat_schedule={
        "check-all-grades-every-30-mins": {
            "task": "workers.tasks.check_all_grades",
            "schedule": 1800.0, # 30 minutes
        },
    }
)
