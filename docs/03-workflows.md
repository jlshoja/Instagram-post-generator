# 3. Workflow Diagrams

## 3.1 Single Scan (Scheduler → Publish)

```
Scheduler fires (interval)
   │
   ▼
create scans row (RUNNING, started_at)
   │
   ▼ Discovery
   ├─ GET /product-category/<slug>/?stock_status=instock
   ├─ follow /page/N/ until no more pages
   ├─ collect product URLs
   └─ upsert products (url = unique); state=DISCOVERED for new
   │
   ▼ Detail (per product, concurrency N=4)
   ├─ GET /product/<url>/
   ├─ extract name, code(کد \d+), price, attributes, description,
   │  gallery (data-large_image), raw-content images, video .mp4
   ├─ change detection: price vs stored
   └─ state=DETAILS_EXTRACTED (or FAILED→retry)
   │
   ▼ Media Downloader (per product)
   ├─ download featured/gallery/raw images + video → temp
   ├─ rows in media_files (status=downloaded)
   └─ state=MEDIA_DOWNLOADED
   │
   ▼ Media Optimizer
   ├─ images → WebP target ≈125 KB (quality iteration, cap dimensions)
   ├─ video integrity check (size>0, moov atom) → temp only
   └─ state=MEDIA_OPTIMIZED
   │
   ▼ Post Generator
   ├─ render fixed Persian template (deterministic, no AI) + hashtags
   ├─ insert telegram_posts (status=draft, topic=pending_posts)
   └─ state=POST_GENERATED
   │
   ▼ Telegram Publisher
   ├─ sendMediaGroup (photos) + caption; then video message
   ├─ store message_id + thread_id
   └─ state=PUBLISHED
   │
   ▼ Cleanup
   └─ delete local media files (status=deleted)
   │
   ▼ finalize scans (COMPLETED, counts)
```

## 3.2 Availability / Price Change Notification

```
During Detail stage:
  price differs from stored → change_log(price_changed) → Changes topic
During Discovery:
  previously active product no longer in instock listing
    → mark is_active=False → change_log(availability_changed) → Changes topic
```

Change notifications never touch the original Pending-Posts card.

## 3.3 Retry / Resume After Crash

```
Process starts
   ▼
load last scans; load products by state
   ▼
for each product, resume at its recorded state (idempotent stage restart)
   ▼
failed jobs → failed_jobs table with attempt counts
   ▼
retry worker re-enqueues with exponential backoff until max_attempts
```

Because each stage is idempotent (re-running detail re-parses HTML, re-running
media skips already-optimized files), a crash anywhere simply resumes from the
persisted state.

## 3.4 Concurrency Model

- Per-product parallelism at the Detail and Media stages (worker pool, default 4).
- Each stage's worker pool is independent; stage-level gates (a queue full of
  `DISCOVERED` blocks nothing downstream because downstream polls its own input
  states).
- Rate limiting: global polite delay between HTTP requests (default 0.5s) to
  avoid hammering the store.