import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .db import Database
from .http_client import HttpClient
from .models import ProductState

logger = logging.getLogger("bazarkif.discovery")

STOCK_PARAM = "?stock_status=instock"
IN_STOCK_LABELS = {"موجود در انبار", "in-stock", "instock"}


def _parse_product_links(html: str, base_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        path = urljoin(base_url, href)
        # product URLs like /product/<id>/ or /product/<slug>/
        if "/product/" in path and "/product-category/" not in path:
            links.add(path)
    return links


class Discovery:
    def __init__(self, config, db: Database, http: HttpClient):
        self.config = config
        self.db = db
        self.http = http
        self.seen_urls: set[str] = set()

    def discover_products(self, on_progress=None) -> int:
        page_urls = self._crawl_shop()
        logger.info("discovered %d product urls from shop", len(page_urls))

        inserted = 0
        for url in sorted(page_urls):
            self.seen_urls.add(url)
            inserted += self._upsert(url)
        logger.info("discovery complete: %d product urls, %d inserted", len(page_urls), inserted)
        return inserted

    def _crawl_shop(self) -> set[str]:
        urls: set[str] = set()
        page = 1
        while True:
            per_page = f"per_page={self.config.shop_per_page}"
            if page == 1:
                url = self.config.shop_url + STOCK_PARAM + "&" + per_page
            else:
                base = self.config.shop_url.rstrip("/") + f"/page/{page}/"
                url = base + STOCK_PARAM + "&" + per_page
            resp, _, err = self.http.get_with_retry(url, logger=logger)
            if err:
                logger.error("shop page failed", extra={"url": url, "error": str(err)})
                break
            found = _parse_product_links(resp.text, self.config.base_url)
            new = found - urls
            urls |= found
            if not new:
                break
            if not _has_next_page(resp.text, page):
                break
            page += 1
        return urls

    def _upsert(self, url: str) -> int:
        exists = self.db.scalar("SELECT COUNT(*) FROM products WHERE url=?", (url,))
        if exists:
            return 0
        self.db.execute(
            "INSERT INTO products (url, state, first_seen_at) VALUES (?, ?, datetime('now'))",
            (url, ProductState.DISCOVERED.value),
        )
        self.db.execute(
            "INSERT INTO processing_state (product_id, state, stage) "
            "SELECT id, ?, ? FROM products WHERE url=?",
            (ProductState.DISCOVERED.value, "detail", url),
        )
        return 1


def _has_next_page(html: str, current_page: int) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    target = f"/page/{current_page + 1}/"
    for link in soup.find_all("a", href=True):
        if target in link["href"]:
            return True
    return False