# Amazon Category Listing Scraper

Apify actor that scrapes Amazon **category listing cards** for any official store, then opens each product page for brand, About this item, description, and overview.

You pick a marketplace ISO code and one All-menu path: `Department -> Subcategory`.

## Inputs

| Field | What it is |
| --- | --- |
| `marketplace` | ISO country code (`IN`, `US`, `GB`, `DE`, …). `UK` is accepted as an alias for `GB`. |
| `category` | One path from the All menu, e.g. `Mobiles, Computers -> All Mobile Phones`. Use `Department -> (All)` for the whole department. |
| `maxPages` or `pages` | Optional. How many listing pages to fetch. `0` or omit = no page limit. |
| `maxItems` | Optional. With details on, stored product rows. `0` or omit = no item limit. |
| `enrichDetails` | Default `true`. Fetch brand / About this item from each `/dp/ASIN` page. |
| `maxConcurrency` | Default `100`. Worker pool size, cap `150`. Each worker keeps a sticky residential IP and rotates it after ~25 product pages or on a block. |
| `proxyConfiguration` | Apify proxy. Residential is recommended. |

The Console has one category dropdown. Labels are `Department -> Subcategory`. The path must exist for that marketplace. A mismatch fails and lists the valid children.

Listing walks category pages on one sticky IP (rotated every 15 pages or on a 503) and feeds ASINs into a bounded queue. Detail workers open `/dp` pages at the same time — you do not wait for every listing page to finish first. Each worker reuses one residential IP and rotates on captcha/timeout or after 25 products. `maxItems` counts stored detailed rows, not listing cards. Product HTML is stripped of scripts, CSS, and reviews before parsing. Stalled proxy downloads abort after ~8s of under 2 KB/s. A details run stores one row per ASIN only if brand, About this item, or overview parsed. Failed detail pages are skipped, not stored as empty rows. Set `enrichDetails` to `false` to store listing cards only.

## Example

```bash
apify run -i '{"marketplace":"IN","category":"Mobiles, Computers -> All Mobile Phones","maxPages":5,"maxItems":200}'
```

Listing cards only:

```bash
apify run -i '{"marketplace":"IN","category":"Mobiles, Computers -> All Mobile Phones","maxPages":5,"enrichDetails":false}'
```

## Output fields

Each dataset item is one product:

Listing card: `asin`, `title`, `url`, `image`, `price`, `originalPrice`, `currency`, `rating`, `reviewsCount`, `isSponsored`, `isPrime`, `badge`, `boughtInPastMonth`, `position`, `page`

Details (when `enrichDetails` is on): `brand`, `aboutThisItem`, `description`, `productOverview`, `productCategory`, `productCategories`, `productCategoryPath`, `productBrowseNodeId`, `hasDetails`

`department` / `subcategory` / `categoryPath` stay the All-menu path you scraped. The product-page breadcrumb is stored separately, e.g. `Home Improvement > Kitchen & Bath Fixtures > Bathroom Fixtures > Showers > Showerhead Filters`.

Scrape snapshot (on every row, for later analysis): `scrapedAt`, `scrapedDate`, `runId`, `marketplace`, `marketName`, `domain`, `browseNodeId`, `department`, `subcategory`, `categoryPath`, `listingUrl`, `proxyCountry`, `recordType`

`recordType` is `detail` when product pages are fetched (default) and `listing` only when `enrichDetails` is off. Each ASIN is stored once.

The run also writes a `SCRAPE_META` object to the default key-value store: input limits, node id, item counts, `finishedAt`.

Missing values are `null`. `aboutThisItem` is a string list when the product page loaded.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_categories.py
python scripts/gen_input_schema.py
apify run -i '{"marketplace":"IN","category":"Mobiles, Computers -> All Mobile Phones","maxPages":5,"maxItems":200}'
```

After you change [`src/categories.json`](src/categories.json) (or the builder), regenerate the Console dropdown:

```bash
python scripts/gen_input_schema.py
```

Amazon will usually block runs without a residential proxy.
