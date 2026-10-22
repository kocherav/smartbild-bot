#!/usr/bin/env python3
"""
"Ведомость работ" calculator (2026-08-25) - last piece of the roadmap item started by
harvest_work_rates.py/import_work_rates.py. Computes a deal's total labour cost from its
own positions (qty x cost_work per unit) so the owner has a real number for the deal's
"Монтажные работы" line instead of guessing. Triggered by chat command (bridge.py's
WORK_STATEMENT_REQUEST marker) - **output stays internal-only for now**: this only builds
a review .xlsx, it never writes anything back onto the deal (unlike apply-supplier-invoice)
- pushing the computed total onto "Монтажные работы" is a deliberate separate step the
owner takes by hand (or a future feature), not automatic here.

Cost-per-unit resolution order, per position (first hit wins):
1. The deal's own local ledger entry's `cost_work` (deal_ledger.py) - already the
   correct per-unit figure for this specific deal's position (accounts for
   _accumulate_position's running-average math if a supplier invoice ever touched it).
2. The live Megaplan catalog Offer's own `cost_work` (offer_catalog_cache, exact/fuzzy
   name match) - catches positions whose ledger predates a catalog cost_work fill-in
   (e.g. import_work_rates.py ran after this deal was created).
3. `work_rates.json` (import_work_rates.py's flat name -> {"unit","cost_work"} table) -
   catches names that were harvested/priced but never made it onto a matching catalog
   Offer (e.g. a totally new position type).
Anything still unresolved after all three is reported, not guessed.

CLI: `python3 build_work_statement.py <deal_id> [--out path.xlsx]`
Prints a single-line JSON summary (this project's established CLI convention).
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import deal_ledger
import offer_catalog_cache

WORK_RATES_PATH = os.path.join(BASE_DIR, "work_rates.json")
# The "Монтажные работы" line is the TARGET of this whole calculation - it will always
# lack its own cost_work (that's exactly what apply_work_statement.py fills in from this
# total), so it must never count as a "missing" position blocking the markup question.
# startswith, not a plain substring check - "Демонтажные работы" contains "монтажные
# работы" as a substring and would false-match otherwise (see apply_work_statement.py,
# which uses the same constant).
MONTAGE_PREFIX = "монтажные работы"


def _load_work_rates():
    if not os.path.exists(WORK_RATES_PATH):
        return {}
    with open(WORK_RATES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _work_rate_lookup(work_rates, name):
    """Exact case-insensitive match first, then best fuzzy match - same threshold/logic
    as offer_catalog_cache.find_candidate, kept separate since this is a different,
    smaller table (harvested names, not the full catalog)."""
    from difflib import SequenceMatcher

    target = name.strip().lower()
    for k, v in work_rates.items():
        if k.strip().lower() == target:
            return v.get("cost_work"), v.get("unit")
    best, best_ratio = None, 0.0
    for k, v in work_rates.items():
        ratio = SequenceMatcher(None, target, k.strip().lower()).ratio()
        if ratio > best_ratio:
            best, best_ratio = v, ratio
    if best and best_ratio >= 0.85:
        return best.get("cost_work"), best.get("unit")
    return None, None


def compute_statement(api, deal_id):
    entries = deal_ledger.load(deal_id)
    work_rates = _load_work_rates()

    rows = []
    total = 0.0
    missing = []
    for e in entries:
        name = e.get("name") or ""
        qty = e.get("qty") or 0
        # The montage line's own cost_work (once apply_work_statement.py has filled it
        # in) is THIS total from a previous run - it must never feed back into its own
        # basis on a later recompute, or the total silently doubles (found 2026-08-25:
        # a second run against a deal that had already gone through apply_work_statement
        # produced exactly 2x the real total). Still shown in `rows` for visibility.
        is_montage = name.strip().lower().startswith(MONTAGE_PREFIX)
        cost_work = e.get("cost_work")
        unit = None
        source = "ledger"

        if not cost_work and not is_montage:
            candidate = offer_catalog_cache.find_candidate(api, name)
            if candidate and candidate.get("cost_work"):
                cost_work = candidate["cost_work"]
                source = "catalog"

        if not cost_work and not is_montage:
            rate_cost, rate_unit = _work_rate_lookup(work_rates, name)
            if rate_cost:
                cost_work = rate_cost
                unit = rate_unit
                source = "work_rates"

        if not cost_work:
            if not is_montage:
                missing.append(name)
            rows.append({"name": name, "unit": unit, "qty": qty, "cost_work": None, "row_total": None, "source": None, "is_montage": is_montage})
            continue

        row_total = qty * cost_work
        if not is_montage:
            total += row_total
        rows.append({"name": name, "unit": unit, "qty": qty, "cost_work": cost_work, "row_total": row_total, "source": source, "is_montage": is_montage})

    return rows, total, missing


def build_xlsx(rows, deal_id, path):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    import xlsx_brand_style as style

    wb = Workbook()
    ws = wb.active
    ws.title = "Ведомость работ"
    ws.sheet_view.showGridLines = False

    headers = ["Наименование", "Ед. изм.", "Кол-во", "Себес работ/ед.", "Итого"]
    header_row = style.write_title_banner(ws, "Ведомость работ", f"Сделка № {deal_id}", len(headers))
    style.write_header_row(ws, header_row, headers)
    align_by_col = {1: style.LEFT, 2: style.CENTER, 3: style.CENTER, 4: style.RIGHT, 5: style.RIGHT}

    for i, r in enumerate(rows):
        # "Итого" (col E) is a live formula (qty * cost/ед), not a pre-computed value -
        # so editing Кол-во/Себес работ directly in Excel keeps the row honest. Left
        # blank (no formula) for rows with no known cost - a formula against a blank
        # cell would silently evaluate to 0, which looks like a confirmed zero cost
        # rather than "unknown" (same 0-is-unset trap spec_review_xlsx.py already
        # guards against elsewhere in this project).
        ws.append([r["name"], r["unit"] or "", r["qty"], r["cost_work"], None])
        row_idx = ws.max_row
        style.style_data_row(ws, row_idx, len(headers), align_by_col, stripe=(i % 2 == 1))
        if r["cost_work"] is None:
            style.apply_warning_fill(ws, row_idx, len(headers))
        else:
            ws.cell(row=row_idx, column=4).number_format = style.MONEY_FMT
            # The montage row's own "Итого" is deliberately left blank (not a formula) -
            # it's the OUTPUT of this whole sheet (see is_montage above), not an input
            # to sum alongside everything else; a blank cell is correctly skipped by the
            # SUM(E...) formula below, whereas a formula here would double-count it on
            # every recompute after apply_work_statement.py has priced it once.
            if not r.get("is_montage"):
                ws.cell(row=row_idx, column=5, value=f"=C{row_idx}*D{row_idx}")
                ws.cell(row=row_idx, column=5).number_format = style.MONEY_FMT

    first_data_row, last_data_row = header_row + 1, ws.max_row
    total_row = ws.max_row + 1
    ws.cell(row=total_row, column=1, value="ИТОГО себестоимость работ")
    total_cell = ws.cell(row=total_row, column=5, value=f"=SUM(E{first_data_row}:E{last_data_row})")
    total_cell.number_format = style.MONEY_FMT
    style.style_total_row(ws, total_row, len(headers))
    ws.row_dimensions[total_row].height = 22

    widths = [55, 10, 10, 16, 16]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    wb.save(path)


def main():
    from megaplan_api import MegaplanAPI

    parser = argparse.ArgumentParser()
    parser.add_argument("deal_id")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    out_path = args.out or os.path.join(BASE_DIR, f"ведомость_работ_{args.deal_id}.xlsx")

    api = MegaplanAPI()
    rows, total, missing = compute_statement(api, args.deal_id)
    build_xlsx(rows, args.deal_id, out_path)

    # The montage line itself is expected to be "missing" (see MONTAGE_PREFIX above) -
    # it still shows up highlighted in the .xlsx, but must not block the markup
    # question the bridge asks once every OTHER position has a known cost.
    blocking_missing = [m for m in missing if not m.strip().lower().startswith(MONTAGE_PREFIX)]

    print(json.dumps({
        "ok": True, "deal_id": args.deal_id, "path": out_path,
        "total_cost_work": total, "position_count": len(rows),
        "missing_count": len(blocking_missing), "missing_names": blocking_missing,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
