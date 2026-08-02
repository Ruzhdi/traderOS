from app.worker.celery_app import celery_app


@celery_app.task(name="app.tasks.system.worker_ping")
def worker_ping() -> str:
    return "pong"
