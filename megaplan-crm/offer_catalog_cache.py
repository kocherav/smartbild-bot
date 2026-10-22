#!/usr/bin/env python3
"""
Local cache of Megaplan's Offer catalog, for name-matching (Phase 1b's "check Мегаплан's
own catalog first" tier - see create_deal_from_spec).

Why this exists (2026-08-23): `GET /offer?q=<name>` - what `search_offer_candidate()`
originally used - turned out to return ZERO results for EVERY query tested, including
an offer's own exact name and exact article (confirmed empirically against a real
account with 4183 offers - a real catalog entry for "Вентиляционная установка Komfovent
ОТД-R-KV-2.5-F-E-R1-M5/M5/1794-GTC-L/A" at 453 000₽ existed and was never found, so the
bot created a duplicate at 0₽ instead of reusing it). The `q` param on this endpoint is
simply non-functional in this account/API version - there's no dedicated `/offer/search`
route either (unlike `/contractorCompany/search`, which does work). `/offerFilter` is a
saved-filter *resource* (title/count/href/owner), not an ad-hoc query builder, so that's
not a substitute either.

The fix: page through the WHOLE catalog once (confirmed working - same `pageAfter`
cursor pattern as `/invoice`/`/deal`, ~500 offers per 2.5s, ~21s for the full 4183),
cache name/price/cost locally, and match client-side (exact, then fuzzy via
difflib). Refreshed automatically when stale (see STALE_AFTER_SEC) - the catalog only
grows (every deal clones referenced offers into new catalog entries, see
create_deal_from_spec's docstring), so a somewhat-stale cache just means a recently
cloned duplicate might not be found yet, not that it'll ever return wrong data.
"""
import json
import os
import time
from difflib import SequenceMatcher

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "offer_catalog_cache.json")
STALE_AFTER_SEC = 12 * 3600  # refresh at most twice a day - catalog only grows, no rush
PAGE_SIZE = 200
MIN_MATCH_RATIO = 0.85  # below this, better to treat as "not found" than risk a wrong match


CATALOG_FIELDS = [
    "name", "price", "Category1000045CustomFieldTsenaZakupki", "Category1000045CustomFieldSebesRabot",
]


def refresh(api):
    """Page through the entire Offer catalog and cache id/name/price/cost. `api` is a
    MegaplanAPI instance (passed in, not imported, to avoid a circular import with
    megaplan_api.py).

    2026-08-24: found (owner noticed the review file's cost columns were always blank
    even for offers that demonstrably have real cost data, e.g. offer 13106) that
    `GET /offer` LIST responses only ever include a small fixed default field set
    (name/quantity/article/unit/price/tax/...) - the two custom cost fields are simply
    absent from every list row regardless of whether that offer actually has them set,
    unless explicitly requested via `fields`. A single `GET /offer/{id}` DOES return
    them without asking - that asymmetry is what made this easy to miss while spot-
    testing individual offers earlier. Must pass `fields` (a JSON array, not a comma
    string - same quirk as everywhere else in this API) on every list page."""
    offers = []
    params = {"limit": PAGE_SIZE, "fields": CATALOG_FIELDS}
    last_id = None
    while True:
        if last_id is not None:
            params = {"limit": PAGE_SIZE, "fields": CATALOG_FIELDS, "pageAfter": {"contentType": "Offer", "id": last_id}}
        result = api._call("GET", "/offer", params=params)
        data = result.get("data") or []
        if not data:
            break
        for o in data:
            offers.append({
                "id": o["id"], "name": o.get("name") or "",
                "price": (o.get("price") or {}).get("value"),
                "cost_material": (o.get("Category1000045CustomFieldTsenaZakupki") or {}).get("value"),
                "cost_work": (o.get("Category1000045CustomFieldSebesRabot") or {}).get("value"),
            })
        last_id = data[-1]["id"]
        if not result.get("meta", {}).get("pagination", {}).get("hasMoreNext"):
            break
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"updated_at": time.time(), "offers": offers}, f, ensure_ascii=False)
    return offers


def _load_or_refresh(api):
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        if time.time() - cached.get("updated_at", 0) < STALE_AFTER_SEC:
            return cached["offers"]
    return refresh(api)


def _candidate(o):
    return {
        "id": o["id"], "name": o["name"], "price": o["price"],
        "cost_material": o.get("cost_material"), "cost_work": o.get("cost_work"),
    }


def find_candidate(api, name):
    """Find the best-matching catalog Offer for `name`. Exact (case-insensitive) match
    wins outright; otherwise the highest-similarity fuzzy match above MIN_MATCH_RATIO.
    Returns {"id", "name", "price", "cost_material", "cost_work"} or None.

    2026-08-24: this used to strip the cost fields out of the return value even though
    `refresh()` already caches them - the review file ended up with a blank
    "Себестоимость" column for a catalog match that actually had real "Цена закупки"/
    "Себестоимость работ" values sitting on the matched Offer in Мегаплан the whole
    time. Now returned as-is (either can legitimately be None if that offer never had
    them filled in - the caller still wants the price even then)."""
    offers = _load_or_refresh(api)
    target = name.strip().lower()
    best, best_ratio = None, 0.0
    for o in offers:
        o_name = o["name"].strip().lower()
        if o_name == target:
            return _candidate(o)
        ratio = SequenceMatcher(None, target, o_name).ratio()
        if ratio > best_ratio:
            best, best_ratio = o, ratio
    if best and best_ratio >= MIN_MATCH_RATIO:
        return _candidate(best)
    return None


if __name__ == "__main__":
    import sys
    sys.path.insert(0, BASE_DIR)
    from megaplan_api import MegaplanAPI
    api = MegaplanAPI()
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        offers = refresh(api)
        print(json.dumps({"ok": True, "count": len(offers)}, ensure_ascii=False))
    elif len(sys.argv) > 2 and sys.argv[1] == "find":
        print(json.dumps(find_candidate(api, sys.argv[2]), ensure_ascii=False))
    else:
        print(__doc__)
