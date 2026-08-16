import json
import logging
import re

from bs4 import BeautifulSoup

from .db import Database
from .http_client import HttpClient
from .models import ChangeType, MediaKind, ProductState

logger = logging.getLogger("bazarkif.detail")

RAW_CONTENT_HEADING = "محتوای خام"
TITLE_SUFFIX = "بازار کیف"
CODE_RE = re.compile(r"کد\s*([\d\w]+)")
PRICE_RE = re.compile(r"([\d۰-۹,]+)")
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
MEDIA_HOST = "bazarkif-wordpress-3.s3.ir-thr-at1.arvanstorage.ir"


def _to_int_en(s: str) -> str:
    return s.translate(PERSIAN_DIGITS).replace(",", "").strip()


def _parse_title(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    t = soup.find("title")
    if t and t.string:
        title = t.string.strip()
        # strip " – بازار کیف" suffix
        if TITLE_SUFFIX in title:
            title = title.split(TITLE_SUFFIX)[0].strip(" –-")
    code = None
    m = CODE_RE.search(title)
    if m:
        code = m.group(1)
        # remove the code segment so the name stays clean: "کوله پشتی – کد 9388" -> "کوله پشتی"
        title = title.replace(m.group(0), "").strip(" –-")
    return title.strip(), code


def _parse_price(html: str) -> int | None:
    soup = BeautifulSoup(html, "html.parser")
    # the main product price lives in <p class="price">…<bdi>…</bdi></p>;
    # placeholder "0" bdi entries elsewhere on the page must be ignored.
    for p in soup.find_all("p", class_="price"):
        bdi = p.find("bdi")
        if not bdi:
            continue
        m = PRICE_RE.search(bdi.get_text())
        if not m:
            continue
        try:
            val = int(_to_int_en(m.group(1)))
        except ValueError:
            continue
        if val > 0:
            return val
    return None


def _parse_attributes(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    attrs: dict[str, str] = {}
    # product attribute table rows
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th and td:
            key = th.get_text(strip=True)
            val = td.get_text(strip=True)
            if key:
                attrs[key] = val
    return attrs


def _parse_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # first use structured data if present, else the description tab panel
    desc = ""
    tab = soup.find(id="tab-description")
    if tab:
        text = tab.get_text("\n", strip=True)
        if text:
            desc = text
    if not desc:
        ld = soup.find("script", type="application/ld+json")
        if ld:
            try:
                data = json.loads(ld.string)
                obj = data.get("@graph", [data]) if isinstance(data, dict) else data
                for item in obj:
                    if isinstance(item, dict) and item.get("description"):
                        desc = item["description"]
                        break
            except (json.JSONDecodeError, AttributeError):
                pass
    return desc


def _parse_gallery(html: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'data-large_image="([^"]+)"', html)))


def _parse_raw_content_media(html: str) -> tuple[list[str], list[str]]:
    """Return (images, videos) found in the Raw Content section only."""
    idx = html.find(RAW_CONTENT_HEADING)
    if idx < 0:
        return [], []
    seg = html[idx:]
    # cut the related-products block so its images are never captured
    for marker in ('class="related', 'class="related products', 'related products'):
        cut = seg.find(marker)
        if cut != -1:
            seg = seg[:cut]
            break
    imgs = []
    for url in re.findall(r'https?://[^"\'\s<>]+\.(?:jpg|jpeg|png|webp)', seg):
        # only the store's own media host counts (exclude embeds e.g. ytimg)
        if MEDIA_HOST not in url:
            continue
        # exclude thumbnail/resized variants (keep full-res)
        if re.search(r'-\d{2,4}x\d{2,4}\.', url):
            continue
        if "logo" in url.lower() or "cropped" in url.lower():
            continue
        # exclude slazzer background-removal watermarks/previews
        if "slazzer" in url.lower() or "preview" in url.lower():
            continue
        imgs.append(url)
    videos = list(dict.fromkeys(
        u for u in re.findall(r'https?://[^"\'\s<>]+\.mp4', seg) if MEDIA_HOST in u
    ))
    return list(dict.fromkeys(imgs)), videos


def _parse_availability(html: str) -> bool:
    # availability from listing is authoritative, but page-level out-of-stock check:
    low = html.lower()
    if "out-of-stock" in low or "ناموجود" in html:
        return False
    return True


class DetailExtractor:
    def __init__(self, config, db: Database, http: HttpClient):
        self.config = config
        self.db = db
        self.http = http

    def extract(self, product_row) -> tuple[bool, str | None]:
        url = product_row["url"]
        resp, _, err = self.http.get_with_retry(url, logger=logger)
        if err:
            return False, str(err)
        html = resp.text

        name, code = _parse_title(html)
        if not name:
            return False, "could not parse product title"
        price = _parse_price(html)
        attrs = _parse_attributes(html)
        description = _parse_description(html)
        gallery = _parse_gallery(html)
        raw_imgs, videos = _parse_raw_content_media(html)

        old_price = product_row["price"]

        self.db.execute(
            "UPDATE products SET name=?, code=?, price=?, attributes=?, description=?, "
            "state=?, updated_at=datetime('now') WHERE id=?",
            (
                name,
                code,
                price,
                json.dumps(attrs, ensure_ascii=False),
                description,
                ProductState.DETAILS_EXTRACTED.value,
                product_row["id"],
            ),
        )
        self.db.execute(
            "UPDATE processing_state SET state=?, stage=?, updated_at=datetime('now') WHERE product_id=?",
            (ProductState.DETAILS_EXTRACTED.value, "media", product_row["id"]),
        )
        self._store_media(product_row["id"], gallery, raw_imgs, videos)
        self._detect_price_change(product_row["id"], old_price, price)
        return True, None

    def _store_media(self, product_id, gallery, raw_imgs, videos) -> None:
        existing = {
            r["source_url"] for r in self.db.query(
                "SELECT source_url FROM media_files WHERE product_id=?", (product_id,)
            )
        }
        to_insert = []
        for url in gallery:
            if url not in existing:
                to_insert.append((product_id, MediaKind.GALLERY.value, url))
                existing.add(url)
        for url in raw_imgs:
            if url not in existing:
                to_insert.append((product_id, MediaKind.RAW.value, url))
                existing.add(url)
        for url in videos:
            if url not in existing:
                to_insert.append((product_id, MediaKind.VIDEO.value, url))
                existing.add(url)
        if to_insert:
            self.db.executemany(
                "INSERT INTO media_files (product_id, kind, source_url, status) VALUES (?,?,?,?)",
                [(p, k, u, "pending") for p, k, u in to_insert],
            )

    def _detect_price_change(self, product_id, old_price, new_price) -> None:
        if old_price is None or new_price is None or old_price == new_price:
            return
        self.db.execute(
            "INSERT INTO change_log (product_id, change_type, old_value, new_value) VALUES (?,?,?,?)",
            (product_id, ChangeType.PRICE_CHANGED.value, str(old_price), str(new_price)),
        )