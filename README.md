# Product Scraper & Telegram Publishing System

Extracts available products from `https://bazarkif.org/shop/`, collects details
and media, builds a fixed Persian product card, and publishes it to Telegram
Topics for human review. Tracks price/availability changes; resumable and
retryable at every stage.

## Status

- **Phase 1 (Design):** complete — see `docs/`.
- **Phase 2–4 (Implementation & Tests):** complete — 31 unit/integration tests
  passing, live smoke-tested against bazarkif.org (325 products discovered, price
  parsing verified, WebP pipeline ~35–75 KB/images, cards render per template).
- **Phase 5 (Production Readiness):** pending review.

## Quick Start

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp config.example.env .env        # set Telegram values to enable publishing
PYTHONPATH=src ./venv/bin/python -m bazarkif.cli run-once          # dry-run
PYTHONPATH=src ./venv/bin/python -m bazarkif.cli --publish run-once  # to Pending Posts
```

Runbook: `docs/09-runbook.md`. Windows setup & daily use: `docs/10-user-guide.md`.

## Pipeline

```
Scheduler → Discovery → Detail → Media Download → Media Optimize
          → Post Generator → Telegram Publisher (Pending Posts)
```

- **Discovery:** the shop page with `?stock_status=instock&per_page=500`, paginated, dedup by URL.
- **Detail:** title/code (`کد \d+`), price (`<p class="price">`), attributes
  ("توضیحات تکمیلی" tab), gallery (`data-large_image`), Raw Content section
  (`محتوای خام (برای تبلیغات)`) images + video, all scoped to the store's
  ArvanStorage host.
- **Media:** images → WebP ≈125 KB (temp only, deleted after upload); video
  downloaded as-is.
- **Telegram:** Bot API, Forum Topics (Pending Posts / Published Posts /
  Changes / Failed Jobs), `message_id` stored, publish guard prevents duplicates.
- **State machine:** every product persists `DISCOVERED → DETAILS_EXTRACTED →
  MEDIA_DOWNLOADED → MEDIA_OPTIMIZED → POST_GENERATED → PUBLISHED`, crashes resume.

## Tests

```bash
PYTHONPATH=src ./venv/bin/python -m pytest
```

## Architecture

| Doc | Contents |
|---|---|
| `docs/01-architecture.md` | Modules, pipeline, site facts, cross-platform design |
| `docs/02-data-model.md` | States, queues, entities, change detection |
| `docs/03-workflows.md` | Scan / change / retry / concurrency flows |
| `docs/04-database-schema.sql` | SQLite schema |
| `docs/05-retry-strategy.md` | Backoff, failure classes, crash resilience |
| `docs/06-telegram-design.md` | Bot API, topics, message shapes |
| `docs/07-storage-strategy.md` | No-permanent-media policy, temp layout, VPS migration |
| `docs/08-implementation-plan.md` | Phase 2 milestones |
| `docs/09-runbook.md` | Commands, config knobs, Docker deploy |
| `scrape-strategy-prompt.md` | Reusable prompt to evaluate scraping approaches on other stores |

## Development Environment

- **Phase 1:** Windows, Python 3.12+, SQLite (`data/bazarkif.db`).
- **Phase 3:** Ubuntu VPS + Docker Compose (`docker-compose.yml`); SQLite on a
  named volume, media on an ephemeral volume. Cross-platform — no code changes
  needed to migrate.