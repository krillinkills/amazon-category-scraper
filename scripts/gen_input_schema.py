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

    for tree in categories.values():
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
                'title': 'Category',
                'type': 'string',
                'description': (
                    'One All-menu path: Department -> Subcategory. '
                    f'Pick "Department -> {ALL_OPTION}" to scrape the whole department. '
                    'The path must exist for the selected marketplace.'
                ),
                'editor': 'select',
                'enum': category_enum,
                'enumTitles': category_enum,
            },
            'maxPages': {
                'title': 'Pages to scrape',
                'type': 'integer',
                'description': 'How many Amazon listing pages to fetch. Set this yourself (1–20). Amazon usually stops after about 20 pages.',
                'minimum': 1,
                'maximum': 20,
                'prefill': 5,
                'sectionCaption': 'How much to scrape',
            },
            'maxItems': {
                'title': 'Max items',
                'type': 'integer',
                'description': 'Stop after this many product cards.',
                'minimum': 1,
                'maximum': 1000,
                'default': 1000,
            },
            'enrichDetails': {
                'title': 'Fetch product details',
                'type': 'boolean',
                'description': (
                    'Open each product page for brand, About this item, description, and overview. '
                    'Listing-card fields are still saved if a detail page fails.'
                ),
                'default': True,
                'sectionCaption': 'Product details',
            },
            'maxConcurrency': {
                'title': 'Detail-page concurrency',
                'type': 'integer',
                'description': 'How many product pages to fetch at once. Each request uses its own proxy IP. Default 50.',
                'minimum': 1,
                'maximum': 50,
                'default': 50,
            },
            'proxyConfiguration': {
                'title': 'Proxy',
                'type': 'object',
                'description': 'Residential proxies are recommended. Amazon blocks most datacenter IPs.',
                'editor': 'proxy',
                'sectionCaption': 'Proxy and browser',
                'default': {'useApifyProxy': True},
            },
        },
        'required': ['marketplace', 'category', 'maxPages'],
    }

    OUT_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Wrote {OUT_PATH} ({len(marketplace_enum)} markets, {len(category_enum)} category paths)')


if __name__ == '__main__':
    main()
