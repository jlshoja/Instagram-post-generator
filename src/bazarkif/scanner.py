import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .change_notifier import ChangeNotifier
from .cleanup import Cleanup
from .db import Database
from .detail import DetailExtractor
from .discovery import Discovery
from .http_client import HttpClient
from .media_downloader import MediaDownloader
from .media_optimizer import MediaOptimizer
from .models import ProductState
from .post_generator import PostGenerator
from .retry_queue import RetryQueue
from .telegram_publisher import TelegramPublisher

logger = logging.getLogger("bazarkif.scanner")

STAGE_ORDER = ["detail", "media", "optimize", "post", "publish"]


def _stage_index(name: str) -> int:
    try:
        return STAGE_ORDER.index(name)
    except ValueError:
        return len(STAGE_ORDER)


class Scanner:
    def __init__(self, config):
        self.config = config
        config.ensure_dirs()
        self.db = Database.connect(config)
        self.http = HttpClient(config)
        self.discovery = Discovery(config, self.db, self.http)
        self.detail = DetailExtractor(config, self.db, self.http)
        self.downloader = MediaDownloader(config, self.db, self.http)
        self.optimizer = MediaOptimizer(config, self.db)
        self.generator = PostGenerator(config, self.db)
        self.publisher = TelegramPublisher(config, self.db)
        self.notifier = ChangeNotifier(config, self.db, self.publisher)
        self.retry = RetryQueue(config, self.db)
        self.cleanup = Cleanup(config, self.db)

    # ---- stage workers --------------------------------------------------
    def _run_detail(self, product_id: int, stage: str = "detail") -> bool:
        row = self.db.query("SELECT * FROM products WHERE id=?", (product_id,))
        if not row:
            return False
        ok, err = self.detail.extract(row[0])
        if not ok:
            self.retry.record_failure(product_id, stage, err or "detail failed")
        return ok

    def _run_media(self, product_id: int) -> bool:
        ok, err = self.downloader.download_product(product_id)
        if not ok:
            self.retry.record_failure(product_id, "media_download", err or "media download failed")
        return ok

    def _run_optimize(self, product_id: int) -> bool:
        ok, err = self.optimizer.optimize_product(product_id)
        if not ok:
            self.retry.record_failure(product_id, "media_optimize", err or "optimize failed")
        return ok

    def _run_post(self, product_id: int) -> bool:
        ok, err = self.generator.generate(product_id)
        if not ok:
            self.retry.record_failure(product_id, "post_generate", err or "post generate failed")
        return ok

    def _run_publish(self, product_id: int) -> bool:
        ok, err = self.publisher.publish_pending(product_id)
        if not ok:
            self.retry.record_failure(product_id, "telegram_publish", err or "publish failed")
        return ok

    def _run_stage(self, product_id: int, stage: str) -> bool:
        if stage == "detail":
            return self._run_detail(product_id)
        if stage == "media":
            return self._run_media(product_id)
        if stage == "optimize":
            return self._run_optimize(product_id)
        if stage == "post":
            return self._run_post(product_id)
        if stage == "publish":
            return self._run_publish(product_id)
        return False

    # ---- orchestrator ---------------------------------------------------
    def run_scan(self, publish: bool = True, until: str | None = None) -> dict:
        """until: run only stages up to this stage name
        (detail|media|optimize|post|publish). None runs everything."""
        scan_id = self.db.execute(
            "INSERT INTO scans (started_at, status) VALUES (datetime('now'),'RUNNING')"
        ).lastrowid
        stats = {"discovered": 0, "processed": 0, "published": 0, "failed": 0, "changes": 0}

        self.cleanup.sweep_orphans()
        stats["discovered"] = self.discovery.discover_products()
        self._mark_unavailable_removed()
        stats["changes"] = self.notifier.notify_pending()

        stages = [
            ("detail", ProductState.DISCOVERED, self._run_detail, "detail"),
            ("media", ProductState.DETAILS_EXTRACTED, self._run_media, "media"),
            ("optimize", ProductState.MEDIA_DOWNLOADED, self._run_optimize, "optimize"),
            ("post", ProductState.MEDIA_OPTIMIZED, self._run_post, "post"),
            ("publish", ProductState.POST_GENERATED, self._run_publish, "publish"),
        ]
        for name, state, worker, stage in stages:
            if until and _stage_index(name) > _stage_index(until):
                break
            if name == "publish" and not publish:
                continue
            self._process_stage(state, worker, stage)

        # requeue any due failed jobs
        self.retry.requeue_due(self._run_stage)

        stats["processed"] = self.db.scalar("SELECT COUNT(*) FROM products WHERE state IN ('POST_GENERATED','PUBLISHED','MEDIA_OPTIMIZED')")
        stats["published"] = self.db.scalar("SELECT COUNT(*) FROM products WHERE state='PUBLISHED'")
        stats["failed"] = self.db.scalar("SELECT COUNT(*) FROM failed_jobs WHERE resolved=0")

        self.db.execute(
            "UPDATE scans SET finished_at=datetime('now'), status='COMPLETED', discovered=?, processed=?, published=?, changes=?, failed=? WHERE id=?",
            (stats["discovered"], stats["processed"], stats["published"], stats["changes"], stats["failed"], scan_id),
        )
        logger.info("scan complete", extra={"stats": stats})
        return stats

    def _process_stage(self, state: ProductState, worker, stage: str) -> None:
        ids = [r["id"] for r in self.db.query(
            "SELECT id FROM products WHERE state=? AND is_active=1", (state.value,)
        )]
        if not ids:
            return
        if self.config.sample_limit > 0:
            ids = ids[: self.config.sample_limit]
            logger.info(
                "sample mode: processing %d of %d at stage %s",
                len(ids), self.config.sample_limit, stage,
            )
        total = len(ids)
        logger.info("stage %s: processing %d products", stage, total)
        lock = threading.Lock()
        done = 0
        with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
            futures = {pool.submit(worker, pid): pid for pid in ids}
            for fut in as_completed(futures):
                pid = futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    logger.exception("stage worker error", extra={"product_id": pid, "stage": stage, "error": str(e)})
                    self.retry.record_failure(pid, stage, str(e))
                with lock:
                    done += 1
                if done == total or done % 5 == 0:
                    logger.info("stage %s progress: %d/%d", stage, done, total)

    def _mark_unavailable_removed(self) -> None:
        """Products previously active but no longer present in the fresh
        instock listing are marked unavailable and logged as a change."""
        seen = self.discovery.seen_urls
        if not seen:
            return  # first scan / empty listing — nothing to compare against
        rows = self.db.query(
            "SELECT id, name, url FROM products WHERE is_active=1 AND url NOT IN "
            f"({','.join('?' * len(seen))})",
            tuple(seen),
        )
        for row in rows:
            self.db.execute(
                "UPDATE products SET is_active=0, updated_at=datetime('now') WHERE id=?",
                (row["id"],),
            )
            self.db.execute(
                "INSERT INTO change_log (product_id, change_type) VALUES (?,?)",
                (row["id"], "availability_changed"),
            )
            logger.info("product unavailable", extra={"product_id": row["id"], "name": row["name"]})

    def resume(self) -> None:
        """Re-feeds products by current state into their queues on startup."""
        self.retry.requeue_due(self._run_stage)