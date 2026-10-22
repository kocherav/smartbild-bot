#!/usr/bin/env python3
"""Suggest unambiguous Megaplan deals for imported bank transactions."""
import json
import os
import re
import sys
import time
from decimal import Decimal

from megaplan_api import MegaplanAPI
import bank_statement

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEAL_CACHE = os.path.join(BASE_DIR, "deal_browser_cache.json")
INDEX_CACHE = os.path.join(BASE_DIR, "bank_match_index.json")
INDEX_TTL = 300


def normalized_number(value):
    value = re.sub(r"[^0-9A-Za-zА-Яа-яЁё/.-]+", "", str(value or "")).upper().strip(".-/")
    if value.isdigit():
        value = str(int(value))
    return value


def references(purpose):
    invoice_patterns = (
        r"(?i)(?:сч[её]т(?:у|а|ом)?|сч\.)\s*(?:на\s+оплату\s*)?№?\s*([0-9][0-9A-Za-zА-Яа-яЁё/._-]*)",
    )
    contract_patterns = (
        r"(?i)договор(?:у|а|ом|е)?\s*№\s*([0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё/._-]*)",
    )
    invoices = {normalized_number(match) for pattern in invoice_patterns for match in re.findall(pattern, purpose or "")}
    contracts = {normalized_number(match) for pattern in contract_patterns for match in re.findall(pattern, purpose or "")}
    return invoices - {""}, contracts - {""}


def deal_id_from_standard_contract(number, index):
    """Resolve the project's standard contract number without crawling all files.

    Generated contracts use ``1.<deal-id>-DDMM/YYYY``.  The candidate must
    already exist in the current Megaplan index and still goes through the
    confirmation screen before an operation is written.
    """
    match = re.fullmatch(r"1\.(\d+)-\d{4}/\d{4}", str(number or ""))
    deal_id = match.group(1) if match else ""
    return deal_id if deal_id and deal_id in (index.get("deal_labels") or {}) else None


def fetch_invoices(api):
    invoices, params = [], {"limit": 100, "fields": ["deal", "payer", "sum"]}
    while True:
        result = api._call("GET", "/invoice", params=params)
        chunk = result.get("data") or []
        invoices.extend(chunk)
        if not chunk or not result.get("meta", {}).get("pagination", {}).get("hasMoreNext"):
            break
        params = {"limit": 100, "fields": ["deal", "payer", "sum"],
                  "pageAfter": {"contentType": "Invoice", "id": chunk[-1]["id"]}}
    return invoices


def build_index(api=None):
    api = api or MegaplanAPI()
    invoices = fetch_invoices(api)
    try:
        deals = json.load(open(DEAL_CACHE, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        deals = []
    invoice_numbers, contract_numbers, deal_payers = {}, {}, {}
    deal_labels = {}
    for deal in deals:
        deal_id = str(deal.get("id"))
        name = deal.get("name") or ""
        number = normalized_number(name)
        if number and not re.fullmatch(r"№?\d+", name.strip()):
            contract_numbers.setdefault(number, []).append(deal_id)
        contractor = deal.get("contractor") or {}
        deal_labels[deal_id] = name or contractor.get("name") or f"Сделка {deal_id}"
    for invoice in invoices:
        deal = invoice.get("deal") or {}
        if not deal.get("id"):
            continue
        deal_id = str(deal["id"])
        number = normalized_number(invoice.get("number"))
        payer = invoice.get("payer") or {}
        row = {"deal_id": deal_id, "invoice_id": str(invoice.get("id")),
               "invoice_number": invoice.get("number") or "", "payer_inn": payer.get("inn") or "",
               "amount": str((invoice.get("sum") or {}).get("value") or "")}
        if number:
            invoice_numbers.setdefault(number, []).append(row)
        if payer.get("inn"):
            deal_payers.setdefault(deal_id, set()).add(str(payer["inn"]))
        deal_labels.setdefault(deal_id, deal.get("name") or deal.get("shortDescription") or f"Сделка {deal_id}")
    result = {"invoice_numbers": invoice_numbers, "contract_numbers": contract_numbers,
              "deal_payers": {key: sorted(value) for key, value in deal_payers.items()},
              "deal_labels": deal_labels, "built_at": time.time()}
    with open(INDEX_CACHE + ".tmp", "w", encoding="utf-8") as target:
        json.dump(result, target, ensure_ascii=False)
    os.replace(INDEX_CACHE + ".tmp", INDEX_CACHE)
    return result


def load_index():
    try:
        if time.time() - os.path.getmtime(INDEX_CACHE) < INDEX_TTL:
            return json.load(open(INDEX_CACHE, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return build_index()


def match_transaction(item, index):
    invoice_refs, contract_refs = references(item.get("purpose") or "")
    evidence = {}
    invoice_details = {}
    # Megaplan invoices here are our sales invoices to clients.  A supplier's invoice
    # number in an outgoing payment may coincidentally equal one of them and must not
    # produce a false deal match.
    if item.get("direction") == "income":
        for number in invoice_refs:
            for candidate in index["invoice_numbers"].get(number, []):
                deal_id = candidate["deal_id"]
                evidence.setdefault(deal_id, []).append(f"счёт №{candidate['invoice_number']}")
                invoice_details.setdefault(deal_id, []).append(candidate)
    # A client contract is an unambiguous basis only for an incoming payment.
    # Outgoing procurement is linked by a registered supplier invoice instead;
    # otherwise an unrelated supplier contract can be attached to a sale deal.
    if item.get("direction") == "income":
        for number in contract_refs:
            candidates = set(index["contract_numbers"].get(number, []))
            derived = deal_id_from_standard_contract(number, index)
            if derived:
                candidates.add(derived)
            for deal_id in candidates:
                evidence.setdefault(deal_id, []).append(f"договор №{number}")
    if len(evidence) != 1:
        return None, "ambiguous" if evidence else "not_found"
    deal_id = next(iter(evidence))
    operation_inn = str(item.get("counterparty_inn") or "")
    known_inns = set(index.get("deal_payers", {}).get(deal_id) or [])
    if item.get("direction") == "income" and operation_inn and known_inns and operation_inn not in known_inns:
        return None, "inn_conflict"
    exact_amount = any(Decimal(str(candidate.get("amount") or "0")) == Decimal(str(item.get("amount") or "0"))
                       for candidate in invoice_details.get(deal_id, []))
    return {"transaction_id": item["id"], "deal_id": deal_id,
            "deal_name": index.get("deal_labels", {}).get(deal_id, ""),
            "basis": ", ".join(dict.fromkeys(evidence[deal_id])),
            "inn_confirmed": bool(operation_inn and operation_inn in known_inns),
            "amount_confirmed": exact_amount}, "matched"


def suggest():
    registry = bank_statement.load_registry()
    index = load_index()
    matches, reasons = [], {}
    for item in registry["transactions"]:
        if item.get("status") != "unassigned":
            continue
        match, reason = match_transaction(item, index)
        if match:
            matches.append(match)
        else:
            reasons[reason] = reasons.get(reason, 0) + 1
    return {"ok": True, "matches": matches, "matched_count": len(matches),
            "unmatched_count": sum(reasons.values()), "reasons": reasons}


if __name__ == "__main__":
    try:
        print(json.dumps(suggest(), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
