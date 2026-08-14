"""Generate .actor/input_schema.json dropdowns from markets.json and categories.json."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKETS_PATH = ROOT / 'src' / 'markets.json'
CATEGORIES_PATH = ROOT / 'src' / 'categories.json'
OUT_PATH = ROOT / '.actor' / 'input_schema.json'

ALL_OPTION = '(All)'


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

    department_markets: dict[str, set[str]] = defaultdict(set)
    subcategory_markets: dict[str, set[str]] = defaultdict(set)
    department_enum: list[str] = []
    subcategory_enum: list[str] = []

    for iso, tree in categories.items():
        for department in tree.get('departments', []):
            dept_name = department['name']
            if dept_name not in department_markets:
                department_enum.append(dept_name)
            department_markets[dept_name].add(iso)

            all_label = f'{dept_name} > {ALL_OPTION}'
            if all_label not in subcategory_markets:
                subcategory_enum.append(all_label)
            subcategory_markets[all_label].add(iso)

            for child in department.get('children', []):
                label = f'{dept_name} > {child["name"]}'
                if label not in subcategory_markets:
                    subcategory_enum.append(label)
                subcategory_markets[label].add(iso)

    department_titles = []
    for name in department_enum:
        isos = sorted(department_markets[name])
        if len(isos) > 1:
            department_titles.append(f'{name} ({", ".join(isos)})')
        else:
            department_titles.append(f'{isos[0]} — {name}')

    subcategory_titles = []
    for label in subcategory_enum:
        isos = sorted(subcategory_markets[label])
        if len(isos) > 1:
            subcategory_titles.append(f'{label} ({", ".join(isos)})')
        else:
            subcategory_titles.append(f'{isos[0]} — {label}')

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
            'department': {
                'title': 'Department',
                'type': 'string',
                'description': 'Amazon All → Shop by Category parent, using the same name Amazon shows.',
                'editor': 'select',
                'enum': department_enum,
                'enumTitles': department_titles,
            },
            'subcategory': {
                'title': 'Subcategory',
                'type': 'string',
                'description': (
                    'Every child under the All menu. Labels are Department > Subcategory. '
                    f'Pick "{ALL_OPTION}" to scrape the whole department. '
                    'The pair must exist for the selected marketplace.'
                ),
                'editor': 'select',
                'enum': subcategory_enum,
                'enumTitles': subcategory_titles,
            },
            'maxPages': {
                'title': 'Max pages',
                'type': 'integer',
                'description': 'Maximum listing pages to fetch. Amazon usually stops around 20.',
                'minimum': 1,
                'maximum': 20,
                'default': 3,
            },
            'maxItems': {
                'title': 'Max items',
                'type': 'integer',
                'description': 'Stop after this many product cards.',
                'minimum': 1,
                'maximum': 1000,
                'default': 60,
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
        'required': ['marketplace', 'department', 'subcategory'],
    }

    OUT_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(
        f'Wrote {OUT_PATH} '
        f'({len(marketplace_enum)} markets, {len(department_enum)} departments, '
        f'{len(subcategory_enum)} subcategory options)'
    )


if __name__ == '__main__':
    main()
