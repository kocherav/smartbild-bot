#!/usr/bin/env python3
"""
Standalone xlsx builder for the KP economics breakdown.

Runs under ~/.report-venv (has openpyxl) - the system python3 that runs generate_kp.py
itself is Debian's externally-managed one (PEP 668, no easy pip install), same reason
WeasyPrint and pypdf are already invoked as subprocesses elsewhere in this project.
generate_kp.py's write_economics_xlsx() shells out to this script.

Reads a JSON spec from stdin (never argv - large payloads have hit ARG_MAX here before,
see project memory): {"path": "...", "client": "...",
"variants": [{"label": ... or null, "summary_items": [...], "economics": {...}}, ...]}.
Writes the .xlsx to `path`. Prints {"ok": true} or {"ok": false, "error": "..."} to stdout.

Multi-variant support (2026-08-26): each variant renders as its own self-contained table
(own header row, own ИТОГО/margin lines) stacked in the SAME sheet, never summed together
across variants - these are alternative options a client picks ONE of, not a combined
order. A single unlabeled variant (the common case, `label: null`) renders exactly like
the pre-2026-08-26 single-table file - no visual change for that path.
"""
import json
import sys

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

MONEY_FMT = '#,##0.00 ₽'
HEADERS = [
    "Позиция", "Ед.", "Кол-во", "Цена в КП", "Сумма в КП",
    "Себестоимость (ед.)", "Себестоимость (сумма)", "Прибыль",
]


def _write_variant_table(ws, label, summary_items, economics):
    if label:
        ws.append([label])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=12, color="0B0F10")

    ws.append(HEADERS)
    header_row = ws.max_row
    for col in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=header_row, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="10222C")

    for it in summary_items:
        kind = it.get("type", "equipment")
        qty = it.get("qty") if kind != "freon_line" else it.get("length_m")
        cost_total_val = it.get("cost_total")

        if kind == "equipment":
            label_cell = f"{it['sku']} ({it.get('availability', '')})"
            unit = "шт."
            price = it["unit_price"]
        elif kind == "install":
            label_cell = f"Монтаж, {it.get('capacity_kw')} кВт (для {it.get('for_sku')})"
            unit = "шт."
            price = it["unit_price"]
        elif kind == "service":
            label_cell = it.get("label") or "Работы"
            unit = it.get("unit") or "шт."
            price = it["unit_price"]
        else:  # freon_line
            label_cell = f"Доп. фреоновая магистраль (для {it.get('for_sku')})"
            if it.get("allocation_note"): label_cell += " — " + it["allocation_note"]
            unit = "м."
            price = it["unit_price_per_m"]

        line_total = it["line_total"]
        cost_unit = round(cost_total_val / qty, 2) if (cost_total_val is not None and qty) else None
        profit = round(line_total - cost_total_val, 2) if cost_total_val is not None else None

        row = [
            label_cell, unit, qty, price, line_total,
            cost_unit if cost_unit is not None else "нет данных",
            cost_total_val if cost_total_val is not None else "нет данных",
            profit if profit is not None else "нет данных",
        ]
        ws.append(row)
        r = ws.max_row
        for col in (4, 5, 6, 7, 8):
            cell = ws.cell(row=r, column=col)
            if isinstance(cell.value, (int, float)):
                cell.number_format = MONEY_FMT

    ws.append([
        "ИТОГО", "", "", "", economics["revenue"],
        "", economics["cost"], economics["profit"],
    ])
    r = ws.max_row
    for col in range(1, len(HEADERS) + 1):
        ws.cell(row=r, column=col).font = Font(bold=True)
    for col in (5, 7, 8):
        ws.cell(row=r, column=col).number_format = MONEY_FMT

    if economics.get("margin_pct") is not None:
        ws.append(["Маржа, %", "", "", "", "", "", "", f"{economics['margin_pct']}%"])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)

    if not economics.get("cost_fully_known"):
        ws.append([
            f"⚠ Нет закупочной цены у поставщика для: "
            f"{', '.join(economics.get('cost_unknown_skus') or [])} — "
            f"себестоимость и прибыль по этим позициям занижены."
        ])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True, color="B5790A")


def build(spec):
    path = spec["path"]
    client = spec["client"]
    variants = spec["variants"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Экономика КП"

    ws.append([f"КП для {client}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])

    for i, v in enumerate(variants):
        if i > 0:
            ws.append([])
            ws.append([])
        _write_variant_table(ws, v.get("label"), v["summary_items"], v["economics"])

    widths = [42, 6, 9, 14, 14, 16, 18, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        # Excel does not reliably auto-fit wrapped rows in generated workbooks.
        lines = max((len(str(cell.value or "")) + widths[i] - 1) // widths[i]
                    for i, cell in enumerate(row))
        ws.row_dimensions[row[0].row].height = max(30, lines * 17)
    ws.freeze_panes = "D4"

    wb.save(path)


if __name__ == "__main__":
    try:
        build(json.load(sys.stdin))
        print(json.dumps({"ok": True}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
