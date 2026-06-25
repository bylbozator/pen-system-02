# backend/app/celery_app.py

from celery import Celery
from app.config import settings

celery_app = Celery(
    "pen_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,   # для хранения результатов (опционально)
)

# Автоматическое обнаружение задач в модулях приложения
celery_app.autodiscover_tasks(['app.tasks'])

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=30 * 60,      # 30 минут максимум на задачу
    task_soft_time_limit=25 * 60, # мягкий лимит
    result_expires=3600,
    worker_max_tasks_per_child=100,  # защита от утечек памяти
    worker_prefetch_multiplier=1,    # справедливое распределение задач
)