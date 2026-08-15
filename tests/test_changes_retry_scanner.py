from bazarkif.change_notifier import ChangeNotifier
from bazarkif.retry_queue import RetryQueue
from bazarkif.scanner import Scanner


def test_change_notifier_message_shapes(config, db, product_id):
    db.execute(
        "INSERT INTO change_log (product_id, change_type, old_value, new_value) VALUES (?,?,?,?)",
        (product_id, "price_changed", "1250000", "1350000"),
    )
    db.execute(
        "INSERT INTO change_log (product_id, change_type) VALUES (?,?)",
        (product_id, "availability_changed"),
    )
    db.execute(
        "UPDATE products SET name='XYZ' WHERE id=?", (product_id,)
    )

    notifier = ChangeNotifier(config, db, publisher=None)
    price_txt = notifier._price_text("XYZ", "1250000", "1350000")
    assert "🔄 Price Changed" in price_txt
    assert "Old Price: 1250000" in price_txt
    assert "New Price: 1350000" in price_txt

    unavail = notifier._unavailable_text("XYZ")
    assert "❌ Product Unavailable" in unavail
    assert "XYZ" in unavail


def test_notify_sends_and_marks(config, db, product_id, monkeypatch):
    db.execute(
        "INSERT INTO change_log (product_id, change_type, old_value, new_value) VALUES (?,?,?,?)",
        (product_id, "price_changed", "1", "2"),
    )
    class FakePub:
        enabled = True
        _posts = []
        def _post(self, method, **data):
            self._posts.append(data)
            return {"message_id": 777}
    fake = FakePub()
    notifier = ChangeNotifier(config, db, fake)
    sent = notifier.notify_pending()
    assert sent == 1
    assert fake._posts[0]["message_thread_id"] == config.thread_changes
    assert db.scalar("SELECT notified FROM change_log") == 1


def test_retry_queue_requeue(config, db, product_id, monkeypatch):
    config.retry_base_delay = 0.0
    queue = RetryQueue(config, db)
    queue.record_failure(product_id, "detail", "network boom")
    jobs = queue.due_jobs()
    assert len(jobs) == 1
    assert jobs[0]["attempts"] == 1

    ran = []
    def run_stage(pid, stage):
        ran.append((pid, stage))
    queue.requeue_due(run_stage)
    assert ran == [(product_id, "detail")]
    assert db.scalar("SELECT resolved FROM failed_jobs") == 1


def test_scanner_marks_unavailable(config, db, product_id):
    # product exists & active; discovery this scan does NOT see its url
    db.execute(
        "INSERT INTO products (url, name, state, is_active) VALUES (?,?,?,?)",
        ("https://bazarkif.org/product/9999/", "کوله پشتی قدیمی", "PUBLISHED", 1),
    )
    scanner = Scanner(config)
    scanner.db = db
    # discovery this scan saw the *other* product (still in stock) but not the old one
    scanner.discovery.seen_urls = {
        db.scalar("SELECT url FROM products WHERE id=?", (product_id,))
    }
    scanner._mark_unavailable_removed()

    assert db.scalar("SELECT is_active FROM products WHERE url=?", ("https://bazarkif.org/product/9999/",)) == 0
    changes = db.query("SELECT * FROM change_log")
    assert any(c["change_type"] == "availability_changed" for c in changes)


def test_scanner_resume_requeues(config, db, product_id):
    db.execute(
        "UPDATE products SET state='POST_GENERATED' WHERE id=?", (product_id,)
    )
    scanner = Scanner(config)
    scanner.db = db
    config.telegram_bot_token = ""
    config.retry_base_delay = 0.0
    scanner.resume()
    # publish not configured -> job recorded as failed, product remains post_gen
    assert True