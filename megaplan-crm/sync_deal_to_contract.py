#!/usr/bin/env python3
"""Synchronise commercial rows of a deal with a signed contract snapshot.

The signed contract is the source of truth for *client* quantities and prices.
This tool deliberately changes only OfferRow quantity/price.  Supplier-invoice
allocations, actual cost fields and accepted installation reports stay intact.
It is therefore safe to use on a live deal that has procurement history.
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone

from megaplan_api import MegaplanAPI
import deal_ledger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "deal_backups")


def key(value):
    return re.sub(r"[^0-9a-zа-я]+", " ", str(value or "").casefold().replace("ё", "е")).strip()


def load_snapshot(path):
    with open(path, encoding="utf-8") as source:
        payload = json.load(source)
    rows = payload.get("rows") or []
    if not rows:
        raise ValueError("в снимке договора нет строк спецификации")
    for row in rows:
        if not row.get("name") or float(row.get("qty") or 0) <= 0:
            raise ValueError(f"некорректная строка договора: {row}")
        row["qty"] = float(row["qty"])
        row["unit_price"] = float(row["unit_price"])
    expected = round(sum(r["qty"] * r["unit_price"] for r in rows), 2)
    declared = float(payload.get("total") or expected)
    if expected != round(declared, 2):
        raise ValueError(f"сумма строк {expected:.2f} не равна сумме договора {declared:.2f}")
    return payload, rows, expected


def backup(deal_id, deal, ledger):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(BACKUP_DIR, f"contract-sync-{deal_id}-{stamp}.json")
    with open(path, "w", encoding="utf-8") as target:
        json.dump({"deal": deal, "ledger": ledger}, target, ensure_ascii=False, indent=2)
    return path


def match_rows(deal_rows, contract_rows):
    indexed = {key((r.get("offer") or {}).get("name")): r for r in deal_rows}
    result, missing = [], []
    for contract in contract_rows:
        actual = indexed.get(key(contract["name"]))
        if actual is None:
            missing.append(contract["name"])
        else:
            result.append((actual, contract))
    extras = [((r.get("offer") or {}).get("name") or "") for r in deal_rows
              if key((r.get("offer") or {}).get("name")) not in {key(c["name"]) for c in contract_rows}]
    if missing or extras or len(result) != len(deal_rows):
        raise ValueError("невозможно безопасно синхронизировать строки: "
                         f"нет в сделке={missing}; лишние в сделке={extras}")
    return result


def sync(deal_id, snapshot_path, apply=False):
    snapshot, contract_rows, expected = load_snapshot(snapshot_path)
    api = MegaplanAPI()
    deal = api._call("GET", f"/deal/{deal_id}")["data"]
    deal_rows = deal.get("positions") or []
    pairs = match_rows(deal_rows, contract_rows)
    changes = [{"offer_row_id": actual["id"], "name": contract["name"],
                "before": {"qty": actual.get("quantity"), "unit_price": (actual.get("price") or {}).get("value")},
                "after": {"qty": contract["qty"], "unit_price": contract["unit_price"]}}
               for actual, contract in pairs]
    if not apply:
        return {"ok": True, "dry_run": True, "deal_id": str(deal_id), "contract_total": expected,
                "deal_total_before": round(sum(float(r.get("quantity") or 0) * float((r.get("price") or {}).get("value") or 0) for r in deal_rows), 2),
                "changes": changes}
    previous_ledger = deal_ledger.load(str(deal_id))
    backup_path = backup(str(deal_id), deal, previous_ledger)
    for actual, contract in pairs:
        api.update_offer_row_price(actual["id"], contract["unit_price"], contract["qty"])
    after = api._call("GET", f"/deal/{deal_id}")["data"]
    actual_total = round(sum(float(r.get("quantity") or 0) * float((r.get("price") or {}).get("value") or 0)
                             for r in after.get("positions") or []), 2)
    if actual_total != expected or len(after.get("positions") or []) != len(contract_rows):
        raise ValueError(f"контроль после записи не пройден: {actual_total:.2f} ₽, строк {len(after.get('positions') or [])}")
    # Refresh IDs/prices from Megaplan but retain procurement and cost-history data.
    prior = {key(x.get("name")): x for x in previous_ledger}
    refreshed = api.ledger_from_deal(after, price_source="signed_contract")
    for entry in refreshed:
        old = prior.get(key(entry.get("name")))
        if old:
            for field, value in old.items():
                if field not in {"offer_id", "offer_row_id", "name", "unit_id", "unit", "qty", "sell_price", "price_source"}:
                    entry[field] = value
    deal_ledger.save(str(deal_id), refreshed)
    snapshot["synced_at"] = datetime.now(timezone.utc).isoformat()
    snapshot["synced_deal_id"] = str(deal_id)
    with open(snapshot_path, "w", encoding="utf-8") as target:
        json.dump(snapshot, target, ensure_ascii=False, indent=2)
    return {"ok": True, "deal_id": str(deal_id), "contract_total": expected,
            "actual_total": actual_total, "positions_count": len(refreshed), "backup": backup_path,
            "changes": changes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("deal_id")
    parser.add_argument("snapshot")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(sync(args.deal_id, args.snapshot, args.apply), ensure_ascii=False, indent=2))
