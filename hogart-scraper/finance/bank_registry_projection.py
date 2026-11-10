#!/usr/bin/env python3
"""Project linked daily-cycle postings into the bank registry used by the bot."""
import argparse
import datetime as dt
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(os.environ.get("MEGAPLAN_CRM_DIR", "/home/kocher.av/megaplan-crm"))))
from registry_transaction import locked


def _cents(value):
    return int((Decimal(str(value or "0")) * 100).quantize(Decimal("1")))


def _identity(row):
    date = str(row.get("date") or "")
    if len(date) >= 10 and date[4:5] == "-":
        date = dt.date.fromisoformat(date[:10]).strftime("%d.%m.%Y")
    return (
        str(row.get("account") or "").replace(" ", ""), date,
        {"in": "income", "out": "expense"}.get(row.get("direction"), row.get("direction")),
        _cents(row.get("amount") if "amount" in row else Decimal(row.get("amount_cents", 0)) / 100),
        str(row.get("counterparty_inn") or row.get("inn") or ""),
        str(row.get("document_number") or row.get("number") or ""),
        str(row.get("purpose") or "").strip(),
    )


def project(ledger_rows, journal, registry_path):
    """Mark only fully linked, uniquely identified bank movements as assigned."""
    linked = {}
    for part in (journal.get("operations") or {}).values():
        if part.get("state") == "linked" and part.get("operation_id"):
            linked.setdefault(part.get("bank_operation_id"), []).append(part)
    completed = {}
    for row in ledger_rows:
        parts = linked.get(row.get("id")) or []
        if parts and sum(int(p.get("amount_cents") or 0) for p in parts) == int(row.get("amount_cents") or 0):
            completed[_identity(row)] = parts

    registry_path = Path(registry_path)
    with locked(registry_path):
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        by_identity = {}
        for tx in data.get("transactions") or []:
            by_identity.setdefault(_identity(tx), []).append(tx)
        changed = 0
        for identity, parts in completed.items():
            matches = by_identity.get(identity) or []
            if len(matches) > 1:
                raise ValueError("Bank registry contains ambiguous duplicate movements")
            if not matches:
                continue
            tx = matches[0]
            operation_ids = sorted({str(p["operation_id"]) for p in parts})
            deal_ids = sorted({str(p.get("deal_id")) for p in parts if p.get("deal_id")})
            values = {"status": "assigned", "megaplan_operation_ids": operation_ids,
                      "assigned_source": "daily_posting_journal"}
            if len(operation_ids) == 1:
                values["megaplan_operation_id"] = operation_ids[0]
            if len(deal_ids) == 1:
                values["deal_id"] = deal_ids[0]
                values["deal_name"] = tx.get("deal_name") or "Проведено ежедневным циклом"
            if any(tx.get(k) != v for k, v in values.items()):
                tx.update(values); changed += 1
        if changed:
            temp = registry_path.with_name(registry_path.name + f".{os.getpid()}.tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, registry_path)
    return {"linked_movements": len(completed), "registry_updates": changed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", default=str(ROOT / "reports/ledger.json"))
    parser.add_argument("--journal", default=str(ROOT / "data/posting_journal.json"))
    parser.add_argument("--registry", default="/home/kocher.av/megaplan-crm/bank_statement_registry.json")
    args = parser.parse_args()
    print(json.dumps(project(json.loads(Path(args.ledger).read_text()),
                             json.loads(Path(args.journal).read_text()), args.registry), ensure_ascii=False))


if __name__ == "__main__":
    main()
