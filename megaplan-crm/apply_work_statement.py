#!/usr/bin/env python3
"""
"Ведомость работ" -> "Монтажные работы" pricing (2026-08-25) - the write-back half of
build_work_statement.py (which is read-only/internal). Owner's rule: once every
position's labour cost is known (build_work_statement.py's missing_count == 0), the
bot asks for a markup on the TOTAL labour cost, then that becomes the real cost/price
for the deal's own "Монтажные работы" line:
    cost_work(Монтажные работы) = total_cost_work (sum across every OTHER position)
    sell_price(Монтажные работы) = cost_work * (1 + markup_pct/100)

Deliberately re-computes the total itself (via build_work_statement.compute_statement)
rather than trusting a number carried in a chat marker - same principle as
_accumulate_position: a figure that writes real money into a live CRM deal must be
script-derived, never LLM-transcribed (see project memory, 2026-08-24 pricing incident).

Matches the "Монтажные работы" position by name.startswith("монтажные работы")
(case-insensitive) - NOT a plain substring check, because "Демонтажные работы"
contains "монтажные работы" as a substring and would false-match otherwise.

CLI: `python3 apply_work_statement.py <deal_id> <markup_pct>`
Prints a single-line JSON summary.
"""
import argparse
import json
import os
import sys
import hashlib
import math

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import deal_ledger
from build_work_statement import compute_statement, MONTAGE_PREFIX
from megaplan_api import MegaplanAPI


def find_montage_entry(entries):
    for e in entries:
        name = (e.get("name") or "").strip().lower()
        if name.startswith(MONTAGE_PREFIX):
            return e
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("deal_id")
    parser.add_argument("markup_pct", type=float)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--expected-fingerprint')
    args = parser.parse_args()
    if not math.isfinite(args.markup_pct) or args.markup_pct < 0:
        raise ValueError('Наценка должна быть конечным неотрицательным числом')

    api = MegaplanAPI()
    entries = deal_ledger.load(args.deal_id)

    montage_entry = find_montage_entry(entries)
    if not montage_entry:
        print(json.dumps({"ok": False, "error": "позиция 'Монтажные работы' не найдена в сделке"}, ensure_ascii=False))
        return

    # The montage line itself has no cost_work yet (that's what we're computing) - it'll
    # show up as "missing" from compute_statement, filtered out below rather than
    # double-counted into its own cost basis.
    rows, total, missing = compute_statement(api, args.deal_id)
    missing = [m for m in missing if not m.strip().lower().startswith(MONTAGE_PREFIX)]
    if missing:
        print(json.dumps({
            "ok": False,
            "error": "не все позиции имеют себестоимость работ - пересчитайте ведомость",
            "missing_names": missing,
        }, ensure_ascii=False))
        return

    sell_price = total * (1 + args.markup_pct / 100)
    if not math.isfinite(total) or total < 0 or not math.isfinite(sell_price):
        raise ValueError('Неверная себестоимость работ')
    fingerprint = hashlib.sha256(json.dumps({'entries':entries,'rows':rows,'total':total},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if args.preview:
        print(json.dumps({'ok':True,'deal_id':args.deal_id,'fingerprint':fingerprint,'total_cost_work':total,'montage_sell_price':sell_price},ensure_ascii=False)); return
    if args.expected_fingerprint != fingerprint:
        print(json.dumps({'ok':False,'no_effect':True,'error':'Исходные данные изменились или нет подтверждённого просмотра. Подготовьте расчёт заново.'},ensure_ascii=False)); return

    api.update_offer_cost(montage_entry["offer_id"], cost_work=total)
    api.update_offer_row_price(montage_entry["offer_row_id"], price=sell_price)

    montage_entry["cost_work"] = total
    montage_entry["cost_material"] = montage_entry.get("cost_material") or 0
    montage_entry["sell_price"] = sell_price
    montage_entry["price_source"] = "work_statement"
    montage_entry["needs_review"] = False
    deal_ledger.save(args.deal_id, entries)

    print(json.dumps({
        "ok": True, "deal_id": args.deal_id,
        "montage_offer_id": montage_entry["offer_id"],
        "montage_offer_row_id": montage_entry["offer_row_id"],
        "total_cost_work": total, "markup_pct": args.markup_pct,
        "montage_sell_price": sell_price,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
