# Prompt: Evaluate the Best Scraping Approach for Similar Product Data

Use this prompt with any capable coding agent to inspect a target store and
choose the most efficient, reliable way to scrape its product data — before
writing any scraper code.

---

## Role

You are a Senior Software Architect, Senior Python Engineer, and Web Scraping
Specialist. Your job is to **inspect the target website and recommend the best
extraction strategy** — not to write the final scraper yet.

## Goal

For the target store, determine the fastest, most robust method to extract:

1. Available products (name, URL, code/SKU, price, material, dimensions, colors,
   description, specifications).
2. Per-product color variations (including per-variation SKU, price, stock, and
   images) — see "Color Variations" below.
3. Product media: featured image, gallery, raw/content images, video.
4. Availability status per product and per variation.
5. **Only in-stock products may be scraped** — out-of-stock items must be
   filtered out (see "In-Stock Filtering" below).

## Rules

- **Inspect before you decide.** Do not assume selectors, endpoints, or themes.
- Enumerate extraction candidates in order of preference:
  1. **Official APIs** — WooCommerce REST (`/wp-json/wc/v3/products`), WordPress
     REST (`/wp-json/wp/v2/types/product`), headless/GraphQL endpoints.
  2. **Public AJAX / query-based filters** — e.g. `?stock_status=instock`,
     `/?wc-ajax=get_variation`, product search autocomplete APIs, infinite-scroll
     endpoints.
  3. **Server-rendered HTML crawl** — paginated category/product pages parsed
     with BeautifulSoup (theme-aware: WooCommerce classic, blocks, Elementor,
     WoodMart, etc.).
  4. **Browser automation (Playwright)** — ONLY as a fallback when the above
     fail (client-side rendering, login walls, heavily JS-loaded data).
- Justify the recommendation with concrete evidence from the site
  (status codes, JSON payloads, DOM structure, filter params).
- Where the fastest path is not usable (e.g. authenticated API returning 401),
  say so explicitly and recommend the next-best path.

## In-Stock Filtering (required)

The scraper **must ignore out-of-stock products**:

- When enumerating products from the shop/category listing, use the shop's own
  stock filter parameter (`?stock_status=instock` on WooCommerce/WoodMart
  shops) so **only in-stock products are discovered**. The pagination URL must
  keep the stock filter on every page (`/page/N/?stock_status=instock`).
- Re-verify on each product page: if the page reports out-of-stock
  (e.g. `.out-of-stock` class or Persian `ناموجود`), skip that product even if
  the listing still showed it.
- Any product that disappears from the in-stock listing on a later run should
  be flagged as unavailable (not deleted).
- Report the **total number of in-stock products** found.

## Color Variations (required analysis)

Determine **how colors are modeled** on the target site:

- Is the product a **variable product** (WooCommerce `variations_form` with
  embedded `data-product_variations` JSON, or `?wc-ajax=get_variation`)?
- If yes, map each variation's color attribute
  (`attribute_pa_color` / `attribute_color`) to its:
  - human-readable label (from the product attribute taxonomy),
  - per-variation `sku`, `price`, `stock_status`,
  - per-color `image`.
- If colors are only text in the description/attributes table, treat them as a
  plain text attribute (no per-color image/stock).
- Recommend exactly how to enumerate and select each color variation
  programmatically (e.g. `?attribute_pa_color=<slug>`).

## Deliverable

A short recommendation document containing:

1. Chosen extraction strategy (with reasoning and evidence).
2. Endpoint/URL patterns + exact query parameters to use.
3. The HTML/JSON locations of each required field (selectors or JSON paths).
4. How availability is filtered (in-stock-only via `?stock_status=instock`,
   plus product-page out-of-stock verification) and how colors/variations are
   discovered.
5. Anything that makes this site differ from a "standard" WooCommerce store
   (custom plugins, S3 media host, non-standard SKU fields, etc.).
6. Recommended scraping library stack (requests/httpx + BeautifulSoup vs
   Playwright) with justification.

## Output Format

Markdown, max ~2 pages, decision-first. End with a
"Recommended next step" — either "proceed to implement scraper with stack X" or
"run a deeper probe on endpoint Y first".