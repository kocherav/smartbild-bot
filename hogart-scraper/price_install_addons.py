#!/usr/bin/env python3
"""
Compute install/freon-line addon prices for hogart-sourced equipment, for use OUTSIDE
the Cliwell-letterhead KP flow (generate_kp.py) - specifically, the Megaplan
"CREATE_MEGAPLAN_DEAL" chat flow in telegram-bridge/bridge.py, which needs the exact
same deterministic tariffs but as extra deal positions, not PDF rows.

Why this exists (2026-08-22): the first real test of "создай сделку ... с монтажом и
доп. трассой" made Claude invent/guess an install price instead of using the same fixed
tariff generate_kp.py already applies - worse, it silently fell back to the unrelated
BUILD_KP flow entirely (which does create a stub deal, but with no real client/positions
- that's why the resulting deal had an empty "Заказ" section). Root cause: the model had
no way to get a *correct* install/freon price for the new deal-creation flow, only for
the KP flow. This script gives it one, by exposing pipe_reference.py's tariffs the same
way HOGART_SEARCH exposes live pricing - a fixed script the bridge shells out to, never
a number the model has to invent.

Usage: stdin JSON {"items": [{"sku": "...", "qty": 2, "include_install": true,
"line_length_m": 15}, ...]} (only items with a sku are looked up; include_install/
line_length_m are optional per item, same meaning as in generate_kp.py's spec).

Prints JSON to stdout: {"ok": true, "addons": [{"for_sku": "...", "type": "install"|
"freon_line", "name": "...", "qty": ..., "unit_price": ..., "cost_material": ...,
"cost_work": ...}, ...], "equipment_costs": {sku: cost_or_null, ...}, "errors": [...]}
or {"ok": false, "error": "..."}. `addons` entries are ready to become their own
positions/Offer catalog items in Мегаплан - name/qty/unit_price/cost_material/cost_work
map directly onto create-full-deal's item shape. `equipment_costs` gives the per-unit
purchase cost (Hogart's contractPrice) for every sku that was found, looked up here too
(2026-08-23) so the CREATE_MEGAPLAN_DEAL flow can fill in Мегаплан's "Цена закупки" field
on the equipment line itself, not just the install/freon addon lines - see
project_megaplan_crm.md for how those custom fields were found.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hogart_api import HogartAPI, HogartAPIError
from pipe_reference import install_price_for_capacity, freon_line_price_per_meter, parse_cooling_capacity_kw
from generate_kp import contract_price_of, INSTALL_COST_RATIO


def live_lookup(api, sku):
    try:
        items = api.search_products(keyword=sku)
    except HogartAPIError:
        return None
    for it in items:
        if it.get("article", "").strip() == sku.strip():
            return it
    return None


def get_features(api, product):
    if not product.get("id"):
        return []
    try:
        detail = api.get_product(product["id"])
    except HogartAPIError:
        return []
    return detail.get("features") or []


def main():
    spec = json.load(sys.stdin)
    api = HogartAPI()
    addons = []
    errors = []
    equipment_costs = {}
    for it in spec.get("items") or []:
        sku = it.get("sku")
        if not sku:
            continue
        qty = it.get("qty") or 1
        include_install = bool(it.get("include_install"))
        line_length_m = float(it.get("line_length_m") or 0)

        live = live_lookup(api, sku)
        if not live:
            # Only a blocking error if install/freon math was actually asked for this
            # sku - a plain equipment line whose sku happens to not resolve just gets
            # no equipment_costs entry (cost_material stays unset), same as before.
            if include_install or line_length_m > 0:
                errors.append(f"{sku}: не найден в hogart, не могу посчитать монтаж/трассу")
            continue
        equipment_costs[sku] = contract_price_of(live)

        if not include_install and line_length_m <= 0:
            continue
        capacity_kw = parse_cooling_capacity_kw(get_features(api, live))
        if capacity_kw is None:
            errors.append(f"{sku}: не удалось определить мощность, не могу посчитать монтаж/трассу")
            continue

        if include_install:
            price = install_price_for_capacity(capacity_kw)
            addons.append({
                "for_sku": sku, "type": "install",
                "name": f"Стандартный монтаж кондиционера, {capacity_kw:g} кВт",
                "qty": qty, "unit_price": price,
                # Same "90% of the KP price" rule generate_kp.py uses - install has no
                # separate materials cost, it's pure labour.
                "cost_material": 0, "cost_work": round(price * INSTALL_COST_RATIO, 2),
            })
        if line_length_m > 0:
            freon = freon_line_price_per_meter(capacity_kw)
            addons.append({
                "for_sku": sku, "type": "freon_line",
                "name": "Дополнительная фреоновая магистраль",
                "qty": line_length_m, "unit_price": freon["sell_price_per_m"],
                "cost_material": freon["materials_cost_basis_per_m"],
                "cost_work": freon["labor_per_m"],
            })

    print(json.dumps({
        "ok": True, "addons": addons, "equipment_costs": equipment_costs, "errors": errors,
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
