import logging

from .db import Database
from .models import ChangeType
from .telegram_publisher import TelegramPublisher

logger = logging.getLogger("bazarkif.change_notify")


class ChangeNotifier:
    def __init__(self, config, db: Database, publisher: TelegramPublisher):
        self.config = config
        self.db = db
        self.publisher = publisher

    def notify_pending(self) -> int:
        rows = self.db.query(
            "SELECT cl.*, p.name FROM change_log cl "
            "LEFT JOIN products p ON p.id=cl.product_id "
            "WHERE cl.notified=0"
        )
        sent = 0
        for row in rows:
            if row["change_type"] == ChangeType.PRICE_CHANGED.value:
                text = self._price_text(row["name"], row["old_value"], row["new_value"])
            else:
                text = self._unavailable_text(row["name"])
            mid = self._send(text)
            if mid is not None:
                self.db.execute(
                    "UPDATE change_log SET notified=1, telegram_message_id=? WHERE id=?",
                    (mid, row["id"]),
                )
                sent += 1
        return sent

    def _send(self, text: str) -> int | None:
        if not self.publisher.enabled:
            return None
        try:
            result = self.publisher._post(
                "sendMessage",
                chat_id=self.config.telegram_chat_id,
                message_thread_id=self.config.thread_changes,
                text=text,
            )
            return result["message_id"]
        except Exception as e:
            logger.error("change notification failed", extra={"error": str(e)})
            return None

    @staticmethod
    def _price_text(name, old_price, new_price) -> str:
        return (
            "🔄 Price Changed\n\n"
            f"Product: {name}\n"
            f"Old Price: {old_price}\n"
            f"New Price: {new_price}"
        )

    @staticmethod
    def _unavailable_text(name) -> str:
        return "❌ Product Unavailable\n\n" f"Product: {name}"