#!/usr/bin/env python3
"""Auditable procurement snapshot and supplier-invoice registry for Megaplan deals."""
import hashlib
import json
import os
import sys
import tempfile
import re
import math
from registry_transaction import transaction
from difflib import SequenceMatcher
from datetime import datetime, timezone

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

import deal_ledger
import own_companies
import financial_amounts

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(BASE_DIR, "procurement_registry.json")
HOGART_JOURNAL = os.path.join(BASE_DIR, "hogart_order_journal.json")
BANK_REGISTRY = os.path.join(BASE_DIR, "bank_statement_registry.json")

FILL_INTERCOMPANY_OPEN = PatternFill("solid", fgColor="FFF2CC")
FILL_INTERCOMPANY_PARTIAL = PatternFill("solid", fgColor="DDEBF7")
FILL_INTERCOMPANY_CLOSED = PatternFill("solid", fgColor="E2F0D9")
FILL_REVIEW = PatternFill("solid", fgColor="F4CCCC")
FILL_PROCUREMENT_COMPLETE = PatternFill("solid", fgColor="C6EFCE")


def empty_registry():
    return {"version": 3, "deals": {}, "invoices": [], "intercompany_settlements": [],
            "unallocated_stock": [], "allocation_audit": [], "mapping_memory": []}


def ensure_schema(data):
    data["version"] = max(3, int(data.get("version") or 0)); data.setdefault("deals", {})
    data.setdefault("invoices", []); data.setdefault("intercompany_settlements", [])
    data.setdefault("unallocated_stock", []); data.setdefault("allocation_audit", [])
    data.setdefault("mapping_memory", [])
    return data


def normalized_item_name(value):
    value = str(value or "").casefold().replace("ё", "е").replace("×", "x")
    value = re.sub(r"\b(шт|штук|метр|метров|м|комплект|комплекта|компл|ед)\.?\b", " ", value)
    return re.sub(r"[^0-9a-zа-я]+", " ", value).strip()


def item_similarity(source, candidate):
    source_sku = normalized_reference(source.get("sku") or source.get("source_sku"))
    candidate_sku = normalized_reference(candidate.get("sku") or candidate.get("supplier_sku"))
    if source_sku and candidate_sku and source_sku == candidate_sku:
        return 1.0, "точный артикул"
    left = normalized_item_name(source.get("name") or source.get("source_name"))
    right = normalized_item_name(candidate.get("name"))
    if not left or not right:
        return 0.0, "нет названия"
    left_tokens, right_tokens = set(left.split()), set(right.split())
    token_score = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence_score = SequenceMatcher(None, left, right).ratio()
    score = max(token_score, sequence_score * 0.9)
    return score, "похожее наименование"


def _unallocated_source_rows(spec):
    rows = []
    updates_by_key = {str(x.get("source_line_key") or ""): x for x in spec.get("updates") or []}
    for index, raw in enumerate(spec.get("unallocated") or []):
        key = str(raw.get("source_line_key") or raw.get("key") or f"line-{index + 1}")
        original = updates_by_key.get(key) or {}
        qty = float(raw.get("qty") or raw.get("source_qty") or 0)
        amount = float(raw.get("amount") or raw.get("source_total") or 0)
        if qty <= 0 and amount <= 0:
            continue
        rows.append({
            "source_line_key": key,
            "name": raw.get("name") or raw.get("source_name") or original.get("source_name") or key,
            "sku": raw.get("sku") or raw.get("source_sku") or original.get("source_sku") or "",
            "unit": raw.get("unit") or original.get("source_unit") or "",
            "qty": qty, "amount": round(amount, 2),
        })
    return rows


def suggest_distribution(spec, limit=10, candidate_deal_ids=None):
    """Suggest other deals for quantities left after satisfying the selected deal."""
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    current_id = str(spec.get("deal_id") or "")
    allowed_deals = {str(x) for x in candidate_deal_ids or []}
    suggestions, inventory = [], []
    deal_rows = []
    for deal_id, deal in (data.get("deals") or {}).items():
        if str(deal_id) == current_id or deal.get("closed_at") or deal.get("status") == "закрыта":
            continue
        if allowed_deals and str(deal_id) not in allowed_deals:
            continue
        for item in deal.get("items") or []:
            needed = max(0.0, float(item.get("qty") or 0) - float(item.get("actual_qty") or 0))
            if needed > 1e-9:
                deal_rows.append((str(deal_id), deal, item, needed))
    for source in _unallocated_source_rows(spec):
        remaining_qty, remaining_amount = source["qty"], source["amount"]
        candidates = []
        for deal_id, deal, item, needed in deal_rows:
            score, reason = item_similarity(source, item)
            if score < 0.62:
                continue
            candidates.append((score, int(deal_id) if deal_id.isdigit() else 0,
                               deal_id, deal, item, needed, reason))
        candidates.sort(key=lambda row: (-row[0], -row[1]))
        for score, _, deal_id, deal, item, needed, reason in candidates[:max(1, int(limit))]:
            if remaining_qty <= 1e-9:
                break
            qty = min(remaining_qty, needed)
            amount = round(source["amount"] * qty / source["qty"], 2) if source["qty"] else 0
            # The last split inherits the rounding remainder.
            if abs(qty - remaining_qty) <= 1e-9:
                amount = remaining_amount
            suggestions.append({
                "source_line_key": source["source_line_key"], "source_name": source["name"],
                "source_sku": source["sku"], "source_qty": source["qty"],
                "source_total": source["amount"], "deal_id": deal_id,
                "offer_id": item.get("offer_id"), "offer_row_id": item.get("offer_row_id"),
                "target_name": item.get("name"), "qty": qty, "amount": amount,
                "needed": needed, "confidence": round(score, 3), "reason": reason,
                "requires_confirmation": score < 0.98,
            })
            remaining_qty -= qty; remaining_amount = round(remaining_amount - amount, 2)
        if remaining_qty > 1e-9 or remaining_amount > 0.01:
            inventory.append({**source, "qty": max(0.0, remaining_qty),
                              "amount": max(0.0, remaining_amount)})
    return {"current_deal_id": current_id, "suggestions": suggestions,
            "inventory_remainder": inventory, "checked_deals": len({x[0] for x in deal_rows})}


@transaction(lambda: REGISTRY)
def put_unallocated_stock(spec, rows, actor="telegram"):
    """Put confirmed invoice remainders into the purchasing company's internal stock."""
    if not rows:
        return []
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    doc = spec.get("invoice") or {}
    document_key = invoice_document_key(doc)
    purchasing = own_companies.resolve_company(inn=doc.get("buyer_inn"), name=doc.get("buyer"))
    created = []
    for index, row in enumerate(rows):
        qty, amount = float(row.get("qty") or 0), round(float(row.get("amount") or 0), 2)
        if qty <= 0 and amount <= 0:
            continue
        source_key = str(row.get("source_line_key") or row.get("key") or f"line-{index + 1}")
        stock_id = hashlib.sha256(f"{document_key}|{source_key}".encode()).hexdigest()[:20]
        existing = next((x for x in data["unallocated_stock"] if x.get("id") == stock_id), None)
        if existing:
            # Idempotent replay of the same confirmed remainder.
            created.append(existing); continue
        item = {
            "id": stock_id, "document_key": document_key, "invoice_number": doc.get("number") or "",
            "invoice_date": doc.get("date") or "", "supplier": doc.get("supplier") or "",
            "supplier_inn": doc.get("supplier_inn") or "", "purchasing_company": company_ref(purchasing),
            "source_path": doc.get("source_path") or "", "source_line_key": source_key,
            "sku": row.get("sku") or row.get("source_sku") or "",
            "name": row.get("name") or row.get("source_name") or source_key,
            "unit": row.get("unit") or "", "initial_qty": qty, "available_qty": qty,
            "initial_amount": amount, "available_amount": amount, "allocations": [],
            "status": "нераспределено", "created_at": datetime.now(timezone.utc).isoformat(), "actor": actor,
        }
        data["unallocated_stock"].append(item); created.append(item)
        data["allocation_audit"].append({"action": "stock_created", "stock_id": stock_id,
            "qty": qty, "amount": amount, "actor": actor,
            "created_at": datetime.now(timezone.utc).isoformat()})
    save_registry(data)
    return created


@transaction(lambda: REGISTRY)
def record_excluded_remainder(spec, rows, reason, actor="telegram"):
    if not str(reason or "").strip():
        raise ValueError("укажите причину исключения остатка")
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    document_key = invoice_document_key(spec.get("invoice") or {})
    events = []
    for row in rows:
        event = {"action": "remainder_excluded", "document_key": document_key,
                 "source_line_key": row.get("source_line_key") or row.get("key"),
                 "name": row.get("name") or row.get("source_name"), "qty": float(row.get("qty") or 0),
                 "amount": float(row.get("amount") or 0), "reason": str(reason).strip(),
                 "actor": actor, "created_at": datetime.now(timezone.utc).isoformat()}
        data["allocation_audit"].append(event); events.append(event)
    save_registry(data); return events


def list_unallocated_stock(company_id=None, query=None):
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    needle = normalized_item_name(query) if query else ""
    rows = []
    for item in data["unallocated_stock"]:
        if float(item.get("available_qty") or 0) <= 1e-9 and float(item.get("available_amount") or 0) <= 0.01:
            continue
        if company_id and (item.get("purchasing_company") or {}).get("id") != company_id:
            continue
        if needle and needle not in normalized_item_name(f"{item.get('sku')} {item.get('name')}"):
            continue
        rows.append(item)
    return sorted(rows, key=lambda x: x.get("created_at") or "", reverse=True)


@transaction(lambda: REGISTRY)
def consume_unallocated_stock(stock_id, deal_id, qty, offer_id=None, offer_row_id=None,
                              actor="telegram"):
    """Reserve a confirmed quantity from internal stock for one deal, idempotently."""
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    stock = next((x for x in data["unallocated_stock"] if x.get("id") == stock_id), None)
    if not stock:
        raise ValueError("нераспределённый остаток не найден")
    qty = float(qty)
    available_qty = float(stock.get("available_qty") or 0)
    if not math.isfinite(qty) or qty <= 0:
        raise ValueError('Количество должно быть конечным положительным числом')
    allocation_key = hashlib.sha256(
        f"{stock_id}|{deal_id}|{offer_row_id}|{qty:.9f}".encode()).hexdigest()[:20]
    previous = next((x for x in stock.get("allocations") or [] if x.get("id") == allocation_key), None)
    if previous:
        return previous
    if qty > available_qty + 1e-9:
        raise ValueError(f"доступно только {available_qty:g} {stock.get('unit') or ''}".strip())
    available_amount = float(stock.get("available_amount") or 0)
    amount = (available_amount if abs(qty - available_qty) <= 1e-9 else
              round(available_amount * qty / available_qty, 2))
    allocation = {"id": allocation_key, "deal_id": str(deal_id), "offer_id": offer_id,
                  "offer_row_id": offer_row_id, "qty": qty, "amount": amount,
                  "created_at": datetime.now(timezone.utc).isoformat(), "actor": actor}
    stock.setdefault("allocations", []).append(allocation)
    stock["available_qty"] = max(0.0, available_qty - qty)
    stock["available_amount"] = max(0.0, round(available_amount - amount, 2))
    stock["status"] = "распределено" if stock["available_qty"] <= 1e-9 else "частично распределено"
    data["allocation_audit"].append({"action": "stock_consumed", "stock_id": stock_id,
        **allocation})
    save_registry(data)
    return allocation


def export_unallocated_stock():
    wb = Workbook(); ws = wb.active; ws.title = "Нераспределённые закупки"
    headers = ["Организация", "Артикул / модель", "Наименование", "Доступно", "Ед.",
               "Стоимость остатка", "Поставщик", "Счёт", "Дата счёта", "Статус"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="263238")
    for item in list_unallocated_stock():
        ws.append([(item.get("purchasing_company") or {}).get("name"), item.get("sku"), item.get("name"),
                   item.get("available_qty"), item.get("unit"), item.get("available_amount"),
                   item.get("supplier"), item.get("invoice_number"), item.get("invoice_date"), item.get("status")])
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    for index, width in enumerate([25, 26, 60, 12, 9, 18, 30, 16, 14, 22], 1):
        ws.column_dimensions[get_column_letter(index)].width = width
    out_dir = tempfile.mkdtemp(prefix="unallocated-stock-")
    path = os.path.join(out_dir, "Нераспределённые закупки.xlsx")
    wb.save(path); return path


def suggest_stock_for_deal(deal_id, limit=20, min_score=0.62):
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    deal = (data.get("deals") or {}).get(str(deal_id)) or snapshot(deal_id)
    suggestions = []
    for target in deal.get("items") or []:
        needed = max(0.0, float(target.get("qty") or 0) - float(target.get("actual_qty") or 0))
        if needed <= 1e-9:
            continue
        for stock in list_unallocated_stock():
            score, reason = item_similarity(stock, target)
            if score < float(min_score):
                continue
            qty = min(needed, float(stock.get("available_qty") or 0))
            unit_cost = (float(stock.get("available_amount") or 0) /
                         float(stock.get("available_qty") or 1))
            suggestions.append({"stock_id": stock["id"], "deal_id": str(deal_id),
                "offer_id": target.get("offer_id"), "offer_row_id": target.get("offer_row_id"),
                "target_name": target.get("name"), "stock_name": stock.get("name"),
                "qty": qty, "amount": round(qty * unit_cost, 2), "needed": needed,
                "confidence": round(score, 3), "reason": reason,
                "cross_company": ((stock.get("purchasing_company") or {}).get("id") !=
                                  (deal.get("selling_company") or {}).get("id"))})
    suggestions.sort(key=lambda x: (-x["confidence"], x["target_name"] or ""))
    return suggestions[:int(limit)]


def company_ref(company):
    return ({"id": company.get("id"), "name": company.get("name"), "inn": company.get("inn")}
            if company else {"id": "unknown", "name": "не определена", "inn": ""})


def deal_selling_company(data, deal_id):
    deal = (data.get("deals") or {}).get(str(deal_id)) or {}
    stored = deal.get("selling_company") or {}
    return own_companies.company_by_id(stored.get("id")) or own_companies.default_selling_company()


def intercompany_status(invoice):
    if invoice.get("organization_mismatch"):
        return "требует проверки"
    if not invoice.get("is_intercompany"):
        return "не требуется"
    total = float(invoice.get("intercompany_amount") or invoice.get("total") or 0)
    settled = float(invoice.get("intercompany_settled") or 0)
    if settled + 0.01 >= total:
        return "компенсировано"
    if settled > 0:
        return "частично компенсировано"
    return "не компенсировано"


def invoice_document_key(doc):
    """Identity of the external document, deliberately independent of a deal."""
    values = [doc.get("supplier_inn"), doc.get("buyer_inn"), doc.get("number"),
              doc.get("date"), doc.get("currency") or "RUB",
              f"{float(doc.get('foreign_total', doc.get('total')) or 0):.2f}"]
    return hashlib.sha256("|".join(str(x or "").strip().casefold() for x in values).encode()).hexdigest()[:20]


def allocation_amount(spec):
    total = sum(float(x.get("material_cost_used") or 0) + float(x.get("work_cost_used") or 0)
                for x in spec.get("updates") or [])
    total += sum((float(x.get("cost_material") or 0) + float(x.get("cost_work") or 0)) *
                 float(x.get("qty") or 0) for x in spec.get("additions") or [])
    total += sum(float(x.get("amount") or x.get("total") or 0)
                 for x in spec.get("additional_expenses") or [])
    return round(total, 2)


def allocation_line_keys(spec):
    keys = []
    for index, row in enumerate(spec.get("updates") or []):
        key = row.get("source_line_key") or row.get("source_sku") or row.get("source_name")
        if key:
            keys.append(str(key).strip().casefold())
    for row in spec.get("additional_expenses") or []:
        key = row.get("source_line_key") or row.get("source_sku") or row.get("source_name")
        if key:
            keys.append(str(key).strip().casefold())
    return keys


def allocation_source_lines(spec):
    lines = []
    for row in spec.get("updates") or []:
        key = row.get("source_line_key") or row.get("source_sku") or row.get("source_name")
        if not key:
            continue
        lines.append({"key": str(key).strip().casefold(), "offer_row_id": row.get("offer_row_id"),
                      "offer_id": row.get("offer_id"), "source_sku": row.get("source_sku") or "",
                      "source_name": row.get("source_name") or "", "source_qty": float(row.get("source_qty") or 0),
                      "source_total": float(row.get("source_total") or 0), "qty_used": float(row.get("qty_used") or 0),
                      "amount_used": float(row.get("material_cost_used") or 0) + float(row.get("work_cost_used") or 0),
                      "foreign_source_total": row.get("foreign_source_total"),
                      "foreign_amount_used": (float(row.get("foreign_material_cost_used") or 0) +
                                              float(row.get("foreign_work_cost_used") or 0)) or None})
    for row in spec.get("additional_expenses") or []:
        key = row.get("source_line_key") or row.get("source_sku") or row.get("source_name")
        if not key:
            continue
        lines.append({"key": str(key).strip().casefold(), "offer_row_id": row.get("offer_row_id"),
                      "offer_id": row.get("offer_id"), "source_sku": row.get("source_sku") or "",
                      "source_name": row.get("source_name") or row.get("name") or "",
                      "source_qty": float(row.get("source_qty") or row.get("qty") or 0),
                      "source_total": float(row.get("source_total") or row.get("amount") or 0),
                      "qty_used": float(row.get("qty") or row.get("source_qty") or 0),
                      "amount_used": float(row.get("amount") or row.get("total") or 0),
                      "foreign_source_total": row.get("foreign_source_total") or row.get("foreign_amount"),
                      "foreign_amount_used": row.get("foreign_amount")})
    return lines


def invoice_source_usage(data, document_key):
    """Return all confirmed use of individual supplier-invoice lines.

    A line can be consumed in two legitimate ways: directly in an invoice
    allocation or later from the internal-stock register.  Treating only the
    first as used made a repeated upload offer stock which had already been
    assigned to a deal for the second time.
    """
    usage = {}

    def add(key, qty, amount):
        key = str(key or "").strip().casefold()
        if not key:
            return
        used = usage.setdefault(key, {"qty": 0.0, "amount": 0.0})
        used["qty"] += float(qty or 0)
        used["amount"] += float(amount or 0)

    for invoice in data.get("invoices") or []:
        if invoice.get("document_key") != document_key:
            continue
        for allocation in invoice.get("allocations") or []:
            for line in allocation.get("source_lines") or []:
                add(line.get("key"), line.get("qty_used"), line.get("amount_used"))
    for stock in data.get("unallocated_stock") or []:
        if stock.get("document_key") != document_key:
            continue
        initial_qty = float(stock.get("initial_qty") or 0)
        initial_amount = float(stock.get("initial_amount") or 0)
        for allocation in stock.get("allocations") or []:
            qty = float(allocation.get("qty") or 0)
            # Stock allocations retain quantity and total, not a separate
            # amount. Keep the source unit cost exactly proportional.
            amount = round(initial_amount * qty / initial_qty, 2) if initial_qty else 0
            add(stock.get("source_line_key"), qty, amount)
    return usage


def prepare_invoice_allocation(spec):
    """Preflight before any Megaplan cost write; prevents duplicate allocation."""
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    doc = spec.get("invoice") or {}
    key = invoice_document_key(doc)
    existing = next((x for x in data["invoices"] if x.get("document_key") == key), None)
    amount = allocation_amount(spec)
    if amount <= 0:
        return {"ok": False, "error": "в выбранную сделку не сопоставлено ни одной позиции счёта"}
    allocated = float(existing.get("allocated_total") or 0) if existing else 0
    total = float(doc.get("total") or 0)
    remaining = round(total - allocated, 2)
    old_usage = invoice_source_usage(data, key)
    legacy_keys = set()
    if existing:
        for allocation in existing.get("allocations") or []:
            detailed = allocation.get("source_lines") or []
            legacy_keys.update(set(allocation.get("source_line_keys") or []) - {x.get("key") for x in detailed})
    for line in allocation_source_lines(spec):
        if line["key"] in legacy_keys:
            return {"ok": False, "error": f"строка счёта уже распределена: {line['key']}"}
        used = old_usage.get(line["key"], {"qty": 0, "amount": 0})
        if line["source_qty"] and used["qty"] + line["qty_used"] > line["source_qty"] + 1e-9:
            return {"ok": False, "error": f"по строке {line['key']} распределяется больше количества, чем в счёте"}
        if line["source_total"] and used["amount"] + line["amount_used"] > line["source_total"] + 0.01:
            return {"ok": False, "error": f"по строке {line['key']} распределяется сумма больше суммы строки"}
    if amount > remaining + 0.01:
        return {"ok": False, "error": (f"распределение {amount:.2f} ₽ превышает "
                                         f"нераспределённый остаток {remaining:.2f} ₽")}
    return {"ok": True, "document_key": key, "existing": bool(existing),
            "allocated_before": allocated, "allocation_amount": amount,
            "remaining_before": remaining, "remaining_after": round(remaining - amount, 2),
            "invoice_id": existing.get("id") if existing else None}


def invoice_allocation_status(spec):
    """Return what has already been allocated from this external invoice.

    This is intentionally read-only.  Telegram uses it before capping a repeated
    upload so already applied source lines are not mistaken for fresh stock.
    """
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    doc = spec.get("invoice") or {}
    key = invoice_document_key(doc)
    existing = next((x for x in data["invoices"] if x.get("document_key") == key), None)
    usage = invoice_source_usage(data, key)
    stocked_line_keys = {
        str(stock.get("source_line_key") or "").strip().casefold()
        for stock in data.get("unallocated_stock") or []
        if stock.get("document_key") == key and stock.get("source_line_key")
    }
    return {"ok": True, "existing": bool(existing), "document_key": key,
            "allocated_total": float(existing.get("allocated_total") or 0) if existing else 0,
            "invoice_total": float(doc.get("total") or 0), "source_usage": usage,
            "stocked_line_keys": sorted(stocked_line_keys)}


def intercompany_balances(data):
    grouped = {}
    for inv in data.get("invoices") or []:
        allocations = inv.get("allocations") or [{"selling_company": inv.get("selling_company"),
                                                    "amount": inv.get("intercompany_amount") or inv.get("total"),
                                                    "intercompany_settled": inv.get("intercompany_settled"),
                                                    "is_intercompany": inv.get("is_intercompany")}]
        for allocation in allocations:
            if not allocation.get("is_intercompany") or inv.get("organization_mismatch"):
                continue
            debtor_ref = allocation.get("selling_company") or {}
            creditor_ref = inv.get("purchasing_company") or {}
            debtor, creditor = debtor_ref.get("id"), creditor_ref.get("id")
            if not debtor or not creditor or debtor == creditor:
                continue
            key = (debtor, creditor)
            row = grouped.setdefault(key, {"debtor": debtor_ref, "creditor": creditor_ref,
                                           "purchases": 0.0, "settled": 0.0,
                                           "invoice_ids": set()})
            row["purchases"] += float(allocation.get("amount") or 0)
            row["settled"] += float(allocation.get("intercompany_settled") or 0)
            row["invoice_ids"].add(inv.get("id"))
    for row in grouped.values():
        row["balance"] = round(row["purchases"] - row["settled"], 2)
        row["invoices"] = len(row.pop("invoice_ids"))
    return sorted(grouped.values(), key=lambda x: (x["debtor"]["name"], x["creditor"]["name"]))


def accounting_hints(deal_id=None):
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    invoices = [x for x in data["invoices"] if deal_id is None or
                str(x.get("deal_id")) == str(deal_id) or
                any(str(a.get("deal_id")) == str(deal_id) for a in x.get("allocations") or [])]
    hints = []
    for inv in invoices:
        if inv.get("organization_mismatch"):
            hints.append({"level": "error", "deal_id": inv.get("deal_id"),
                          "text": f"Счёт №{inv.get('number') or 'б/н'}: организация-покупатель или плательщик требует проверки."})
        else:
            allocations = inv.get("allocations") or [{"deal_id": inv.get("deal_id"),
                "selling_company": inv.get("selling_company"), "amount": inv.get("intercompany_amount") or inv.get("total"),
                "intercompany_settled": inv.get("intercompany_settled"), "is_intercompany": inv.get("is_intercompany")}]
            for allocation in allocations:
                if not allocation.get("is_intercompany"):
                    continue
                selling = (allocation.get("selling_company") or {}).get("name")
                purchasing = (inv.get("purchasing_company") or {}).get("name")
                balance = float(allocation.get("amount") or 0) - float(allocation.get("intercompany_settled") or 0)
                hints.append({"level": "warning", "deal_id": allocation.get("deal_id"),
                              "text": (f"{purchasing} приобрело для сделки №{allocation.get('deal_id')} ({selling}) "
                                       f"по счёту №{inv.get('number')} на {float(allocation.get('amount') or 0):,.2f} ₽; "
                                       f"осталось компенсировать {balance:,.2f} ₽.").replace(",", " ")})
    outstanding_pairs = {}
    for inv in invoices:
        if not inv.get("is_intercompany") or intercompany_status(inv) == "компенсировано":
            continue
        pair = ((inv.get("selling_company") or {}).get("id"),
                (inv.get("purchasing_company") or {}).get("id"))
        try:
            invoice_date = datetime.strptime(inv.get("date") or "", "%d.%m.%Y")
        except ValueError:
            invoice_date = None
        if pair[0] and pair[1] and invoice_date and (pair not in outstanding_pairs or invoice_date < outstanding_pairs[pair]):
            outstanding_pairs[pair] = invoice_date
    bank = load_json(BANK_REGISTRY, {"transactions": []})
    candidates = []
    used = {x.get("transaction_id") for x in data.get("intercompany_settlements") or []}
    for tx in bank.get("transactions") or []:
        if tx.get("direction") != "expense" or tx.get("id") in used:
            continue
        sender = own_companies.resolve_company(account=tx.get("account"))
        receiver = own_companies.resolve_company(inn=tx.get("counterparty_inn"),
                                                 account=tx.get("counterparty_account"),
                                                 name=tx.get("counterparty"))
        if sender and receiver and sender.get("id") != receiver.get("id"):
            pair = (sender.get("id"), receiver.get("id"))
            try:
                payment_date = datetime.strptime(tx.get("date") or "", "%d.%m.%Y")
            except ValueError:
                payment_date = None
            # A transfer made before the oldest still-open obligation cannot settle it.
            if pair not in outstanding_pairs or not payment_date or payment_date < outstanding_pairs[pair]:
                continue
            candidates.append({"transaction_id": tx.get("id"), "date": tx.get("date"),
                               "amount": float(tx.get("amount") or 0), "from": company_ref(sender),
                               "to": company_ref(receiver), "purpose": tx.get("purpose") or ""})
    return {"hints": hints, "balances": intercompany_balances(data),
            "settlement_candidates": candidates}


@transaction(lambda: REGISTRY)
def record_intercompany_settlement(transaction_id, debtor_id, creditor_id, amount, date=""):
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    if any(x.get("transaction_id") == transaction_id for x in data["intercompany_settlements"]):
        raise ValueError("этот межфирменный платёж уже учтён")
    amount = float(amount)
    if amount <= 0:
        raise ValueError("сумма компенсации должна быть больше нуля")
    remaining = amount; allocations = []
    for inv in sorted(data["invoices"], key=lambda x: (x.get("date") or "", x.get("created_at") or "")):
        if not inv.get("is_intercompany"):
            continue
        if (inv.get("selling_company") or {}).get("id") != debtor_id:
            continue
        if (inv.get("purchasing_company") or {}).get("id") != creditor_id:
            continue
        open_amount = float(inv.get("intercompany_amount") or inv.get("total") or 0) - float(inv.get("intercompany_settled") or 0)
        applied = min(max(0, open_amount), remaining)
        if applied <= 0:
            continue
        inv["intercompany_settled"] = round(float(inv.get("intercompany_settled") or 0) + applied, 2)
        inv["intercompany_status"] = intercompany_status(inv)
        allocations.append({"invoice_id": inv["id"], "deal_id": inv["deal_id"], "amount": applied})
        remaining -= applied
        if remaining <= 0.01:
            break
    if remaining > 0.01:
        raise ValueError(f"компенсация превышает подтверждённую задолженность на {remaining:.2f} ₽")
    row = {"transaction_id": transaction_id, "debtor_id": debtor_id, "creditor_id": creditor_id,
           "amount": amount, "date": date, "allocations": allocations,
           "created_at": datetime.now(timezone.utc).isoformat()}
    data["intercompany_settlements"].append(row); save_registry(data)
    return row


@transaction(lambda: REGISTRY)
def set_deal_company(deal_id, company_id):
    company = own_companies.company_by_id(company_id)
    if not company:
        raise ValueError("наша организация не найдена в справочнике")
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    deal = data["deals"].setdefault(str(deal_id), {"deal_id": str(deal_id), "items": []})
    deal["selling_company"] = company_ref(company)
    for inv in data["invoices"]:
        if str(inv.get("deal_id")) != str(deal_id):
            continue
        inv["selling_company"] = company_ref(company)
        purchasing_id = (inv.get("purchasing_company") or {}).get("id")
        inv["is_intercompany"] = bool(purchasing_id and purchasing_id != "unknown" and purchasing_id != company_id)
        inv["intercompany_amount"] = float(inv.get("total") or 0) if inv["is_intercompany"] else 0
        inv["intercompany_status"] = intercompany_status(inv)
    save_registry(data)
    return deal


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as source:
            return json.load(source)
    except FileNotFoundError:
        return default


def reconcile_invoice_totals(data):
    """Recompute summaries from original allocations AND later stock consumption.

    Never append stock consumption to invoice allocations: those are two distinct
    sources of usage and doing so would charge the same goods twice.
    """
    from decimal import Decimal
    money = lambda value: Decimal(str(value or 0))
    for invoice in data.get("invoices", []):
        if "allocations" not in invoice:
            continue  # Do not invent detail for legacy summaries.
        direct = sum((money(a.get("amount")) for a in invoice["allocations"]), Decimal(0))
        stock_used = sum((money(a.get("amount"))
                          for s in data.get("unallocated_stock", [])
                          if s.get("document_key") == invoice.get("document_key")
                          for a in s.get("allocations", [])), Decimal(0))
        invoice["allocated_total"] = float(round(direct + stock_used, 2))
        invoice["stock_allocated_total"] = float(round(stock_used, 2))
        invoice["unallocated_total"] = float(round(money(invoice.get("total")) - direct - stock_used, 2))
        invoice["allocation_status"] = "распределён" if abs(invoice["unallocated_total"]) <= 0.01 else (
            "требует сверки" if invoice["unallocated_total"] < 0 else "частично распределён")
        if invoice.get("status") in ("распределён", "частично распределён", "распределяется", "требует сверки"):
            invoice["status"] = invoice["allocation_status"]
    return data


def save_registry(data):
    reconcile_invoice_totals(data)
    tmp = f"{REGISTRY}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as target:
        json.dump(data, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.flush(); os.fsync(target.fileno())
    os.replace(tmp, REGISTRY)


def procurement_items(deal_id):
    rows = deal_ledger.load(str(deal_id))
    result = []
    for row in rows:
        material_values = financial_amounts.component_values(deal_id, row, "cost_material")
        material = material_values["unit"]
        supplier = row.get("supplier") or (row.get("price_source") if row.get("price_source") in ("hogart", "daichi") else None)
        # Pure labour is not purchased. Unknown-cost tangible lines remain visible.
        pure_work = row.get("position_type") == "service" if row.get("position_type") else float(row.get("cost_work") or 0) > 0 and material == 0 and not supplier
        if pure_work:
            continue
        item = {
            "offer_id": row.get("offer_id"), "offer_row_id": row.get("offer_row_id"),
            "name": row.get("name"), "sku": row.get("supplier_sku") or "",
            "qty": row.get("qty"), "unit": row.get("unit") or "",
            "supplier": supplier or "не определён", "planned_unit_cost": material,
            "planned_unit_work": float(row.get("cost_work") or 0),
            "planned_total": round(material_values["line_total"], 2),
            "planned_material_basis": material_values["basis"],
            "actual_qty": float(row.get("consumed_qty") or 0),
            "actual_total": float(row.get("cumulative_cost_material") or 0),
        }
        item["status"] = "заказано через API" if supplier == "hogart" else "запросить счёт"
        if supplier == "daichi":
            item["status"] = "запросить счёт (API без заказа)"
        if supplier in ("hogart", "daichi") and not item["sku"]:
            item["status"] = "требует артикула"
        result.append(item)
    return result


@transaction(lambda: REGISTRY)
def snapshot(deal_id):
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    hogart = load_json(HOGART_JOURNAL, {}).get(str(deal_id)) or {}
    items = procurement_items(deal_id)
    from procurement_projection import confirmed_totals
    confirmed = confirmed_totals(data)
    for item in items:
        proof = confirmed.get((str(deal_id), str(item.get("offer_row_id"))), {})
        item["actual_qty"] = max(item["actual_qty"], float(proof.get("qty", 0)))
        item["actual_total"] = max(item["actual_total"], float(proof.get("cost", 0)))
    previous = (data.get("deals") or {}).get(str(deal_id)) or {}
    previous_by_row = {str(x.get("offer_row_id")): x for x in previous.get("items") or []}
    for item in items:
        old = previous_by_row.get(str(item.get("offer_row_id"))) or {}
        # Planned costs are re-derived from the canonical basis on every snapshot.
        # Preserve operational state only; otherwise a legacy line-total value can
        # survive forever as a falsely multiplied unit price.
        for key in ("received_qty", "received_at", "receipt_history"):
            if key in old:
                item[key] = old[key]
        received = float(item.get("received_qty") or 0)
        item["received_qty"] = received
        item["remaining_qty"] = max(0, float(item.get("qty") or 0) - received)
        if received >= float(item.get("qty") or 0) and float(item.get("qty") or 0) > 0:
            item["status"] = "получено"
        elif received > 0:
            item["status"] = "частично получено"
    deal_record = {
        "deal_id": str(deal_id), "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items, "hogart_order": hogart,
    }
    for key in ("closed_at", "status", "selling_company"):
        if key in previous:
            deal_record[key] = previous[key]
    if not deal_record.get("selling_company"):
        deal_record["selling_company"] = company_ref(own_companies.default_selling_company())
    data["deals"][str(deal_id)] = deal_record
    save_registry(data)
    return data["deals"][str(deal_id)]


def deal_item_supplier_links(data, deal_id):
    """Suppliers proven by invoice allocations, keyed by Megaplan offer row/id."""
    by_row, by_offer = {}, {}
    for invoice in data.get("invoices") or []:
        supplier = str(invoice.get("supplier") or "не указан").strip()
        for allocation in invoice.get("allocations") or []:
            if str(allocation.get("deal_id")) != str(deal_id):
                continue
            for update in allocation.get("updates") or []:
                row_id, offer_id = str(update.get("offer_row_id") or ""), str(update.get("offer_id") or "")
                if row_id:
                    by_row.setdefault(row_id, [])
                    if supplier not in by_row[row_id]: by_row[row_id].append(supplier)
                if offer_id:
                    by_offer.setdefault(offer_id, [])
                    if supplier not in by_offer[offer_id]: by_offer[offer_id].append(supplier)
    return by_row, by_offer


@transaction(lambda: REGISTRY)
def export(deal_id, accounting=False):
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    deal = data["deals"].get(str(deal_id)) or snapshot(deal_id)
    wb = Workbook(); ws = wb.active
    ws.title = "Закупка"
    headers = ["Поставщик", "Артикул / модель", "Наименование", "Кол-во", "Ед.",
               "План, ₽/ед.", "План, ₽", "Закуплено", "Факт, ₽", "Получено", "Осталось", "Статус"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="263238")
    suppliers_by_row, suppliers_by_offer = deal_item_supplier_links(data, deal_id)
    for item in deal["items"]:
        linked_suppliers = (suppliers_by_row.get(str(item.get("offer_row_id") or "")) or
                            suppliers_by_offer.get(str(item.get("offer_id") or "")) or [])
        supplier = "; ".join(linked_suppliers) if linked_suppliers else item.get("supplier") or "не определён"
        planned_qty, actual_qty = float(item.get("qty") or 0), float(item.get("actual_qty") or 0)
        fully_linked = planned_qty > 0 and actual_qty + 1e-9 >= planned_qty
        status = "полностью привязано к счетам" if fully_linked else item.get("status")
        values = [supplier] + [item.get(k, 0 if k in ("received_qty", "remaining_qty") else "") for k in
                   ("sku", "name", "qty", "unit", "planned_unit_cost", "planned_total",
                    "actual_qty", "actual_total", "received_qty", "remaining_qty")] + [status]
        ws.append(values)
        if fully_linked:
            for cell in ws[ws.max_row]: cell.fill = FILL_PROCUREMENT_COMPLETE
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    widths = [18, 30, 62, 11, 9, 15, 15, 12, 15, 12, 12, 22]
    for index, width in enumerate(widths, 1): ws.column_dimensions[chr(64 + index)].width = width
    inv = wb.create_sheet("Счета поставщиков")
    inv.append(["Сделка", "Организация продажи", "Организация закупки", "Поставщик", "ИНН поставщика",
                "Счёт", "Дата счёта", "Валюта", "Сумма в валюте", "План, ₽", "Курс плана", "НДС", "Факт оплаты, ₽", "Дата оплаты", "Статус счёта",
                "Межфирменная закупка", "Компенсировано", "Статус взаиморасчётов", "Привязан"])
    for cell in inv[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="263238")
    deal_invoices = [x for x in data.get("invoices", []) if str(x.get("deal_id")) == str(deal_id) or
                     any(str(a.get("deal_id")) == str(deal_id) for a in x.get("allocations") or [])]
    for row in deal_invoices:
        payments = row.get("payments") or []
        status = intercompany_status(row); row["intercompany_status"] = status
        inv.append([row.get("deal_id", ""), (row.get("selling_company") or {}).get("name", ""),
                    (row.get("purchasing_company") or {}).get("name", ""), row.get("supplier", ""),
                    row.get("supplier_inn", ""), row.get("number", ""), row.get("date", ""),
                    row.get("currency", "RUB"), row.get("foreign_total", ""), row.get("plan_total_rub", row.get("total", 0)), row.get("plan_rate", ""),
                    row.get("vat", 0), row.get("paid_total", 0),
                    ", ".join(x.get("date", "") for x in payments), row.get("status", ""),
                    "Да" if row.get("is_intercompany") else "Нет", row.get("intercompany_settled", 0),
                    status, row.get("created_at", "")])
        fill = (FILL_REVIEW if row.get("organization_mismatch") else
                FILL_INTERCOMPANY_CLOSED if status == "компенсировано" else
                FILL_INTERCOMPANY_PARTIAL if status == "частично компенсировано" else
                FILL_INTERCOMPANY_OPEN if row.get("is_intercompany") else None)
        if fill:
            for cell in inv[inv.max_row]: cell.fill = fill
    inv.freeze_panes = "A2"; inv.auto_filter.ref = inv.dimensions
    for index, width in enumerate([10, 24, 24, 28, 16, 14, 14, 10, 18, 16, 16, 14, 18, 18, 20, 18, 18, 24, 24], 1):
        inv.column_dimensions[get_column_letter(index)].width = width

    allocations = wb.create_sheet("Распределение по сделкам")
    allocations.append(["Счёт", "Поставщик", "Сделка", "Организация продажи",
                        "Организация закупки", "Распределено, ₽", "Остаток счёта, ₽", "Строки счёта"])
    for cell in allocations[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="263238")
    for invoice in deal_invoices:
        for allocation in invoice.get("allocations") or []:
            allocations.append([invoice.get("number"), invoice.get("supplier"), allocation.get("deal_id"),
                                (allocation.get("selling_company") or {}).get("name"),
                                (invoice.get("purchasing_company") or {}).get("name"), allocation.get("amount"),
                                invoice.get("unallocated_total"), ", ".join(allocation.get("source_line_keys") or [])])
            if allocation.get("is_intercompany"):
                for cell in allocations[allocations.max_row]: cell.fill = FILL_INTERCOMPANY_OPEN
    for index, width in enumerate([14, 28, 12, 25, 25, 18, 18, 55], 1):
        allocations.column_dimensions[get_column_letter(index)].width = width

    balances = wb.create_sheet("Межфирменный баланс")
    balances.append(["Должник", "Кредитор", "Закупки в интересах должника", "Компенсировано",
                     "Текущий баланс", "Количество счетов", "Подсказка бухгалтерии"])
    for cell in balances[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="263238")
    for row in intercompany_balances(data):
        hint = (f"{row['debtor']['name']} должно {row['creditor']['name']} "
                f"{row['balance']:,.2f} ₽").replace(",", " ")
        balances.append([row["debtor"]["name"], row["creditor"]["name"], row["purchases"],
                         row["settled"], row["balance"], row["invoices"], hint])
        for cell in balances[balances.max_row]: cell.fill = FILL_INTERCOMPANY_OPEN if row["balance"] else FILL_INTERCOMPANY_CLOSED
    for index, width in enumerate([25, 25, 26, 18, 18, 18, 65], 1):
        balances.column_dimensions[get_column_letter(index)].width = width
    candidates = accounting_hints(deal_id).get("settlement_candidates") or []
    review = wb.create_sheet("Переводы на проверку")
    review.append(["Дата", "От организации", "К организации", "Сумма", "Назначение", "Решение"])
    for cell in review[1]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="263238")
    for candidate in candidates:
        review.append([candidate.get("date"), candidate["from"]["name"], candidate["to"]["name"],
                       candidate.get("amount"), candidate.get("purpose"),
                       "Подтвердить, является ли компенсацией межфирменной закупки"])
        for cell in review[review.max_row]: cell.fill = FILL_REVIEW
    for index, width in enumerate([14, 25, 25, 16, 70, 55], 1):
        review.column_dimensions[get_column_letter(index)].width = width
    save_registry(data)
    out_dir = tempfile.mkdtemp(prefix=f"procurement-{deal_id}-")
    path = os.path.join(out_dir, f"Перечень оборудования и материалов — сделка №{deal_id}.xlsx")
    wb.save(path)
    return path


@transaction(lambda: REGISTRY)
def record_invoice(spec, result):
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    doc = spec.get("invoice") or {}
    preflight = prepare_invoice_allocation(spec)
    if not preflight.get("ok"):
        raise ValueError(preflight.get("error"))
    document_key = preflight["document_key"]
    row = next((x for x in data["invoices"] if x.get("document_key") == document_key), None)
    selling = deal_selling_company(data, spec["deal_id"])
    purchasing = own_companies.resolve_company(inn=doc.get("buyer_inn"), name=doc.get("buyer"))
    if row is None:
        row = {"id": document_key[:16], "document_key": document_key,
               "supplier": doc.get("supplier") or "не указан", "supplier_inn": doc.get("supplier_inn") or "",
               "buyer": doc.get("buyer") or "", "buyer_inn": doc.get("buyer_inn") or "",
               "purchasing_company": company_ref(purchasing), "number": doc.get("number") or "",
               "date": doc.get("date") or "", "total": doc.get("total") or 0, "vat": doc.get("vat") or 0,
               "currency": doc.get("currency") or "RUB", "foreign_total": doc.get("foreign_total"),
               "cbr_rate": doc.get("cbr_rate"), "cbr_effective_date": doc.get("cbr_effective_date"),
               "cbr_markup_pct": doc.get("cbr_markup_pct") or 0, "plan_rate": doc.get("plan_rate"),
               "rate_source": doc.get("rate_source") or "", "plan_total_rub": doc.get("plan_total_rub", doc.get("total") or 0),
               "source_path": doc.get("source_path") or "",
               "status": "распределяется", "created_at": datetime.now(timezone.utc).isoformat(),
               "allocated_total": 0, "allocations": [], "payments": [], "paid_total": 0,
               "organization_mismatch": purchasing is None}
        data["invoices"].append(row)
    allocation = {"id": hashlib.sha256((document_key + "|" + str(spec["deal_id"]) + "|" +
                                          json.dumps(spec.get("updates") or [], sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:16],
                  "deal_id": str(spec["deal_id"]), "selling_company": company_ref(selling),
                  "amount": preflight["allocation_amount"], "plan_amount_rub": preflight["allocation_amount"],
                  "source_line_keys": allocation_line_keys(spec),
                  "source_lines": allocation_source_lines(spec),
                  "updates": spec.get("updates") or [], "additions": spec.get("additions") or [],
                  "additional_expenses": spec.get("additional_expenses") or [],
                  "created_at": datetime.now(timezone.utc).isoformat(), "intercompany_settled": 0}
    allocation["is_intercompany"] = bool(purchasing and selling and purchasing.get("id") != selling.get("id"))
    row.setdefault("allocations", []).append(allocation)
    row["allocated_total"] = round(float(row.get("allocated_total") or 0) + allocation["amount"], 2)
    row["unallocated_total"] = round(float(row.get("total") or 0) - row["allocated_total"], 2)
    row["status"] = "распределён" if row["unallocated_total"] <= 0.01 else "частично распределён"
    # Compatibility summaries used by older exports and payment matching.
    row["deal_id"] = allocation["deal_id"] if len(row["allocations"]) == 1 else "несколько"
    row["selling_company"] = allocation["selling_company"]
    row["is_intercompany"] = any(x.get("is_intercompany") for x in row["allocations"])
    row["intercompany_amount"] = sum(float(x.get("amount") or 0) for x in row["allocations"] if x.get("is_intercompany"))
    row["intercompany_settled"] = sum(float(x.get("intercompany_settled") or 0) for x in row["allocations"])
    row["intercompany_status"] = intercompany_status(row)
    save_registry(data); snapshot(spec["deal_id"])
    return {**row, "allocation": allocation, "existing_document": preflight["existing"]}


def normalized_reference(value):
    normalized = str(value or "").casefold().replace("ё", "е")
    # Invoice references are often retyped with visually identical Cyrillic letters.
    normalized = normalized.translate(str.maketrans({
        "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h",
        "о": "o", "р": "p", "с": "c", "т": "t", "х": "x",
    }))
    return re.sub(r"[^0-9a-zа-я]", "", normalized)


@transaction(lambda: REGISTRY)
def reconcile_bank():
    """Apply only unambiguous expense payments to registered supplier invoices."""
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    bank = load_json(BANK_REGISTRY, {"transactions": [], "imports": []})
    matched, review = [], []
    used = {p.get("transaction_id") for inv in data["invoices"] for p in inv.get("payments") or []}
    for tx in bank.get("transactions") or []:
        if tx.get("direction") != "expense" or tx.get("id") in used:
            continue
        purpose = normalized_reference(tx.get("purpose"))
        candidates = []
        for inv in data["invoices"]:
            inn_ok = bool(inv.get("supplier_inn") and str(inv["supplier_inn"]) == str(tx.get("counterparty_inn") or ""))
            number = normalized_reference(inv.get("number"))
            number_ok = bool(number and number in purpose)
            if inn_ok and number_ok:
                candidates.append(inv)
        if len(candidates) != 1:
            if len(candidates) > 1:
                review.append({"transaction_id": tx.get("id"), "reason": "несколько счетов с тем же номером и ИНН"})
            continue
        inv = candidates[0]
        paying_company = own_companies.resolve_company(account=tx.get("account"))
        purchasing_id = (inv.get("purchasing_company") or {}).get("id")
        if not paying_company:
            review.append({"transaction_id": tx.get("id"), "invoice_id": inv["id"],
                           "reason": "не определена наша организация по расчётному счёту"})
            inv["organization_mismatch"] = True
            inv["intercompany_status"] = intercompany_status(inv)
            continue
        if purchasing_id and purchasing_id != "unknown" and paying_company.get("id") != purchasing_id:
            review.append({"transaction_id": tx.get("id"), "invoice_id": inv["id"],
                           "reason": (f"счёт выставлен на {(inv.get('purchasing_company') or {}).get('name')}, "
                                      f"а оплата идёт со счёта {paying_company.get('name')}")})
            inv["organization_mismatch"] = True
            inv["intercompany_status"] = intercompany_status(inv)
            continue
        already = float(inv.get("paid_total") or 0)
        amount = float(tx.get("amount") or 0)
        total = float(inv.get("total") or 0)
        foreign = str(inv.get("currency") or "RUB").upper() not in ("", "RUB", "RUR")
        # RUB invoices have an exact payable total. A foreign invoice has a RUB
        # planning equivalent only; the bank debit is intentionally allowed to
        # differ because it is the fact used for the currency deviation.
        if total <= 0 or amount <= 0 or (not foreign and already + amount > total + 0.01):
            review.append({"transaction_id": tx.get("id"), "invoice_id": inv["id"], "reason": "сумма требует проверки"})
            continue
        payment = {"transaction_id": tx["id"], "date": tx.get("date"), "amount": amount,
                   "document_number": tx.get("document_number"),
                   "paying_company": company_ref(paying_company), "account": tx.get("account")}
        inv.setdefault("payments", []).append(payment)
        inv["paid_total"] = round(already + amount, 2)
        if foreign:
            inv["status"] = "оплачен (факт по выписке)"
            inv["currency_deviation_rub"] = round(inv["paid_total"] - total, 2)
        else:
            inv["status"] = "оплачен" if abs(inv["paid_total"] - total) <= 0.01 else "частично оплачен"
        tx.update({"status": "assigned", "deal_id": str(inv["deal_id"]),
                   "deal_name": f"Оплата счёта поставщика №{inv.get('number')}",
                   "supplier_invoice_id": inv["id"], "assigned_at": datetime.now().isoformat(timespec="seconds")})
        matched.append({"transaction_id": tx["id"], "invoice_id": inv["id"], "deal_id": inv["deal_id"],
                        "amount": amount, "status": inv["status"],
                        "paying_company": company_ref(paying_company)})
    if matched or review:
        save_registry(data)
        tmp = BANK_REGISTRY + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as target:
            json.dump(bank, target, ensure_ascii=False, indent=2)
        os.replace(tmp, BANK_REGISTRY)
        for deal_id in {str(x["deal_id"]) for x in matched}:
            snapshot(deal_id)
    return {"matched": matched, "review": review}


@transaction(lambda: REGISTRY)
def record_receipt(deal_id, offer_row_id, qty):
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    deal = (data.get("deals") or {}).get(str(deal_id))
    if not deal:
        deal = snapshot(deal_id)
        data = ensure_schema(load_json(REGISTRY, empty_registry()))
        deal = data["deals"][str(deal_id)]
    item = next((x for x in deal.get("items") or [] if str(x.get("offer_row_id")) == str(offer_row_id)), None)
    if not item:
        raise ValueError("позиция закупки не найдена")
    qty = float(qty)
    if qty <= 0:
        raise ValueError("количество поступления должно быть больше нуля")
    planned = float(item.get("qty") or 0)
    received = float(item.get("received_qty") or 0)
    if received + qty > planned + 1e-9:
        raise ValueError(f"поступление превышает остаток {max(0, planned - received):g}")
    event = {"qty": qty, "date": datetime.now().strftime("%d.%m.%Y"),
             "created_at": datetime.now(timezone.utc).isoformat()}
    item.setdefault("receipt_history", []).append(event)
    item["received_qty"] = received + qty
    item["remaining_qty"] = max(0, planned - item["received_qty"])
    item["received_at"] = event["date"]
    item["status"] = "получено" if item["remaining_qty"] <= 1e-9 else "частично получено"
    save_registry(data)
    return item


def supplier_invoices_for_deal(deal_id):
    """Return supplier invoices that have an allocation in this deal."""
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    return [invoice for invoice in data.get("invoices") or []
            if str(invoice.get("deal_id")) == str(deal_id)
            or any(str(part.get("deal_id")) == str(deal_id)
                   for part in invoice.get("allocations") or [])]


@transaction(lambda: REGISTRY)
def record_closing_document(deal_id, invoice_id, filename, sha256="", document_type="УПД"):
    """Attach a supplier UПД/act to one already registered supplier invoice.

    This is metadata only; the original itself is first attached to Megaplan and
    archived in OneDrive by the caller.  SHA-256 makes a Telegram retry
    idempotent rather than creating duplicate closing documents.
    """
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    invoice = next((x for x in data.get("invoices") or []
                    if str(x.get("id")) == str(invoice_id)
                    and (str(x.get("deal_id")) == str(deal_id)
                         or any(str(part.get("deal_id")) == str(deal_id)
                                for part in x.get("allocations") or []))), None)
    if not invoice:
        raise ValueError("счёт поставщика для этой сделки не найден")
    docs = invoice.setdefault("closing_documents", [])
    if sha256:
        present = next((x for x in docs if x.get("sha256") == sha256), None)
        if present:
            return {**present, "duplicate": True}
    document = {
        "id": hashlib.sha256(f"{invoice_id}|{sha256 or filename}".encode()).hexdigest()[:20],
        "type": str(document_type or "УПД"), "filename": str(filename or "Закрывающий документ"),
        "sha256": str(sha256 or ""),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    docs.append(document)
    save_registry(data)
    return {**document, "duplicate": False}


def closure_check(deal_id):
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    deal = (data.get("deals") or {}).get(str(deal_id)) or snapshot(deal_id)
    invoices = supplier_invoices_for_deal(deal_id)
    problems = []
    for item in deal.get("items") or []:
        qty = float(item.get("qty") or 0)
        actual = float(item.get("actual_qty") or 0)
        received = float(item.get("received_qty") or 0)
        if actual + 1e-9 < qty:
            problems.append({"type": "invoice", "name": item.get("name"), "missing": qty - actual})
        if received + 1e-9 < qty:
            problems.append({"type": "receipt", "name": item.get("name"), "missing": qty - received})
    for invoice in invoices:
        total = float(invoice.get("total") or 0)
        paid = float(invoice.get("paid_total") or 0)
        if total > 0 and paid + 0.01 < total:
            problems.append({"type": "payment", "name": f"Счёт №{invoice.get('number') or 'б/н'}",
                             "missing": total - paid})
        if not (invoice.get("closing_documents") or []):
            problems.append({"type": "closing", "name": f"Счёт №{invoice.get('number') or 'б/н'}"})
    return {"ready": not problems and bool(deal.get("items")), "problems": problems,
            "items_count": len(deal.get("items") or []), "invoices_count": len(invoices),
            "closed": bool(deal.get("closed_at"))}


def procurement_status(deal_id):
    """Compact, read-only status of the supplier-document chain for one deal."""
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    deal = (data.get("deals") or {}).get(str(deal_id)) or snapshot(deal_id)
    invoices = supplier_invoices_for_deal(deal_id)
    rows = []
    for invoice in invoices:
        total = float(invoice.get("plan_total_rub", invoice.get("total")) or 0)
        paid = float(invoice.get("paid_total") or 0)
        rows.append({"number": invoice.get("number") or "б/н", "date": invoice.get("date") or "",
                     "supplier": invoice.get("supplier") or "не указан", "total": total, "paid": paid,
                     "id": str(invoice.get("id") or ""),
                     "closing_count": len(invoice.get("closing_documents") or []),
                     "payment_status": "оплачен" if paid + 0.01 >= total and total else
                                       "частично оплачен" if paid > 0 else "ожидает оплаты"})
    items = deal.get("items") or []
    ordered = sum(float(x.get("qty") or 0) for x in items)
    invoiced = sum(min(float(x.get("actual_qty") or 0), float(x.get("qty") or 0)) for x in items)
    received = sum(min(float(x.get("received_qty") or 0), float(x.get("qty") or 0)) for x in items)
    return {"deal_id": str(deal_id), "invoices": rows, "items_total": len(items),
            "ordered_qty": ordered, "invoiced_qty": invoiced, "received_qty": received,
            "closing_documents": ("загружены" if invoices and all(x.get("closing_documents") for x in invoices)
                                  else "есть не по всем счетам") if invoices else "пока не загружены"}


@transaction(lambda: REGISTRY)
def close_procurement(deal_id):
    check = closure_check(deal_id)
    if not check["ready"]:
        raise ValueError("закупка не готова к закрытию")
    data = ensure_schema(load_json(REGISTRY, empty_registry()))
    deal = data["deals"][str(deal_id)]
    if not deal.get("closed_at"):
        deal["closed_at"] = datetime.now(timezone.utc).isoformat()
        deal["status"] = "закрыта"
        save_registry(data)
    return {**check, "closed": True, "closed_at": deal["closed_at"]}


def main():
    spec = json.load(sys.stdin); action = spec["action"]; deal_id = str(spec.get("deal_id") or "")
    if action == "snapshot": print(json.dumps({"ok": True, "snapshot": snapshot(deal_id)}, ensure_ascii=False))
    elif action == "export": print(json.dumps({"ok": True, "path": export(deal_id)}, ensure_ascii=False))
    elif action == "record_invoice": print(json.dumps({"ok": True, "record": record_invoice(spec["invoice_spec"], spec.get("result") or {})}, ensure_ascii=False))
    elif action == "prepare_invoice_allocation": print(json.dumps(prepare_invoice_allocation(spec["invoice_spec"]), ensure_ascii=False))
    elif action == "invoice_allocation_status": print(json.dumps(invoice_allocation_status(spec["invoice_spec"]), ensure_ascii=False))
    elif action == "suggest_distribution": print(json.dumps({"ok": True, **suggest_distribution(
        spec["invoice_spec"], spec.get("limit") or 10, spec.get("candidate_deal_ids"))}, ensure_ascii=False))
    elif action == "put_unallocated_stock": print(json.dumps({"ok": True, "items": put_unallocated_stock(
        spec["invoice_spec"], spec.get("rows") or [], spec.get("actor") or "telegram")}, ensure_ascii=False))
    elif action == "record_excluded_remainder": print(json.dumps({"ok": True, "events": record_excluded_remainder(
        spec["invoice_spec"], spec.get("rows") or [], spec.get("reason"), spec.get("actor") or "telegram")}, ensure_ascii=False))
    elif action == "list_unallocated_stock": print(json.dumps({"ok": True, "items": list_unallocated_stock(
        spec.get("company_id"), spec.get("query"))}, ensure_ascii=False))
    elif action == "suggest_stock_for_deal": print(json.dumps({"ok": True, "suggestions": suggest_stock_for_deal(
        deal_id, spec.get("limit") or 20, spec.get("min_score") or 0.62)}, ensure_ascii=False))
    elif action == "consume_unallocated_stock": print(json.dumps({"ok": True, "allocation": consume_unallocated_stock(
        spec["stock_id"], deal_id, spec["qty"], spec.get("offer_id"), spec.get("offer_row_id"),
        spec.get("actor") or "telegram")}, ensure_ascii=False))
    elif action == "export_unallocated_stock": print(json.dumps({"ok": True, "path": export_unallocated_stock()}, ensure_ascii=False))
    elif action == "reconcile_bank": print(json.dumps({"ok": True, **reconcile_bank()}, ensure_ascii=False))
    elif action == "accounting_hints": print(json.dumps({"ok": True, **accounting_hints(deal_id or None)}, ensure_ascii=False))
    elif action == "record_intercompany_settlement": print(json.dumps({"ok": True, "settlement": record_intercompany_settlement(
        spec["transaction_id"], spec["debtor_id"], spec["creditor_id"], spec["amount"], spec.get("date") or "")}, ensure_ascii=False))
    elif action == "set_deal_company": print(json.dumps({"ok": True, "deal": set_deal_company(deal_id, spec["company_id"])}, ensure_ascii=False))
    elif action == "record_receipt": print(json.dumps({"ok": True, "item": record_receipt(deal_id, spec["offer_row_id"], spec["qty"])}, ensure_ascii=False))
    elif action == "supplier_invoices": print(json.dumps({"ok": True, "invoices": supplier_invoices_for_deal(deal_id)}, ensure_ascii=False))
    elif action == "record_closing_document": print(json.dumps({"ok": True, "document": record_closing_document(
        deal_id, spec["invoice_id"], spec.get("filename"), spec.get("sha256"), spec.get("document_type", "УПД"))}, ensure_ascii=False))
    elif action == "closure_check": print(json.dumps({"ok": True, **closure_check(deal_id)}, ensure_ascii=False))
    elif action == "procurement_status": print(json.dumps({"ok": True, **procurement_status(deal_id)}, ensure_ascii=False))
    elif action == "close": print(json.dumps({"ok": True, **close_procurement(deal_id)}, ensure_ascii=False))
    else: raise ValueError("неизвестное действие")


if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)); raise SystemExit(1)
