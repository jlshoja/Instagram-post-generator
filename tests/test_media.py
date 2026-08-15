import io

from PIL import Image

from bazarkif.http_client import HttpClient
from bazarkif.media_downloader import MediaDownloader
from bazarkif.media_optimizer import MediaOptimizer
from conftest import IMG_1, IMG_2, VIDEO, seed_media


def _png_bytes(width=800, height=800):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 100, 50)).save(buf, "PNG")
    return buf.getvalue()


def _fake_http(url):
    class R:
        status_code = 200
        content = _png_bytes()
        headers = {"content-type": "image/png"}
    return R()


def test_download_then_optimize(config, db, product_id, monkeypatch):
    seed_media(db, product_id)
    http = HttpClient(config)
    monkeypatch.setattr(http, "get", lambda url, **kw: _fake_http(url))

    dl = MediaDownloader(config, db, http)
    ok, err = dl.download_product(product_id)
    assert ok
    rows = db.query("SELECT * FROM media_files WHERE product_id=?", (product_id,))
    assert all(r["status"] == "downloaded" for r in rows)
    assert all(r["local_path"] for r in rows)

    opt = MediaOptimizer(config, db)
    ok, err = opt.optimize_product(product_id)
    assert ok
    imgs = db.query(
        "SELECT * FROM media_files WHERE product_id=? AND kind='gallery'", (product_id,)
    )
    for r in imgs:
        assert r["status"] == "optimized"
        assert r["optimized_path"].endswith(".webp")
        assert r["size_bytes"] <= config.webp_target_bytes * 1.1


def test_webp_target_sizing(config, db, product_id, monkeypatch):
    seed_media(db, product_id)
    http = HttpClient(config)
    monkeypatch.setattr(http, "get", lambda url, **kw: _fake_http(url))
    MediaDownloader(config, db, http).download_product(product_id)
    MediaOptimizer(config, db).optimize_product(product_id)
    # small 800x800 png compresses far below target; ensure quality not floor
    row = db.query(
        "SELECT * FROM media_files WHERE product_id=? AND kind='gallery' LIMIT 1",
        (product_id,),
    )[0]
    assert row["size_bytes"] <= config.webp_target_bytes
    assert row["width"] == 800


def test_missing_source_image_fails(config, db, product_id):
    seed_media(db, product_id)
    opt = MediaOptimizer(config, db)
    ok, err = opt.optimize_product(product_id)
    assert not ok
    assert "no optimized images" in err


def test_non_ascii_url_percent_encoded(config, db, product_id, monkeypatch):
    seed_media(db, product_id)
    persian_url = IMG_1.replace("photo_1.jpg", "لینک-تصاویر-گالری_1.jpg")
    row = db.query(
        "SELECT id FROM media_files WHERE product_id=? AND kind='gallery' LIMIT 1",
        (product_id,),
    )[0]
    db.execute("UPDATE media_files SET source_url=? WHERE id=?", (persian_url, row["id"]))

    seen = []

    def _fake_http(url, **kw):
        seen.append(url)
        class R:
            status_code = 200
            content = _png_bytes()
            headers = {"content-type": "image/png"}
        return R()

    http = HttpClient(config)
    monkeypatch.setattr(http, "get", _fake_http)
    ok, _err = MediaDownloader(config, db, http).download_product(product_id)
    assert ok
    assert seen
    assert "%D9" in seen[0]  # percent-encoded UTF-8 Persian
    assert "ل" not in seen[0]  # no raw non-ascii bytes sent


def test_dead_404_urls_marked_deleted(config, db, product_id, monkeypatch):
    seed_media(db, product_id)

    def _fake_404(url):
        class R:
            status_code = 404
            content = b""
            headers = {"content-type": "text/html"}
        return R()

    http = HttpClient(config)
    monkeypatch.setattr(http, "get", lambda url, **kw: _fake_404(url))

    dl = MediaDownloader(config, db, http)
    ok, _err = dl.download_product(product_id)
    assert not ok
    rows = db.query("SELECT * FROM media_files WHERE product_id=?", (product_id,))
    assert rows and all(r["status"] == "deleted" for r in rows)

    # a later scan must not re-query / retry the dead URLs
    dl.download_product(product_id)
    rows = db.query("SELECT * FROM media_files WHERE product_id=?", (product_id,))
    assert all(r["status"] == "deleted" for r in rows)