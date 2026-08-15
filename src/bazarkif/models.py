from enum import Enum


class ProductState(str, Enum):
    DISCOVERED = "DISCOVERED"
    DETAILS_EXTRACTED = "DETAILS_EXTRACTED"
    MEDIA_DOWNLOADED = "MEDIA_DOWNLOADED"
    POST_GENERATED = "POST_GENERATED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


STAGE_ORDER = [
    ProductState.DISCOVERED,
    ProductState.DETAILS_EXTRACTED,
    ProductState.MEDIA_DOWNLOADED,
    ProductState.POST_GENERATED,
    ProductState.PUBLISHED,
]

STAGE_TO_QUEUE = {
    ProductState.DISCOVERED: "detail",
    ProductState.DETAILS_EXTRACTED: "media",
    ProductState.MEDIA_DOWNLOADED: "post",
    ProductState.POST_GENERATED: "publish",
}


class MediaKind(str, Enum):
    FEATURED = "featured"
    GALLERY = "gallery"
    RAW = "raw"
    VIDEO = "video"


class MediaStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    UPLOADED = "uploaded"
    DELETED = "deleted"


class Topic(str, Enum):
    PENDING = "pending_posts"
    PUBLISHED = "published_posts"
    CHANGES = "changes"
    FAILED = "failed_jobs"


class ChangeType(str, Enum):
    PRICE_CHANGED = "price_changed"
    AVAILABILITY_CHANGED = "availability_changed"


class PostStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    FAILED = "failed"