import logging
import time
from pathlib import Path
from urllib.parse import quote, urlparse

from .db import Database
from .http_client import HttpClient
from .models import MediaKind, MediaStatus, ProductState
from .detail import MEDIA_HOST

logger = logging.getLogger("bazarkif.media_download")


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name or "media"
    # keep only safe chars, retain extension
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    return safe


class MediaDownloader:
    def __init__(self, config, db: Database, http: HttpClient):
        self.config = config
        self.db = db
        self.http = http

    def download_product(self, product_id: int) -> tuple[bool, str | None]:
        # get product SKU (code)
        prod = self.db.query(
            "SELECT code FROM products WHERE id=?", (product_id,)
        )
        sku = prod[0]["code"] if prod else str(product_id)

        rows = self.db.query(
            "SELECT * FROM media_files WHERE product_id=? AND status IN ('pending','downloaded')",
            (product_id,),
        )
        # purge stale pending rows pointing at non-store hosts (e.g. embeds)
        for r in rows:
            if r["status"] == "pending" and MEDIA_HOST not in r["source_url"]:
                self.db.execute(
                    "UPDATE media_files SET status=? WHERE id=?",
                    (MediaStatus.DELETED.value, r["id"]),
                )
        rows = [r for r in rows if MEDIA_HOST in r["source_url"] or r["status"] == "downloaded"]

        # assign SKU-based letter suffixes per kind
        # featured -> a, gallery -> b,c,d..., video -> a,b,c...
        counters = {"featured": 0, "gallery": 0, "video": 0}
        for row in rows:
            kind = row["kind"]
            idx = counters.get(kind, 0)
            counters[kind] = idx + 1
            if kind == "featured":
                suffix = "a"
            elif kind == "gallery":
                suffix = chr(ord("b") + idx)
            else:  # video
                suffix = chr(ord("a") + idx)
            self.db.execute(
                "UPDATE media_files SET sku_suffix=? WHERE id=?", (suffix, row["id"])
            )

        rows = self.db.query(
            "SELECT * FROM media_files WHERE product_id=? AND status IN ('pending','downloaded')",
            (product_id,),
        )
        rows = [r for r in rows if MEDIA_HOST in r["source_url"] or r["status"] == "downloaded"]

        image_rows = [r for r in rows if r["kind"] != MediaKind.VIDEO.value]
        image_ok = 0
        for row in image_rows:
            if row["status"] == "downloaded" and Path(row["local_path"]).exists():
                image_ok += 1
                continue
            res = self._download_one(row, sku)
            if res is True:
                image_ok += 1
            elif res == "gone":
                pass
            else:
                logger.warning("media download failed", extra={"product_id": product_id, "url": row["source_url"]})

        for row in rows:
            if row["kind"] == MediaKind.VIDEO.value:
                if row["status"] == "downloaded" and Path(row["local_path"]).exists():
                    continue
                res = self._download_one(row, sku)
                if res == "gone":
                    pass
                elif not res:
                    logger.warning("video download failed", extra={"product_id": product_id, "url": row["source_url"]})

        # the card needs at least one image; individual file failures do not
        # block the product
        if self.config.require_gallery and image_ok == 0:
            return False, "no images downloaded"

        self.db.execute(
            "UPDATE products SET state=?, updated_at=datetime('now') WHERE id=?",
            (ProductState.MEDIA_DOWNLOADED.value, product_id),
        )
        self.db.execute(
            "UPDATE processing_state SET state=?, stage=?, updated_at=datetime('now') WHERE product_id=?",
            (ProductState.MEDIA_DOWNLOADED.value, "post", product_id),
        )
        return True, None

    def _download_one(self, row, sku: str) -> bool | str:
        url = row["source_url"]
        request_url = quote(url, safe=":/?&=%")
        resp = None
        last_err = None
        for attempt in range(3):
            try:
                resp = self.http.get(request_url)
            except Exception as e:
                resp = None
                last_err = e
            if resp is not None and resp.status_code < 500:
                break
            if attempt < 2:
                time.sleep(1 + attempt)
        if resp is None:
            logger.warning("media fetch error", extra={"url": url, "error": str(last_err)})
            return False
        if resp.status_code in (404, 410):
            self.db.execute(
                "UPDATE media_files SET status=? WHERE id=?",
                (MediaStatus.DELETED.value, row["id"]),
            )
            logger.debug("media permanently gone (404/410); marked deleted", extra={"url": url})
            return "gone"
        if resp.status_code >= 400 or not resp.content:
            return False

        dest_dir = self.config.media_root / "download" / str(row["product_id"])
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = self._ext_from_content_type(resp.headers.get("content-type", "")) or Path(
            _filename_from_url(url)
        ).suffix
        suffix = row["sku_suffix"] if "sku_suffix" in row.keys() else ""
        if not suffix:
            suffix = "a"
        filename = f"{sku}{suffix}{ext}"
        path = dest_dir / filename
        path.write_bytes(resp.content)

        self.db.execute(
            "UPDATE media_files SET local_path=?, size_bytes=?, mime=?, status=? WHERE id=?",
            (str(path), len(resp.content), resp.headers.get("content-type", ""), MediaStatus.DOWNLOADED.value, row["id"]),
        )
        return True

    @staticmethod
    def _ext_from_content_type(ct: str) -> str | None:
        ct = ct.lower()
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
        }
        return mapping.get(ct)