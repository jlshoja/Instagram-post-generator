# 2. Data Model

## 2.1 Processing States

Every product moves through a fixed lifecycle. States persist in SQLite and
survive restart (crash-resume reads the last known state and resumes).

```
DISCOVERED → DETAILS_EXTRACTED → MEDIA_DOWNLOADED → MEDIA_OPTIMIZED
          → POST_GENERATED → PUBLISHED
                              ↘ FAILED (any stage)
```

Additional implicit states handled by the scanner:

| State | Meaning |
|---|---|
| `DISCOVERED` | URL seen in discovery; not yet detailed. |
| `DETAILS_EXTRACTED` | Product fields populated. |
| `MEDIA_DOWNLOADED` | Raw media on temp disk; record in `media_files`. |
| `MEDIA_OPTIMIZED` | Images are WebP ≈125 KB; video verified. |
| `POST_GENERATED` | Persian card text rendered (draft). |
| `PUBLISHED` | Sent to Pending Posts; `message_id` stored. |
| `FAILED` | Terminal for this run; moved to `failed_jobs` for the queue retry loop. |
| (computed) `INACTIVE` | Previously available, now out of stock → not a processing state but a flag. |

No stage is marked complete unless fully successful.

## 2.2 Queues

Each stage has an independent queue. Items are picked by their current state, so
the queues are effectively **derived from `products.state`** (crash-safe: no
in-memory queue survives a crash, but the DB does). An in-memory `queue` layer is
kept only for ordering/concurrency; the source of truth is the DB.

```
Discovery Queue   → product URLs awaiting detail extraction
Detail Queue      → product_ids awaiting media download
Media Queue       → product_ids awaiting media optimization
Post Queue        → product_ids awaiting card generation
Publish Queue     → product_ids awaiting Telegram upload
```

A failure in one stage only marks that product's stage; other products/other
stages continue.

## 2.3 Entities

### Product
```python
@dataclass
class Product:
    id: int
    url: str            # UNIQUE identifier
    name: str
    code: str | None    # from title regex "کد (\d+)"
    price: int | None   # numeric toman
    description: str
    attributes: dict[str, str]   # e.g. {"ابعاد": "45 × 30 × 10 سانتیمتر", ...}
    category: str
    state: str          # processing state enum
    is_active: bool
    created_at: str
    updated_at: str
```

### MediaFile
```python
@dataclass
class MediaFile:
    id: int
    product_id: int
    kind: str          # featured | gallery | raw | video
    source_url: str
    local_path: str    # temp
    optimized_path: str | None
    size_bytes: int | None
    mime: str | None
    telegram_file_id: str | None
    status: str        # pending | downloaded | optimized | uploaded | deleted
    created_at: str
```

### TelegramPost
```python
@dataclass
class TelegramPost:
    id: int
    product_id: int
    text: str          # rendered Persian card
    topic: str         # pending_posts | published_posts | changes | failed_jobs
    chat_id: str
    message_id: int | None   # stored after send
    thread_id: int | None    # Telegram Topic id
    status: str        # draft | sent | failed
    created_at: str
```

## 2.4 Identity & Change Detection

- **Product URL is the unique identifier** (natural key). `products.url` is
  `UNIQUE`.
- **Price change**: compare latest extracted price vs stored price. If different
  and product was previously `PUBLISHED` → emit `change_log` row + Changes topic
  message. Do **not** regenerate the original post.
- **Availability change**: if previously active and now absent from `instock`
  listing (or page shows out-of-stock) → mark `is_active = False`, emit
  `change_log` row + Changes topic message.

## 2.5 Change Log

```python
@dataclass
class ChangeLog:
    id: int
    product_id: int
    change_type: str   # price_changed | availability_changed
    old_value: str | None
    new_value: str | None
    notified: bool
    telegram_message_id: int | None
    created_at: str
```