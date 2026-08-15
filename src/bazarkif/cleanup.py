import logging
import time
from pathlib import Path

from .db import Database

logger = logging.getLogger("bazarkif.cleanup")


class Cleanup:
    def __init__(self, config, db: Database):
        self.config = config
        self.db = db

    def sweep_orphans(self) -> int:
        """Delete temp files older than the retention window."""
        cutoff = time.time() - self.config.orphan_retention_hours * 3600
        removed = 0
        for folder in (self.config.media_root / "download", self.config.media_root / "optimize"):
            if not folder.exists():
                continue
            for path in folder.rglob("*"):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    try:
                        path.unlink()
                        removed += 1
                    except OSError:
                        pass
        if removed:
            logger.info("removed %d orphan media files", removed)
        return removed