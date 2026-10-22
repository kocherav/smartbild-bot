"""Canonical interpretation of a deal line's monetary values.

Every calculation must use a line total.  A unit value is converted to a line
total once; a value declared as a line total is never multiplied by quantity.
The explicit override registry exists for historical Megaplan rows where the API
does not tell us how a legacy custom cost field had been entered.
"""
import json
import os
import math
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OVERRIDES_PATH = os.path.join(BASE_DIR, "financial_amount_overrides.json")

def crm_money_in_main(value):
    """CRM Money is denominated in its currency; accounting uses valueInMain.

    Never add USD/EUR nominal values to RUB. Zero is a valid converted amount.
    A missing conversion fails explicitly rather than assuming a rate of one.
    """
    if not isinstance(value, dict):
        return None
    if value.get('valueInMain') is not None:
        return _number(value['valueInMain'])
    raw = value.get('value')
    if raw is None:
        return None
    if value.get('currency') in (None, '', 'RUB'):
        return _number(raw)
    rate = _number(value.get('rate'))
    if rate <= 0:
        raise ValueError('Валютная сумма Мегаплана не содержит рублёвого эквивалента или курса')
    return _number(raw) * rate


def _number(value):
    if value is None or value == '':
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError('Некорректное финансовое значение; расчёт остановлен') from None
    if not math.isfinite(result):
        raise ValueError('Неконечное финансовое значение; расчёт остановлен')
    return result


def load_overrides():
    try:
        with open(OVERRIDES_PATH, encoding="utf-8") as source:
            data = json.load(source)
    except FileNotFoundError:
        data = {"version": 1, "overrides": {}}
    # Corrupt or inaccessible overrides must never silently restore multiplication
    # by quantity for a historical line-total cost.
    if not isinstance(data, dict) or not isinstance(data.get('overrides', {}), dict):
        raise ValueError('Повреждён реестр трактовки себестоимости')
    data.setdefault("overrides", {})
    return data


def _override(deal_id, entry, component):
    data = load_overrides()
    deal = data["overrides"].get(str(deal_id), {})
    row_id = str(entry.get("offer_row_id") or "")
    return (deal.get(row_id) or {}).get(component) or {}


def component_values(deal_id, entry, component, qty=None):
    """Return explicit unit/line amounts and basis for one material/work field."""
    quantity = _number(entry.get("qty") if qty is None else qty)
    raw = _number(entry.get(component))
    override = _override(deal_id, entry, component)
    basis = str(override.get("basis") or entry.get(component + "_basis") or "unit")
    if basis not in ("unit", "line_total"):
        raise ValueError('Неизвестная база себестоимости: требуется unit или line_total')
    if basis == "line_total":
        line_total = raw
        unit = (raw / quantity) if quantity else 0.0
    else:
        unit = raw
        line_total = raw * quantity
    return {"basis": basis, "raw": raw, "unit": unit, "line_total": line_total,
            "override": bool(override), "reason": override.get("reason") or ""}


def audit_entry(deal_id, entry):
    """Identify unit-vs-total ambiguities; this never changes a live deal."""
    qty = _number(entry.get("qty"))
    revenue = _number(entry.get("sell_price")) * qty
    findings = []
    for component in ("cost_material", "cost_work"):
        item = component_values(deal_id, entry, component, qty)
        if item["raw"] <= 0 or qty <= 1 or item["basis"] == "line_total":
            continue
        # A cost can legitimately exceed selling price, but >3x is sufficiently
        # improbable to require review instead of silently accepting a likely
        # "line total entered as unit price" error.
        if revenue > 0 and item["line_total"] > revenue * 3:
            findings.append({"component": component, "current_basis": "unit",
                             "suggested_basis": "line_total", "raw": item["raw"],
                             "current_total": item["line_total"], "suggested_total": item["raw"],
                             "reason": "стоимость после умножения более чем втрое превышает выручку строки"})
    return findings


def audit_rows(deal_id, entries):
    rows = []
    for entry in entries:
        for component in ("cost_material", "cost_work"):
            applied = component_values(deal_id, entry, component)
            if applied["override"]:
                rows.append({"offer_row_id": entry.get("offer_row_id"), "name": entry.get("name"),
                             "qty": _number(entry.get("qty")), "component": component,
                             "current_basis": "зафиксировано", "suggested_basis": applied["basis"],
                             "raw": applied["raw"], "current_total": applied["line_total"],
                             "suggested_total": applied["line_total"], "reason": applied["reason"]})
        for finding in audit_entry(deal_id, entry):
            rows.append({"offer_row_id": entry.get("offer_row_id"), "name": entry.get("name"),
                         "qty": _number(entry.get("qty")), **finding})
    return rows
