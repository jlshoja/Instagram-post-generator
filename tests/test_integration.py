"""End-to-end integration test: scanner runs the whole pipeline against mocked
HTTP responses and a product reaches PUBLISHED (with telegram disabled we stop
at POST_GENERATED)."""

import io

from PIL import Image

from bazarkif.scanner import Scanner
from conftest import IMG_1, IMG_2, build_product_html


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (600, 600), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


class FakeHttp:
    """Simulates the whole site over a tiny virtual product set."""

    PRODUCTS = {
        "https://bazarkif.org/product/9388/": build_product_html(
            title="کوله پشتی – کد 9388 – بازار کیف",
            price="2,414,000",
            attrs=(("ابعاد", "45 × 30 × 10 سانتیمتر"), ("جنس", "چرم")),
        ),
    }

    def __init__(self):
        self.media_bytes = _png()

    def get_with_retry(self, url, **kw):
        class R:
            status_code = 200
            text = ""
        r = R()
        if "/shop/" in url or url.rstrip("/").endswith("/shop"):
            r.text = '<a href="https://bazarkif.org/product/9388/">p</a>'
        elif "/product/9388/" in url:
            r.text = self.PRODUCTS["https://bazarkif.org/product/9388/"]
        else:
            r.text = ""
        return r, 1, None

    def get(self, url, **kw):
        class R:
            status_code = 200
            headers = {"content-type": "image/png"}
        r = R()
        r.content = self.media_bytes
        return r


def test_full_scan_to_published(config, db, monkeypatch):
    config.telegram_bot_token = ""
    config.request_delay = 0.0
    scanner = Scanner(config)
    scanner.db = db
    scanner.http = FakeHttp()
    # discovery reads products straight from the paginated shop page
    scanner.discovery.http = scanner.http
    scanner.detail.http = scanner.http
    scanner.downloader.http = scanner.http

    stats = scanner.run_scan(publish=False)

    assert stats["discovered"] == 1
    p = db.query("SELECT * FROM products WHERE url=?", ("https://bazarkif.org/product/9388/",))[0]
    assert p["name"] == "کوله پشتی"
    assert p["code"] == "9388"
    assert p["price"] == 2414000
    assert p["state"] == "POST_GENERATED"
    # media downloaded & optimized
    assert db.scalar(
        "SELECT COUNT(*) FROM media_files WHERE product_id=? AND status='optimized'", (p["id"],)
    ) >= 1
    # draft post generated
    posts = db.query("SELECT * FROM telegram_posts WHERE product_id=?", (p["id"],))
    assert len(posts) == 1
    assert posts[0]["status"] == "draft"
    assert "#لوکس_باز" in posts[0]["text"]


def test_full_scan_idempotent_rerun(config, db, monkeypatch):
    """Re-running a scan must not duplicate posts or media."""
    config.telegram_bot_token = ""
    config.request_delay = 0.0
    scanner = Scanner(config)
    scanner.db = db
    scanner.http = FakeHttp()
    scanner.discovery.http = scanner.http
    scanner.detail.http = scanner.http
    scanner.downloader.http = scanner.http

    scanner.run_scan(publish=False)
    scanner.run_scan(publish=False)

    assert db.scalar("SELECT COUNT(*) FROM products") == 1
    assert db.scalar("SELECT COUNT(*) FROM telegram_posts") == 1
    assert db.scalar(
        "SELECT COUNT(*) FROM media_files WHERE status='optimized'"
    ) == db.scalar("SELECT COUNT(*) FROM media_files")