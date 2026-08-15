import logging
from datetime import datetime, timedelta

from .db import Database
from .models import MediaKind, ProductState

logger = logging.getLogger("bazarkif.retry_queue")


class RetryQueue:
    """Durable retry queue over failed_jobs table."""

    STAGE_MAP = {
        "discovery": None,  # discovery is handled by the scanner
        "detail": "detail",
        "media_download": "media",
        "media_optimize": "optimize",
        "post_generate": "post",
        "telegram_publish": "publish",
    }

    def __init__(self, config, db: Database):
        self.config = config
        self.db = db

    def record_failure(self, product_id: int, stage: str, error: str) -> None:
        self.db.execute(
            "INSERT INTO failed_jobs (product_id, stage, attempts, next_retry_at, last_error) "
            "VALUES (?,?,?,?,?)",
            (product_id, stage, 1, self._next_retry(1), error[:2000]),
        )

    def _next_retry(self, attempt: int) -> str:
        delay = min(self.config.retry_max_delay, self.config.retry_base_delay * (self.config.retry_factor ** (attempt - 1)))
        when = datetime.now() + timedelta(seconds=delay)
        return when.isoformat()

    def due_jobs(self):
        return self.db.query(
            "SELECT * FROM failed_jobs WHERE resolved=0 AND next_retry_at <= ?",
            (datetime.now().isoformat(),),
        )

    def requeue_due(self, run_stage) -> int:
        """Re-enqueue due failed jobs into their stage. run_stage is a callable
        (product_id, stage_name) -> None."""
        jobs = self.due_jobs()
        for job in jobs:
            stage = job["stage"]
            if stage not in self.STAGE_MAP:
                continue
            try:
                run_stage(job["product_id"], stage)
                self.db.execute(
                    "UPDATE failed_jobs SET resolved=1 WHERE id=?", (job["id"],)
                )
            except Exception as e:
                attempts = job["attempts"] + 1
                if attempts >= job["max_attempts"]:
                    self.db.execute(
                        "UPDATE failed_jobs SET attempts=?, last_error=? WHERE id=?",
                        (attempts, str(e)[:2000], job["id"]),
                    )
                    self._surface_to_failed_topic(job["product_id"], stage, str(e))
                else:
                    self.db.execute(
                        "UPDATE failed_jobs SET attempts=?, last_error=?, next_retry_at=? WHERE id=?",
                        (attempts, str(e)[:2000], self._next_retry(attempts), job["id"]),
                    )
        return len(jobs)

    def _surface_to_failed_topic(self, product_id, stage, error) -> None:
        from .telegram_publisher import TelegramPublisher

        # avoid circular import; mark as terminal FAILED
        self.db.execute(
            "UPDATE products SET state=?, last_error=? WHERE id=?",
            (ProductState.FAILED.value, error[:2000], product_id),
        )
        self.db.execute(
            "UPDATE processing_state SET state=?, stage=? WHERE product_id=?",
            (ProductState.FAILED.value, stage, product_id),
        )
        logger.error("job permanently failed", extra={"product_id": product_id, "stage": stage, "error": error})