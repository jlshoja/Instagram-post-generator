import json

from bazarkif.post_generator import PostGenerator
from bazarkif.pricing import PricingTable

SAMPLE = (
    "مقدار_از(تومان),مقدار_تا(تومان),درصد_افزایش,درصد_تخفیف\n"
    ' 0,"600,000",20,0\n'
    '"600,000","800,000",20,20\n'
    '"800,000","10,000,000",15,0\n'
)


def _write_csv(tmp_path, content=SAMPLE) -> str:
    p = tmp_path / "pricing.csv"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_load_ranges(tmp_path):
    t = PricingTable(_write_csv(tmp_path))
    assert [(r.range_from, r.range_to, r.increase_percent, r.discount_percent) for r in t.rules] == [
        (0, 600000, 20, 0),
        (600000, 800000, 20, 20),
        (800000, 10000000, 15, 0),
    ]


def test_rule_lookup_inclusive(tmp_path):
    t = PricingTable(_write_csv(tmp_path))
    assert t.rule_for(0).increase_percent == 20
    assert t.rule_for(600001).discount_percent == 20
    assert t.rule_for(799999).discount_percent == 20
    assert t.rule_for(800001).increase_percent == 15
    assert t.rule_for(9999999).increase_percent == 15


def test_rule_clamps_above_last_range(tmp_path):
    t = PricingTable(_write_csv(tmp_path))
    assert t.rule_for(50_000_000).increase_percent == 15


def test_price_increase_only(tmp_path):
    # user example: base 434000, increase 20 -> 520800, rounded down to 520000
    t = PricingTable(_write_csv(tmp_path))
    offer = t.price(434_000)
    assert offer.price == 520_000
    assert offer.increase_percent == 20
    assert offer.discount_percent == 0
    assert offer.original_price is None


def test_price_rounds_last_three_digits_to_zero(tmp_path):
    t = PricingTable(_write_csv(tmp_path))
    assert t.price(500_100).price == 600_000   # 500100*1.2=600120 -> 600000
    assert t.price(999_000).price == 1_148_000  # 999000*1.15=1148850 -> 1148000
    assert t.price(1_234_567).price == 1_419_000  # *1.15=1419677 -> 1419000


def test_price_with_discount_offer(tmp_path):
    t = PricingTable(_write_csv(tmp_path))
    offer = t.price(700_000)
    assert offer.price == 840_000  # 700k * 1.20
    assert offer.discount_percent == 20
    assert offer.original_price == 1_050_000  # 840k / 0.80


def test_price_none():
    t = PricingTable("/nonexistent/pricing.csv")
    assert t.price(None) is None
    assert t.price(500_000).price == 500_000  # fallback when no file/rules


def test_persian_digits_and_commas(tmp_path):
    content = (
        "مقدار_از(تومان),مقدار_تا(تومان),درصد_افزایش,درصد_تخفیف\n"
        '۰,"۶۰۰,۰۰۰",۲۰,۰\n'
    )
    t = PricingTable(_write_csv(tmp_path, content))
    offer = t.price(100_000)
    assert offer.price == 120_000


def _seed_product(db, product_id, price, attrs=None):
    db.execute(
        "UPDATE products SET name=?, code=?, price=?, attributes=?, state=? WHERE id=?",
        (
            "کوله پشتی",
            "9388",
            price,
            json.dumps(attrs or {"ابعاد": "x", "جنس": "چرم"}, ensure_ascii=False),
            "MEDIA_OPTIMIZED",
            product_id,
        ),
    )


def test_post_generator_applies_increase(config, db, product_id, tmp_path):
    config.pricing_enabled = True
    config.pricing_file = tmp_path / "pricing.csv"
    (tmp_path / "pricing.csv").write_text(SAMPLE, encoding="utf-8")
    _seed_product(db, product_id, 1_000_000)  # range 800k-10M -> +15%
    gen = PostGenerator(config, db)
    ok, text = gen.generate(product_id)
    assert ok
    assert "قیمت: 1,150,000 تومان" in text
    assert "تخفیف" not in text


def test_post_generator_shows_discount_offer(config, db, product_id, tmp_path):
    config.pricing_enabled = True
    config.pricing_file = tmp_path / "pricing.csv"
    (tmp_path / "pricing.csv").write_text(SAMPLE, encoding="utf-8")
    _seed_product(db, product_id, 700_000)  # range 600k-800k -> +20%, 20% تخفیف
    gen = PostGenerator(config, db)
    ok, text = gen.generate(product_id)
    assert ok
    assert "1,050,000 تومان" in text  # crossed original
    assert "قیمت: 840,000 تومان" in text
    assert "20٪ تخفیف" in text
    assert "<s>" in text