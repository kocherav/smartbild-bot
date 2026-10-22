#!/usr/bin/env python3
"""
Import step for the "ведомость работ" tariff-seeding flow (see harvest_work_rates.py's
docstring for the harvest half). Owner filled in the missing "Себес работ" cells in the
xlsx harvest_work_rates.py produced and sent it back; this script:

1. Parses the filled xlsx (name / unit / cost_work per row).
2. Writes work_rates.json - a flat name -> {"unit", "cost_work"} table, same shape
   convention as hogart-scraper/pipe_reference.py's lookup tables.
3. For each row with a real cost_work, matches it against the live Megaplan catalog
   (offer_catalog_cache.find_candidate - exact/fuzzy name match) and, if found, pushes
   cost_work onto that real Offer via update_offer_cost (cost_material is left alone -
   only cost_work is ever passed here, see MegaplanAPI._cost_fields).

Default mode is --dry-run (report only, no writes) - this touches the live production
catalog across potentially 300+ offers, so a real run needs the flag spelled out
explicitly. CLI: `python3 import_work_rates.py <path.xlsx> [--dry-run|--apply]`.
Prints a single-line JSON summary (matches this project's established CLI convention).
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_RATES_PATH = os.path.join(BASE_DIR, "work_rates.json")

sys.path.insert(0, BASE_DIR)


def parse_xlsx(path):
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    header_idx = None
    for i, row in enumerate(rows):
        if row and row[0] and str(row[0]).strip() == "Наименование":
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("header row ('Наименование', 'Ед. изм.', 'Себес работ') not found")

    positions = []
    for row in rows[header_idx + 1:]:
        if not row or not row[0]:
            continue
        name = str(row[0]).strip()
        unit = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        cost_work = row[2] if len(row) > 2 else None
        if isinstance(cost_work, str):
            cost_work = cost_work.strip().replace(",", ".")
            cost_work = float(cost_work) if cost_work else None
        positions.append({"name": name, "unit": unit, "cost_work": cost_work})
    return positions


def build_work_rates(positions):
    return {p["name"]: {"unit": p["unit"], "cost_work": p["cost_work"]} for p in positions}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx_path")
    parser.add_argument("--apply", action="store_true", help="actually write cost_work to matching catalog Offers (default is dry-run)")
    args = parser.parse_args()

    positions = parse_xlsx(args.xlsx_path)
    work_rates = build_work_rates(positions)
    with open(WORK_RATES_PATH, "w", encoding="utf-8") as f:
        json.dump(work_rates, f, ensure_ascii=False, indent=2, sort_keys=True)

    still_missing = [p["name"] for p in positions if not p["cost_work"]]

    matched, unmatched, updated = [], [], []
    if positions:
        import offer_catalog_cache
        from megaplan_api import MegaplanAPI

        api = MegaplanAPI()
        for p in positions:
            if not p["cost_work"]:
                continue
            candidate = offer_catalog_cache.find_candidate(api, p["name"])
            if not candidate:
                unmatched.append(p["name"])
                continue
            matched.append({
                "name": p["name"], "offer_id": candidate["id"],
                "catalog_name": candidate["name"],
                "old_cost_work": candidate.get("cost_work"),
                "new_cost_work": p["cost_work"],
            })
            if args.apply:
                api.update_offer_cost(candidate["id"], cost_work=p["cost_work"])
                updated.append(candidate["id"])

    print(json.dumps({
        "ok": True,
        "work_rates_path": WORK_RATES_PATH,
        "parsed_count": len(positions),
        "still_missing_cost_work": still_missing,
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "unmatched_names": unmatched,
        "applied": args.apply,
        "updated_offer_ids": updated,
        "sample_matches": matched[:10],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
