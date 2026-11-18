#!/usr/bin/env python3
"""Build the owner's read-only morning action list without per-deal CRM calls."""
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

os.environ.setdefault("MEGAPLAN_PRIORITY", "background")
# At 09:00 other scans hold the shared CRM queue; waiting is cheap, giving up is not (28.10).
os.environ.setdefault("MEGAPLAN_BACKGROUND_WAIT", "90")
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


def _issued(invoice):
    """The invoice date. Megaplan's Invoice has no ``timeCreated`` (asking for it fails the
    whole request with 422, every morning since it was added); ``invoiceDate`` is the
    document date {year, month (0-based), day}."""
    date = invoice.get("invoiceDate")
    if isinstance(date, dict) and date.get("year"):
        try:
            return datetime(int(date["year"]), int(date.get("month") or 0) + 1, int(date.get("day") or 1),
                            tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None
    return _moment(invoice.get("created_at"))


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
    params = {"limit": 100, "fields": ["deal", "invoiceDate", "status", "sum", "number"]}
    while True:
        response = api._call("GET", "/invoice", params=params)
        page = response.get("data") or []
        rows.extend(page)
        pagination = (response.get("meta") or {}).get("pagination") or {}
        if not page or not pagination.get("hasMoreNext"):
            return rows
        params = {**params, "pageAfter": {"contentType": "Invoice", "id": page[-1]["id"]}}


def _open(deal, completed):
    """Whether a deal is still in work. Megaplan's ``result`` (``active`` while open; set when
    the deal is won or lost) decides; status names are only a fallback for a cache read before
    ``result`` was requested. 18.11: 829 of 859 «stale» deals had no status name in the
    compact cache and counted as open; 281 of 312 «overdue» invoices were older than a year."""
    result = str(deal.get("result") or (deal.get("state") or {}).get("type") or "")
    if result:
        return result == "active"
    status = str(deal_browser.summary(deal).get("status") or "").casefold()
    return not any(marker in status for marker in completed)


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

    completed = tuple(str(x).casefold() for x in completed_statuses)
    overdue = []
    by_deal = {}
    for invoice in invoices:
        deal_id = str((invoice.get("deal") or {}).get("id") or invoice.get("deal_id") or "")
        issued = _issued(invoice)
        # Paid invoices take part in the allocation too: the money that settled
        # them must not be counted again against a later unpaid invoice (QA 23.10).
        if deal_id and issued and str(invoice.get("status") or "") in ("drawn", "partially_paid", "paid"):
            by_deal.setdefault(deal_id, []).append((issued, invoice))
    for deal_id, rows in by_deal.items():
        paid = payments.get(deal_id, Decimal("0"))
        for issued, invoice in sorted(rows, key=lambda row: row[0]):
            total = _money(invoice.get("sum"))
            applied = min(paid, total)
            paid -= applied
            remainder = total - applied
            age = (now - issued).days
            if str(invoice.get("status") or "") == "paid":
                continue
            deal = deals.get(deal_id) or {}
            # A won or lost deal is not today's work: its old unpaid invoice is history.
            if remainder > 0 and age > int(invoice_days) and (not deal or _open(deal, completed)):
                overdue.append({"deal_id": deal_id, "client": deal_browser.summary(deal).get("client"),
                                "amount": str(total), "remainder": str(remainder), "days": age,
                                "invoice_number": invoice.get("number") or invoice.get("id")})

    stale = []
    for deal_id, deal in deals.items():
        item = deal_browser.summary(deal)
        status = str(item.get("status") or "")
        updated = _moment(deal.get("timeUpdated") or deal.get("timeCreated"))
        age = (now - updated).days if updated else -1
        if updated and age > int(stale_days) and _open(deal, completed):
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
