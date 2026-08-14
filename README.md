# Amazon Category Listing Scraper

Apify actor that scrapes Amazon **category listing cards** for any official store, then opens each product page for brand, About this item, description, and overview.

You pick a marketplace ISO code and one All-menu path: `Department -> Subcategory`.

## Inputs

| Field | What it is |
| --- | --- |
| `marketplace` | ISO country code (`IN`, `US`, `GB`, `DE`, …). `UK` is accepted as an alias for `GB`. |
| `category` | One path from the All menu, e.g. `Mobiles, Computers -> All Mobile Phones`. Use `Department -> (All)` for the whole department. |
| `maxPages` or `pages` | **Required.** How many listing pages to fetch (1–100). |
| `maxItems` | Default `5000`. |
| `enrichDetails` | Default `true`. Fetch brand / About this item from each `/dp/ASIN` page. |
| `maxConcurrency` | Default `50`. Worker pool size. Each worker keeps a sticky residential IP and rotates it after ~25 product pages or on a block. |
| `proxyConfiguration` | Apify proxy. Residential is recommended. |

The Console has a single Category dropdown. Labels are `Department -> Subcategory` with no marketplace codes.

The path must exist for that marketplace. A mismatch fails and lists the valid children.

Listing pages stay sequential on one sticky IP (rotated every 10 pages or on a 503). Product-detail fetches run in a 50-wide pool: each worker reuses one residential IP, then rotates on captcha/timeout or after 25 products. A failed detail page still stores the listing card.

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

`asin`, `title`, `url`, `image`, `price`, `originalPrice`, `currency`, `rating`, `reviewsCount`, `isSponsored`, `isPrime`, `badge`, `boughtInPastMonth`, `brand`, `aboutThisItem`, `description`, `productOverview`, `position`, `page`, `marketplace`, `department`, `subcategory`, `categoryPath`

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
