#!/usr/bin/env python3
"""
Review-file builder for Phase 1b's "спецификация без цен" deal-creation flow (2026-08-23).
Sibling to xlsx_report.py (same ~/.report-venv + openpyxl pattern, shelled out to by
megaplan-crm's create-deal-from-spec caller / bridge.py) - one row per position with its
resolved price/source, and a highlighted flag for catalog matches that need the owner's
confirmation (Megaplan's own search could have matched the wrong product).

Reads a JSON spec from stdin (never argv - see project memory on ARG_MAX):
{"path": "...", "client": "...", "entries": [deal_ledger entries, see deal_ledger.py]}.
Writes the .xlsx to `path`. Prints {"ok": true} or {"ok": false, "error": "..."}.
"""
import json
import sys

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

MONEY_FMT = '#,##0.00 ₽'
SOURCE_LABELS = {
    "megaplan_catalog": "справочник Мегаплан",
    "megaplan_live": "текущая сделка Мегаплана",
    "hogart": "Hogart",
    "daichi": "Daichi",
    "kemiks": "КЕМИКС",
    "unresolved": "не найдено",
}


def _cost_note(e):
    """Cost-specific half of the note column (2026-08-24: the file used to leave
    "Себестоимость" blank even for catalog matches that already had real cost data
    sitting on the matched Offer in Мегаплан - see project memory). Only speaks up when
    there's something actionable: a catalog match missing one/both cost figures, or an
    unresolved item that has none yet."""
    # Мегаплан's own Money custom fields default to 0 (not null) when nobody's ever
    # filled them in - treat a bare 0 the same as "not set" here, or a genuinely-unset
    # cost prints as if it were confirmed at zero rubles, which is worse than the
    # original blank-column bug this file exists to fix.
    has_material = e.get("cost_material") is not None
    has_work = e.get("cost_work") is not None
    if e.get("price_source") == "megaplan_catalog":
        if has_material and has_work:
            return "себестоимость (материал+работы) тоже из каталога — сверьте"
        if has_material:
            return "себестоимость материала из каталога — сверьте; себестоимость работ в каталоге не указана, впишите"
        if has_work:
            return "себестоимость работ из каталога — сверьте; себестоимость материала в каталоге не указана, впишите"
        return "себестоимость в каталоге не указана — впишите вручную"
    if e.get("price_source") == "unresolved":
        return "себестоимость впишется вместе с ценой по счёту поставщика"
    return ""


def build(spec):
    path = spec["path"]
    client = spec["client"]
    entries = spec["entries"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Проверка позиций"

    ws.append([f"Сделка для {client} — проверьте позиции ниже"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])

    headers = [
        "Позиция", "Кол-во", "Цена продажи", "Себестоимость материала",
        "Себестоимость работ", "Источник цены", "Требует подтверждения",
    ]
    ws.append(headers)
    header_row = ws.max_row
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="10222C")

    review_fill = PatternFill("solid", fgColor="FFF3B0")
    unresolved_fill = PatternFill("solid", fgColor="F8D0D0")

    for e in entries:
        needs_review = e.get("needs_review")
        notes = []
        if needs_review:
            notes.append(f'цена — сверьте с "{e.get("matched_catalog_name", "")}"')
        elif e.get("price_source") == "unresolved":
            notes.append("цена не найдена нигде — заполнится по счёту поставщика")
        cost_note = _cost_note(e)
        if cost_note:
            notes.append(cost_note)
        note = "; ".join(notes)

        row = [
            e["name"], e["qty"], e["sell_price"], e.get("cost_material"), e.get("cost_work"),
            SOURCE_LABELS.get(e.get("price_source"), e.get("price_source")), note,
        ]
        ws.append(row)
        r = ws.max_row
        for col in (3, 4, 5):
            cell = ws.cell(row=r, column=col)
            if isinstance(cell.value, (int, float)):
                cell.number_format = MONEY_FMT
        if needs_review:
            for col in range(1, len(headers) + 1):
                ws.cell(row=r, column=col).fill = review_fill
        elif e.get("price_source") == "unresolved":
            for col in range(1, len(headers) + 1):
                ws.cell(row=r, column=col).fill = unresolved_fill

        # Per-cell override (2026-08-24, owner's ask): a missing cost is just as much a
        # "fill this in" gap as an unresolved price, regardless of what the rest of the
        # row looks like - red it out on its own, on top of whatever row-level fill was
        # just applied above (so a yellow needs_review row still shows red specifically
        # on the cost cell that's actually empty). Same 0-is-unset treatment as _cost_note.
        if e.get("cost_material") is None:
            ws.cell(row=r, column=4).fill = unresolved_fill
        if e.get("cost_work") is None:
            ws.cell(row=r, column=5).fill = unresolved_fill

    widths = [46, 8, 14, 18, 16, 18, 52]
    from openpyxl.utils import get_column_letter
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    wb.save(path)


if __name__ == "__main__":
    try:
        build(json.load(sys.stdin))
        print(json.dumps({"ok": True}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
