import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _load_dotenv(path: Path) -> None:
    """Load KEY=value lines from a .env file into os.environ without
    overriding variables that are already set (real env wins)."""
    if not path.exists():
        return
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if not key:
                    continue
                if key in os.environ:
                    continue
                os.environ[key] = value
    except OSError:
        pass


@dataclass
class Config:
    base_url: str = "https://bazarkif.org"
    shop_url: str = "https://bazarkif.org/shop/"
    shop_per_page: int = 500  # products read per shop page request
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

    # media
    image_max_dimension: int = 1080
    orphan_retention_hours: float = 24.0

    # pricing (benefit increase applied to the price before publishing)
    pricing_file: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "mapping" / "pricing_sample.csv")
    pricing_enabled: bool = True

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
        _load_dotenv(PROJECT_ROOT / ".env")
        c.base_url = os.environ.get("BASE_URL", c.base_url)
        c.shop_url = os.environ.get("SHOP_URL", c.shop_url)
        c.shop_per_page = _env_int("SHOP_PER_PAGE", c.shop_per_page)
        c.db_path = Path(os.environ.get("DB_PATH", str(c.db_path)))
        c.media_root = Path(os.environ.get("MEDIA_ROOT", str(c.media_root)))
        c.log_dir = Path(os.environ.get("LOG_DIR", str(c.log_dir)))

        c.request_timeout = _env_int("REQUEST_TIMEOUT", c.request_timeout)
        c.request_delay = float(os.environ.get("REQUEST_DELAY", c.request_delay) or c.request_delay)
        c.workers = _env_int("WORKERS", c.workers)
        c.concurrency_download = _env_int("CONCURRENCY_DOWNLOAD", c.concurrency_download)
        c.sample_limit = _env_int("SAMPLE_LIMIT", c.sample_limit)

        c.scan_interval_minutes = _env_int("SCAN_INTERVAL_MINUTES", c.scan_interval_minutes)
        c.enable_scheduler = _env_bool("ENABLE_SCHEDULER", c.enable_scheduler)

        c.max_attempts = _env_int("MAX_ATTEMPTS", c.max_attempts)
        c.retry_base_delay = float(os.environ.get("RETRY_BASE_DELAY", c.retry_base_delay) or c.retry_base_delay)
        c.retry_max_delay = float(os.environ.get("RETRY_MAX_DELAY", c.retry_max_delay) or c.retry_max_delay)
        c.retry_factor = float(os.environ.get("RETRY_FACTOR", c.retry_factor) or c.retry_factor)

        c.pricing_file = Path(os.environ.get("PRICING_FILE", str(c.pricing_file)))
        c.pricing_enabled = _env_bool("PRICING_ENABLED", c.pricing_enabled)

        c.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", c.telegram_bot_token)
        c.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", c.telegram_chat_id)
        c.thread_pending_posts = _env_int("TELEGRAM_THREAD_PENDING", c.thread_pending_posts)
        c.thread_published_posts = _env_int("TELEGRAM_THREAD_PUBLISHED", c.thread_published_posts)
        c.thread_changes = _env_int("TELEGRAM_THREAD_CHANGES", c.thread_changes)
        c.thread_failed_jobs = _env_int("TELEGRAM_THREAD_FAILED", c.thread_failed_jobs)

        c.require_gallery = _env_bool("REQUIRE_GALLERY", c.require_gallery)
        c.log_level = os.environ.get("LOG_LEVEL", c.log_level)
        return c

    def ensure_dirs(self) -> None:
        for p in (self.db_path.parent, self.media_root, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)