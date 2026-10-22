#!/usr/bin/env python3
"""
Local cache of Daichi's full catalog + per-store stock/price (2026-08-26) - mirrors
megaplan-crm/offer_catalog_cache.py's pattern (page once, cache to JSON, refresh when
stale). Needed because `productparams/get` pages 100/request (~53 pages for the full
~5250-item catalog) and `products/get` per store returns the whole store's catalog in
one call but still needs one call per warehouse - too slow to redo on every search.

**Pricing semantics (owner correction, 2026-08-26) - the API's own field NAME is
backwards from real usage**: `PRICES.BASE` (API calls it "Розничная цена") is actually
Daichi's price TO US (cost/закупка). `PRICES.mprc` ("МПРЦ") is the real retail/sell
price. This cache stores both as `cost_price`/`sell_price` respectively - never as
"base"/"mprc" - so nothing downstream has to remember the API's mislabeling.

Product NAMEs are cryptic model codes (e.g. "ECO07AN/LETTA07AN") - Daichi's own `q`-style
`filter[NAME]` search only does substring match on that code, not on descriptive Russian
text like "инвертор"/"сплит-система". Real filtering has to happen client-side on the
cached attributes - see daichi_search.py.

CLI: `python3 daichi_catalog_cache.py refresh` prints `{"ok": true, "count": N}`.
"""
import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "daichi_catalog_cache.json")
STALE_AFTER_SEC = 12 * 3600

STORES = {
    "Москва": "d56a04ef-8afd-11eb-804d-00155db05a13",
    "Химки": "3c468729-c551-11ec-8070-00155db05a13",
    "Никольское": "cfd425ff-9938-11eb-804f-00155db05a13",
}

# Attribute codes worth showing in a KP specs table - the rest (packaging dims, internal
# codes) are noise. Matches the groups seen live on real household split-system items.
SPEC_ATTR_CODES = [
    "ATTR_CAPACITY_COOL", "ATTR_CAPACITY_HEAT", "ATTR_AREA",
    "ATTR_POWINPUT_COOL_NOM", "ATTR_POWINPUT_HEAT_NOM",
    "ATTR_EER_CLASS", "ATTR_COP_CLASS", "ATTR_ANNUAL_POW_IN_NOM",
    "ATTR_L_CLASS_NOMCOOL", "ATTR_L_CLASS_NOMHEAT", "ATTR_MAIN_MODES",
    "ATTR_SOUND_PRESSURE_IU_COOL", "ATTR_AIRFLOW_IU_COOL", "ATTR_DEHUM",
    "ATTR_PIPING_LIQ", "ATTR_PIPING_GAS", "ATTR_PIPING_LENGTH_MAX", "ATTR_PIPING_DIFF_MAX",
    "ATTR_L_REFR", "ATTR_L_COLOR", "ATTR_POWER_SUPPLY", "ATTR_SROK_EKSP", "ATTR_STRANA",
    "ATTR_WEIGHT_NET_IU", "ATTR_WEIGHT_NET_OU", "ATTR_DIMENS_IU", "ATTR_DIMENS_OU",
]


_SUP_DIGITS = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴"}


def _clean_daichi_text(s):
    """Daichi's own attribute NAMEs come through with literal HTML-entity text baked in
    (e.g. the raw string 'м&lt;sup&gt;2&lt;/sup&gt;' for "м²") - a quirk of whatever CMS
    export produced their API. Rendering that straight into an already-html.escape()'d
    template double-escapes it, so it shows up as the literal entity codes on the page
    (found 2026-08-26, first real multi-source KP test - see generate_kp.py). Unescape
    once, then replace <sup>N</sup> with a real unicode superscript digit and strip any
    other leftover tags, rather than passing real HTML through a text-only template."""
    if not s:
        return s
    s = html.unescape(s)
    s = re.sub(r"<sup>(\d)</sup>", lambda m: _SUP_DIGITS.get(m.group(1), m.group(1)), s)
    s = re.sub(r"<[^>]+>", "", s)
    return s


def _refresh_productparams(api):
    first = api.get_productparams(page=1, page_size=100)
    all_params = dict(first["data"])
    total = int(first["total_count"])
    if total > len(all_params):
        if not all_params:
            raise ValueError('Daichi returned an empty first page for a nonempty catalog')
        page_count = (total + len(all_params) - 1) // len(all_params)
        # Independent read-only pages; bound load on the supplier to four requests.
        with ThreadPoolExecutor(max_workers=4) as pool:
            pages = pool.map(lambda page: api.get_productparams(page=page, page_size=100), range(2, page_count + 1))
            for result in pages:
                all_params.update(result["data"])
        if len(all_params) < total:
            raise ValueError('Daichi catalog refresh is incomplete')
    return all_params


def refresh(api):
    all_params = _refresh_productparams(api)

    products_by_store = {}
    for store_name, store_id in STORES.items():
        r = api.get_products(store_id=store_id)
        products_by_store[store_name] = {k: v for k, v in r.items() if k != "_count"}

    catalog = {}
    for pid, spec in all_params.items():
        cost_price = None
        sell_price = None
        stock_by_store = {}
        for store_name, products in products_by_store.items():
            prod = products.get(pid)
            if not prod:
                continue
            prices = prod.get("PRICES") or {}
            base = prices.get("BASE")
            mprc = prices.get("mprc")
            if cost_price is None and base and base.get("PRICE"):
                cost_price = float(base["PRICE"])
            if sell_price is None and mprc and mprc.get("PRICE"):
                sell_price = float(mprc["PRICE"])
            stock_by_store[store_name] = (prod.get("STORE") or {}).get("STORE_AMOUNT") or 0

        specs = {}
        for code in SPEC_ATTR_CODES:
            attr = spec.get(code)
            if attr:
                specs[code] = {
                    "name": _clean_daichi_text(attr.get("NAME")),
                    "value": _clean_daichi_text(attr.get("VALUE")),
                }

        catalog[pid] = {
            "id": pid,
            "xml_id": spec.get("XML_ID"),
            "name": spec.get("NAME"),
            "brand": spec.get("BRAND"),
            "series": _clean_daichi_text((spec.get("ATTR_L_SERIA") or {}).get("VALUE")),
            "description": _clean_daichi_text((spec.get("ATTR_DESCRIPTIONS") or {}).get("VALUE")),
            "goodgroup": (spec.get("ATTR_L_GOODGROUP") or {}).get("VALUE"),
            "goodtype": (spec.get("ATTR_L_GOODTYPE") or {}).get("VALUE"),
            "inverter": (spec.get("ATTR_L_INVERTER") or {}).get("VALUE"),
            "refrigerant": (spec.get("ATTR_L_REFR") or {}).get("VALUE"),
            "area_m2_raw": (spec.get("ATTR_AREA") or {}).get("VALUE"),
            "capacity_cool_raw": (spec.get("ATTR_CAPACITY_COOL") or {}).get("VALUE") or (spec.get("ATTR_CAP_COOL_NOM") or {}).get("VALUE"),
            "photo_url": (spec.get("PHOTOES") or [None])[0],
            "photos": spec.get("PHOTOES") or [],
            "specs": specs,
            "cost_price": cost_price,
            "sell_price": sell_price,
            "stock_by_store": stock_by_store,
            "stock_total": sum(stock_by_store.values()),
        }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"updated_at": time.time(), "catalog": catalog}, f, ensure_ascii=False)
    return catalog


def load_or_refresh(api):
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        if time.time() - cached.get("updated_at", 0) < STALE_AFTER_SEC:
            return cached["catalog"]
    return refresh(api)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, BASE_DIR)
    from daichi_api import DaichiAPI
    api = DaichiAPI()
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        catalog = refresh(api)
        print(json.dumps({"ok": True, "count": len(catalog)}, ensure_ascii=False))
    else:
        print(__doc__)
