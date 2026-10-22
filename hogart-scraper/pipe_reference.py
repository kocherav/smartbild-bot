#!/usr/bin/env python3
"""
KP economics for two line items, per owner's spec (2026-08-21):

1. "Стандартный монтаж кондиционера, мощностью X кВт" - fixed price by capacity tier
   (INSTALL_PRICE_BY_CAPACITY_KW), X = the same peak/upper-bound cooling capacity (kW)
   already used below for pipe-diameter selection - one kW lookup serves both decisions.
2. "Дополнительная фреоновая магистраль" (per meter) - see freon_line_price_per_meter():
   cost_basis (себестоимость) = (2 copper pipes + 2 insulation + interconnect cable,
   all priced from КЕМИКС's price list, NOT Hogart) x 1.10, PLUS labor
   (LABOR_PRICE_BY_CAPACITY_KW, added after the 1.10 - owner caught this missing piece
   2026-08-21, labor isn't a purchased material so doesn't get the materials markup);
   sell price = cost_basis x 2, rounded UP to the nearest 50р. Uses
   KEMIX_PIPE_SKU_BY_MM / KEMIX_INSULATION_SKU_BY_ID_MM / CABLE_INTERCONNECT /
   LABOR_PRICE_BY_CAPACITY_KW below - real numbers from the owner's own КЕМИКС price
   list and invoice #53168 (attached 2026-08-21), not the earlier broken AJAX probing.

Earlier (superseded) Hogart-priced version of the same pipe/insulation reference is kept
below as HOGART_PIPE_SKU_BY_MM / HOGART_INSULATION_SKU_BY_ID_MM / hogart_freon_line_cost_
per_meter() purely for comparison (see the Hogart-vs-Kemix price comparison earlier in
this conversation) - the real KP formula now uses the Kemix-sourced functions instead.

**Prices are refreshed from `kemix_prices.json`** (owner sends a fresh КЕМИКС price-list
PDF to the Telegram bot every ~6 weeks; see the update mechanism this file loads at
import time below) - the KEMIX_* dicts hardcoded further down are the fallback/original
values, overridden at import time by whatever `kemix_prices.json` has, if present.

Where the pipe-diameter-by-capacity numbers come from:
- Pipe diameter by capacity (PIPE_BY_CAPACITY_KW): read directly off official Haier
  installation-spec pages (haier-rus.ru product pages, 2026-08-20) for ~10 real models
  spanning 0.8-13.5 kW peak cooling. Confirmed the diameter tracks *actual cooling
  capacity in kW*, NOT the marketing class number in the article (e.g. Tundra
  "AS18TT5HRA" peaks at 5.8kW and needs a 1/2" gas line, while Flexis "AS25S2SF3FA"
  peaks at only 3.2kW and only needs 3/8" - the "18"/"25" digits are not comparable
  across series). Always look up the real kW from the product's own `features[]`
  (Hogart `холодопроизводительность, кВт` upper bound), never parse it out of the
  article string.
- Hogart SKUs for pipe/insulation (HOGART_PIPE_SKU_BY_MM, HOGART_INSULATION_SKU_BY_ID_MM): found by
  searching hogart_api.py `search_products()` for the exact mm figure (e.g. "9,52") and
  for "K-FLEX ST" (iterated the whole sub-catalog via `iter_all_products`). K-FLEX ST
  article/name format is WALL x ID in mm (e.g. "09х12" = 9mm wall, 12mm bore) - verified
  against real per-meter prices, not guessed (an earlier reading of the code as ID x WALL
  didn't hold up: there is no ID=13mm variant at all in the wall-9 line, and the actual
  in-catalog set of second-number values - 6,8,10,12,15,18,22,25,28,30,35,42,48,54,60,70,
  80,89,102,108,114,133,140 - matches the ID series, not a wall-thickness series).
- Hogart does NOT sell electrical cable (searched "кабель ВВГ/ПВС/силовой/межблочный" -
  zero hits; they're an HVAC/plumbing distributor, not an electrical one). Owner's fixed
  choice for the "межблочный кабель" part: ВВГнг LS 5x2,5, priced from КЕМИКС
  (kemixspb.ru), not Hogart.
- КЕМИКС's own site (kemixspb.ru, Joomla/JShopping) shows "0.00 р." on the static page -
  price is (supposedly) AJAX-loaded per attribute combo via
  `POST /component/jshopping/product/ajax_attrib_select_and_price/<product_id>?ajax=1&Itemid=0`.
  **This turned out NOT to be reliable and the earlier "300 р./м, confirmed" claim in
  this conversation was wrong** - caught by cross-checking: calling the same endpoint
  with NO attributes selected at all (`quantity=1&product_id=<id>` only) still returned
  "300.00 р." for both the cable product (175) AND, separately, the copper-pipe product
  (209) *regardless of which diameter (1/4" through 7/8") was selected* - a 1/4" and a
  7/8" copper pipe cannot plausibly cost the same, so this is an unconfigured/placeholder
  base price on Kemix's product master, not a real attribute-specific figure (other,
  unrelated product ids returned 0.00 or other flat numbers with the same no-attribute
  call, confirming it's not a universal site-wide constant either - just not wired up for
  these two specific "master" products). **Conclusion: Kemix's public site does not
  expose trustworthy per-item pricing for this cable or these pipes without a real
  dealer/B2B login** - same situation Hogart itself was in before the owner got official
  API access. Don't trust a single AJAX response as "confirmed" without sanity-checking
  it against at least one other attribute combo on the same product first (would have
  caught this immediately - a real price table changes with diameter/cross-section, a
  placeholder doesn't).
"""

CABLE_INTERCONNECT = {
    "name": "Кабель ВВГнг LS 5х2,5",
    "supplier": "КЕМИКС (kemixspb.ru), прайс-лист владельца от 2026-08-21",
    "price_per_m": 156.06,
    "price_per_m_gost": 210.35,
    "coil_m": 100,
    "note": "Real price list figure (not the earlier broken AJAX probe). Two variants "
            "exist: plain 'Кабель ВВГнг LS 0,66кВ 5*2,5' (156.06р/м, used by default) and "
            "'ГОСТ Кабель ВВГнг LS 0,66кВ 5*2,5' (210.35р/м, certified) - swap in "
            "price_per_m_gost if the owner wants the GOST-certified cable instead.",
}

# Peak/upper-bound cooling capacity (kW) -> (liquid line OD mm, gas line OD mm).
# Verified against real Haier product pages; gaps above 13.5 kW not yet checked.
PIPE_BY_CAPACITY_KW = [
    (4.5, 6.35, 9.52),    # up to ~4.5 kW: 1/4" liquid, 3/8" gas
    (6.0, 6.35, 12.7),    # ~5.0-6.0 kW: 1/4" liquid, 1/2" gas
    (11.0, 9.52, 15.88),  # ~7.0-11 kW: 3/8" liquid, 5/8" gas
    (14.0, 9.52, 19.05),  # ~13.5 kW: 3/8" liquid, 3/4" gas
]


def pipe_diameters_for_capacity(cooling_kw_max):
    """Given a product's peak cooling capacity (kW, from Hogart features
    'холодопроизводительность, кВт' upper bound), return (liquid_mm, gas_mm).
    Raises ValueError if above the verified range (>14 kW - not yet researched)."""
    for cap, liquid_mm, gas_mm in PIPE_BY_CAPACITY_KW:
        if cooling_kw_max <= cap:
            return liquid_mm, gas_mm
    raise ValueError(f"no verified pipe-diameter data above 14 kW (got {cooling_kw_max})")


# Copper pipe by OD mm -> Hogart article + real price-per-meter (derived from list price;
# see coil_m for the minimum order batch these actually ship in).
HOGART_PIPE_SKU_BY_MM = {
    6.35: {
        "article": "Cu-DHP R220 EN12735-1 (ICG) (6,35х0,76х15000 (1/4))",
        "name": "Труба медная, ICG, Cu-DHP R220 EN12735-1, 1/4\" (6,35мм)",
        "price_per_m": 264.0,
        "coil_m": 15,
    },
    9.52: {
        "article": "STANDART 15 м 3/8\" (9,52 х 0,81 х 15 м) ASTM B280",
        "name": "Труба медная, ICG, STANDART, 3/8\" (9,52мм), бухта 15м",
        "price_per_m": round(8566.6 / 15, 2),  # this SKU is priced per-coil (шт), not per-m
        "coil_m": 15,
        "note": "priced as a whole 15m coil (8566.60р/шт) in Hogart, not per meter - divided here",
    },
    12.7: {
        "article": "Cu-DHP 12,7х0,71х15000 1/2",
        "name": "Медная труба, Sharq Tubes, Cu-DHP R220 EN12735-1, 1/2\" (12,7мм)",
        "price_per_m": 573.4,
        "coil_m": 15,
    },
    15.88: {
        "article": "Cu-DHP R220 EN12735-1 (ST) (15,88х0,75х15000 (5/8))",
        "name": "Труба медная, Cu-DHP R220 EN12735-1, 5/8\" (15,88мм)",
        "price_per_m": 698.0,
        "coil_m": 15,
    },
    19.05: {
        "article": "Cu-DHP 19,05х0,81х15000 3/4",
        "name": "Медная труба, Sharq Tubes, Cu-DHP R220 EN12735-1, 3/4\" (19,05мм)",
        "price_per_m": 995.16,
        "coil_m": 15,
    },
}

# K-FLEX ST insulation, wall=9mm always (owner's spec), keyed by bore/ID mm that fits
# over the pipe OD above (chosen as the smallest standard K-FLEX ID >= pipe OD).
HOGART_INSULATION_SKU_BY_ID_MM = {
    6: {
        "article": "09006005508",
        "name": "Трубка K-FLEX ST 9х06 (стенка 9мм, диам. 6мм)",
        "price_per_m": 54.9,
        "fits_pipe_od_mm": 6.35,
    },
    10: {
        "article": "R09010215508",
        "name": "Трубка K-FLEX ST 9х10 (стенка 9мм, диам. 10мм)",
        "price_per_m": 58.97,
        "fits_pipe_od_mm": 9.52,
    },
    12: {
        "article": "R09012215508",
        "name": "Трубка K-FLEX ST 9х12 (стенка 9мм, диам. 12мм)",
        "price_per_m": 61.0,
        "fits_pipe_od_mm": 12.7,
        "note": "tight fit - ID 12mm vs pipe OD 12.7mm. R09015215508 (9х15, 69.13р/м) is the "
                "next size up if a looser/easier-to-install fit is wanted.",
    },
    18: {
        "article": "R09018215508",
        "name": "Трубка K-FLEX ST 9х18 (стенка 9мм, диам. 18мм)",
        "price_per_m": 74.22,
        "fits_pipe_od_mm": 15.88,
    },
    22: {
        "article": "R09022215508",
        "name": "Трубка K-FLEX ST 9х22 (стенка 9мм, диам. 22мм)",
        "price_per_m": 88.45,
        "fits_pipe_od_mm": 19.05,
    },
}

# OD mm -> insulation ID mm to use (smallest standard K-FLEX bore that clears the pipe OD)
INSULATION_ID_FOR_PIPE_OD_MM = {
    6.35: 6,
    9.52: 10,
    12.7: 12,
    15.88: 18,
    19.05: 22,
}


def hogart_freon_line_cost_per_meter(cooling_kw_max, cable_price_per_m=None):
    """Cost per meter of the 'Дополнительная фреоновая магистраль' KP line item:
    liquid pipe + its insulation + gas pipe + its insulation (+ cable, if a price is
    supplied - Hogart doesn't sell cable, so this is None/omitted by default).
    Returns a dict breakdown; total excludes cable unless cable_price_per_m is given."""
    liquid_mm, gas_mm = pipe_diameters_for_capacity(cooling_kw_max)
    liquid_pipe = HOGART_PIPE_SKU_BY_MM[liquid_mm]
    gas_pipe = HOGART_PIPE_SKU_BY_MM[gas_mm]
    liquid_ins = HOGART_INSULATION_SKU_BY_ID_MM[INSULATION_ID_FOR_PIPE_OD_MM[liquid_mm]]
    gas_ins = HOGART_INSULATION_SKU_BY_ID_MM[INSULATION_ID_FOR_PIPE_OD_MM[gas_mm]]

    materials_total = (
        liquid_pipe["price_per_m"] + liquid_ins["price_per_m"]
        + gas_pipe["price_per_m"] + gas_ins["price_per_m"]
    )
    total = materials_total + (cable_price_per_m or 0)

    return {
        "liquid_pipe": liquid_pipe, "liquid_insulation": liquid_ins,
        "gas_pipe": gas_pipe, "gas_insulation": gas_ins,
        "cable_price_per_m": cable_price_per_m,
        "materials_total_per_m": round(materials_total, 2),
        "total_per_m": round(total, 2),
    }


# ============================================================================
# Real KP formula (2026-08-21): install price tiers + Kemix-priced freon line
# ============================================================================

import json
import math
import os
import re

# Peak/upper-bound cooling capacity (kW) -> fixed install price, owner's tiers.
# Same kW value as PIPE_BY_CAPACITY_KW above (peak/upper bound of Hogart's
# "холодопроизводительность, кВт" feature) - one capacity lookup for both decisions.
INSTALL_PRICE_BY_CAPACITY_KW = [
    (3.5, 20000),
    (5.5, 23000),
    (8.0, 27000),
    (10.5, 32000),
]


def install_price_for_capacity(cooling_kw_max):
    """Fixed 'Стандартный монтаж кондиционера' price for this peak cooling capacity (kW).
    Raises ValueError above 10.5 kW - owner hasn't given a tier for that yet."""
    for cap, price in INSTALL_PRICE_BY_CAPACITY_KW:
        if cooling_kw_max <= cap:
            return price
    raise ValueError(f"no install price tier above 10.5 kW (got {cooling_kw_max})")


def parse_cooling_capacity_kw(features):
    """Pull the peak/upper-bound value out of Hogart's 'холодопроизводительность, кВт'
    feature (e.g. 'от 0.79 до 5.5' -> 5.5; a bare '5' -> 5.0). Returns None if the
    feature is missing entirely (some equipment, e.g. chillers, ship with an empty
    features[] - see the residential/semi-industrial/industrial characteristics
    research earlier in this conversation) or has no parseable number."""
    for f in features or []:
        name = (f.get("name") or "").strip().lower()
        if name.startswith("холодопроизводительность"):
            nums = re.findall(r"\d+[.,]?\d*", str(f.get("value") or ""))
            if not nums:
                return None
            return max(float(n.replace(",", ".")) for n in nums)
    return None


def ceil_to_50(x):
    return math.ceil(x / 50) * 50


# Copper pipe by OD mm, priced from the owner's own КЕМИКС price list (2026-08-21,
# re-checked in full - all 34 pages - 2026-08-22 after initially only skimming the
# first section; see the lesson note below). HARD SHARQ tier where it exists (cheaper
# of the two ASTM B280 lines Kemix carries, tracks the owner's real invoice #53168
# within ~1-13% - see the Hogart-vs-Kemix comparison earlier in this conversation);
# Kemix doesn't stock a SHARQ variant for 5/8" or 3/4" at all (confirmed by grepping
# the full extracted text for "SHARQ" - only 1/4", 3/8", 1/2" have one), so those two
# use the plain HARD line instead.
#
# LESSON (2026-08-22): the owner caught that the 3/4" entry was actually in the price
# list all along - I'd stopped scanning after the first section that didn't have it.
# **Don't stop at the first section/page without a match in a multi-page supplier
# document - grep/read the WHOLE thing (`pymupdf` page-by-page text extraction, not
# just the Read tool's rendered preview) before concluding a price isn't listed.**
KEMIX_PIPE_SKU_BY_MM = {
    6.35: {
        "name": "Труба медная HARD SHARQ 1/4\" (6,35х0,76х15м) ASTM B280",
        "price_per_m": 170.91,
        "coil_m": 15,
    },
    9.52: {
        "name": "Труба медная HARD SHARQ 3/8\" (9,52х0,80х15м) ASTM B280",
        "price_per_m": 288.90,
        "coil_m": 15,
    },
    12.7: {
        "name": "Труба медная HARD SHARQ 1/2\" (12,7х0,81х15м) ASTM B280",
        "price_per_m": 338.35,
        "coil_m": 15,
    },
    15.88: {
        "name": "Труба медная HARD 5/8\" (15,88х0,89х15м) ASTM B280",
        "price_per_m": 608.40,
        "coil_m": 15,
        "note": "no SHARQ variant stocked by Kemix for this size, using plain HARD",
    },
    19.05: {
        "name": "Труба медная HARD 3/4\" (19,05х0,89х15м)",
        "price_per_m": 741.78,
        "coil_m": 15,
        "note": "no SHARQ variant stocked by Kemix for this size, using plain HARD",
    },
}

# Armaflex ACe insulation, wall=9mm (owner's spec), keyed by bore/ID mm - Kemix's
# equivalent of the K-FLEX line above (Kemix doesn't carry K-FLEX at all). All sizes
# needed for the pipe ODs above are now confirmed against the full 34-page price list.
KEMIX_INSULATION_SKU_BY_ID_MM = {
    6: {"name": "Трубка Armaflex ACe 09х006 (стенка 9мм, диам. 6мм)", "price_per_m": 37.26},
    10: {"name": "Трубка Armaflex ACe 09х010 (стенка 9мм, диам. 10мм)", "price_per_m": 38.76},
    12: {"name": "Трубка Armaflex ACe 09х012 (стенка 9мм, диам. 12мм)", "price_per_m": 40.92},
    18: {"name": "Трубка Armaflex ACe 09х018 (стенка 9мм, диам. 18мм)", "price_per_m": 43.92},
    22: {"name": "Трубка Armaflex ACe 09х022 (стенка 9мм, диам. 22мм)", "price_per_m": 39.36},
}

KEMIX_PRICES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kemix_prices.json")
KEMIX_PRICES_UPDATED_AT = None  # set by _load_kemix_price_overrides() below, if the file exists


def _load_kemix_price_overrides():
    """Override the hardcoded KEMIX_* dicts/CABLE_INTERCONNECT above with whatever
    `kemix_prices.json` has, if it exists - that file is rewritten by
    `update_kemix_prices.py` whenever the owner sends a fresh КЕМИКС price list to the
    Telegram bot (see bridge.py's UPDATE_KEMIX_PRICES marker). Falls back to the
    hardcoded values above (silently) if the file is missing/unreadable/malformed -
    those are real, previously-confirmed prices, a reasonable fallback, not a guess."""
    global KEMIX_PRICES_UPDATED_AT
    try:
        with open(KEMIX_PRICES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return

    for mm_str, entry in (data.get("pipe_price_per_m") or {}).items():
        mm = float(mm_str)
        if mm in KEMIX_PIPE_SKU_BY_MM:
            KEMIX_PIPE_SKU_BY_MM[mm]["price_per_m"] = entry["price"]
            KEMIX_PIPE_SKU_BY_MM[mm]["name"] = entry.get("name", KEMIX_PIPE_SKU_BY_MM[mm]["name"])

    for id_str, entry in (data.get("insulation_price_per_m") or {}).items():
        id_mm = int(id_str)
        if id_mm in KEMIX_INSULATION_SKU_BY_ID_MM:
            KEMIX_INSULATION_SKU_BY_ID_MM[id_mm]["price_per_m"] = entry["price"]
            KEMIX_INSULATION_SKU_BY_ID_MM[id_mm]["name"] = entry.get(
                "name", KEMIX_INSULATION_SKU_BY_ID_MM[id_mm]["name"]
            )

    cable = data.get("cable") or {}
    if "price_per_m" in cable:
        CABLE_INTERCONNECT["price_per_m"] = cable["price_per_m"]
    if "price_per_m_gost" in cable:
        CABLE_INTERCONNECT["price_per_m_gost"] = cable["price_per_m_gost"]

    KEMIX_PRICES_UPDATED_AT = data.get("updated_at")


_load_kemix_price_overrides()


def kemix_prices_age_days():
    """Days since kemix_prices.json was last updated, or None if never loaded (missing
    file / bad date). Used both by the Telegram bot's staleness nag and to flag a stale
    price warning inside a KP's economics if it's gotten too old."""
    if not KEMIX_PRICES_UPDATED_AT:
        return None
    try:
        import datetime
        updated = datetime.date.fromisoformat(KEMIX_PRICES_UPDATED_AT)
        return (datetime.date.today() - updated).days
    except ValueError:
        return None

# Работа по прокладке трассы (owner's addition, 2026-08-21) - per meter, by the same
# peak cooling capacity (kW) used everywhere else. Added AFTER materials get their 10%
# (labor isn't a purchased material, doesn't get the same waste/logistics markup) -
# owner confirmed this is what they'd missed in the original formula, not a change to
# how materials themselves are priced.
LABOR_PRICE_BY_CAPACITY_KW = [
    (3.5, 600),
    (5.5, 700),
    (7.2, 800),
    (10.5, 1000),
]


def labor_price_for_capacity(cooling_kw_max):
    """Прокладка трассы, руб/м, by peak cooling capacity (kW). Raises ValueError above
    10.5 kW - owner hasn't given a tier for that yet."""
    for cap, price in LABOR_PRICE_BY_CAPACITY_KW:
        if cooling_kw_max <= cap:
            return price
    raise ValueError(f"no trassa labor price tier above 10.5 kW (got {cooling_kw_max})")


def freon_line_price_per_meter(cooling_kw_max):
    """'Дополнительная фреоновая магистраль' - owner's formula (2026-08-21, revised
    2026-08-21): себестоимость = (труба жидкостная + труба газовая + изоляция x2 +
    кабель ВВГнг LS 5х2,5) x 1.10, все цены материалов из прайса КЕМИКС, + работа по
    прокладке (по мощности, см. LABOR_PRICE_BY_CAPACITY_KW - НЕ умножается на 1.10, это
    не материал); цена продажи = себестоимость x 2, округлено ВВЕРХ до 50р. Raises
    ValueError/KeyError if this capacity needs a pipe/insulation size not yet priced
    from Kemix (see the two dicts above), or a labor tier above 10.5 kW."""
    liquid_mm, gas_mm = pipe_diameters_for_capacity(cooling_kw_max)
    liquid_pipe = KEMIX_PIPE_SKU_BY_MM[liquid_mm]
    gas_pipe = KEMIX_PIPE_SKU_BY_MM[gas_mm]
    liquid_ins = KEMIX_INSULATION_SKU_BY_ID_MM[INSULATION_ID_FOR_PIPE_OD_MM[liquid_mm]]
    gas_ins = KEMIX_INSULATION_SKU_BY_ID_MM[INSULATION_ID_FOR_PIPE_OD_MM[gas_mm]]
    cable = CABLE_INTERCONNECT["price_per_m"]
    labor_per_m = labor_price_for_capacity(cooling_kw_max)

    materials_sum = (
        liquid_pipe["price_per_m"] + gas_pipe["price_per_m"]
        + liquid_ins["price_per_m"] + gas_ins["price_per_m"] + cable
    )
    materials_cost_basis = round(materials_sum * 1.10, 2)
    cost_basis_per_m = round(materials_cost_basis + labor_per_m, 2)
    sell_price_per_m = ceil_to_50(cost_basis_per_m * 2)

    return {
        "liquid_pipe": liquid_pipe, "gas_pipe": gas_pipe,
        "liquid_insulation": liquid_ins, "gas_insulation": gas_ins,
        "cable_price_per_m": cable,
        "materials_sum_per_m": round(materials_sum, 2),
        "materials_cost_basis_per_m": materials_cost_basis,
        "labor_per_m": labor_per_m,
        "cost_basis_per_m": cost_basis_per_m,
        "sell_price_per_m": sell_price_per_m,
    }


if __name__ == "__main__":
    import json
    # The two running-example models from this conversation:
    for label, kw in [
        ("Flexis Super Match 2,5 kW (AS25S2SF3FA-B/1U25S2SM4FA, peak cooling 3.2 kW)", 3.2),
        ("ECO R32 канальная 5 kW (AD50S2LM1FA/1U50S1LM1FA, peak cooling 5.5 kW)", 5.5),
    ]:
        print(f"{label}:")
        print("  монтаж:", install_price_for_capacity(kw), "р.")
        print("  фреоновая магистраль:", json.dumps(freon_line_price_per_meter(kw), ensure_ascii=False, indent=2))
        print()
