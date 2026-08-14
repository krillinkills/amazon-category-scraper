# Amazon Category Listing Scraper

Apify actor that scrapes Amazon **category listing cards** for any official store. You pick a marketplace ISO code, an All-menu department, and one of that department’s subcategories.

It does not open product detail pages.

## Inputs

| Field | What it is |
| --- | --- |
| `marketplace` | ISO country code (`IN`, `US`, `GB`, `DE`, …). `UK` is accepted as an alias for `GB`. |
| `department` | Amazon All → Shop by Category parent, e.g. `Mobiles, Computers`. |
| `subcategory` | One child of that department, labeled `Department > Child`. Use `(All)` for the whole department. |
| `maxPages` | Default `3`, max `20`. |
| `maxItems` | Default `60`. |
| `proxyConfiguration` | Apify proxy. Residential is recommended. |

Dropdown options are generated from [`src/categories.json`](src/categories.json). If a department has three children on Amazon, all three appear in the subcategory select.

The chosen department + subcategory must exist for that marketplace. A mismatch fails and lists the valid children.

## Example

```bash
apify run -i '{"marketplace":"IN","department":"Mobiles, Computers","subcategory":"All Mobile Phones","maxPages":1,"maxItems":20}'
```

Equivalent subcategory label from the Console dropdown:

```json
{
  "marketplace": "IN",
  "department": "Mobiles, Computers",
  "subcategory": "Mobiles, Computers > All Mobile Phones",
  "maxPages": 1,
  "maxItems": 20
}
```

## Output fields

Each dataset item is one listing card:

`asin`, `title`, `url`, `image`, `price`, `originalPrice`, `currency`, `rating`, `reviewsCount`, `isSponsored`, `isPrime`, `badge`, `boughtInPastMonth`, `position`, `page`, `marketplace`, `department`, `subcategory`, `categoryPath`

Missing values are `null`.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_categories.py
python scripts/gen_input_schema.py
apify run -i '{"marketplace":"IN","department":"Mobiles, Computers","subcategory":"All Mobile Phones","maxPages":1,"maxItems":20}'
```

After you change [`src/categories.json`](src/categories.json) (or the builder), regenerate the Console dropdowns:

```bash
python scripts/gen_input_schema.py
```

Amazon will usually block runs without a residential proxy.
