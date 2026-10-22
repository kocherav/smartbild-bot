#!/usr/bin/env python3
"""Create one Hogart supplier order when a Megaplan deal reaches «Закупка».

Only ledger rows explicitly tagged as Hogart are eligible.  The durable journal is
written *before* the network request: after an ambiguous connection failure the bot
will never retry automatically and accidentally create a duplicate supplier order.
"""
import fcntl
import hashlib
import json
import os
import sys
import math
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOGART_DIR = os.path.expanduser("~/hogart-scraper")
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, HOGART_DIR)

import deal_ledger
from hogart_api import HogartAPI, HogartAPIError

JOURNAL_FILE = os.path.join(BASE_DIR, "hogart_order_journal.json")
LOCK_FILE = JOURNAL_FILE + ".lock"


def _load_journal():
    try:
        with open(JOURNAL_FILE, encoding="utf-8") as source:
            return json.load(source)
    except FileNotFoundError:
        return {}


def _save_journal(data):
    tmp = f"{JOURNAL_FILE}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as target:
        json.dump(data, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.flush()
        os.fsync(target.fileno())
    os.replace(tmp, JOURNAL_FILE)


def order_items(entries, api):
    result = []
    for entry in entries:
        if entry.get("supplier") != "hogart" and entry.get("price_source") != "hogart":
            continue
        sku = str(entry.get("supplier_sku") or entry.get("hogart_sku") or "").strip()
        if not sku:
            raise ValueError(
                f"у позиции «{entry.get('name')}» не сохранён артикул/модель Hogart; "
                "заявка не создана"
            )
        product_id = entry.get("supplier_product_id")
        if not product_id and sku:
            products = api.search_products(keyword=sku)
            exact = next((p for p in products if str(p.get("article") or "").strip().casefold() == sku.casefold()), None)
            product_id = exact.get("id") if exact else None
        if not product_id:
            raise ValueError(f"у позиции «{entry.get('name')}» нет подтверждённого productId Hogart")
        # Quantities already covered by supplier invoices or confirmed internal
        # stock must never be ordered from Hogart again.
        qty=float(entry.get('qty') or 0); consumed=float(entry.get('consumed_qty') or 0)
        if not math.isfinite(qty) or not math.isfinite(consumed) or qty<0 or consumed<0:
            raise ValueError('Неверное количество оборудования; заказ не отправлен')
        amount = max(0.0, qty - consumed)
        if amount <= 1e-9:
            continue
        if amount <= 0:
            raise ValueError(f"у позиции «{entry.get('name')}» неверное количество")
        result.append({"productId": str(product_id), "amount": int(amount) if amount.is_integer() else amount,
                       "sku": sku, "name": entry.get("name")})
    return result


def ensure_order(deal_id, status, dry_run=False, api=None):
    normalized = " ".join(str(status or "").casefold().replace("ё", "е").split())
    if normalized != "закупка":
        return {"ok": True, "skipped": True, "reason": "status_not_procurement"}
    api = api or HogartAPI()
    items = order_items(deal_ledger.load(str(deal_id)), api)
    if not items:
        return {"ok": True, "skipped": True, "reason": "no_hogart_items"}
    public_items = [{"productId": item["productId"], "amount": item["amount"]} for item in items]
    fingerprint = hashlib.sha256(json.dumps(public_items, sort_keys=True).encode()).hexdigest()
    if dry_run:
        return {"ok": True, "dry_run": True, "deal_id": str(deal_id), "items": items,
                "fingerprint": fingerprint}

    with open(LOCK_FILE, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        journal = _load_journal()
        existing = journal.get(str(deal_id))
        if existing:
            return {"ok": existing.get("state") == "submitted", "skipped": True,
                    "reason": "already_recorded", "record": existing}
        record = {"state": "submitting", "fingerprint": fingerprint,
                  "created_at": datetime.now(timezone.utc).isoformat(), "items": public_items}
        journal[str(deal_id)] = record
        _save_journal(journal)
        try:
            response = api.create_order(public_items, comment=f"Заявка по сделке Мегаплана №{deal_id}")
            created = response.get("data") or response
            if not created.get('id'):
                raise ValueError('Hogart не вернул ID заказа; требуется сверка, повтор запрещён')
            accepted_count = created.get("orderItemsCount")
            if accepted_count is not None and int(accepted_count) != len(public_items):
                record.update({
                    "state": "incomplete",
                    "hogart_order_id": created.get("id"),
                    "hogart_order_number": created.get("number"),
                    "requested_items_count": len(public_items),
                    "accepted_items_count": int(accepted_count),
                    "error": (
                        f"Hogart создал заказ только с {int(accepted_count)} из "
                        f"{len(public_items)} переданных позиций"
                    ),
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                })
                _save_journal(journal)
                return {
                    "ok": False,
                    "deal_id": str(deal_id),
                    "hogart_order_id": record.get("hogart_order_id"),
                    "hogart_order_number": record.get("hogart_order_number"),
                    "requested_items_count": len(public_items),
                    "accepted_items_count": int(accepted_count),
                    "error": record["error"],
                }
            record.update({"state": "submitted", "hogart_order_id": created.get("id"),
                           "hogart_order_number": created.get("number"),
                           "requested_items_count": len(public_items),
                           "accepted_items_count": (int(accepted_count) if accepted_count is not None else None),
                           "submitted_at": datetime.now(timezone.utc).isoformat()})
            _save_journal(journal)
            return {"ok": True, "deal_id": str(deal_id), "items_count": len(items),
                    "hogart_order_id": record.get("hogart_order_id"),
                    "hogart_order_number": record.get("hogart_order_number")}
        except Exception as exc:
            # The remote outcome can be unknown after a timeout. Never retry silently.
            record.update({"state": "needs_review", "error": str(exc),
                           "failed_at": datetime.now(timezone.utc).isoformat()})
            _save_journal(journal)
            raise


if __name__ == "__main__":
    try:
        spec = json.load(sys.stdin)
        print(json.dumps(ensure_order(spec["deal_id"], spec.get("status"), spec.get("dry_run", False)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
