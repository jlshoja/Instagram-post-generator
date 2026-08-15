import json
import logging
import logging.handlers
import sys
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        for key in ("product_id", "stage", "url", "attempt"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bazarkif")
    logger.setLevel(level.upper())
    logger.propagate = False

    if not logger.handlers:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_dir / "app.log", when="midnight", backupCount=14, encoding="utf-8"
        )
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)

        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(JsonFormatter())
        logger.addHandler(stream)
    return logger