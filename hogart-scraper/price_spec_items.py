#!/usr/bin/env python3
"""
Tiered price/cost resolution for raw spec items (Phase 1b, 2026-08-23) - covers the
Hogart and Kemiks tiers of the owner's pricing algorithm for "создай сделку по
спецификации" (Megaplan's own catalog is checked separately, in megaplan_api.py's
create-deal-from-spec, since that's where the catalog lives).

Usage: stdin JSON {"items": [{"name": "...", "qty": 2, "hogart_sku": "..." (optional)}, ...]}.
`hogart_sku` should already be the exact article Claude resolved via HOGART_SEARCH for
this item, same as Phase 1's install/freon-line flow (price_install_addons.py) - this
script does NOT fuzzy-match a bare equipment name against Hogart's catalog itself, only
looks up the exact article if one is given (Hogart's `search_products` is a broad
keyword search that returns dozens of loosely-related hits for a descriptive name -
letting an LLM disambiguate via HOGART_SEARCH first, like it already does elsewhere in
this project, is much safer than a script guessing). Items with no hogart_sku just skip
straight to the Kemiks tier (which matches on descriptive Russian text, not articles).

Prints JSON to stdout: {"ok": true, "resolved": [{"name": "...", "qty": ...,
"sell_price": ..., "cost_price": ..., "price_source": "hogart"|"kemiks"}, ...],
"unresolved": [{"name": "...", "qty": ...}, ...]} (items not matched by either tier -
caller sets price_source="unresolved", sell_price=0, cost_price=None for these).

Daichi is deliberately not wired in yet - `project_daichi_api.md` notes its API token
is still pending a real value, so there's nothing useful to query yet. Add a Daichi
lookup here (same shape as the Hogart one below) once that lands, ahead of Kemiks in
the tier order per the plan.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hogart_api import HogartAPI, HogartAPIError
from pipe_reference import (
    KEMIX_PIPE_SKU_BY_MM, KEMIX_INSULATION_SKU_BY_ID_MM, CABLE_INTERCONNECT, ceil_to_50,
)

# Same markup convention already established for the freon-line composite material
# price in pipe_reference.py (materials cost -> sell = cost x2, rounded up to the
# nearest 50 rub) - there's no other standalone markup convention on record for a bare
# Kemiks item, so this is the closest consistent choice rather than inventing a new one.
KEMIX_MARKUP_MULTIPLIER = 2


def hogart_lookup(api, sku):
    """Look up the authoritative price for an EXACT Hogart article (already resolved by
    Claude via HOGART_SEARCH, never guessed here from a bare name - see module
    docstring). Returns (sell_price, cost_price) or None if the article doesn't
    actually exist. Same exact-match-among-results pattern as generate_kp.py's
    live_lookup() - search_products() is a broad keyword search that can return dozens
    of loosely-related hits even for a full article string."""
    try:
        items = api.search_products(keyword=sku)
    except HogartAPIError:
        return None
    product = next((it for it in items if it.get("article", "").strip().lower() == sku.strip().lower()), None)
    if product is None:
        return None
    sell = product.get("defaultPrice")
    cost = product.get("contractPrice")
    if sell is None:
        return None
    return float(sell), (float(cost) if cost is not None else None), str(product.get("id"))


_MM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:мм|mm)\b", re.IGNORECASE)
_FRACTION_INCH_MM = {"1/4": 6.35, "3/8": 9.52, "1/2": 12.7, "5/8": 15.88, "3/4": 19.05}


def _extract_diameter_mm(name):
    """Best-effort diameter extraction from a free-text item name: a plain 'NN мм'
    number, or a fractional-inch pipe size (1/4", 3/8", etc - Kemix's own catalog
    naming), mapped to its known OD in mm."""
    for frac, mm in _FRACTION_INCH_MM.items():
        if frac in name:
            return mm
    m = _MM_RE.search(name)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def kemiks_lookup(name):
    """Best-effort Kemiks match: pipe (by OD mm), insulation (by ID mm), or cable, all
    keyed by keywords already used consistently elsewhere in this project (see
    pipe_reference.py / bridge.py's SYSTEM_PROMPT for the same vocabulary)."""
    lower = name.lower()
    if "кабель" in lower and ("ввг" in lower or "vvg" in lower):
        cost = CABLE_INTERCONNECT["price_per_m"]
        return ceil_to_50(cost * KEMIX_MARKUP_MULTIPLIER), cost

    mm = _extract_diameter_mm(name)
    if mm is None:
        return None

    if "труб" in lower and "изоля" not in lower and "армафлекс" not in lower and "armaflex" not in lower:
        entry = KEMIX_PIPE_SKU_BY_MM.get(mm)
        if entry:
            cost = entry["price_per_m"]
            return ceil_to_50(cost * KEMIX_MARKUP_MULTIPLIER), cost
    if "изоля" in lower or "армафлекс" in lower or "armaflex" in lower or "трубка" in lower:
        entry = KEMIX_INSULATION_SKU_BY_ID_MM.get(int(mm))
        if entry:
            cost = entry["price_per_m"]
            return ceil_to_50(cost * KEMIX_MARKUP_MULTIPLIER), cost
    return None


def main():
    spec = json.load(sys.stdin)
    api = HogartAPI()
    resolved = []
    unresolved = []
    for item in spec.get("items") or []:
        name, qty = item["name"], item["qty"]
        hit = hogart_lookup(api, item["hogart_sku"]) if item.get("hogart_sku") else None
        if hit:
            sell, cost, product_id = hit
            resolved.append({"name": name, "qty": qty, "sell_price": sell, "cost_price": cost,
                             "price_source": "hogart", "supplier": "hogart",
                             "supplier_sku": item["hogart_sku"], "supplier_product_id": product_id})
            continue
        hit = kemiks_lookup(name)
        if hit:
            sell, cost = hit
            resolved.append({"name": name, "qty": qty, "sell_price": sell, "cost_price": cost, "price_source": "kemiks"})
            continue
        unresolved.append({"name": name, "qty": qty})

    print(json.dumps({"ok": True, "resolved": resolved, "unresolved": unresolved}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
