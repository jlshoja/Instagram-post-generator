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