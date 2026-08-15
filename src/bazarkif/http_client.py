import time

import requests

from .config import Config
from .retry import PermanentError, RetryPolicy, TransientError, with_retry


class HttpClient:
    def __init__(self, config: Config):
        self.config = config
        self.policy = RetryPolicy.from_config(config)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.user_agent})
        self._last_request = 0.0

    def _throttle(self) -> None:
        wait = self.config.request_delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str, **kw) -> requests.Response:
        self._throttle()
        return self.session.get(
            url, timeout=self.config.request_timeout, allow_redirects=True, **kw
        )

    def get_with_retry(self, url: str, logger=None, **logctx) -> tuple[requests.Response, int, Exception | None]:
        def _fetch(attempt: int):
            resp = self.get(url)
            if resp.status_code == 404:
                raise PermanentError(f"HTTP 404 for {url}")
            if resp.status_code in self.policy.retry_on_http:
                raise TransientError(f"HTTP {resp.status_code}")
            if resp.status_code >= 400:
                raise PermanentError(f"HTTP {resp.status_code}")
            return resp

        return with_retry(self.policy, _fetch, logger=logger, **logctx)