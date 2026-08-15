from conftest import IMG_1, IMG_2, RELATED, VIDEO, build_product_html

from bazarkif.detail import (
    _parse_attributes,
    _parse_gallery,
    _parse_price,
    _parse_raw_content_media,
    _parse_title,
)


def test_parse_title_extracts_name_and_code():
    html = build_product_html(title="کوله پشتی – کد 9388 – بازار کیف")
    name, code = _parse_title(html)
    assert name == "کوله پشتی"
    assert code == "9388"


def test_parse_price():
    html = build_product_html(price="2,414,000")
    assert _parse_price(html) == 2414000


def test_parse_persian_digits_price():
    html = build_product_html(price="۲,۴۱۴,۰۰۰")
    assert _parse_price(html) == 2414000


def test_parse_attributes():
    html = build_product_html(attrs=(("ابعاد", "45 × 30 × 10 سانتیمتر"), ("جنس", "چرم")))
    attrs = _parse_attributes(html)
    assert attrs["ابعاد"] == "45 × 30 × 10 سانتیمتر"
    assert attrs["جنس"] == "چرم"


def test_parse_gallery_full_res_only():
    html = build_product_html(gallery=(IMG_1, IMG_2))
    gal = _parse_gallery(html)
    assert gal == [IMG_1, IMG_2]


def test_parse_raw_content_excludes_related():
    html = build_product_html(raw_imgs=(IMG_1,))
    imgs, vids = _parse_raw_content_media(html)
    assert imgs == [IMG_1]
    assert RELATED not in imgs
    assert vids == [VIDEO]


def test_parse_raw_content_empty_when_no_raw():
    html = build_product_html(include_raw=False)
    imgs, vids = _parse_raw_content_media(html)
    assert imgs == []
    assert vids == []