# 10. User Guide — Windows

Practical guide for running the Product Scraper & Telegram Publishing System on
Windows. Setup is handled by `run.bat`; no manual environment configuration is
required.

---

## What this system does

- Discovers **in-stock** products on `https://bazarkif.org/shop/`
  (the shop page is filtered with `?stock_status=instock`).
- Downloads product details (name, code, price, specs), media (featured,
  gallery, raw-content images, video) and builds a Persian product card.
- Applies your **pricing rules** (`data/mapping/pricing_sample.csv`): the
  published price is `base × (1 + increase%)`, rounded down to the nearest
  thousand, with a crossed-out original + discount badge when the rules include
  a discount.
- Publishes each card to the **اطلاعات محصول** topic of your Telegram group.
- Retries failures automatically and can be re-run safely (resumable).

---

## Prerequisites

1. **Git** — for cloning the project.
2. **Python 3.12+** — installed and on your PATH (the installer default adds
   `py`/`python`). Verify with:
   ```bat
   py -3.12 --version
   ```
3. A **Telegram bot token** and the group/thread ids (see [Telegram setup](#telegram-setup)).

Everything else (virtual environment, dependencies) is installed automatically
by `run.bat`.

---

## First-time run (Windows)

### 1. Get the project

The repository is **public**, so use HTTPS — no SSH key is needed:

```bat
git clone https://github.com/jlshoja/Instagram-post-generator.git
cd Instagram-post-generator
```

> The repo ships with the pricing rules (`data/mapping/pricing_sample.csv`),
> so pricing works out of the box on a fresh clone.

### 2. Configure Telegram

The first time you run `run.bat`, it creates `.env` from `config.example.env`
and stops with instructions. Open `.env` and set at least:

```env
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
TELEGRAM_CHAT_ID=-1001234567890
TELEGRAM_THREAD_PENDING=6
```

> `.env` is never committed to git. The app reads it automatically — on Windows
> there is **no `source .env` step** needed.

### 3. Do the full first download

```bat
run.bat fresh
```

This one command:

1. Creates the virtual environment + installs dependencies (first time only).
2. Validates the Telegram configuration.
3. Resets the local database and temp media.
4. Discovers all ~326 in-stock products, downloads details + media,
   applies pricing, and publishes every card to the topic.

It takes a few minutes for the full catalog. Progress is written to
`logs\app.log`.

### 4. Confirm the cards arrived

Open the **اطلاعات محصول** topic in Telegram. Each card shows the product name,
code, key specs, the priced amount, and order instructions. Prices should end in
`000` and match your pricing rules.

---

## Day-to-day usage

Open a terminal in the project folder and run:

| Command | What it does |
|---|---|
| `run.bat` | Full update: scan + build + publish everything new/changed |
| `run.bat fresh` | Reset DB + media, then full update (use for a clean re-download) |
| `run.bat dry` | Scan + build cards only — **does not** send to Telegram |
| `run.bat retry` | **Force-retry all failed items now**, then update |
| `run.bat resume` | Requeue pending / due failed jobs, then update |
| `run.bat publish` | Send already-drafted cards to Telegram (no scan) |
| `run.bat sample [N]` | Test mode: process only `N` products (default 3) |
| `run.bat until detail` | Partial run — stop after a stage |
| `run.bat until media` | `detail \| media \| optimize \| post` |
| `run.bat until publish` | Partial run **through** publish (sends cards) |
| `run.bat daemon` | Run the daily scheduler (once/day, `SCAN_INTERVAL_MINUTES`) |

Examples:

```bat
run.bat          rem normal daily update + publish
run.bat retry    rem retry everything that failed
run.bat sample 5 rem quick sanity test with 5 products
```

---

## Retrying failed items

Failures are stored in the database (`failed_jobs`) and retried automatically
with backoff up to `MAX_ATTEMPTS` (default 5).

- **Due retries only:** `run.bat resume`
- **Force everything now:** `run.bat retry`

Both run a full scan afterwards, so successfully retried items continue through
the pipeline to publishing.

---

## Where things live

| Path | Purpose |
|---|---|
| `data\bazarkif.db` | SQLite state (products, media, posts, failures) |
| `data\mapping\pricing_sample.csv` | Pricing rules (**tracked in git**) |
| `.media\` | Temp media — deleted after upload by design |
| `logs\app.log` | Daily-rotated JSON log (keeps 14 backups) |
| `.env` | Secrets/configuration (never committed) |
| `venv\` | Local Python environment |

---

## Configuration (`.env`)

Key settings — see `config.example.env` for the full list:

| Var | Default | Purpose |
|---|---|---|
| `SAMPLE_LIMIT` | *(unset = all)* | `>0`: process only N products (test mode) |
| `SCAN_INTERVAL_MINUTES` | `1440` | daemon frequency (once/day) |
| `WORKERS` / `CONCURRENCY_DOWNLOAD` | `4` | parallelism |
| `REQUEST_DELAY` | `0.5` | politeness delay (seconds) |
| `PRICING_FILE` | `data/mapping/pricing_sample.csv` | path to pricing rules |
| `PRICING_ENABLED` | `1` | `0` = publish base prices unchanged |
| `WEBP_TARGET_BYTES` | `128000` | image size target (≈125 KB) |

---

## Troubleshooting

**Cards are not published.**
Open `.env` and confirm `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are filled,
and `TELEGRAM_THREAD_PENDING` is the correct topic thread id. `run.bat` validates
these before starting.

**Prices look wrong (no margin applied).**
Make sure `data\mapping\pricing_sample.csv` exists (it ships with the repo) and
`PRICING_ENABLED=1`. If the file is missing the app logs a warning and publishes
base prices.

**Some products failed.**
Run `run.bat retry`. If they still fail after `MAX_ATTEMPTS`, check
`logs\app.log` for the specific error.

**Want to wipe everything and start over?**
`run.bat fresh` resets the database + media. The pricing file is preserved.

**The scheduler daemon stays in the foreground.**
`run.bat daemon` is meant to run continuously (e.g. under Task Scheduler on
login). Stop it with `Ctrl+C`. For a one-shot update use `run.bat` instead.

---

## Telegram setup (once)

1. Create a supergroup and enable **Topics** in group settings.
2. Add your bot as admin.
3. Create a topic named **اطلاعات محصول**.
4. Get the group `chat_id` and the topic's `message_thread_id` from
   `@BotFather` / the Bot API `getUpdates` after posting a message there.
5. Put them in `.env` as `TELEGRAM_CHAT_ID` and `TELEGRAM_THREAD_PENDING`.
