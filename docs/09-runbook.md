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

1. Get the code on Windows (the repo is **public** — HTTPS needs no SSH key):
   ```bat
   git clone https://github.com/jlshoja/Instagram-post-generator.git
   cd Instagram-post-generator
   ```
   `.env`, `venv/`, `logs/`, `.media/` are git-ignored. **`data/mapping/pricing_sample.csv` is tracked**, so a fresh clone already has the pricing rules.
2. Copy the ready `.env` from the VPS (has the real Telegram token), run from the
   project folder:
   ```powershell
   scp root@91.239.211.45:/home/root/projects/Instagram-post-generator/.env .env
   ```
   Or create `.env` by hand from `config.example.env` — the app **auto-loads
   `.env`** (no `source` needed on Windows).
3. First full download. `run.bat` creates the venv, installs deps (retrying via
   the Iranian PyPI mirror automatically if the normal source is blocked), and
   validates Telegram on first use. **Double-click `run.bat`** and pick `fresh`
   from the menu, or from PowerShell:
   ```powershell
   .\run.bat fresh
   ```
   `fresh` resets only the DB/media; the tracked pricing file is preserved.
4. Day-to-day: **double-click `run.bat`** and pick a mode from the menu, or use
   arguments from PowerShell (note the `.\` prefix):
   - `.\run.bat` — interactive menu (update / fresh / dry / resume / retry / publish / sample / until publish / daemon).
   - `.\run.bat retry` — force-retry all failed jobs; `.\run.bat resume` — retry only due ones.
   - `.\run.bat until <stage>` — partial/resumable runs (detail | media | optimize | post).
   - `.\run.bat dry` — build posts without sending; `.\run.bat publish` — send drafts only.
   - `.\run.bat sample [N]` — quick test with N products.

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