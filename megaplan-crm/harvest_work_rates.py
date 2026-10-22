#!/usr/bin/env python3
"""
One-off harvest (2026-08-24): pull unique position names/units/"Себес работ" (labour
cost) from the last N REAL (non-bot-created) Megaplan deals, to seed the "ведомость
работ" tariff table for the upcoming labour-cost-statement feature. Owner fills in
whatever's missing in the resulting review file and sends it back; that then becomes
work_rates.json (a flat name -> rate table, same shape as pipe_reference.py's tables).

`GET /deal` with `fields: ["positions"]` conveniently returns each position's full
`offer` object already expanded, including the `Category1000045CustomFieldSebesRabot`
custom field - no separate /offer calls needed (unlike offer_catalog_cache.py's LIST
endpoint, which does NOT include custom fields unless the finer-grained top-level
`fields` param names them explicitly - this is a *nested* field inside `positions`, a
different code path, and came through by default here without extra effort).

`--exclude` is a manually-curated list of deal ids created by THIS bot during
development/testing (871, 876, 878, 883 as of 2026-08-24 - the rest of that era's test
deals, 872-875/877/879-882, were already deleted during cleanup and never show up in
the API results at all). If more bot-test deals accumulate later, extend this list -
there's no reliable automatic way to distinguish "real" from "bot" deals in program 16,
since Phase 1b deals DO get a real linked contractor like any other deal.

CLI: `python3 harvest_work_rates.py [--count 20] [--exclude 871,876,878,883] [--out path.xlsx]`
Prints {"ok": true, "path": ..., "unique_count": ..., "missing_count": ...}.
"""
import argparse
import json
import os
import sys

from megaplan_api import MegaplanAPI

DEFAULT_EXCLUDE = {"871", "876", "878", "883"}
SCAN_START_ID = "800"  # a safe margin below the current max id - walking the FULL
# ~860-deal history just to find the last 20 would be needlessly slow; this window is
# comfortably wider than `count` ever needs to be and still wide enough to catch a
# unit-name's first occurrence (see fetch_real_deals). Raise it if `--count` ever
# exceeds ~80.


def fetch_real_deals(api, count, exclude):
    """Page through /deal (fields=positions) from the very start, keep every deal not
    in `exclude`, return the most recent `count` of them (by id, descending) plus a
    unit-name lookup built from the FULL scan (see `unique_positions`'s docstring for
    why this can't just be built from the returned subset - the id -> name first-
    occurrence might land in a deal outside the kept `count`)."""
    deals = []
    unit_names_by_id = {}
    params = {"limit": 100, "fields": ["positions"], "pageAfter": {"contentType": "Deal", "id": SCAN_START_ID}}
    last_id = SCAN_START_ID
    while True:
        result = api._call("GET", "/deal", params=params)
        data = result.get("data") or []
        if not data:
            break
        for d in data:
            for row in d.get("positions") or []:
                unit = row.get("unit") or {}
                if unit.get("id") and unit.get("name") and unit["id"] not in unit_names_by_id:
                    unit_names_by_id[unit["id"]] = unit["name"]
            if d["id"] not in exclude:
                deals.append(d)
        last_id = data[-1]["id"]
        if not result.get("meta", {}).get("pagination", {}).get("hasMoreNext"):
            break
        params = {"limit": 100, "fields": ["positions"], "pageAfter": {"contentType": "Deal", "id": last_id}}
    deals.sort(key=lambda d: int(d["id"]), reverse=True)
    return deals[:count], unit_names_by_id


def unique_positions(deals, unit_names_by_id):
    """Dedupe by position NAME across all fetched deals' positions. Prefers the most
    recent (higher deal id, deals are pre-sorted descending) non-empty "Себес работ"
    value if the same name appears with different figures across deals - an older 0/
    unset row shouldn't shadow a newer real one, but a newer 0/unset also shouldn't
    blank out an older real figure (owner fills in the rest by hand anyway - this is a
    best-effort seed, not authoritative).

    2026-08-24: Мегаплан's `/deal` response only embeds a referenced sub-entity's
    `name` on its FIRST occurrence in the whole payload - repeat references to the same
    `unit` (or `offer`, `tax`, etc.) further down just carry `{"contentType","id"}` with
    no `name`, presumably a dedup optimization. So `unit.name` is missing on most rows
    even though the id is the same "шт." every time - `unit_names_by_id` (built from
    the FULL scan in `fetch_real_deals`, not just these `deals`) backfills it."""
    seen = {}
    for d in deals:
        for row in d.get("positions") or []:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            unit = row.get("unit") or {}
            unit_name = unit.get("name") or unit_names_by_id.get(unit.get("id"), "")
            offer = row.get("offer") or {}
            cost_work = ((offer.get("Category1000045CustomFieldSebesRabot") or {}).get("value"))
            existing = seen.get(name)
            if existing is None:
                seen[name] = {"name": name, "unit": unit_name, "cost_work": cost_work}
            else:
                if not existing.get("unit") and unit_name:
                    existing["unit"] = unit_name
                if not existing.get("cost_work") and cost_work:
                    existing["cost_work"] = cost_work
    return sorted(seen.values(), key=lambda p: p["name"].lower())


def build_xlsx(positions, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Тариф на работы"
    ws.append(["Заполните пустые (красные) строки — себестоимость работ, руб. за единицу"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([])

    headers = ["Наименование", "Ед. изм.", "Себес работ"]
    ws.append(headers)
    header_row = ws.max_row
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="10222C")

    missing_fill = PatternFill("solid", fgColor="F8D0D0")
    missing_count = 0
    for p in positions:
        ws.append([p["name"], p["unit"], p["cost_work"]])
        r = ws.max_row
        if isinstance(ws.cell(row=r, column=3).value, (int, float)):
            ws.cell(row=r, column=3).number_format = "#,##0.00"
        if not p["cost_work"]:
            missing_count += 1
            for col in range(1, len(headers) + 1):
                ws.cell(row=r, column=col).fill = missing_fill

    widths = [55, 10, 18]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    wb.save(path)
    return missing_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--exclude", default=",".join(sorted(DEFAULT_EXCLUDE, key=int)))
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "тариф_на_работы.xlsx"))
    args = parser.parse_args()
    exclude = set(args.exclude.split(",")) if args.exclude else set()

    api = MegaplanAPI()
    deals, unit_names_by_id = fetch_real_deals(api, args.count, exclude)
    positions = unique_positions(deals, unit_names_by_id)
    missing_count = build_xlsx(positions, args.out)
    print(json.dumps({
        "ok": True, "path": args.out, "deal_ids": [d["id"] for d in deals],
        "unique_count": len(positions), "missing_count": missing_count,
    }, ensure_ascii=False))
