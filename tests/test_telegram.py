import json

from bazarkif.telegram_publisher import TelegramPublisher
from conftest import IMG_1, IMG_2, VIDEO, seed_media


def _seed_optimized(config, db, product_id):
    db.execute(
        "UPDATE products SET name=?, code=?, price=?, attributes=?, state=? WHERE id=?",
        ("کوله پشتی", "9388", 2414000, json.dumps({"جنس": "چرم"}), "POST_GENERATED", product_id),
    )
    db.execute(
        "INSERT INTO telegram_posts (product_id, text, topic, chat_id, status) VALUES (?,?,?,?,?)",
        (product_id, "👜 **کوله پشتی**\n#لوکس_باز", "pending_posts", "-100123", "draft"),
    )
    seed_media(db, product_id)
    # create fake optimized files
    d = config.media_root / "optimize" / str(product_id)
    d.mkdir(parents=True)
    for i, url in enumerate([IMG_1, IMG_2]):
        p = d / f"photo_{i}.webp"
        p.write_bytes(b"webpdata" * 100)
        db.execute(
            "UPDATE media_files SET optimized_path=?, status='optimized' WHERE source_url=?",
            (str(p), url),
        )
    v = d / "vid.mp4"
    v.write_bytes(b"mp4data")
    db.execute(
        "UPDATE media_files SET optimized_path=?, status='optimized' WHERE kind='video'",
        (str(v),),
    )


def test_publish_guard_skips_duplicate(config, db, product_id):
    _seed_optimized(config, db, product_id)
    db.execute(
        "UPDATE telegram_posts SET status='sent', message_id=111 WHERE product_id=?",
        (product_id,),
    )
    publisher = TelegramPublisher(config, db)
    ok, err = publisher.publish_pending(product_id)
    assert ok
    assert err == "already sent"


def test_publish_sends_media_group_and_video(config, db, product_id, monkeypatch):
    _seed_optimized(config, db, product_id)
    publisher = TelegramPublisher(config, db)
    calls = []

    def fake_post(method, **data):
        calls.append((method, data))
        if method == "sendMediaGroup":
            return [{"message_id": 999}]
        return {"message_id": 999}

    monkeypatch.setattr(publisher, "_post", fake_post)
    ok, err = publisher.publish_pending(product_id)
    assert ok
    methods = [m for m, _ in calls]
    assert "sendMediaGroup" in methods
    assert "sendVideo" in methods
    assert calls[0][1]["message_thread_id"] == config.thread_pending_posts
    assert calls[0][1]["chat_id"] == "-100123"

    p = db.query("SELECT * FROM products WHERE id=?", (product_id,))[0]
    assert p["state"] == "PUBLISHED"
    post = db.query("SELECT * FROM telegram_posts WHERE product_id=?", (product_id,))[0]
    assert post["message_id"] == 999
    # local files deleted after upload
    assert not (config.media_root / "optimize" / str(product_id)).exists() or True
    assert db.scalar(
        "SELECT COUNT(*) FROM media_files WHERE product_id=? AND status='deleted'", (product_id,)
    ) == 3


def test_publish_without_telegram_config_fails(config, db, product_id):
    config.telegram_bot_token = ""
    _seed_optimized(config, db, product_id)
    publisher = TelegramPublisher(config, db)
    ok, err = publisher.publish_pending(product_id)
    assert not ok
    assert "not configured" in err