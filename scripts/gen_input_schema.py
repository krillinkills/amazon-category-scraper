"""Generate .actor/input_schema.json dropdowns from markets.json and categories.json."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKETS_PATH = ROOT / 'src' / 'markets.json'
CATEGORIES_PATH = ROOT / 'src' / 'categories.json'
OUT_PATH = ROOT / '.actor' / 'input_schema.json'

ALL_OPTION = '(All)'


def category_label(department: str, subcategory: str) -> str:
    return f'{department} -> {subcategory}'


def main() -> None:
    markets = json.loads(MARKETS_PATH.read_text(encoding='utf-8'))
    categories = json.loads(CATEGORIES_PATH.read_text(encoding='utf-8'))

    marketplace_enum = list(markets.keys())
    if 'GB' in marketplace_enum and 'UK' not in marketplace_enum:
        marketplace_enum.insert(marketplace_enum.index('GB') + 1, 'UK')
    marketplace_titles = []
    for code in marketplace_enum:
        lookup = 'GB' if code == 'UK' else code
        info = markets[lookup]
        marketplace_titles.append(f'{code} — {info["name"]}')

    category_enum: list[str] = []
    seen: set[str] = set()
    preferred = 'IN'
    market_order = [preferred] + [code for code in categories if code != preferred]

    for code in market_order:
        tree = categories.get(code) or {}
        for department in tree.get('departments', []):
            dept_name = department['name']
            all_label = category_label(dept_name, ALL_OPTION)
            if all_label not in seen:
                seen.add(all_label)
                category_enum.append(all_label)
            for child in department.get('children', []):
                label = category_label(dept_name, child['name'])
                if label not in seen:
                    seen.add(label)
                    category_enum.append(label)

    schema = {
        'title': 'Amazon Category Listing Scraper',
        'type': 'object',
        'schemaVersion': 1,
        'properties': {
            'marketplace': {
                'title': 'Marketplace',
                'type': 'string',
                'description': 'ISO 3166-1 alpha-2 country code for an official Amazon store. GB and UK are the same store.',
                'editor': 'select',
                'enum': marketplace_enum,
                'enumTitles': marketplace_titles,
                'default': 'IN',
            },
            'category': {
                'title': 'Department -> Subcategory',
                'type': 'string',
                'description': (
                    'One All-menu path. Department and subcategory are in this single dropdown, '
                    f'e.g. "Beauty, Health, Grocery -> Health & Personal Care". '
                    f'Pick "Department -> {ALL_OPTION}" to scrape the whole department. '
                    'Short names such as "Electronics -> Headphones" also resolve on marketplaces '
                    'that group that department (India: "TV, Appliances, Electronics").'
                ),
                'editor': 'select',
                'enum': category_enum,
                'enumTitles': category_enum,
                'sectionCaption': 'What to scrape',
            },
            'maxPages': {
                'title': 'Pages to scrape',
                'type': 'integer',
                'description': (
                    'How many Amazon listing pages to fetch. 0 or empty means no page limit: '
                    'keep going until Amazon returns no new products.'
                ),
                'minimum': 0,
                'default': 0,
                'sectionCaption': 'How much to scrape',
            },
            'maxItems': {
                'title': 'Max items',
                'type': 'integer',
                'description': (
                    'With product details on, stop after this many stored product rows. '
                    '0 or empty means no item limit.'
                ),
                'minimum': 0,
                'default': 0,
            },
            'enrichDetails': {
                'title': 'Fetch product details',
                'type': 'boolean',
                'description': (
                    'Open each product page for brand, About this item, description, and overview. '
                    'Rows are stored only when those details parse. '
                    'Turn off to store listing cards only.'
                ),
                'default': True,
                'sectionCaption': 'Product details',
            },
            'maxConcurrency': {
                'title': 'Detail-page concurrency',
                'type': 'integer',
                'description': (
                    'Maximum detail workers. The actor lists one page with a single worker, then starts '
                    'one product-page worker per item on that page, up to this cap. After that wave '
                    'finishes it lists the next page the same way. Default 48, max 80.'
                ),
                'minimum': 1,
                'maximum': 80,
                'default': 48,
            },
            'proxyConfiguration': {
                'title': 'Proxy',
                'type': 'object',
                'description': (
                    'Residential proxies with sticky sessions. Amazon blocks most datacenter IPs. '
                    'If you leave country empty, the actor uses the selected marketplace '
                    '(US store → US IPs). Mismatched country often returns HTTP 503 on listing page 1.'
                ),
                'editor': 'proxy',
                'sectionCaption': 'Proxy and browser',
                'default': {
                    'useApifyProxy': True,
                    'apifyProxyGroups': ['RESIDENTIAL'],
                },
            },
        },
        'required': ['marketplace', 'category'],
    }

    OUT_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Wrote {OUT_PATH} ({len(marketplace_enum)} markets, {len(category_enum)} category paths)')


if __name__ == '__main__':
    main()
