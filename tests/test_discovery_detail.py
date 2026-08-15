from conftest import IMG_1, build_product_html

from bazarkif.detail import DetailExtractor
from bazarkif.discovery import Discovery, _parse_product_links
from bazarkif.http_client import HttpClient


def _fake_resp(html):
    class R:
        status_code = 200
        text = html
    return R()


def test_discovery_parse_product_links():
    html = '<a href="https://bazarkif.org/product/10115/">a</a>' \
           '<a href="https://bazarkif.org/product-category/foo/">cat</a>'
    links = _parse_product_links(html, "https://bazarkif.org")
    assert "https://bazarkif.org/product/10115/" in links
    assert all("product-category" not in u for u in links)


def test_detail_extract_populates_and_detects_price_change(config, db, product_id, monkeypatch):
    html = build_product_html(
        title="کوله پشتی – کد 9388 – بازار کیف",
        price="3,000,000",
        attrs=(("ابعاد", "45 × 30 × 10 سانتیمتر"), ("جنس", "چرم")),
        raw_imgs=("https://bazarkif-wordpress-3.s3.ir-thr-at1.arvanstorage.ir/2026/08/raw_photo_9.jpg",),
    )
    extractor = DetailExtractor(config, db, HttpClient(config))
    monkeypatch.setattr(
        extractor.http, "get_with_retry",
        lambda url, **kw: (_fake_resp(html), 1, None),
    )

    row = db.query("SELECT * FROM products WHERE id=?", (product_id,))[0]
    ok, err = extractor.extract(row)
    assert ok and err is None

    p = db.query("SELECT * FROM products WHERE id=?", (product_id,))[0]
    assert p["name"] == "کوله پشتی"
    assert p["code"] == "9388"
    assert p["price"] == 3000000
    assert p["state"] == "DETAILS_EXTRACTED"

    media = db.query("SELECT kind, source_url FROM media_files WHERE product_id=?", (product_id,))
    kinds = {m["kind"] for m in media}
    assert "gallery" in kinds and "raw" in kinds and "video" in kinds

    # price changed 2414000 -> 3000000 should create a change_log row
    changes = db.query("SELECT * FROM change_log WHERE product_id=?", (product_id,))
    assert any(c["change_type"] == "price_changed" for c in changes)


def test_detail_extract_dedup_media(config, db, product_id, monkeypatch):
    html = build_product_html(price="2,414,000")
    extractor = DetailExtractor(config, db, HttpClient(config))
    monkeypatch.setattr(
        extractor.http, "get_with_retry",
        lambda url, **kw: (_fake_resp(html), 1, None),
    )
    row = db.query("SELECT * FROM products WHERE id=?", (product_id,))[0]
    extractor.extract(row)
    extractor.extract(row)  # run twice -> no duplicate rows
    count = db.scalar("SELECT COUNT(*) FROM media_files WHERE product_id=?", (product_id,))
    assert count == 3  # img1 (raw+gallery deduped), img2, video