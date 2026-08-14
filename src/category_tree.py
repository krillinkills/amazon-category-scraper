from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
ALL_OPTION = '(All)'


class CategoryLookupError(ValueError):
    """Raised when marketplace / department / subcategory do not match the All-menu tree."""


@dataclass(frozen=True)
class Market:
    code: str
    domain: str
    currency: str
    name: str


@dataclass(frozen=True)
class ResolvedCategory:
    marketplace: str
    domain: str
    currency: str
    department: str
    subcategory: str
    category_path: str
    url_path: str


def normalize_marketplace(code: str) -> str:
    normalized = (code or '').strip().upper()
    if normalized == 'UK':
        return 'GB'
    return normalized


def _norm_name(value: str) -> str:
    return ' '.join((value or '').replace('&', 'and').replace(',', ' ').split()).casefold()


@lru_cache(maxsize=1)
def load_markets() -> dict[str, Market]:
    raw = json.loads((DATA_DIR / 'markets.json').read_text(encoding='utf-8'))
    return {
        code: Market(code=code, domain=item['domain'], currency=item['currency'], name=item['name'])
        for code, item in raw.items()
    }


@lru_cache(maxsize=1)
def load_categories() -> dict:
    return json.loads((DATA_DIR / 'categories.json').read_text(encoding='utf-8'))


def _department_names(tree: dict) -> list[str]:
    return [department['name'] for department in tree.get('departments', [])]


def _find_department(tree: dict, department_name: str) -> dict | None:
    wanted = _norm_name(department_name)
    for department in tree.get('departments', []):
        if _norm_name(department['name']) == wanted:
            return department
    return None


PATH_SEPARATORS = (' -> ', ' → ', ' > ')


def format_category_path(department: str, subcategory: str) -> str:
    return f'{department} -> {subcategory}'


def parse_category_path(value: str) -> tuple[str, str]:
    text = _strip_path_prefix(value)
    for separator in PATH_SEPARATORS:
        if separator in text:
            department, subcategory = text.split(separator, 1)
            department = department.strip()
            subcategory = subcategory.strip()
            if department and subcategory:
                return department, subcategory
    raise CategoryLookupError(
        f'Category {value!r} must look like "Department -> Subcategory".'
    )


def _strip_path_prefix(value: str) -> str:
    text = (value or '').strip()
    if ' — ' in text:
        text = text.split(' — ', 1)[1].strip()
    return text


def _subcategory_name(department_name: str, raw_subcategory: str) -> str:
    text = _strip_path_prefix(raw_subcategory)
    for separator in PATH_SEPARATORS:
        prefix = f'{department_name}{separator}'
        if text.casefold().startswith(prefix.casefold()):
            return text[len(prefix):].strip()
    return text


def _child_names(department: dict) -> list[str]:
    return [child['name'] for child in department.get('children', [])]


def _find_child(department: dict, subcategory_name: str) -> dict | None:
    wanted = _norm_name(subcategory_name)
    for child in department.get('children', []):
        if _norm_name(child['name']) == wanted:
            return child
    return None


def resolve_category_input(
    marketplace: str,
    category: str | None = None,
    department: str | None = None,
    subcategory: str | None = None,
) -> ResolvedCategory:
    if category:
        department, subcategory = parse_category_path(category)
    if not department or not subcategory:
        raise CategoryLookupError('Pick a category like "Mobiles, Computers -> All Mobile Phones".')
    return resolve_category(marketplace, department, subcategory)


def resolve_category(marketplace: str, department: str, subcategory: str) -> ResolvedCategory:
    iso = normalize_marketplace(marketplace)
    markets = load_markets()
    if iso not in markets:
        supported = ', '.join(sorted(markets))
        raise CategoryLookupError(f'Unknown marketplace {marketplace!r}. Supported ISO codes: {supported}.')

    market = markets[iso]
    tree = load_categories().get(iso)
    if not tree:
        raise CategoryLookupError(f'No All-menu tree is shipped for marketplace {iso}.')

    department_name = _strip_path_prefix(department)
    found_department = _find_department(tree, department_name)
    if found_department is None:
        available = ', '.join(_department_names(tree))
        raise CategoryLookupError(
            f'Department {department!r} is not in the {iso} All menu. Available: {available}.'
        )

    child_name = _subcategory_name(found_department['name'], subcategory)
    if not child_name:
        raise CategoryLookupError('Subcategory is required.')

    if _norm_name(child_name) == _norm_name(ALL_OPTION):
        url_path = found_department.get('url') or (
            found_department['children'][0]['url'] if found_department.get('children') else None
        )
        if not url_path:
            raise CategoryLookupError(f'Department {found_department["name"]!r} has no listing URL.')
        return ResolvedCategory(
            marketplace=iso,
            domain=market.domain,
            currency=market.currency,
            department=found_department['name'],
            subcategory=ALL_OPTION,
            category_path=format_category_path(found_department['name'], ALL_OPTION),
            url_path=url_path,
        )

    found_child = _find_child(found_department, child_name)
    if found_child is None:
        available = ', '.join(_child_names(found_department)) or '(none)'
        raise CategoryLookupError(
            f'Subcategory {subcategory!r} is not under {found_department["name"]!r} on {iso}. '
            f'Available: {available}.'
        )

    return ResolvedCategory(
        marketplace=iso,
        domain=market.domain,
        currency=market.currency,
        department=found_department['name'],
        subcategory=found_child['name'],
        category_path=format_category_path(found_department['name'], found_child['name']),
        url_path=found_child['url'],
    )


def listing_url(resolved: ResolvedCategory, page: int = 1) -> str:
    path = resolved.url_path
    if path.startswith('http://') or path.startswith('https://'):
        url = path
    else:
        url = f'https://{resolved.domain}{path}'
    separator = '&' if '?' in url else '?'
    extras: list[str] = []
    if '/s?' in url and 'fs=' not in url:
        extras.append('fs=true')
    if 'page=' not in url:
        extras.append(f'page={page}')
    if not extras:
        return url
    return f'{url}{separator}{"&".join(extras)}'
