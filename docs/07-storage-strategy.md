# 7. Storage Strategy

## 7.1 Policy: No Permanent Media Storage

Media is **never** stored permanently. The only durable data is metadata, URLs,
and processing history (SQLite).

```
Download  →  Optimize  →  Telegram Upload  →  Delete Local Files
```

- Local files live under a configurable `media_root` (default `<project>/.media/`).
- After a successful Telegram upload, `cleanup` deletes local files and marks
  `media_files.status='deleted'`.
- On crash, a sweep deletes orphan temp files older than a retention window
  (default 24h) at startup.
- Original large images/videos are re-fetchable from `source_url` (ArvanStorage
  S3) if ever re-required — so deleting locals loses nothing.

## 7.2 Temp Directory Layout

```
media_root/
  download/<product_id>/       # raw originals
  optimize/<product_id>/       # WebP / video copies
  orphans.cleanup.log
```

## 7.3 Image Optimization

- Target ≈125 KB WebP, preserve acceptable visual quality.
- Method: decode with Pillow → convert RGB → save WebP; start at quality 82 and
  step quality down (or up) until size ≤ target or a quality floor (default 55)
  is hit; also cap the largest dimension (default 1080px) to control size.
- Output name `<source-stem>.webp`.
- Persist optimized file size/dims in `media_files`.

## 7.4 Video

- Download original `.mp4`; verify integrity (non-zero size, parseable `moov`
  atom) — no transcoding (cross-platform, preserves original).
- Stored only temporarily (temp), uploaded via `sendVideo`, then deleted.

## 7.5 What Is Stored Permanently (SQLite)

| Data | Where |
|---|---|
| Product metadata (name, code, price, attributes, description, URL, state) | `products` |
| Media URLs + temp paths + telegram file ids | `media_files` |
| Rendered card text + `message_id` + `thread_id` + topic | `telegram_posts` |
| Price/availability changes | `change_log` |
| Retry queue | `failed_jobs` |
| Processing state | `processing_state` |

## 7.6 Logs & Secrets

- Structured JSON logs (INFO/WARNING/ERROR/CRITICAL), rotated daily, timestamped
  and searchable under `logs/`.
- Secrets (bot token) live in `.env` / env vars; **never committed**.
- `.gitignore` covers `.env`, `.media/`, `logs/`, `venv/`, `__pycache__/`.

## 7.7 Phase Migration

- Phase 1: local SQLite file + local temp `media_root` (Windows).
- Phase 3 (Ubuntu VPS + Docker Compose):
  - SQLite file mounted on a **named volume** so data survives container restarts.
  - `media_root` as an **ephemeral volume** (cleared per lifecycle) — aligns with
    no-permanent-media policy.
  - Same SQLite schema; `pathlib` config points at the volume mount. No code
    changes required to migrate storage roots (config-driven).