#!/usr/bin/env python3
"""
"Расчёт рентабельности сделки" (2026-08-25) - whole-deal economics, the second document
in the ведомость-работ -> монтаж-наценка -> рентабельность chain (see
apply_work_statement.py for the previous step). Run AFTER apply_work_statement.py, once
the "Монтажные работы" line has a real cost/price - otherwise its row just shows zeros,
which isn't wrong, just an incomplete picture.

Per position: revenue = sell_price * qty, cost = (cost_material + cost_work) * qty (both
per-unit fields, same convention as everywhere else in this project - see
_accumulate_position's docstring in megaplan_api.py for why sell_price/cost_material/
cost_work are always PER-UNIT, never totals). Deal totals: revenue, cost, profit
(revenue - cost), margin % (profit / revenue). Also pushes the profit (RUB) onto the
deal's own `Category1000068CustomFieldRentabelnost` custom field (discovered 2026-08-25 -
this account's Deal schema already has a "Рентабельность" Money field sitting unused).

CLI: `python3 build_profitability_report.py <deal_id> [--out path.xlsx]`
Prints a single-line JSON summary.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import deal_ledger
from megaplan_api import MegaplanAPI
import financial_amounts
import math
import procurement_workflow
from procurement_projection import effective_registry

PROCUREMENT_REGISTRY = os.path.join(BASE_DIR, "procurement_registry.json")
INSTALLATIONS_DB = os.path.join(BASE_DIR, "installations.sqlite3")

def norm(value):
    return re.sub(r'[^0-9a-zа-я]+',' ',str(value or '').casefold().replace('ё','е')).strip()


def is_aggregate_montage_line(entry):
    """True for the commercial summary line, not an individual installation work.

    A deal may contain a sale position named ``Монтажные работы`` and, at the
    same time, a detailed installation statement whose rows already carry the
    labour cost.  The summary position is then revenue-only: counting its
    planned cost again would double-count the very same labour.  Supplier
    invoices explicitly allocated to this row are still allowed below.
    """
    return norm(entry.get("name")).startswith("монтажные работы")

def load_installation_items(deal_id):
    if not os.path.exists(INSTALLATIONS_DB): return {}
    db=sqlite3.connect(INSTALLATIONS_DB); db.row_factory=sqlite3.Row
    try:
        columns={x[1] for x in db.execute('PRAGMA table_info(work_items)')}
        kind="w.cost_kind" if 'cost_kind' in columns else "'work'"
        rows=db.execute(f'''SELECT w.id,w.name,w.source_key,w.planned_qty,w.rate,w.active,{kind} AS cost_kind,
          COALESCE(SUM(CASE WHEN r.status IN ('approved','partially_approved') THEN ri.accepted_qty ELSE 0 END),0) accepted_qty,
          COALESCE(SUM(CASE WHEN r.status IN ('approved','partially_approved') THEN COALESCE(ri.accepted_amount,ri.accepted_qty*w.rate) ELSE 0 END),0) accepted_amount
          FROM work_items w LEFT JOIN report_items ri ON ri.work_item_id=w.id LEFT JOIN reports r ON r.id=ri.report_id
          WHERE w.deal_id=? GROUP BY w.id''',(str(deal_id),)).fetchall()
        def key(item):
            source=str(item['source_key'] or '')
            if source.startswith('deal:'): source=source[5:]
            return 'row:'+source if source.isdigit() else 'work:'+str(item['id'])
        return {key(x):
                {'work_id':str(x['id']),'name':x['name'], 'active':bool(x['active']),'cost_kind':x['cost_kind'],
                 'planned_qty':float(x['planned_qty'] or 0) if x['active'] else float(x['accepted_qty'] or 0),
                 'rate':float(x['rate'] or 0),'accepted_qty':float(x['accepted_qty'] or 0),'accepted_amount':float(x['accepted_amount'] or 0),
                 'legacy_total_cost':str(x['source_key'] or '').startswith('legacy:')}
                for x in rows if x['active'] or float(x['accepted_amount'] or 0)}
    finally: db.close()


def load_procurement_items(deal_id):
    try:
        with open(PROCUREMENT_REGISTRY, encoding="utf-8") as source:
            data = json.load(source)
    except FileNotFoundError:
        return {}
    data = effective_registry(data)
    deal = (data.get("deals") or {}).get(str(deal_id)) or {}
    result = {str(x.get("offer_row_id")): dict(x) for x in deal.get("items") or []}
    # A supplier invoice establishes the planned acquisition cost.  A bank payment
    # establishes the fact.  Do not treat an un-paid invoice as fact merely because
    # it was already allocated to a deal.
    invoice_plan = {}
    for invoice in data.get("invoices") or []:
        planned_total = float(invoice.get("plan_total_rub", invoice.get("total")) or 0)
        paid_total = float(invoice.get("paid_total") or 0)
        paid_ratio = paid_total / planned_total if planned_total > 0 else 0.0
        for allocation in invoice.get("allocations") or []:
            if str(allocation.get("deal_id")) != str(deal_id):
                continue
            for line in allocation.get("source_lines") or []:
                row_id = str(line.get("offer_row_id") or "")
                # Older allocations do not have offer_row_id inside source_lines;
                # recover it from their corresponding update deterministically.
                if not row_id:
                    key = str(line.get("key") or "")
                    for update in allocation.get("updates") or []:
                        update_key = str(update.get("source_line_key") or update.get("source_sku") or update.get("source_name") or "").strip().casefold()
                        if update_key == key:
                            row_id = str(update.get("offer_row_id") or ""); break
                if row_id not in result:
                    continue
                item = invoice_plan.setdefault(row_id, {"qty": 0.0, "plan": 0.0, "fact": 0.0, "paid_qty": 0.0})
                qty = float(line.get("qty_used") or 0)
                amount = float(line.get("amount_used") or 0)
                item["qty"] += qty; item["plan"] += amount
                item["paid_qty"] += qty * paid_ratio
                # For a foreign invoice the payment can differ from the planned
                # RUB equivalent.  The actual bank amount is spread by the planned
                # allocation share, preserving the complete paid amount.
                item["fact"] += amount * paid_ratio
    for row_id, values in invoice_plan.items():
        target = result[row_id]
        target["invoiced_qty"] = values["qty"]
        target["invoice_plan_total"] = round(values["plan"], 2)
        target["paid_invoice_qty"] = values["paid_qty"]
        target["paid_invoice_total"] = round(values["fact"], 2)
    expenses = []
    for invoice in data.get("invoices") or []:
        for allocation in invoice.get("allocations") or []:
            if str(allocation.get("deal_id")) != str(deal_id):
                continue
            for item in allocation.get("additional_expenses") or []:
                expenses.append({**item, "supplier": invoice.get("supplier"),
                                 "invoice_number": invoice.get("number")})
    result["__additional_expenses__"] = expenses
    return result


def compute_profitability(entries, procurement=None, installation=None, deal_id=None):
    procurement = procurement or {}
    installation = installation or {}
    rows = []
    total_revenue = 0.0
    total_cost = 0.0
    itemized_labour_exists = any(
        not is_aggregate_montage_line(candidate)
        and float(candidate.get("cost_work") or 0) > 0
        for candidate in entries
    ) or any(float(item.get("rate") or 0) > 0 for item in installation.values())
    used_installation=set()
    names_count={norm(e.get('name')):sum(norm(x.get('name'))==norm(e.get('name')) for x in entries) for e in entries}
    for e in entries:
        row_key='row:'+str(e.get('offer_row_id') or '')
        selected_key=row_key if row_key in installation else None
        if selected_key is None:
            name=norm(e.get('name'))
            candidates=[key for key,item in installation.items() if item.get('cost_kind','work')=='work' and (key==name or norm(item.get('name'))==name)]
            if candidates and (len(candidates)>1 or names_count.get(name,0)>1):
                raise ValueError('Неоднозначная привязка монтажных затрат: '+str(e.get('name'))+'. Требуется ID строки, расчёт не опубликован.')
            selected_key=candidates[0] if candidates else None
        installation_row=installation.get(selected_key) or {}
        if selected_key:
            if selected_key in used_installation:
                raise ValueError('Одна монтажная работа сопоставлена нескольким коммерческим строкам')
            used_installation.add(selected_key)
        # Commercial quantity is immutable for revenue and materials.  The
        # installation statement may have a different quantity (e.g. metres of
        # work actually included in a contractor's scope); it governs *work*
        # planning only and must never rewrite the client specification.
        qty = float(e.get("qty") or 0)
        work_qty = float(installation_row.get('planned_qty', qty) or 0)
        sell_price = e.get("sell_price") or 0
        purchase = procurement.get(str(e.get("offer_row_id"))) or {}
        material = financial_amounts.component_values(str(deal_id or ''), e, 'cost_material', qty)
        work = financial_amounts.component_values(str(deal_id or ''), e, 'cost_work', qty)
        # The summary sale line must not duplicate the detailed монтажная
        # ведомость.  A real supplier invoice or payment allocated directly to
        # it remains an independently auditable cost and is preserved.
        aggregate_montage = is_aggregate_montage_line(e) and itemized_labour_exists
        direct_invoice_cost = float(purchase.get("invoice_plan_total") or 0) > 0 or \
                              float(purchase.get("actual_total") or 0) > 0
        if aggregate_montage and not direct_invoice_cost:
            material = {"unit": 0.0, "basis": "unit"}
            work = {"unit": 0.0, "basis": "unit"}
            # The registry snapshot may have inherited the erroneous planned
            # material value from Megaplan.  Do not let it re-enter the report
            # after the component values above have been deliberately zeroed.
            purchase = {}
        material_basis = purchase.get("planned_material_basis", material["basis"])
        plan_material_unit=float(purchase.get("planned_unit_cost", material["unit"]))
        plan_material=float(purchase.get("planned_total", plan_material_unit*qty))
        plan_work_unit = installation_row.get('rate',purchase.get("planned_unit_work", work["unit"]))
        invoiced_qty = min(float(purchase.get("invoiced_qty") or 0), float(qty or 0))
        invoice_plan_total = float(purchase.get("invoice_plan_total") or 0)
        if invoice_plan_total > 0:
            # The currency/invoice plan replaces only the quantities actually
            # covered by that invoice; untouched quantities retain the deal plan.
            plan_material = invoice_plan_total + plan_material_unit * max(0, float(qty or 0) - invoiced_qty)
        fact_qty = min(float(purchase.get("paid_invoice_qty") or 0), float(qty or 0))
        fact_material = float(purchase.get("paid_invoice_total") or 0)
        if not invoice_plan_total:
            # Backwards compatibility for old procurement data predating payment
            # tracking. It has no invoice allocation detail, so retain its fact.
            fact_qty = min(float(purchase.get("actual_qty") or 0), float(qty or 0))
            fact_material = float(purchase.get("actual_total") or 0)
        if invoice_plan_total:
            unpaid_invoice_plan = max(0, invoice_plan_total - (invoice_plan_total * (fact_qty / invoiced_qty) if invoiced_qty else 0))
            remaining_qty = max(0, float(qty or 0) - invoiced_qty)
            remaining_plan_material = unpaid_invoice_plan + plan_material_unit * remaining_qty
        else:
            remaining_qty = max(0, float(qty or 0) - fact_qty)
            # A historic line-total is the cost of the complete line.  Its
            # quantity in an installation report may differ from the commercial
            # quantity, but that must not prorate/re-multiply the stored total.
            remaining_plan_material = (plan_material if material_basis == "line_total" and fact_qty <= 0
                                       else plan_material_unit * remaining_qty)
        forecast_material = fact_material + remaining_plan_material
        plan_work = plan_work_unit * work_qty
        fact_work_qty=min(float(installation_row.get('accepted_qty') or 0), work_qty)
        fact_work=float(installation_row.get('accepted_amount', fact_work_qty*plan_work_unit))
        remaining_plan_work=max(0,work_qty-fact_work_qty)*plan_work_unit
        forecast_cost = forecast_material + fact_work + remaining_plan_work
        gross_revenue = sell_price * qty
        from document_tax_policy import vat
        output_vat = float(vat(gross_revenue, e.get("tax_rate",-1)))
        revenue = gross_revenue - output_vat
        plan_cost = plan_material + plan_work
        profit = revenue - forecast_cost
        total_revenue += revenue
        total_cost += forecast_cost
        rows.append({
            "name": e.get("name"), "qty": qty, "sell_price": sell_price,
            "revenue": revenue, "output_vat": output_vat, "gross_revenue": gross_revenue, "plan_material": plan_material, "plan_work": plan_work,
            "plan_cost": plan_cost, "fact_qty": fact_qty, "fact_material": fact_material,
            "remaining_plan_material": remaining_plan_material,
            "fact_work_qty":fact_work_qty,"fact_work":fact_work,"remaining_plan_work":remaining_plan_work,
            "forecast_cost": forecast_cost, "deviation": forecast_cost - plan_cost,
            "profit": profit,
        })
    # Manual/historical work can have no commercial position. It still belongs
    # to the deal cost and must not disappear because names did not match.
    for key,item in installation.items():
        if key in used_installation: continue
        planned=float(item.get('planned_qty') or 0); rate=float(item.get('rate') or 0)
        accepted=float(item.get('accepted_qty') or 0)
        fact=float(item.get('accepted_amount', accepted*rate))
        if item.get('cost_kind')=='material':
            total_cost+=fact
            rows.append({'name':'Материалы монтажника: '+str(item.get('name') or key),
                'qty':accepted,'sell_price':0,'revenue':0,'plan_material':fact,'plan_work':0,'plan_cost':fact,
                'fact_qty':accepted,'fact_material':fact,'remaining_plan_material':0,'fact_work_qty':0,'fact_work':0,
                'remaining_plan_work':0,'forecast_cost':fact,'deviation':0,'profit':-fact})
            continue
        remaining=max(0,planned-accepted)*rate; cost=fact+remaining
        total_cost+=cost
        rows.append({'name':'Монтажная ведомость: '+str(item.get('name') or key),
            'qty':planned,'sell_price':0,'revenue':0,'plan_material':0,'plan_work':planned*rate,'plan_cost':planned*rate,
            'fact_qty':0,'fact_material':0,'remaining_plan_material':0,'fact_work_qty':accepted,'fact_work':fact,
            'remaining_plan_work':remaining,'forecast_cost':cost,'deviation':cost-planned*rate,'profit':-cost})
    for expense in procurement.get("__additional_expenses__") or []:
        amount = float(expense.get("amount") or expense.get("total") or 0)
        total_cost += amount
        rows.append({"name": f"Доп. расход: {expense.get('source_name') or expense.get('name') or 'без названия'}",
            "qty": expense.get("qty") or expense.get("source_qty") or 1, "sell_price": 0,
            "revenue": 0, "plan_material": 0, "plan_work": 0, "plan_cost": 0,
            "fact_qty": expense.get("qty") or expense.get("source_qty") or 1,
            "fact_material": amount, "remaining_plan_material": 0,
            "fact_work_qty":0,"fact_work":0,"remaining_plan_work":0,
            "forecast_cost": amount, "deviation": amount, "profit": -amount})
    total_profit = total_revenue - total_cost
    margin_pct = (total_profit / total_revenue * 100) if total_revenue else 0.0
    if not all(math.isfinite(float(value)) for row in rows for key,value in row.items() if key != 'name'):
        raise ValueError('В расчёте есть неконечное значение; экономика не опубликована')
    return rows, total_revenue, total_cost, total_profit, margin_pct


def build_xlsx(rows, deal_id, path, audit=None, totals=None):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    import xlsx_brand_style as style

    wb = Workbook()
    ws = wb.active
    ws.title = "Расчёт рентабельности"
    ws.sheet_view.showGridLines = False

    headers = ["Наименование", "Кол-во", "Цена продажи/ед.", "Выручка",
               "План материалов", "План работ", "План себестоимости",
               "Закрыто счетами, кол-во", "Факт материалов по счетам",
               "Остаток материалов по плану", "Принято работ, кол-во",
               "Факт работ по отчётам", "Остаток работ по плану", "Прогноз себестоимости",
               "Отклонение от плана", "Прибыль по прогнозу"]
    header_row = style.write_title_banner(ws, "Расчёт рентабельности сделки", f"Сделка № {deal_id}", len(headers))
    style.write_header_row(ws, header_row, headers)
    align_by_col = {1: style.LEFT, 2: style.CENTER, **{i: style.RIGHT for i in range(3, len(headers) + 1)}}

    money_cols = (3,4,5,6,7,9,10,12,13,14,15,16)
    for i, r in enumerate(rows):
        ws.append([r["name"], r["qty"], r["sell_price"], r["revenue"], r["plan_material"],
                   r["plan_work"], r["plan_cost"], r["fact_qty"], r["fact_material"],
                   r["remaining_plan_material"],r["fact_work_qty"],r["fact_work"],r["remaining_plan_work"],
                   r["forecast_cost"],r["deviation"],r["profit"]])
        row_idx = ws.max_row
        style.style_data_row(ws, row_idx, len(headers), align_by_col, stripe=(i % 2 == 1))
        for col in money_cols:
            ws.cell(row=row_idx, column=col).number_format = style.MONEY_FMT

    first_data_row, last_data_row = header_row + 1, ws.max_row
    summary_row = ws.max_row + 1
    # Mobile previewers (including Telegram's) often display an XLSX formula's
    # *old cached value* and never calculate it.  Finance documents must show a
    # truthful result everywhere, therefore totals are saved as checked numeric
    # values. Rows remain editable; a later bot regeneration recalculates totals.
    calculated = totals or {
        "revenue": round(sum(float(x["revenue"]) for x in rows), 2),
        "cost": round(sum(float(x["forecast_cost"]) for x in rows), 2),
    }
    calculated["profit"] = round(calculated.get("profit", calculated["revenue"] - calculated["cost"]), 2)
    calculated["margin"] = float(calculated.get("margin", (calculated["profit"] / calculated["revenue"] * 100) if calculated["revenue"] else 0))
    labels_values = [
        ("Выручка без исходящего НДС", calculated["revenue"]),
        ("Прогноз себестоимости (факт + незакрытый план)", calculated["cost"]),
        ("Прибыль", calculated["profit"]),
    ]
    for i, (label, value) in enumerate(labels_values):
        r = summary_row + i
        ws.cell(row=r, column=1, value=label)
        cell = ws.cell(row=r, column=14, value=value)
        cell.number_format = style.MONEY_FMT
        style.style_total_row(ws, r, len(headers))
        ws.row_dimensions[r].height = 20
    margin_row = summary_row + len(labels_values)
    ws.cell(row=margin_row, column=1, value="Рентабельность, %")
    ws.cell(row=margin_row, column=14, value=calculated["margin"]).number_format = '0.0"%"'
    style.style_total_row(ws, margin_row, len(headers))
    ws.row_dimensions[margin_row].height = 20

    widths = [45,9,16,16,17,15,18,18,20,22,18,20,20,21,18,20]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    audit_sheet = wb.create_sheet("Проверка трактовки сумм")
    audit_sheet.append(["Позиция", "Кол-во", "Поле", "Текущая трактовка", "Предлагаемая трактовка",
                        "Значение", "Сейчас получается, ₽", "При трактовке как сумма строки, ₽", "Причина"])
    for cell in audit_sheet[1]:
        cell.font = style.Font(bold=True, color="FFFFFF")
        cell.fill = style.PatternFill("solid", fgColor="263238")
    for item in audit or []:
        audit_sheet.append([item.get("name"), item.get("qty"), item.get("component"), item.get("current_basis"),
                            item.get("suggested_basis"), item.get("raw"), item.get("current_total"),
                            item.get("suggested_total"), item.get("reason")])
    if not audit:
        audit_sheet.append(["Подозрительных строк не найдено. Явно заданные исправления применены в расчёте."])
    audit_sheet.freeze_panes = "A2"; audit_sheet.auto_filter.ref = audit_sheet.dimensions
    for index, width in enumerate([58, 12, 18, 18, 22, 18, 24, 30, 68], 1):
        audit_sheet.column_dimensions[get_column_letter(index)].width = width

    wb.save(path)


# Bump when the workbook layout or the meaning of its numbers changes.
REPORT_FORMAT = "profitability-v1"


def data_fingerprint(deal_id, rows, totals, audit):
    """Identity of the numbers in the workbook, not of the xlsx bytes.

    The file itself carries build-time metadata, so its hash changes on every
    run.  This digest changes only when a figure the reader sees can change.
    """
    payload = json.dumps({"format": REPORT_FORMAT, "deal_id": str(deal_id), "rows": rows,
                          "totals": totals, "audit": audit},
                         sort_keys=True, ensure_ascii=False, default=str, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def money_field_matches(field, expected, tolerance=0.0001):
    field = field or {}
    current = field.get("valueInMain")
    if current is None:
        current = field.get("value")
    try:
        return abs(float(current) - float(expected)) <= tolerance
    except (TypeError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("deal_id")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    out_path = args.out or os.path.join(
        BASE_DIR, f"Экономика сделки №{args.deal_id} — план и факт.xlsx"
    )

    api = MegaplanAPI()
    # Always calculate from the live deal. Managers commonly edit material/work costs
    # directly in Megaplan; the local ledger may legitimately lag behind those edits.
    deal = api._call("GET", f"/deal/{args.deal_id}")["data"]
    entries = api.ledger_from_deal(deal, price_source="megaplan_live")
    # The deal header is the commercial control total.  A position can be
    # accidentally edited in Megaplan without updating it (or vice versa).
    # Publishing economics in that state turns a CRM inconsistency into a
    # misleading profit figure, so stop before writing either Excel or margin.
    deal_price = deal.get("price") or {}
    deal_revenue = float(deal_price.get("valueInMain") or deal_price.get("value") or 0)
    positions_revenue = sum(float(entry.get("qty") or 0) * float(entry.get("sell_price") or 0)
                            for entry in entries)
    if deal_revenue > 0 and abs(deal_revenue - positions_revenue) > 0.01:
        print(json.dumps({
            "ok": False,
            "deal_id": args.deal_id,
            "error": ("сумма карточки сделки и сумма позиций расходятся; экономика не обновлена"),
            "deal_revenue": round(deal_revenue, 2),
            "positions_revenue": round(positions_revenue, 2),
            "difference": round(positions_revenue - deal_revenue, 2),
        }, ensure_ascii=False))
        return
    # Megaplan exposes numeric cost fields but not their basis. Preserve the
    # explicit unit/line-total metadata maintained in our local ledger while
    # retaining the current live quantities/prices from the deal.
    saved_by_row = {str(x.get("offer_row_id")): x for x in deal_ledger.load(args.deal_id)}
    for entry in entries:
        saved = saved_by_row.get(str(entry.get("offer_row_id"))) or {}
        for key in ("cost_material_basis", "cost_work_basis"):
            if saved.get(key) in ("unit", "line_total"):
                entry[key] = saved[key]
    # Refresh planned totals through the explicit unit/line-total interpreter
    # before reading the procurement snapshot.
    procurement_workflow.snapshot(args.deal_id)
    rows, total_revenue, total_cost, total_profit, margin_pct = compute_profitability(
        entries, load_procurement_items(args.deal_id),load_installation_items(args.deal_id), args.deal_id)
    audit = financial_amounts.audit_rows(args.deal_id, entries)
    totals = {"revenue": total_revenue, "cost": total_cost, "profit": total_profit, "margin": margin_pct}
    build_xlsx(rows, args.deal_id, out_path, audit, totals)

    current_profit = deal.get("Category1000068CustomFieldRentabelnost") or {}
    profit_is_current = money_field_matches(current_profit, total_profit)
    # A timeout/502 can arrive after Megaplan committed the field.  The next
    # reconciliation reads the deal first; if the exact value is already there,
    # do not replay even this otherwise-idempotent write.
    if not profit_is_current:
        api._call("POST", f"/deal/{args.deal_id}", json_body={
            "contentType": "Deal",
            "Category1000068CustomFieldRentabelnost": {"contentType": "Money", "currency": "RUB", "value": total_profit},
        })

    print(json.dumps({
        "ok": True, "deal_id": args.deal_id, "path": out_path,
        "total_revenue": total_revenue, "total_cost": total_cost,
        "total_profit": total_profit, "margin_pct": margin_pct,
        "financial_audit_count": len(audit),
        "data_fingerprint": data_fingerprint(args.deal_id, rows, totals, audit),
        "profitability_write": "unchanged" if profit_is_current else "updated",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
