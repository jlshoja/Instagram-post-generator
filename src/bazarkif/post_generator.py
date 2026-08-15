import html
import json
import logging

from .db import Database
from .models import ProductState, Topic
from .pricing import PricedOffer, PricingTable

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
# among "جنس*" attributes only "جنس رویه" is shown in the card
FABRIC_KEYS = {"جنس رویه", "جنس‌رویه"}


def format_price_toman(price: int) -> str:
    return f"{price:,}"


class PostGenerator:
    def __init__(self, config, db: Database):
        self.config = config
        self.db = db
        self._pricing: PricingTable | None = None

    @property
    def pricing(self) -> PricingTable | None:
        if self._pricing is None:
            self._pricing = (
                PricingTable(self.config.pricing_file) if self.config.pricing_enabled else None
            )
        return self._pricing

    def generate(self, product_id: int) -> tuple[bool, str | None]:
        row = self.db.query("SELECT * FROM products WHERE id=?", (product_id,))
        if not row:
            return False, "product not found"
        p = row[0]
        attrs = json.loads(p["attributes"] or "{}")
        offer = self.pricing.price(p["price"]) if self.pricing else None
        if offer is None and p["price"] is not None:
            offer = PricedOffer(p["price"], 0, 0, p["price"], None)
        text = self._render(p["name"], p["code"], attrs, offer)

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

    def _render(self, name, code, attrs: dict, offer: PricedOffer | None) -> str:
        code_line = f"▫️ کد محصول: {code}\n\n" if code else ""
        specs_lines = self._spec_lines(attrs, code)
        if specs_lines:
            specs_block = "\n".join(f"▫️ {line}" for line in specs_lines) + "\n\n"
        else:
            specs_block = ""

        price_line = self._price_line(offer) if offer else ""

        parts = [f"👜 {self._esc(name)}\n\n"]
        if code_line:
            parts.append(code_line)
        if specs_block:
            parts.append("💫مشخصات: \n\n")
            parts.append(specs_block)
        parts.append(price_line)
        parts.append(
            f"🛍 ثبت سفارش از ۳ طریق:\n\n"
            f"1️⃣ سایت: {ORDER_SITE}\n"
            f"2️⃣ {INSTAGRAM}\n"
            f"3️⃣ {WHATSAPP}\n\n"
            f"🔗 لینک سایت و واتساپ در بیو\n\n"
            f"📦 {DELIVERY}\n\n"
            f"{HASHTAGS}"
        )
        return "".join(parts)

    @staticmethod
    def _esc(value) -> str:
        return html.escape(str(value), quote=False)

    @staticmethod
    def _price_line(offer: PricedOffer) -> str:
        price = format_price_toman(offer.price)
        if offer.discount_percent > 0 and offer.original_price is not None:
            original = format_price_toman(offer.original_price)
            return (
                f"💰 <s>{original} تومان</s> 🔥 "
                f"قیمت: {price} تومان "
                f"({offer.discount_percent}٪ تخفیف)\n\n"
            )
        return f"💰 قیمت: {price} تومان\n\n"

    @staticmethod
    def _is_fabric_key(key) -> bool:
        nk = str(key).replace("\u200c", " ").strip()
        return nk.startswith("جنس") and nk not in FABRIC_KEYS

    def _spec_lines(self, attrs: dict, code) -> list[str]:
        lines = []
        excluded = COLOR_KEYS | {k for k in attrs if self._is_fabric_key(k)}
        ordered_keys = [k for k in PREFERRED_ATTR_ORDER if k in attrs]
        for key in ordered_keys:
            if key == "کد محصول" or key in excluded:
                continue
            lines.append(f"{key}: {self._esc(attrs[key])}")
        shown = set(ordered_keys) | excluded
        for key, val in attrs.items():
            if key in shown or key == "کد محصول" or key in excluded:
                continue
            lines.append(f"{key}: {self._esc(val)}")
            if len(lines) >= 4:
                break
        return lines