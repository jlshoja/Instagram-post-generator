import json

from bazarkif.post_generator import PostGenerator, format_price_toman
from conftest import IMG_1, IMG_2, build_product_html


def _seed_detailed_product(db, product_id, attrs=None):
    db.execute(
        "UPDATE products SET name=?, code=?, price=?, attributes=?, state=? WHERE id=?",
        (
            "کوله پشتی",
            "9388",
            2414000,
            json.dumps(attrs or {"ابعاد": "45 × 30 × 10 سانتیمتر", "جنس رویه": "چرم"}, ensure_ascii=False),
            "MEDIA_OPTIMIZED",
            product_id,
        ),
    )


def test_format_price():
    assert format_price_toman(2414000) == "2,414,000"


def test_render_template(config, db, product_id):
    _seed_detailed_product(db, product_id)
    gen = PostGenerator(config, db)
    ok, text = gen.generate(product_id)
    assert ok
    assert "👜 کوله پشتی" in text
    assert "💫مشخصات:" in text
    assert "کد محصول: 9388" in text
    assert "جنس رویه: چرم" in text
    assert "ابعاد: 45 × 30 × 10 سانتیمتر" in text
    assert "قیمت: 2,414,000 تومان" in text
    assert "LUXBAZ.COM" in text
    assert "واتساپ" in text
    assert "ارسال به سراسر کشور" in text
    assert "#لوکس_باز #کیف_زنانه #کیف_مردانه #خرید_کیف #کیف_جدید" in text
    assert len(text) < 1024  # telegram caption limit


def test_no_color_in_card(config, db, product_id):
    # attributes contain color, but card must not include it
    _seed_detailed_product(
        db, product_id,
        attrs={"ابعاد": "x", "جنس رویه": "چرم", "رنگ": "مشکی"},
    )
    gen = PostGenerator(config, db)
    ok, text = gen.generate(product_id)
    assert ok
    assert "مشکی" not in text
    assert "رنگ" not in text


def test_only_outer_fabric_shown(config, db, product_id):
    # among جنس attributes only جنس رویه may appear; جنس آستر and other
    # جنس variants must be omitted even when present
    _seed_detailed_product(
        db, product_id,
        attrs={"ابعاد": "x", "جنس رویه": "چرم", "جنس آستر": "پلی‌استر", "جنس": "چرم", "جنس زاپدار": "پوست"},
    )
    gen = PostGenerator(config, db)
    ok, text = gen.generate(product_id)
    assert ok
    assert "جنس رویه: چرم" in text
    assert "آستر" not in text
    assert "زاپدار" not in text
    assert text.count("جنس") == 1


def test_no_outer_fabric_no_fabric_line(config, db, product_id):
    # without جنس رویه no other جنس line is written
    _seed_detailed_product(
        db, product_id,
        attrs={"ابعاد": "x", "جنس آستر": "پلی‌استر"},
    )
    gen = PostGenerator(config, db)
    ok, text = gen.generate(product_id)
    assert ok
    assert "آستر" not in text
    assert "جنس" not in text


def test_draft_post_created(config, db, product_id):
    _seed_detailed_product(db, product_id)
    gen = PostGenerator(config, db)
    gen.generate(product_id)
    posts = db.query("SELECT * FROM telegram_posts WHERE product_id=?", (product_id,))
    assert len(posts) == 1
    assert posts[0]["topic"] == "pending_posts"
    assert posts[0]["status"] == "draft"