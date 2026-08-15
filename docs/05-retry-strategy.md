# 5. Retry Strategy

Every stage supports automatic retry, exponential backoff, and resume after a
crash. No stage is considered complete unless fully successful.

## 5.1 RetryPolicy

A single shared policy object, configurable via environment, applied uniformly
across stages (per-stage overrides allowed):

| Parameter | Default | Notes |
|---|---|---|
| `max_attempts` | 5 | hard cap per stage per product |
| `base_delay` | 2 s | first backoff delay |
| `max_delay` | 300 s | cap on backoff |
| `factor` | 2.0 | exponential multiplier |
| `jitter` | 0.25 | ±25% random jitter to avoid thundering herd |
| `retry_on_http` | {429, 500, 502, 503, 504} | HTTP statuses that trigger retry |
| `timeout` | 30 s | per-request timeout |

Backoff formula:

```
delay = min(max_delay, base_delay * factor**(attempt-1)) * uniform(1-jitter, 1+jitter)
```

## 5.2 Failure Classification

| Class | Behavior |
|---|---|
| **Transient** (network error, 429/5xx, timeout, empty response) | Retry with backoff. |
| **Permanent** (HTTP 404 product gone, 4xx auth, malformed/unparseable page, missing required field) | Do not retry past a small bound; record in `failed_jobs`; alert to Failed Jobs topic. |
| **Recoverable-by-state** (crash mid-stage) | Idempotent re-run of the stage on resume. |

## 5.3 Stage-Specific Notes

- **Discovery**: transient on category page fetch; permanent if category 404s
  (skip and log). Dedup by URL regardless of retries.
- **Detail**: permanent if product page 404 (mark inactive + availability
  change). Retry otherwise.
- **Media Download**: per-file retry; missing individual file does not fail the
  whole product (collect partial, log warning) — but **product not PUBLISHED**
  until required media present. Configurable `require_gallery` (default true).
- **Media Optimize**: retry on PIL decode errors (re-download source); permanent
  on corrupt source beyond `max_attempts`.
- **Post Generate**: deterministic; permanent only on template/data errors.
- **Telegram Publish**: transient on API 429/network; permanent on 400/403
  (wrong chat/thread) → move to Failed Jobs topic, human reviews.

## 5.4 Durable Queue (failed_jobs)

- On final failure, a row is written to `failed_jobs` with `stage`,
  `attempts`, `next_retry_at`.
- A retry worker (runs each scan and on a short loop) selects rows where
  `resolved=0 AND next_retry_at <= now`, re-enqueues into the right stage, and
  re-attempts with backoff.
- After `max_attempts`, the job is surfaced to the **Failed Jobs** Telegram
  topic and left for human review; it never silently disappears.

## 5.5 Crash Resilience

- **Source of truth is the DB.** Every state transition is committed in the same
  transaction as its effect.
- On startup, `scanner.resume()` reads `products.state` and re-feeds each
  product into the correct queue. Idempotent stage functions make re-runs safe:
  - Detail re-parses HTML (no side effect).
  - Media skips files already `optimized` for this product+kind.
  - Publish checks for an existing `telegram_posts` `message_id` before sending
    again.
- `attempts` counter persists across restarts so backoff never resets the clock.

## 5.6 Guarantees

- A product stuck in `FAILED` does not block any other product or stage.
- At-least-once semantics for each stage effect; idempotency makes the "at-least"
  collapse to "exactly-once" for publish (via `message_id` guard).