import sys
from pathlib import Path

import pytest

from bazarkif.config import Config
from bazarkif.db import Database

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

FIXTURES = Path(__file__).resolve().parent / "fixtures"

IMG_1 = "https://bazarkif-wordpress-3.s3.ir-thr-at1.arvanstorage.ir/2026/08/photo_1.jpg"
IMG_2 = "https://bazarkif-wordpress-3.s3.ir-thr-at1.arvanstorage.ir/2026/08/photo_2.jpg"
VIDEO = "https://bazarkif-wordpress-3.s3.ir-thr-at1.arvanstorage.ir/2026/08/IMG_100.mp4"
RELATED = "https://bazarkif-wordpress-3.s3.ir-thr-at1.arvanstorage.ir/2026/05/9320.jpg"


def build_product_html(
    title="کوله پشتی – کد 9388 – بازار کیف",
    price="2,414,000",
    gallery=(IMG_1, IMG_2),
    attrs=(("ابعاد", "45 × 30 × 10 سانتیمتر"), ("جنس", "چرم")),
    raw_imgs=(IMG_1,),
    video=VIDEO,
    include_raw=True,
) -> str:
    gal = "".join(
        f'<a href="#"><img data-large_image="{u}" src="{u}"></a>' for u in gallery
    )
    attr_rows = "".join(
        f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in attrs
    )
    raw = ""
    if include_raw:
        raw_imgs_html = "".join(f'<img src="{u}">' for u in raw_imgs)
        vid = f'<video src="{video}"></video>' if video else ""
        raw = (
            f'<h2><strong>محتوای خام (برای تبلیغات)</strong></h2>'
            f'<section>{raw_imgs_html}{vid}</section>'
        )
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="fa-IR">
<head><title>{title}</title></head>
<body>
<div class="product"><p class="price"><span class="woocommerce-Price-amount"><bdi>{price}&nbsp;<span class="woocommerce-Price-currencySymbol">تومان</span></bdi></span></p></div>
<div class="woocommerce-product-gallery">{gal}</div>
<div class="woocommerce-tabs">
  <div id="tab-description"><p>توضیح محصول نمونه</p></div>
  <div id="tab-additional_information"><table>{attr_rows}</table></div>
</div>
{raw}
<section class="related"><a href="/product/9320/"><img src="{RELATED}"></a></section>
</body></html>"""


@pytest.fixture
def config(tmp_path) -> Config:
    c = Config()
    c.db_path = tmp_path / "test.db"
    c.media_root = tmp_path / ".media"
    c.log_dir = tmp_path / "logs"
    c.request_delay = 0.0
    c.enable_scheduler = False
    c.telegram_bot_token = "testtoken"
    c.telegram_chat_id = "-100123"
    c.thread_pending_posts = 11
    c.thread_changes = 12
    c.thread_failed_jobs = 13
    return c


@pytest.fixture
def db(config) -> Database:
    return Database(config.db_path)


@pytest.fixture
def product_id(db) -> int:
    db.execute(
        "INSERT INTO products (url, name, price, state, is_active) VALUES (?,?,?,?,?)",
        ("https://bazarkif.org/product/9388/", "کوله پشتی", 2414000, "DISCOVERED", 1),
    )
    return db.scalar("SELECT id FROM products WHERE url=?", ("https://bazarkif.org/product/9388/",))


def seed_media(db, product_id):
    db.execute(
        "INSERT INTO media_files (product_id, kind, source_url, status) VALUES (?,?,?,?)",
        (product_id, "gallery", IMG_1, "pending"),
    )
    db.execute(
        "INSERT INTO media_files (product_id, kind, source_url, status) VALUES (?,?,?,?)",
        (product_id, "gallery", IMG_2, "pending"),
    )
    db.execute(
        "INSERT INTO media_files (product_id, kind, source_url, status) VALUES (?,?,?,?)",
        (product_id, "video", VIDEO, "pending"),
    )