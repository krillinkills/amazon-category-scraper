from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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
    market_name: str
    browse_node_id: str | None


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


_FILLER_TOKENS = frozenset({'and', 'the', 'of'})


def _tokens(value: str) -> list[str]:
    return _norm_name(value).split()


def _significant_tokens(value: str) -> list[str]:
    return [token for token in _tokens(value) if token not in _FILLER_TOKENS]


def _contains_tokens(haystack_name: str, needle_name: str) -> bool:
    needle = _significant_tokens(needle_name)
    haystack = _significant_tokens(haystack_name)
    if not needle or not haystack:
        return False
    width = len(needle)
    if any(haystack[index : index + width] == needle for index in range(len(haystack) - width + 1)):
        return True
    return set(needle) <= set(haystack)


def _find_department(tree: dict, department_name: str) -> dict | None:
    wanted = _norm_name(department_name)
    for department in tree.get('departments', []):
        if _norm_name(department['name']) == wanted:
            return department
    return None


def _department_candidates(tree: dict, department_name: str) -> list[dict]:
    exact = _find_department(tree, department_name)
    if exact is not None:
        return [exact]
    return [
        department
        for department in tree.get('departments', [])
        if _contains_tokens(department['name'], department_name)
    ]


def _children_with_name(tree: dict, subcategory_name: str) -> list[tuple[dict, dict]]:
    matches: list[tuple[dict, dict]] = []
    wanted = _norm_name(subcategory_name)
    if not wanted or wanted == _norm_name(ALL_OPTION):
        return matches
    for department in tree.get('departments', []):
        for child in department.get('children', []):
            if _norm_name(child['name']) == wanted:
                matches.append((department, child))
    return matches


PATH_SEPARATORS = (' -> ', ' → ', ' > ')


def browse_node_id_from_url(url_path: str | None) -> str | None:
    if not url_path:
        return None
    match = re.search(r'(?:[?&]rh=n:|[?&]node=|n:)(\d+)', url_path)
    return match.group(1) if match else None


def _browse_node_id(item: dict) -> str | None:
    node = item.get('browseNodeId')
    if node:
        return str(node)
    return browse_node_id_from_url(item.get('url'))


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
    candidates = _department_candidates(tree, department_name)
    child_name = _subcategory_name(candidates[0]['name'] if candidates else department_name, subcategory)
    if not child_name:
        raise CategoryLookupError('Subcategory is required.')

    if _norm_name(child_name) == _norm_name(ALL_OPTION):
        if len(candidates) == 1:
            return _resolved_department_all(market, iso, candidates[0])
        if len(candidates) > 1:
            names = ' | '.join(item['name'] for item in candidates)
            raise CategoryLookupError(
                f'Department {department!r} matches more than one {iso} All-menu group: {names}. '
                f'Pick the full path, e.g. "{candidates[0]["name"]} -> {ALL_OPTION}".'
            )
        available = ' | '.join(_department_names(tree))
        raise CategoryLookupError(
            f'Department {department!r} is not in the {iso} All menu. Available: {available}.'
        )

    found_department = None
    found_child = None
    if len(candidates) == 1:
        found_department = candidates[0]
        found_child = _find_child(found_department, child_name)
    elif len(candidates) > 1:
        with_child = [
            (item, _find_child(item, child_name))
            for item in candidates
        ]
        with_child = [(item, child) for item, child in with_child if child is not None]
        if len(with_child) == 1:
            found_department, found_child = with_child[0]
        elif len(with_child) > 1:
            names = ' | '.join(item['name'] for item, _child in with_child)
            raise CategoryLookupError(
                f'{subcategory!r} is under more than one {iso} department matching {department!r}: {names}.'
            )

    if found_child is None:
        elsewhere = _children_with_name(tree, child_name)
        if len(elsewhere) == 1:
            found_department, found_child = elsewhere[0]
        elif len(elsewhere) > 1:
            names = ' | '.join(item['name'] for item, _child in elsewhere)
            raise CategoryLookupError(
                f'Subcategory {subcategory!r} exists under more than one {iso} department: {names}. '
                f'Pick the full path, e.g. "{elsewhere[0][0]["name"]} -> {elsewhere[0][1]["name"]}".'
            )

    if found_department is None:
        available = ' | '.join(_department_names(tree))
        raise CategoryLookupError(
            f'Department {department!r} is not in the {iso} All menu. Available: {available}.'
        )

    if found_child is None:
        available = ' | '.join(_child_names(found_department)) or '(none)'
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
        market_name=market.name,
        browse_node_id=_browse_node_id(found_child) or browse_node_id_from_url(found_child.get('url')),
    )


def _resolved_department_all(market: Market, iso: str, found_department: dict) -> ResolvedCategory:
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
        market_name=market.name,
        browse_node_id=_browse_node_id(found_department) or browse_node_id_from_url(url_path),
    )


def _absolute_listing_url(resolved: ResolvedCategory) -> str:
    path = resolved.url_path
    if path.startswith('http://') or path.startswith('https://'):
        return path
    return f'https://{resolved.domain}{path}'


def listing_url(resolved: ResolvedCategory, page: int = 1, *, include_fs: bool = True) -> str:
    parsed = urlparse(_absolute_listing_url(resolved))
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if include_fs and parsed.path.startswith('/s') and 'fs' not in query:
        query['fs'] = 'true'
    if not include_fs:
        query.pop('fs', None)
    query['page'] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def listing_url_candidates(resolved: ResolvedCategory, page: int = 1) -> list[str]:
    urls = [listing_url(resolved, page, include_fs=True)]
    without_fs = listing_url(resolved, page, include_fs=False)
    if without_fs not in urls:
        urls.append(without_fs)
    node = resolved.browse_node_id
    if node and page == 1:
        for extra in (
            f'https://{resolved.domain}/s?rh=n%3A{node}&fs=true&page=1',
            f'https://{resolved.domain}/b?node={node}',
        ):
            if extra not in urls:
                urls.append(extra)
    return urls
