#!/usr/bin/env python3
"""
Daichi catalog search for the Telegram bridge's DAICHI_SEARCH marker (2026-08-26) -
mirrors hogart-scraper/search_live.mjs's role, but Daichi's product NAMEs are cryptic
model codes (no descriptive Russian text to substring-match), so this searches the
cached, normalized catalog (daichi_catalog_cache.py) client-side instead of hitting a
"q"-style endpoint.

Filters (all optional, combine with AND):
  keyword          - matched against name/brand/series/description (case-insensitive substring)
  --goodtype       - e.g. "Комплект" (complete split system), "Наружный блок", "Внутренний блок"
  --inverter-only  - only ATTR_L_INVERTER == "Inverter"
  --capacity-kw    - target cooling capacity; kept within --tolerance kW of it
  --tolerance      - default 0.5 kW
  --in-stock-only  - only items with real positive stock_total (see catalog cache)
  --max-price      - sell_price (mprc) ceiling
  --limit          - default 10

Results sorted by sell_price ascending (cheapest first - matches how the owner actually
shops this catalog in practice). Prints a JSON list, each entry the same shape as
daichi_catalog_cache.py's per-item record (id/xml_id/name/brand/cost_price/sell_price/
stock_by_store/specs/photo_url/...) - `generate_kp.py` can take an item's `xml_id`
directly as its "sku" once the owner (via Claude) has picked one from these results.

CLI: `python3 daichi_search.py [keyword] [--goodtype X] [--inverter-only]
[--capacity-kw 2.5] [--tolerance 0.5] [--in-stock-only] [--max-price N] [--limit 10]`
"""
import argparse
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from daichi_api import DaichiAPI
import daichi_catalog_cache as cache


def _capacity_kw(item):
    nums = re.findall(r"\d+[.,]?\d*", item.get("capacity_cool_raw") or "")
    if not nums:
        return None
    return max(float(n.replace(",", ".")) for n in nums)


def search(catalog, keyword=None, goodtype=None, inverter_only=False,
           capacity_kw=None, tolerance=0.5, in_stock_only=False, max_price=None, limit=10):
    results = []
    kw = (keyword or "").strip().lower()
    for item in catalog.values():
        if kw:
            haystack = " ".join(str(item.get(f) or "") for f in ("name", "brand", "series", "description")).lower()
            if kw not in haystack:
                continue
        if goodtype and item.get("goodtype") != goodtype:
            continue
        if inverter_only and item.get("inverter") != "Inverter":
            continue
        if item.get("sell_price") is None:
            continue
        if max_price is not None and item["sell_price"] > max_price:
            continue
        if in_stock_only and not item.get("stock_total"):
            continue
        if capacity_kw is not None:
            cap = _capacity_kw(item)
            if cap is None or abs(cap - capacity_kw) > tolerance:
                continue
        results.append(item)

    results.sort(key=lambda i: i["sell_price"])
    return results[:limit]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", nargs="?", default=None)
    parser.add_argument("--goodtype", default=None)
    parser.add_argument("--inverter-only", action="store_true")
    parser.add_argument("--capacity-kw", type=float, default=None)
    parser.add_argument("--tolerance", type=float, default=0.5)
    parser.add_argument("--in-stock-only", action="store_true")
    parser.add_argument("--max-price", type=float, default=None)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    api = DaichiAPI()
    catalog = cache.load_or_refresh(api)
    results = search(
        catalog, keyword=args.keyword, goodtype=args.goodtype, inverter_only=args.inverter_only,
        capacity_kw=args.capacity_kw, tolerance=args.tolerance, in_stock_only=args.in_stock_only,
        max_price=args.max_price, limit=args.limit,
    )
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
