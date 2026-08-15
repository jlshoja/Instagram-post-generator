import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    base_url: str = "https://bazarkif.org"
    shop_url: str = "https://bazarkif.org/shop/"
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )

    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "bazarkif.db")
    media_root: Path = field(default_factory=lambda: PROJECT_ROOT / ".media")
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")

    request_timeout: int = 30
    request_delay: float = 0.5
    workers: int = 4
    concurrency_download: int = 4
    sample_limit: int = 0  # >0: process only this many products (test mode)

    scan_interval_minutes: int = 1440  # once per day by default
    enable_scheduler: bool = True

    # retry policy
    max_attempts: int = 5
    retry_base_delay: float = 2.0
    retry_max_delay: float = 300.0
    retry_factor: float = 2.0
    retry_jitter: float = 0.25
    retry_on_http: tuple = (429, 500, 502, 503, 504)

    # media optimization
    webp_target_bytes: int = 125 * 1024
    webp_quality_start: int = 82
    webp_quality_floor: int = 55
    image_max_dimension: int = 1080
    orphan_retention_hours: float = 24.0

    # telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    thread_pending_posts: int = 0
    thread_published_posts: int = 0
    thread_changes: int = 0
    thread_failed_jobs: int = 0

    require_gallery: bool = True
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        c = cls()
        c.base_url = os.environ.get("BASE_URL", c.base_url)
        c.shop_url = os.environ.get("SHOP_URL", c.shop_url)
        c.db_path = Path(os.environ.get("DB_PATH", str(c.db_path)))
        c.media_root = Path(os.environ.get("MEDIA_ROOT", str(c.media_root)))
        c.log_dir = Path(os.environ.get("LOG_DIR", str(c.log_dir)))

        c.request_timeout = int(os.environ.get("REQUEST_TIMEOUT", c.request_timeout))
        c.request_delay = float(os.environ.get("REQUEST_DELAY", c.request_delay))
        c.workers = int(os.environ.get("WORKERS", c.workers))
        c.concurrency_download = int(
            os.environ.get("CONCURRENCY_DOWNLOAD", c.concurrency_download)
        )
        c.sample_limit = int(os.environ.get("SAMPLE_LIMIT", c.sample_limit))

        c.scan_interval_minutes = int(
            os.environ.get("SCAN_INTERVAL_MINUTES", c.scan_interval_minutes)
        )
        c.enable_scheduler = _env_bool("ENABLE_SCHEDULER", c.enable_scheduler)

        c.max_attempts = int(os.environ.get("MAX_ATTEMPTS", c.max_attempts))
        c.retry_base_delay = float(
            os.environ.get("RETRY_BASE_DELAY", c.retry_base_delay)
        )
        c.retry_max_delay = float(os.environ.get("RETRY_MAX_DELAY", c.retry_max_delay))
        c.retry_factor = float(os.environ.get("RETRY_FACTOR", c.retry_factor))

        c.webp_target_bytes = int(os.environ.get("WEBP_TARGET_BYTES", c.webp_target_bytes))
        c.image_max_dimension = int(
            os.environ.get("IMAGE_MAX_DIMENSION", c.image_max_dimension)
        )

        c.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", c.telegram_bot_token)
        c.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", c.telegram_chat_id)
        c.thread_pending_posts = int(
            os.environ.get("TELEGRAM_THREAD_PENDING", c.thread_pending_posts)
        )
        c.thread_published_posts = int(
            os.environ.get("TELEGRAM_THREAD_PUBLISHED", c.thread_published_posts)
        )
        c.thread_changes = int(os.environ.get("TELEGRAM_THREAD_CHANGES", c.thread_changes))
        c.thread_failed_jobs = int(
            os.environ.get("TELEGRAM_THREAD_FAILED", c.thread_failed_jobs)
        )

        c.require_gallery = _env_bool("REQUIRE_GALLERY", c.require_gallery)
        c.log_level = os.environ.get("LOG_LEVEL", c.log_level)
        return c

    def ensure_dirs(self) -> None:
        for p in (self.db_path.parent, self.media_root, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)