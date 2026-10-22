#!/usr/bin/env python3
"""
SmartBild brand styling for openpyxl reports (2026-08-25). Colors taken from
~/OneDrive-SmartBild/SmartBild_Complete_Handoff/01_brand/03_Colors/SmartBild_Tokens.css
(the project's own CLAUDE.md brand rule: Smart Green is an interactive/status ACCENT
only, never a fill across a large surface - Deep Black/Light Gray carry the bulk of the
area here, same ~42%/~39% split the brand book specifies elsewhere). Shared by
build_work_statement.py and build_profitability_report.py so both reports look like one
system rather than two ad hoc sheets.
"""
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

DEEP_BLACK = "0B0F10"
LIGHT_GRAY = "E6E8EB"
WHITE = "FFFFFF"
SMART_GREEN = "19D38A"
SMART_GREEN_TINT = "DDF8ED"  # Smart Green blended ~85% toward white - status/total rows
ORANGE_ACCENT = "FF6B3D"
ORANGE_TINT = "FFE9E2"  # orange accent blended ~85% toward white - warning/missing rows

FONT_NAME = "Inter"  # brand's UI font; Excel falls back silently if not installed

TITLE_FONT = Font(name=FONT_NAME, bold=True, size=13, color=WHITE)
SUBTITLE_FONT = Font(name=FONT_NAME, size=9, italic=True, color=LIGHT_GRAY)
HEADER_FONT = Font(name=FONT_NAME, bold=True, size=10, color=WHITE)
BODY_FONT = Font(name=FONT_NAME, size=10, color=DEEP_BLACK)
TOTAL_FONT = Font(name=FONT_NAME, bold=True, size=11, color=DEEP_BLACK)

TITLE_FILL = PatternFill("solid", fgColor=DEEP_BLACK)
HEADER_FILL = PatternFill("solid", fgColor=DEEP_BLACK)
STRIPE_FILL = PatternFill("solid", fgColor=LIGHT_GRAY)
WARNING_FILL = PatternFill("solid", fgColor=ORANGE_TINT)
TOTAL_FILL = PatternFill("solid", fgColor=SMART_GREEN_TINT)

_GRID_SIDE = Side(style="thin", color=LIGHT_GRAY)
CELL_BORDER = Border(left=_GRID_SIDE, right=_GRID_SIDE, top=_GRID_SIDE, bottom=_GRID_SIDE)
HEADER_BORDER = Border(bottom=Side(style="medium", color=SMART_GREEN))
TOTAL_BORDER = Border(top=Side(style="medium", color=SMART_GREEN))

CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")
RIGHT = Alignment(horizontal="right", vertical="center")

MONEY_FMT = '#,##0.00 ₽'


def write_title_banner(ws, title, subtitle, n_cols):
    """Row 1 (+ row 2 if subtitle given): dark banner spanning every column, same
    Deep Black the header row uses - reads as one continuous header block, not a
    separate box. Returns the row number the column header row should start on."""
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    cell = ws.cell(row=1, column=1, value=title)
    cell.font = TITLE_FONT
    cell.alignment = LEFT
    ws.row_dimensions[1].height = 24
    next_row = 2
    if subtitle:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
        sub = ws.cell(row=2, column=1, value=subtitle)
        sub.font = SUBTITLE_FONT
        sub.alignment = LEFT
        ws.row_dimensions[2].height = 16
        next_row = 3
    for r in range(1, next_row):
        for c in range(1, n_cols + 1):
            ws.cell(row=r, column=c).fill = TITLE_FILL
    return next_row


def write_header_row(ws, row, headers):
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = HEADER_BORDER
    ws.row_dimensions[row].height = 20
    ws.freeze_panes = ws.cell(row=row + 1, column=1).coordinate
    ws.auto_filter.ref = f"A{row}:{get_column_letter(len(headers))}{row}"


def style_data_row(ws, row, n_cols, align_by_col, stripe):
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = BODY_FONT
        cell.border = CELL_BORDER
        if stripe:
            cell.fill = STRIPE_FILL
        cell.alignment = align_by_col.get(col, LEFT)


def apply_warning_fill(ws, row, n_cols):
    for col in range(1, n_cols + 1):
        ws.cell(row=row, column=col).fill = WARNING_FILL


def style_total_row(ws, row, n_cols, label_col=1):
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = TOTAL_FONT
        cell.fill = TOTAL_FILL
        cell.border = TOTAL_BORDER
        cell.alignment = LEFT if col == label_col else RIGHT
