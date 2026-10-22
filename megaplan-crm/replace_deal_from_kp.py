#!/usr/bin/env python3
"""Atomically replace an existing deal's rows with a confirmed KP specification."""
import json
import os
import sys
import hashlib
import math
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOGART_DIR = os.path.expanduser("~/hogart-scraper")
sys.path.insert(0, HOGART_DIR)

from generate_kp import live_lookup, full_price_of, contract_price_of
from daichi_catalog_cache import load_or_refresh as load_daichi_cache
from daichi_api import DaichiAPI
from megaplan_api import MegaplanAPI
import deal_ledger

BACKUP_DIR = os.path.join(BASE_DIR, "deal_backups")
UNIT_IDS = {"шт.": "1", "шт": "1", "м": "4", "м.": "4", "компл.": "8", "компл": "8", "к-т": "8", "усл.": "9"}


def normalize_spec(spec):
    discount = float(spec.get("discount_pct") or 0)
    rows = []
    daichi = None
    for item in spec.get("items") or []:
        source = item.get("source", "hogart")
        qty = float(item.get("qty") or 1)
        if qty.is_integer(): qty = int(qty)
        if source == "hogart":
            live = live_lookup(item["sku"])
            if not live: raise ValueError(f"не найдено оборудование Hogart: {item['sku']}")
            price = round(full_price_of(live) * (1 - discount / 100), 2)
            rows.append({"name": item.get("label") or item["sku"], "qty": qty, "unit_price": price,
                         "cost_material": (float(item["cost_price"]) if item.get("cost_price") is not None else contract_price_of(live)),
                         "cost_work": 0, "unit_id": "1", "supplier": "hogart",
                         "supplier_sku": item["sku"], "supplier_product_id": str(live["id"])})
        elif source == "daichi":
            if daichi is None:
                daichi = load_daichi_cache(DaichiAPI())
            live = next((value for value in daichi.values() if str(value.get("xml_id")) == str(item["sku"]) or str(value.get("id")) == str(item["sku"])), None)
            if not live: raise ValueError(f"не найдено оборудование Daichi: {item['sku']}")
            rows.append({"name": item.get("label") or live.get("name") or item["sku"], "qty": qty,
                         "unit_price": round(float(live["sell_price"]) * (1 - discount / 100), 2),
                         "cost_material": live.get("cost_price"), "cost_work": 0, "unit_id": "1"})
        elif source in ("manual", "service"):
            unit = item.get("unit") or "шт."
            rows.append({"name": item.get("label") or item.get("name") or "Работы", "qty": qty,
                         "unit_price": round(float(item.get("unit_price") or 0), 2), "cost_material": 0,
                         "cost_work": (float(item["cost_price"]) if item.get("cost_price") is not None else None),
                         "unit_id": UNIT_IDS.get(unit, "1")})
        else:
            raise ValueError(f"неподдерживаемый источник позиции: {source}")
    if not rows:
        raise ValueError("в КП нет позиций")
    return rows


def backup_deal(deal_id, deal):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(BACKUP_DIR, f"deal-{deal_id}-{stamp}.json")
    with open(path, "w", encoding="utf-8") as target:
        json.dump(deal, target, ensure_ascii=False, indent=2)
    return path


def deal_fingerprint(deal):
    relevant = {key: deal.get(key) for key in ('positions', 'price', 'contractor', 'payer')}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_rows(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Нет подтверждённых позиций')
    for row in rows:
        if not row.get('name') or not row.get('unit_id'):
            raise ValueError('Не указаны название или единица измерения')
        for key in ('qty', 'unit_price', 'cost_material', 'cost_work'):
            value = row.get(key)
            if value is None and key.startswith('cost_'):
                continue
            number = float(value)
            if not math.isfinite(number) or number < 0 or (key == 'qty' and number == 0):
                raise ValueError('Неверное количество или цена')
    return rows


def run(payload):
    deal_id = str(payload["deal_id"])
    rows = validate_rows(payload['prepared_rows'] if payload.get('prepared_rows') is not None else normalize_spec(payload["kp"]))
    expected_total = round(sum(float(row["qty"]) * row["unit_price"] for row in rows), 2)
    if payload.get("dry_run"):
        return {"ok": True, "dry_run": True, "deal_id": deal_id, "positions_count": len(rows),
                "total": expected_total, "rows": rows}
    api = MegaplanAPI()
    before = api._call("GET", f"/deal/{deal_id}")["data"]
    if payload.get('preview'):
        return {'ok': True, 'deal_id': deal_id, 'rows': rows, 'total': expected_total,
                'before_count': len(before.get('positions') or []), 'before_price': before.get('price'),
                'fingerprint': deal_fingerprint(before)}
    if payload.get('expected_fingerprint') != deal_fingerprint(before):
        return {'ok': False, 'no_effect': True, 'error': 'Сделка изменена или нет подтверждённого предварительного просмотра. Сформируйте просмотр заново.'}
    from document_tax_policy import company_rate,approved_deal
    from seller_documents import selected_seller
    if approved_deal(deal_id):raise ValueError("У сделки согласованы разные даты передачи и ставки НДС; массовая замена позиций требует пересмотра этой разбивки")
    policy=company_rate(selected_seller(deal_id)["id"])
    tax_id=api.resolve_tax_id("none" if policy in (None,-1) else str(policy))
    backup = backup_deal(deal_id, before)
    positions = []
    for row in rows:
        offer_id = api.find_or_create_offer(row["name"], row["unit_price"], row["cost_material"], row["cost_work"], row["unit_id"])
        positions.append({"contentType": "OfferRow", "offer": {"contentType": "Offer", "id": str(offer_id)},
                          "quantity": row["qty"], "price": {"contentType": "Money", "currency": "RUB", "value": row["unit_price"]},
                          "tax": {"contentType": "Tax", "id": str(tax_id)}})
    api._call("POST", f"/deal/{deal_id}", json_body={"contentType": "Deal", "positions": positions})
    after = api._call("GET", f"/deal/{deal_id}")["data"]
    actual_rows = after.get("positions") or []
    actual_total = round(sum(float(row.get("quantity") or 0) * float((row.get("price") or {}).get("value") or 0) for row in actual_rows), 2)
    if len(actual_rows) != len(rows) or actual_total != expected_total:
        raise ValueError(f"проверка после записи не пройдена: {len(actual_rows)} строк/{actual_total} руб.")
    # Megaplan clones catalog Offers when rows are attached.  Cost fields belong to
    # those cloned Offers, so copy the KP economics onto the returned real offer ids.
    for source, actual in zip(rows, actual_rows):
        api.update_offer_cost((actual.get("offer") or {}).get("id"), source["cost_material"], source["cost_work"])
    after = api._call("GET", f"/deal/{deal_id}")["data"]
    ledger = api.ledger_from_deal(after, price_source="kp_revision")
    for source, entry in zip(rows, ledger):
        for key in ("supplier", "supplier_sku", "supplier_product_id"):
            if source.get(key) is not None:
                entry[key] = source[key]
    deal_ledger.save(deal_id, ledger)
    return {"ok": True, "deal_id": deal_id, "positions_count": len(rows), "total": actual_total,
            "backup": backup, "url": api.deal_url(deal_id), "ledger": ledger}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
