from bazarkif.retry import PermanentError, RetryPolicy, TransientError, with_retry


def test_no_retry_on_success():
    calls = []

    def func(attempt):
        calls.append(attempt)
        return "ok"

    result, attempts, err = with_retry(RetryPolicy(max_attempts=3), func)
    assert result == "ok"
    assert attempts == 1
    assert err is None


def test_retry_on_transient_then_success(monkeypatch):
    calls = []

    def fake_sleep(_):
        calls.append("sleep")

    monkeypatch.setattr("bazarkif.retry.time.sleep", fake_sleep)

    def func(attempt):
        if attempt < 3:
            raise TransientError("boom")
        return "done"

    result, attempts, err = with_retry(RetryPolicy(max_attempts=5, base_delay=1), func)
    assert result == "done"
    assert attempts == 3
    assert "sleep" in calls


def test_permanent_error_no_retry(monkeypatch):
    calls = []

    def fake_sleep(_):
        calls.append("sleep")

    monkeypatch.setattr("bazarkif.retry.time.sleep", fake_sleep)

    def func(attempt):
        raise PermanentError("404")

    result, attempts, err = with_retry(RetryPolicy(max_attempts=5), func)
    assert result is None
    assert attempts == 1
    assert isinstance(err, PermanentError)
    assert "sleep" not in calls


def test_exhausts_attempts():
    def func(attempt):
        raise TransientError("always")

    result, attempts, err = with_retry(RetryPolicy(max_attempts=3, base_delay=0.001), func)
    assert result is None
    assert attempts == 3
    assert isinstance(err, TransientError)


def test_backoff_is_exponential_and_capped():
    p = RetryPolicy(base_delay=1, factor=2, max_delay=4, jitter=0.0)
    d1 = p.delay_for(1)
    d2 = p.delay_for(2)
    d3 = p.delay_for(3)
    d10 = p.delay_for(10)
    assert d1 == 1.0
    assert d2 == 2.0
    assert d3 == 4.0
    assert d10 == 4.0  # capped


def test_retry_on_http_status():
    import requests

    resp = requests.Response()
    resp.status_code = 503
    calls = []

    def func(attempt):
        calls.append(attempt)
        if attempt < 2:
            return resp
        return "ok"

    result, attempts, _ = with_retry(RetryPolicy(max_attempts=3, base_delay=0.001), func)
    assert result == "ok"
    assert attempts == 2