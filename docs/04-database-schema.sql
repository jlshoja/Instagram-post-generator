-- 4. Database Schema (SQLite)
-- Phase 1 targets; SQLite with WAL mode for crash safety.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Products: source of truth, keyed by URL (natural unique identifier)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT    NOT NULL UNIQUE,          -- unique identifier
    name          TEXT,
    code          TEXT,                             -- extracted from title "کد \d+"
    price         INTEGER,                          -- numeric toman (nullable when unavailable)
    description   TEXT,
    attributes    TEXT,                             -- JSON dict {label: value}
    category      TEXT,
    state         TEXT    NOT NULL DEFAULT 'DISCOVERED',
    is_active     INTEGER NOT NULL DEFAULT 1,       -- availability flag
    attempts      INTEGER NOT NULL DEFAULT 0,       -- current-stage attempt count
    last_error    TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_products_state    ON products(state);
CREATE INDEX IF NOT EXISTS idx_products_active   ON products(is_active);

-- ---------------------------------------------------------------------------
-- Scans: one row per scheduler run
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'RUNNING',  -- RUNNING|COMPLETED|FAILED
    discovered   INTEGER NOT NULL DEFAULT 0,
    processed    INTEGER NOT NULL DEFAULT 0,
    published    INTEGER NOT NULL DEFAULT 0,
    changes      INTEGER NOT NULL DEFAULT 0,
    failed       INTEGER NOT NULL DEFAULT 0,
    notes        TEXT
);

-- ---------------------------------------------------------------------------
-- Media files: metadata + temp paths only (no permanent storage)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media_files (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id       INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    kind             TEXT    NOT NULL,             -- featured|gallery|raw|video
    source_url       TEXT    NOT NULL,
    local_path       TEXT,                         -- temp
    optimized_path   TEXT,                         -- temp (WebP/video)
    size_bytes       INTEGER,
    mime             TEXT,
    width            INTEGER,
    height           INTEGER,
    telegram_file_id TEXT,
    status           TEXT    NOT NULL DEFAULT 'pending', -- pending|downloaded|optimized|uploaded|deleted
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_media_product ON media_files(product_id);

-- ---------------------------------------------------------------------------
-- Telegram posts: cards + message ids + topic routing
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telegram_posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    text       TEXT NOT NULL,
    topic      TEXT NOT NULL,                      -- pending_posts|published_posts|changes|failed_jobs
    chat_id    TEXT NOT NULL,
    thread_id  INTEGER,                            -- Telegram Topic id
    message_id INTEGER,                            -- stored after send
    status     TEXT NOT NULL DEFAULT 'draft',      -- draft|sent|failed
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    sent_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_tg_product ON telegram_posts(product_id);
CREATE INDEX IF NOT EXISTS idx_tg_topic   ON telegram_posts(topic, status);

-- ---------------------------------------------------------------------------
-- Change log: price / availability changes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS change_log (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id           INTEGER REFERENCES products(id) ON DELETE CASCADE,
    change_type          TEXT NOT NULL,            -- price_changed|availability_changed
    old_value            TEXT,
    new_value            TEXT,
    notified             INTEGER NOT NULL DEFAULT 0,
    telegram_message_id  INTEGER,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Failed jobs: durable retry queue
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS failed_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER REFERENCES products(id) ON DELETE CASCADE,
    stage           TEXT NOT NULL,                 -- discovery|detail|media_download|media_optimize|post_generate|telegram_publish
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 5,
    next_retry_at   TEXT,                          -- for backoff scheduling
    last_error      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    resolved        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_failed_stage ON failed_jobs(stage, resolved, next_retry_at);

-- ---------------------------------------------------------------------------
-- Processing state mirror (for fast state-scoped queries / queue reads)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processing_state (
    product_id  INTEGER PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    state       TEXT NOT NULL,
    stage       TEXT NOT NULL,                     -- queue stage currently owning it
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);