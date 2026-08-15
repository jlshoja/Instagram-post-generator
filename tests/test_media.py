import io

from PIL import Image

from bazarkif.http_client import HttpClient
from bazarkif.media_downloader import MediaDownloader
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


def test_download_images(config, db, product_id, monkeypatch):
    seed_media(db, product_id)
    http = HttpClient(config)
    monkeypatch.setattr(http, "get", lambda url, **kw: _fake_http(url))

    dl = MediaDownloader(config, db, http)
    ok, err = dl.download_product(product_id)
    assert ok
    rows = db.query("SELECT * FROM media_files WHERE product_id=?", (product_id,))
    assert all(r["status"] == "downloaded" for r in rows)
    assert all(r["local_path"] for r in rows)


def test_missing_source_image_fails(config, db, product_id, monkeypatch):
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
    ok, err = dl.download_product(product_id)
    assert not ok
    assert "no images downloaded" in err


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


def test_transient_fetch_error_retried(config, db, product_id, monkeypatch):
    seed_media(db, product_id)
    calls = []

    def _flaky(url, **kw):
        calls.append(url)
        if len(calls) < 3:
            raise Exception("transient boom")
        class R:
            status_code = 200
            content = _png_bytes()
            headers = {"content-type": "image/png"}
        return R()

    http = HttpClient(config)
    monkeypatch.setattr(http, "get", _flaky)
    ok, _err = MediaDownloader(config, db, http).download_product(product_id)
    assert ok
    assert len(calls) >= 3  # the first file was retried before succeeding


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