import random
import time
from dataclasses import dataclass

import requests

from .config import Config


class PermanentError(Exception):
    """Non-retryable error (404, auth, unparseable, missing required field)."""


class TransientError(Exception):
    """Retryable error (network, 5xx, timeout, 429)."""


@dataclass
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 2.0
    max_delay: float = 300.0
    factor: float = 2.0
    jitter: float = 0.25
    retry_on_http: tuple = (429, 500, 502, 503, 504)

    @classmethod
    def from_config(cls, config: Config) -> "RetryPolicy":
        return cls(
            max_attempts=config.max_attempts,
            base_delay=config.retry_base_delay,
            max_delay=config.retry_max_delay,
            factor=config.retry_factor,
            jitter=config.retry_jitter,
            retry_on_http=config.retry_on_http,
        )

    def delay_for(self, attempt: int) -> float:
        base = min(self.max_delay, self.base_delay * (self.factor ** (attempt - 1)))
        return base * random.uniform(1 - self.jitter, 1 + self.jitter)


def is_retryable_response(resp: requests.Response) -> bool:
    return resp.status_code in (429, 500, 502, 503, 504)


def with_retry(policy: RetryPolicy, func, logger=None, **logctx):
    """Run `func(attempt)` until success or max_attempts.

    func must raise PermanentError (no retry) or TransientError (retry), or
    return a requests.Response whose status is checked for retryable codes.
    Returns (result, attempts, error).
    """
    last_error = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = func(attempt)
            if isinstance(result, requests.Response):
                if result.status_code in policy.retry_on_http:
                    raise TransientError(f"HTTP {result.status_code}")
                if result.status_code >= 400:
                    raise PermanentError(f"HTTP {result.status_code}")
            return result, attempt, None
        except PermanentError as e:
            return None, attempt, e
        except TransientError as e:
            last_error = e
        except requests.RequestException as e:
            last_error = TransientError(str(e))
        except Exception as e:  # unexpected -> transient
            last_error = TransientError(str(e))

        if attempt < policy.max_attempts:
            delay = policy.delay_for(attempt)
            if logger:
                logger.warning(
                    "retry scheduled",
                    extra={**logctx, "attempt": attempt, "delay": round(delay, 2), "error": str(last_error)},
                )
            time.sleep(delay)
    return None, policy.max_attempts, last_error