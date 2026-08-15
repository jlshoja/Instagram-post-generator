# 6. Telegram Design

## 6.1 Transport Choice

Use the **Telegram Bot API** directly over `requests`. Rationale:

- Topics require `Bot API 6.0+` (`message_thread_id` on `sendMessage` /
  `sendMediaGroup` / `sendVideo`). Handled fine with raw HTTP.
- No heavy SDK dependency, no async runtime needed; simpler, cross-platform,
  and easier to test/mock than `python-telegram-bot`.
- If we later want webhooks, rate-limit helpers, or `MessageEntity` editing, we
  can add `python-telegram-bot` without changing the publisher interface.

Publisher interface (`telegram_publisher.send_card(...)`) is SDK-agnostic so the
transport is swappable.

## 6.2 Topics

A single Telegram group (or supergroup) with **Forum Topics** enabled. Four
topics are required:

| Topic | Purpose |
|---|---|
| **Pending Posts** | New product cards, sent here first. Human review happens here. |
| **Published Posts** | Optional mirror after human approval (a human re-posts manually; bot never auto-publishes). |
| **Changes** | Price / availability change notifications. |
| **Failed Jobs** | Jobs that exceeded retries; human investigates. |

**No automatic publishing.** Products only ever go to Pending Posts; a human
reviews and decides whether to forward/share.

## 6.3 Configuration

```
TELEGRAM_BOT_TOKEN        # from @BotFather
TELEGRAM_CHAT_ID          # group id (negative number for supergroups)
TELEGRAM_THREAD_PENDING   # message_thread_id for Pending Posts
TELEGRAM_THREAD_PUBLISHED # message_thread_id for Published Posts
TELEGRAM_THREAD_CHANGES   # message_thread_id for Changes
TELEGRAM_THREAD_FAILED    # message_thread_id for Failed Jobs
```

`message_thread_id` = the numeric `thread_id` Telegram assigns to each topic
(obtainable via `getUpdates`/`getChat` once topics exist). Stored per post.

## 6.4 Message Shapes

### Product Card (Pending Posts)
Media group of optimized WebP images + optional separate video message, with the
rendered Persian card as caption (see template in `post_generator`). Caption
limit 1024 chars enforced by template.

### Price Change (Changes topic)
```
🔄 Price Changed

Product: XYZ
Old Price: 1,250,000
New Price: 1,350,000
```

### Availability Change (Changes topic)
```
❌ Product Unavailable

Product: XYZ
```

### Failed Job (Failed Jobs topic)
```
⚠️ Failed Job
Stage: telegram_publish
Product: <name> (<url>)
Attempts: 5/5
Error: <last_error>
```

## 6.5 Sending Order

1. `sendMediaGroup` with photos (≤10 per call; batch if more) + caption on the
   **first** photo.
2. `sendVideo` for the product video (if present).
3. Persist returned `message_id`(s) + `thread_id` into `telegram_posts`.

## 6.6 Error Handling / Retries

- Map Bot API errors: `429` → parse `retry_after`, honor it; `400/403` →
  permanent → Failed Jobs topic; network → transient retry (see `05`).
- If the first photo's caption exceeds 1024 chars, split caption into a separate
  follow-up text message (template is designed to stay under the limit).

## 6.7 Publish Guard (idempotency)

Before sending, check for an existing `telegram_posts.message_id` for the
product+topic. If present, skip to avoid duplicate cards after a crash/resume.