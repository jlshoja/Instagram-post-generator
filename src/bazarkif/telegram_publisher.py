import logging
import time
from pathlib import Path

import requests

from .db import Database
from .models import MediaKind, PostStatus, ProductState, Topic

logger = logging.getLogger("bazarkif.telegram_publish")


class TelegramPublisher:
    API_BASE = "https://api.telegram.org/bot{token}/"

    def __init__(self, config, db: Database):
        self.config = config
        self.db = db
        self.session = requests.Session()
        self.base = self.API_BASE.format(token=config.telegram_bot_token)

    @property
    def enabled(self) -> bool:
        return bool(self.config.telegram_bot_token and self.config.telegram_chat_id)

    def _post(self, method: str, files=None, **data):
        url = self.base + method
        last_err = None
        for attempt in range(1, 5):
            try:
                resp = self.session.post(url, data=data, files=files, timeout=120)
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(2 * attempt)
                continue
            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                logger.warning("telegram 429, waiting %ss", retry_after)
                time.sleep(min(retry_after, 30))
                continue
            if resp.status_code >= 400:
                body = resp.text[:500]
                last_err = f"HTTP {resp.status_code}: {body}"
                time.sleep(2 * attempt)
                continue
            body = resp.json()
            if not body.get("ok"):
                last_err = f"telegram api error: {body.get('description')}"
                time.sleep(2 * attempt)
                continue
            return body["result"]
        raise RuntimeError(f"telegram call failed: {last_err}")

    def publish_pending(self, product_id: int) -> tuple[bool, str | None]:
        if not self.enabled:
            return False, "telegram not configured"

        # publish guard: avoid duplicates after crash/resume
        existing = self.db.scalar(
            "SELECT COUNT(*) FROM telegram_posts WHERE product_id=? AND topic=? AND status='sent'",
            (product_id, Topic.PENDING.value),
        )
        if existing:
            self._mark_published(product_id)
            return True, "already sent"

        post = self.db.query(
            "SELECT * FROM telegram_posts WHERE product_id=? AND topic=? ORDER BY id DESC LIMIT 1",
            (product_id, Topic.PENDING.value),
        )
        if not post:
            return False, "no draft post found"
        post = post[0]

        thread_id = self.config.thread_pending_posts
        photos = self._photo_paths(product_id)
        video = self._video_path(product_id)

        try:
            message_id = None
            if photos:
                message_id = self._send_photo_group(photos, post["text"], thread_id)
            elif video:
                result = self._post(
                    "sendVideo",
                    files={"video": (video.name, video.read_bytes())},
                    chat_id=self.config.telegram_chat_id,
                    message_thread_id=thread_id,
                    caption=post["text"],
                    parse_mode="HTML",
                )
                message_id = result["message_id"]
            else:
                result = self._post(
                    "sendMessage",
                    chat_id=self.config.telegram_chat_id,
                    message_thread_id=thread_id,
                    text=post["text"],
                    parse_mode="HTML",
                )
                message_id = result["message_id"]

            if photos and video:
                self._post(
                    "sendVideo",
                    files={"video": (video.name, video.read_bytes())},
                    chat_id=self.config.telegram_chat_id,
                    message_thread_id=thread_id,
                )

            self.db.execute(
                "UPDATE telegram_posts SET status=?, message_id=?, thread_id=?, sent_at=datetime('now') WHERE id=?",
                (PostStatus.SENT.value, message_id, thread_id, post["id"]),
            )
            self.db.execute(
                "UPDATE media_files SET telegram_file_id=?, status='uploaded' WHERE product_id=? AND status='optimized'",
                (str(message_id), product_id),
            )
        except Exception as e:
            logger.error("telegram publish failed", extra={"product_id": product_id, "error": str(e)})
            self.db.execute(
                "UPDATE telegram_posts SET status=? WHERE id=?",
                (PostStatus.FAILED.value, post["id"]),
            )
            return False, str(e)

        self._mark_published(product_id)
        self._delete_local(product_id)
        return True, None

    def _send_photo_group(self, photos: list[Path], caption: str, thread_id: int) -> int:
        """Send photos as a media group (Bot API local-file multipart upload).
        sendMediaGroup requires >= 2 media; a single photo uses sendPhoto."""
        if len(photos) == 1:
            result = self._post(
                "sendPhoto",
                chat_id=self.config.telegram_chat_id,
                message_thread_id=thread_id,
                photo=("photo.webp", photos[0].read_bytes()),
                caption=caption,
                parse_mode="HTML",
            )
            return result["message_id"]

        media, files = [], {}
        for i, path in enumerate(photos[:10], start=1):
            attach = f"photo{i}"
            media.append({"type": "photo", "media": f"attach://{attach}"})
            files[attach] = (path.name, path.read_bytes())
        media[0]["caption"] = caption
        media[0]["parse_mode"] = "HTML"
        result = self._post(
            "sendMediaGroup",
            files=files,
            chat_id=self.config.telegram_chat_id,
            message_thread_id=thread_id,
            media=__import__("json").dumps(media),
        )
        return result[0]["message_id"]

    def _photo_paths(self, product_id: int) -> list[Path]:
        rows = self.db.query(
            "SELECT optimized_path FROM media_files WHERE product_id=? "
            "AND kind IN ('featured','gallery','raw') AND status='optimized' AND optimized_path IS NOT NULL "
            "ORDER BY CASE kind WHEN 'featured' THEN 0 WHEN 'gallery' THEN 1 ELSE 2 END, id",
            (product_id,),
        )
        paths = [Path(r["optimized_path"]) for r in rows if Path(r["optimized_path"]).exists()]
        # de-dup by source file (raw content may duplicate gallery)
        seen, uniq = set(), []
        for p in paths:
            key = p.stem
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        return uniq

    def _video_path(self, product_id: int) -> Path | None:
        row = self.db.query(
            "SELECT optimized_path FROM media_files WHERE product_id=? AND kind='video' "
            "AND status='optimized' AND optimized_path IS NOT NULL LIMIT 1",
            (product_id,),
        )
        if not row:
            return None
        p = Path(row[0]["optimized_path"])
        return p if p.exists() else None

    def _mark_published(self, product_id: int) -> None:
        self.db.execute(
            "UPDATE products SET state=?, updated_at=datetime('now') WHERE id=?",
            (ProductState.PUBLISHED.value, product_id),
        )
        self.db.execute(
            "UPDATE processing_state SET state=?, stage=?, updated_at=datetime('now') WHERE product_id=?",
            (ProductState.PUBLISHED.value, "done", product_id),
        )

    def _delete_local(self, product_id: int) -> None:
        rows = self.db.query(
            "SELECT local_path, optimized_path FROM media_files WHERE product_id=?", (product_id,)
        )
        for r in rows:
            for key in ("local_path", "optimized_path"):
                val = r[key]
                if val:
                    try:
                        Path(val).unlink(missing_ok=True)
                    except OSError:
                        pass
        self.db.execute(
            "UPDATE media_files SET status='deleted' WHERE product_id=? AND status IN ('uploaded','optimized')",
            (product_id,),
        )