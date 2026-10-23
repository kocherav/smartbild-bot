#!/usr/bin/env python3
"""Build the owner's read-only morning action list without per-deal CRM calls."""
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

os.environ.setdefault("MEGAPLAN_PRIORITY", "background")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import bank_statement
import deal_browser
from megaplan_api import MegaplanAPI


def _moment(value):
    if isinstance(value, dict):
        value = value.get("value")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _money(value):
    if isinstance(value, dict):
        value = value.get("value")
    try:
        result = Decimal(str(value or 0))
        return result if result.is_finite() and result >= 0 else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def _all_invoices(api):
    rows = []
    params = {"limit": 100, "fields": ["deal", "timeCreated", "status", "sum", "number"]}
    while True:
        response = api._call("GET", "/invoice", params=params)
        page = response.get("data") or []
        rows.extend(page)
        pagination = (response.get("meta") or {}).get("pagination") or {}
        if not page or not pagination.get("hasMoreNext"):
            return rows
        params = {**params, "pageAfter": {"contentType": "Invoice", "id": page[-1]["id"]}}


def build(api=None, now=None, invoice_days=7, stale_days=14, completed_statuses=()):
    """Return presentation-neutral rows. Payments are allocated oldest invoice first."""
    now = now or datetime.now(timezone.utc)
    api = api or MegaplanAPI()
    deals_raw = deal_browser.fetch_all(api)
    invoices = _all_invoices(api)  # one paginated collection, never one call per deal
    deals = {str(item.get("id")): item for item in deals_raw}
    payments = {}
    for tx in bank_statement.load_registry().get("transactions") or []:
        if tx.get("status") == "assigned" and tx.get("direction") == "income" and tx.get("deal_id"):
            key = str(tx["deal_id"])
            payments[key] = payments.get(key, Decimal("0")) + _money(tx.get("amount"))

    overdue = []
    by_deal = {}
    for invoice in invoices:
        deal_id = str((invoice.get("deal") or {}).get("id") or invoice.get("deal_id") or "")
        issued = _moment(invoice.get("timeCreated") or invoice.get("created_at"))
        if deal_id and issued and str(invoice.get("status") or "") in ("drawn", "partially_paid"):
            by_deal.setdefault(deal_id, []).append((issued, invoice))
    for deal_id, rows in by_deal.items():
        paid = payments.get(deal_id, Decimal("0"))
        for issued, invoice in sorted(rows, key=lambda row: row[0]):
            total = _money(invoice.get("sum"))
            applied = min(paid, total)
            paid -= applied
            remainder = total - applied
            age = (now - issued).days
            if remainder > 0 and age > int(invoice_days):
                deal = deals.get(deal_id) or {}
                overdue.append({"deal_id": deal_id, "client": deal_browser.summary(deal).get("client"),
                                "amount": str(total), "remainder": str(remainder), "days": age,
                                "invoice_number": invoice.get("number") or invoice.get("id")})

    completed = tuple(str(x).casefold() for x in completed_statuses)
    stale = []
    for deal_id, deal in deals.items():
        item = deal_browser.summary(deal)
        status = str(item.get("status") or "")
        updated = _moment(deal.get("timeUpdated") or deal.get("timeCreated"))
        age = (now - updated).days if updated else -1
        if updated and age > int(stale_days) and not any(marker in status.casefold() for marker in completed):
            stale.append({"deal_id": deal_id, "client": item.get("client"), "amount": str(_money(item.get("price"))),
                          "days": age, "status": status})
    return {"ok": True, "overdue": overdue, "stale": stale}


def main():
    spec = json.load(sys.stdin)
    try:
        print(json.dumps(build(invoice_days=spec.get("invoice_days", 7), stale_days=spec.get("stale_days", 14),
                               completed_statuses=spec.get("completed_statuses") or ()), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
