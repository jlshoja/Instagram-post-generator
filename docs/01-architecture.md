# 1. Architecture Document

## 1.1 System Overview

Product Scraper & Telegram Publishing System extracts available products from a
WooCommerce store, collects details and media, builds a fixed Persian product
card, and publishes it to Telegram Topics for human review.

```
                    ┌──────────────┐
                    │  Scheduler   │  APScheduler, interval configurable (default: daily)
                    └──────┬───────┘
                           │ run_scan() per interval
                    ┌──────▼───────┐
                    │   Discovery  │  category pages + ?stock_status=instock
                    └──────┬───────┘
                    ┌──────▼───────┐
                    │    Detail    │  per-product HTML extraction
                    └──────┬───────┘
                    ┌──────▼───────┐
                    │    Media     │  download gallery/raw/video
                    │  Downloader  │
                    └──────┬───────┘
                    ┌──────▼───────┐
                    │    Media     │  WebP ≈125KB / video temp
                    │  Optimizer   │
                    └──────┬───────┘
                    ┌──────▼───────┐
                    │    Post      │  deterministic Persian template
                    │  Generator   │
                    └──────┬───────┘
                    ┌──────▼───────┐
                    │   Telegram   │  → Pending Posts topic (human review)
                    │  Publisher   │  → Changes topic (price/availability)
                    └──────────────┘
```

Each stage is an independent Python module with its own queue, its own retry
policy, and its own persistence. A failure in one stage never blocks another.

## 1.2 Module Responsibilities

| Module | Responsibility | Persistence |
|---|---|---|
| `scheduler` | Trigger scans on a configurable interval (default daily). No code change to change frequency. | `scans` |
| `discovery` | Enumerate product categories, walk pagination with `?stock_status=instock`, collect product URLs. Deduplicate by URL. | `products`, `scans` |
| `detail` | Fetch each product page, extract title, code (from title), price, attributes, description, raw-content images, gallery, video URL. | `products` |
| `media_downloader` | Download featured/gallery/raw images + video to temp storage. | `media_files` |
| `media_optimizer` | Convert images to WebP ≈125 KB; verify video integrity; tag temp files. | `media_files`, `processing_state` |
| `post_generator` | Render deterministic Persian card with fixed template + hashtags. | `telegram_posts` (draft), `processing_state` |
| `telegram_publisher` | Send to Pending Posts topic; store `message_id`; emit change notifications. | `telegram_posts`, `change_log` |
| `cleanup` | Delete local media after successful Telegram upload. | `media_files` |

## 1.3 Cross-Platform Design

- Pure Python 3.12+, `sqlite3` (stdlib), `requests`, `APScheduler`, `Pillow`,
  `python-telegram-bot` (or raw `requests` to Bot API — see §6).
- Paths via `pathlib`; temp dirs under a configurable `media_root` (Phase 2 uses
  local disk, Phase 3 uses ephemeral Docker volumes).
- No OS-specific calls; no shelling out.

## 1.4 Site Facts (bazarkif.org) — Verified 2026-08-15

| Fact | Value |
|---|---|
| WooCommerce REST API | `/wp-json/wc/v3/products` → **401** (no public key). Not usable. |
| Discovery source | Category pages `/product-category/<slug>/`, pagination `/page/N/`. |
| Availability filter | `?stock_status=instock` (موجود در انبار). `onsale` also exists. |
| Theme | WoodMart + Elementor + custom `bazarkif-wordpress-plugin`. |
| Product title | `<title>کیف پاسپورتی – کد 4753 – بازار کیف</title>` |
| Product code | NOT in `data-product_sku` (empty). Extracted from title regex `کد (\d+)`. |
| Price | `<p class="price"><span class="woocommerce-Price-amount"><bdi>2,414,000 … تومان</bdi></span></p>` |
| Attributes | "توضیحات تکمیلی" tab → `<th>/<td>` pairs (ابعاد، تعداد جیب بیرونی، …). |
| Gallery | `data-large_image="<full-res-url>"` attributes on the gallery element. |
| Raw Content | Elementor section headed `محتوای خام (برای تبلیغات)`; contains full-res `photo_*.jpg` + one `.mp4`. |
| Video | Single `.mp4` on ArvanStorage S3, referenced in raw content section. |
| Media host | `https://bazarkif-wordpress-3.s3.ir-thr-at1.arvanstorage.ir/…` |
| Related products | Bottom of page lists other products — **must be excluded** by scoping extraction to the Raw Content section. |

## 1.5 Why No Playwright

A fast API-based path was not available (WooCommerce REST requires keys). However
the site is server-rendered WooCommerce HTML with deterministic markup and a
simple `stock_status` query filter, so plain `requests` + BeautifulSoup is
sufficient, faster, and far more robust than browser automation. Playwright is a
**fallback only** (documented in `07-storage-strategy.md` / runbook) if the site
switches to client-side rendering.

## 1.6 Directory Layout (Phase 2)

```
src/
  bazarkif/            # package
    config.py          # env/config loading (cross-platform, pydantic-style)
    db.py              # sqlite connection, migrations, schema DDL
    logging_conf.py    # structured logging setup
    scheduler.py       # APScheduler entrypoint
    scanner.py         # orchestrates one full scan
    discovery.py
    detail.py
    media_downloader.py
    media_optimizer.py
    post_generator.py
    telegram_publisher.py
    change_detector.py
    retry.py           # RetryPolicy, backoff helpers
    models.py          # dataclasses / enums (states, queues)
  cli.py               # CLI: run once, run daemon, resume
tests/
  unit/ integration/ retry/ change/ telegram/
config.example.env
requirements.txt
```