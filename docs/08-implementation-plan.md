# 8. Implementation Plan (Phase 2)

Build order maximizes an always-green, testable system. Each milestone ends in
runnable tests.

## M0 — Project Scaffold
- Package `src/bazarkif/`, `pyproject.toml`/`requirements.txt`, `.gitignore`,
  `config.example.env`, logging setup, SQLite bootstrap (runs `04-database-schema.sql`,
  WAL mode). Tests: schema creation, config load.

## M1 — Discovery
- Category enumeration + pagination + `?stock_status=instock`.
- Product upsert by URL, `state=DISCOVERED`; scan bookkeeping.
- Tests: fixture HTML parsing, pagination loop, instock filter, dedup.

## M2 — Detail Extraction
- Selectors table for name/code/price/attributes/description/gallery/raw/video
  (from `01-architecture.md` §1.4). BeautifulSoup extractors.
- Change detection (price) + availability checks.
- Tests: fixture page parse, price diff, missing-required-field handling.

## M3 — Media Downloader
- Concurrent download (featured/gallery/raw/video) to `media_root/download`.
- `media_files` rows; per-file retry; partial-collection policy.
- Tests: mock HTTP, dedup, failure classification.

## M4 — Media Optimizer
- Pillow WebP converter targeting ≈125 KB; video integrity check.
- Tests: size targeting, dimension caps, corrupt-source fallback.

## M5 — Post Generator
- Deterministic Persian template + hashtags (see below); caption-length guard.
- Tests: exact template rendering, no-color rule, length.

## M6 — Telegram Publisher
- Bot API client (media group + video), topic routing, `message_id` persistence,
  publish guard, error mapping, retries.
- Tests: mocked Bot API, 429/400 handling, idempotency.

## M7 — Orchestrator + Scheduler
- `scanner` composing stages; `scheduler` (APScheduler) configurable interval
  (default daily; no code change for hourly/3h/6h).
- `cli.py`: `run-once`, `daemon`, `resume`.
- Tests: end-to-end on fixtures, crash-resume.

## M8 — Retry Queue & Cleanup
- `failed_jobs` worker with backoff; cleanup sweep; Failed-Jobs topic.
- Tests: retry tests, backoff timing, orphan sweep.

## M9 — Change Notifications
- Wire `change_log` → Changes topic (price/unavailable), notify flag.
- Tests: change detection → message shape.

## M10 — Production Readiness Review (Phase 5)
- Concurrency tuning, rate limiting, logging review, migration doc (VPS/Docker).

## Deliverables Per Phase
- **Phase 2:** Implementation Plan (this doc) → approved before M0 code.
- **Phase 3:** incremental development M0–M9.
- **Phase 4:** test suites (unit/integration/retry/change/telegram).
- **Phase 5:** production readiness review.