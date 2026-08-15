import logging
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .db import Database
from .models import MediaKind, MediaStatus, ProductState

logger = logging.getLogger("bazarkif.media_optimize")


class MediaOptimizer:
    def __init__(self, config, db: Database):
        self.config = config
        self.db = db

    def optimize_product(self, product_id: int) -> tuple[bool, str | None]:
        rows = self.db.query(
            "SELECT * FROM media_files WHERE product_id=? AND status IN ('downloaded','optimized')",
            (product_id,),
        )
        for row in rows:
            if row["status"] == "optimized" and Path(row["optimized_path"]).exists():
                continue
            if row["kind"] == MediaKind.VIDEO.value:
                self._optimize_video(row)
            else:
                self._optimize_image(row)

        # verify at least one optimized image exists
        has_img = self.db.scalar(
            "SELECT COUNT(*) FROM media_files WHERE product_id=? AND kind IN ('featured','gallery','raw') AND status='optimized'",
            (product_id,),
        )
        if not has_img:
            return False, "no optimized images produced"

        self.db.execute(
            "UPDATE products SET state=?, updated_at=datetime('now') WHERE id=?",
            (ProductState.MEDIA_OPTIMIZED.value, product_id),
        )
        self.db.execute(
            "UPDATE processing_state SET state=?, stage=?, updated_at=datetime('now') WHERE product_id=?",
            (ProductState.MEDIA_OPTIMIZED.value, "post", product_id),
        )
        return True, None

    def _optimize_image(self, row) -> bool:
        src = Path(row["local_path"])
        if not src.exists():
            logger.warning("missing source image", extra={"product_id": row["product_id"], "url": row["source_url"]})
            return False
        out_dir = self.config.media_root / "optimize" / str(row["product_id"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / (src.stem + ".webp")
        try:
            with Image.open(src) as im:
                im = im.convert("RGBA").convert("RGB")
                im = self._cap_dimensions(im)
                out_path = self._compress(im, out_path)
        except (UnidentifiedImageError, OSError) as e:
            logger.warning("image optimize error", extra={"product_id": row["product_id"], "error": str(e)})
            return False
        size = out_path.stat().st_size if out_path.exists() else 0
        with Image.open(out_path) as im:
            w, h = im.size
        self.db.execute(
            "UPDATE media_files SET optimized_path=?, size_bytes=?, width=?, height=?, status=? WHERE id=?",
            (str(out_path), size, w, h, MediaStatus.OPTIMIZED.value, row["id"]),
        )
        return True

    def _cap_dimensions(self, im) -> Image.Image:
        max_dim = self.config.image_max_dimension
        if max(im.size) <= max_dim:
            return im
        ratio = max_dim / max(im.size)
        return im.resize((int(im.width * ratio), int(im.height * ratio)), Image.LANCZOS)

    def _compress(self, im, out_path: Path) -> Path:
        target = self.config.webp_target_bytes
        quality = self.config.webp_quality_start
        floor = self.config.webp_quality_floor
        while quality >= floor:
            im.save(out_path, "WEBP", quality=quality, method=6)
            if out_path.stat().st_size <= target:
                return out_path
            quality -= 5
        return out_path

    def _optimize_video(self, row) -> bool:
        src = Path(row["local_path"])
        if not src.exists() or src.stat().st_size == 0:
            logger.warning("missing/empty video", extra={"product_id": row["product_id"]})
            return False
        self.db.execute(
            "UPDATE media_files SET optimized_path=?, status=? WHERE id=?",
            (str(src), MediaStatus.OPTIMIZED.value, row["id"]),
        )
        return True