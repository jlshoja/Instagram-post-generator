# 9. Runbook

## Prerequisites

- Python 3.12+
- `pip install -r requirements.txt`
- Copy `config.example.env` to `.env` and fill in Telegram values to publish.

## Commands

```bash
# one scan, build posts but do NOT send to Telegram (dry-run)
python -m bazarkif.cli run-once

# test mode: process only N products (e.g. 3) end-to-end
SAMPLE_LIMIT=3 python -m bazarkif.cli run-once

# one scan and publish to Pending Posts topic
python -m bazarkif.cli --publish run-once

# partial / resumable run: stop after a given stage
python -m bazarkif.cli --until detail run-once   # discovery + detail only
python -m bazarkif.cli --until media run-once    # + media download
python -m bazarkif.cli --until optimize run-once # + WebP optimize
python -m bazarkif.cli --until post run-once     # + card generation

# requeue pending/failed jobs, then run one scan
python -m bazarkif.cli resume

# scheduler daemon (default: one scan per day; set SCAN_INTERVAL_MINUTES)
python -m bazarkif.cli daemon
```

## Config knobs (env vars, no code change)

| Var | Default | Purpose |
|---|---|---|
| `SCAN_INTERVAL_MINUTES` | `1440` | schedule frequency (60, 180, 360, …) |
| `ENABLE_SCHEDULER` | `1` | disable daemon scheduling |
| `WORKERS` / `CONCURRENCY_DOWNLOAD` | `4` | parallelism |
| `REQUEST_DELAY` | `0.5` | politeness delay between requests |
| `MAX_ATTEMPTS` | `5` | retry cap per stage |
| `WEBP_TARGET_BYTES` | `128000` | ≈125 KB target |
| `IMAGE_MAX_DIMENSION` | `1080` | resize cap before WebP |

## Moving from VPS to Windows

1. Transfer the project (via git, or `rsync -avz --exclude venv --exclude data --exclude .media --exclude logs ./ user@win:path/`).
   `data/`, `.media/`, `logs/`, `venv/`, `.env` are git-ignored on purpose.
2. On Windows: `py -3.12 -m venv venv && venv\Scripts\pip install -r requirements.txt`.
3. **Full first run downloads everything:** delete `data/` (fresh SQLite) and run
   `venv\Scripts\python -m bazarkif.cli --publish run-once`. All ~326 products are
   downloaded, optimized, and sent to the Pending Posts topic.
4. For a quick sanity test first: `SAMPLE_LIMIT=3 ... run-once`.

## Deployment (Phase 3 — Ubuntu VPS + Docker)

```bash
docker compose build
docker compose up -d
docker compose logs -f bazarkif
```

- SQLite is on the named `bazarkif_data` volume (survives restarts).
- Media lives on the ephemeral `bazarkif_media` volume (temp-only by design).

## Observability

- Structured JSON logs: `logs/app.log`, rotated daily, 14 backups kept.
- Levels: INFO / WARNING / ERROR / CRITICAL.
- Console output mirrors file logging.

## Telegram Topic Setup (once)

1. Create a supergroup, enable **Topics** in settings.
2. Add the bot as admin.
3. Create 4 topics: Pending Posts, Published Posts, Changes, Failed Jobs.
4. Get the group `chat_id` and each topic's `message_thread_id`
   (via `getUpdates` after sending a message into each topic).
5. Fill `TELEGRAM_CHAT_ID` and the four `TELEGRAM_THREAD_*` vars in `.env`.