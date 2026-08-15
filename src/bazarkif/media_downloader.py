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
        image_rows = [r for r in rows if r["kind"] != MediaKind.VIDEO.value]
        image_ok = 0
        for row in image_rows:
            if row["status"] == "downloaded" and Path(row["local_path"]).exists():
                image_ok += 1
                continue
            if self._download_one(row):
                image_ok += 1
            else:
                logger.warning("media download failed", extra={"product_id": product_id, "url": row["source_url"]})

        for row in rows:
            if row["kind"] == MediaKind.VIDEO.value:
                if row["status"] == "downloaded" and Path(row["local_path"]).exists():
                    continue
                if not self._download_one(row):
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
            (ProductState.MEDIA_DOWNLOADED.value, "optimize", product_id),
        )
        return True, None

    def _download_one(self, row) -> bool:
        url = row["source_url"]
        # percent-encode explicitly so non-ASCII (Persian) filenames are sent
        # in exactly the form the CDN expects regardless of proxy/urllib3 IRI handling
        request_url = quote(url, safe=":/?&=%")
        # retry transient failures (network errors / 5xx) up to 3 attempts
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
            # permanently gone (e.g. stale raw-content links on the site):
            # mark dead so it is never retried on later scans
            self.db.execute(
                "UPDATE media_files SET status=? WHERE id=?",
                (MediaStatus.DELETED.value, row["id"]),
            )
            return False
        if resp.status_code >= 400 or not resp.content:
            return False

        dest_dir = self.config.media_root / "download" / str(row["product_id"])
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = self._ext_from_content_type(resp.headers.get("content-type", "")) or Path(
            _filename_from_url(url)
        ).suffix
        path = dest_dir / f"{row['id']}_{_filename_from_url(url)}"
        if not path.suffix:
            path = path.with_suffix(ext)
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