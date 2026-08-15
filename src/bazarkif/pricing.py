import csv
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("bazarkif.pricing")

# Persian/Arabic -> ASCII digits
_DIGIT_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

COL_KEYS = {
    "range_from": {"مقدار_از", "مقدار_از(تومان)"},
    "range_to": {"مقدار_تا", "مقدار_تا(تومان)"},
    "increase": {"درصد_افزایش"},
    "discount": {"درصد_تخفیف"},
}


def _to_int(raw: str) -> int | None:
    if raw is None:
        return None
    cleaned = (
        raw.strip()
        .replace(",", "")
        .replace("٬", "")
        .replace("،", "")
        .replace(" ", "")
        .translate(_DIGIT_TRANS)
    )
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


@dataclass
class PricingRule:
    range_from: int
    range_to: int
    increase_percent: int
    discount_percent: int


@dataclass
class PricedOffer:
    base_price: int
    increase_percent: int
    discount_percent: int
    price: int  # real selling price after the benefit increase
    original_price: int | None  # crossed-out list price, present only when discount > 0


class PricingTable:
    """Loads the business pricing rules (data/mapping/pricing_sample.csv) and
    computes the final price to publish for a product.

    real_price = base_price * (1 + increase_percent/100), rounded down
    to the nearest 1000 so the last 3 digits are 0.
    original_price = real_price / (1 - discount_percent/100)  when discount > 0
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.rules: list[PricingRule] = []
        self.load()

    def load(self) -> None:
        self.rules = []
        if not self.path.exists():
            logger.warning("pricing file not found: %s (publishing base prices)", self.path)
            return
        try:
            with open(self.path, encoding="utf-8-sig", newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader, None)
                idx = self._column_indexes(header)
                for row in reader:
                    if not row or not row[0].strip():
                        continue
                    r_from = _to_int(row[idx["range_from"]])
                    if r_from is None:
                        continue
                    r_to = _to_int(row[idx["range_to"]])
                    if r_to is None:
                        r_to = r_from
                    inc = _to_int(row[idx["increase"]]) or 0
                    disc = _to_int(row[idx["discount"]]) or 0
                    self.rules.append(PricingRule(r_from, r_to, inc, disc))
        except (OSError, IndexError, ValueError) as e:
            logger.warning("failed to parse pricing file %s: %s", self.path, e)
            self.rules = []
        self.rules.sort(key=lambda r: r.range_from)
        logger.info("pricing rules loaded: %d ranges", len(self.rules))

    def _column_indexes(self, header: list[str]) -> dict[str, int]:
        by_lower = {}
        if header:
            by_lower = {str(h).strip().lower(): i for i, h in enumerate(header)}
        out: dict[str, int] = {}
        for field, keys in COL_KEYS.items():
            out[field] = next(
                (by_lower[k.lower()] for k in keys if k.lower() in by_lower),
                None,
            )
        # fall back to positional order when headers are unknown/missing
        if any(v is None for v in out.values()):
            order = ["range_from", "range_to", "increase", "discount"]
            for i, field in enumerate(order):
                if out[field] is None:
                    out[field] = i
        return out

    def rule_for(self, price: int) -> PricingRule | None:
        if not self.rules:
            return None
        # inclusive range lookup; prices above the last row use the last rule
        for rule in self.rules:
            if price <= rule.range_to:
                return rule
        return self.rules[-1]

    def price(self, base_price: int | None) -> PricedOffer | None:
        if base_price is None:
            return None
        rule = self.rule_for(base_price)
        if rule is None:
            return PricedOffer(base_price, 0, 0, base_price, None)
        # real = base * (1 + increase/100), rounded down so the last 3 digits are 0
        real = base_price * (100 + rule.increase_percent) // 100
        real = real // 1000 * 1000
        original = None
        if rule.discount_percent > 0:
            original = real * 100 // (100 - rule.discount_percent)
            original = original // 1000 * 1000
        return PricedOffer(base_price, rule.increase_percent, rule.discount_percent, real, original)