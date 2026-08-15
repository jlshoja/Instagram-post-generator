import json
import logging

from .db import Database
from .models import ProductState, Topic

logger = logging.getLogger("bazarkif.post_generator")

HASHTAGS = "#لوکس_باز #کیف_زنانه #کیف_مردانه #خرید_کیف #کیف_جدید"

# Fixed store info (deterministic, no AI)
BRAND_LABEL = "لوکس‌باز"
ORDER_SITE = "LUXBAZ.COM"
INSTAGRAM = "دایرکت اینستاگرام"
WHATSAPP = "واتساپ"
DELIVERY = "ارسال به سراسر کشور"

PREFERRED_ATTR_ORDER = ["جنس", "ابعاد", "کد محصول", "رنگ", "رنگ‌بندی"]
COLOR_KEYS = {"رنگ", "رنگ‌بندی", "رنگ بندی", "color", "رنگ‌ها"}


def format_price_toman(price: int) -> str:
    return f"{price:,}"


class PostGenerator:
    def __init__(self, config, db: Database):
        self.config = config
        self.db = db

    def generate(self, product_id: int) -> tuple[bool, str | None]:
        row = self.db.query("SELECT * FROM products WHERE id=?", (product_id,))
        if not row:
            return False, "product not found"
        p = row[0]
        attrs = json.loads(p["attributes"] or "{}")
        text = self._render(p["name"], p["code"], p["price"], attrs)

        self.db.execute(
            "INSERT INTO telegram_posts (product_id, text, topic, chat_id, status) "
            "VALUES (?,?,?,?,?)",
            (product_id, text, Topic.PENDING.value, self.config.telegram_chat_id, "draft"),
        )
        self.db.execute(
            "UPDATE products SET state=?, updated_at=datetime('now') WHERE id=?",
            (ProductState.POST_GENERATED.value, product_id),
        )
        self.db.execute(
            "UPDATE processing_state SET state=?, stage=?, updated_at=datetime('now') WHERE product_id=?",
            (ProductState.POST_GENERATED.value, "publish", product_id),
        )
        return True, text

    def _render(self, name, code, price, attrs: dict) -> str:
        main_feature = self._main_feature(attrs)
        code_line = f"▫️ کد محصول: {code}\n\n" if code else ""
        specs_lines = self._spec_lines(attrs, code)
        if specs_lines:
            specs_block = "\n".join(f"▫️ {line}" for line in specs_lines) + "\n\n"
        else:
            specs_block = ""

        price_line = f"💰 **قیمت: {format_price_toman(price)} تومان**\n\n" if price else ""

        parts = [
            f"👜 **{name}**\n",
            f"اگر دنبال یک {main_feature} هستی، این مدل می‌تواند انتخاب جذابی برات باشه ✨\n",
            "**مشخصات محصول:**\n",
        ]
        if code_line:
            parts.append(code_line)
        if specs_block:
            parts.append(specs_block)
        parts.append(price_line)
        parts.append(
            f"🛍 **ثبت سفارش از ۳ طریق:**\n"
            f"1️⃣ سایت: **{ORDER_SITE}**\n"
            f"2️⃣ {INSTAGRAM}\n"
            f"3️⃣ {WHATSAPP}\n\n"
            f"🔗 لینک سایت و واتساپ در بیو\n\n"
            f"📦 {DELIVERY}\n\n"
            f"{HASHTAGS}"
        )
        return "".join(parts)

    def _main_feature(self, attrs: dict) -> str:
        # a deterministic "main feature" phrase; fall back to generic
        for key in ("جنس", "نوع", "کاربرد"):
            val = attrs.get(key)
            if val:
                return f"کیف {val}".replace(",", "،")
        return "کیف شیک و باکیفیت"

    def _spec_lines(self, attrs: dict, code) -> list[str]:
        lines = []
        ordered_keys = [k for k in PREFERRED_ATTR_ORDER if k in attrs]
        for key in ordered_keys:
            if key == "کد محصول" or key in COLOR_KEYS:
                continue
            lines.append(f"{key}: {attrs[key]}")
        shown = set(ordered_keys) | COLOR_KEYS
        for key, val in attrs.items():
            if key in shown or key == "کد محصول" or key in COLOR_KEYS:
                continue
            lines.append(f"{key}: {val}")
            if len(lines) >= 4:
                break
        return lines