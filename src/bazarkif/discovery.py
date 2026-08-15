import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .db import Database
from .http_client import HttpClient
from .models import ProductState

logger = logging.getLogger("bazarkif.discovery")

STOCK_PARAM = "?stock_status=instock"
IN_STOCK_LABELS = {"موجود در انبار", "in-stock", "instock"}


def _parse_category_links(html: str, base_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/product-category/" in href:
            links.add(urljoin(base_url, href))
    return links


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

    def discover_categories(self) -> list[str]:
        resp, _, err = self.http.get_with_retry(self.config.shop_url, logger=logger)
        if err:
            raise err
        cats = _parse_category_links(resp.text, self.config.base_url)
        return sorted(cats)

    def discover_products(self, on_progress=None) -> int:
        categories = self.discover_categories()
        logger.info("discovered %d categories", len(categories))
        all_urls: set[str] = set()
        for cat in categories:
            page_urls = self._crawl_category(cat)
            all_urls |= page_urls
            if on_progress:
                on_progress(len(all_urls))

        inserted = 0
        for url in sorted(all_urls):
            self.seen_urls.add(url)
            inserted += self._upsert(url)
        logger.info("discovery complete: %d product urls, %d inserted", len(all_urls), inserted)
        return inserted

    def _crawl_category(self, category_url: str) -> set[str]:
        urls: set[str] = set()
        page = 1
        while True:
            url = category_url + STOCK_PARAM
            if page > 1:
                # filter + pagination must both apply
                base = category_url + f"/page/{page}/" + STOCK_PARAM
                url = base
            resp, _, err = self.http.get_with_retry(url, logger=logger)
            if err:
                logger.error("category page failed", extra={"url": url, "error": str(err)})
                break
            found = _parse_product_links(resp.text, self.config.base_url)
            urls |= found
            if not _has_next_page(resp.text):
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


def _has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", class_="next"):
        if a.get("href"):
            return True
    for link in soup.find_all("a", href=True):
        if "/page/" in link["href"]:
            return True
    return False