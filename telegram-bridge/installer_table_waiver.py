"""A «по таблице» line that closes the whole installation statement needs no table file.

Owner 20.11: on small deals «по таблице» means «100 % of the statement is done». Asking
the installer to copy an unchanged table into Telegram is busywork. When the amount in
the report equals what is still open in the deal's statement, the bot accepts the line as
100 % and builds the table rows itself from the statement; the manager still approves
the whole report, and the line says plainly that no file was attached.

Lines whose amount does not match keep the old rule: the installer sends the table.
"""

TOLERANCE = 0.01


def statement_rows(statement):
    """Rows in the shape the intake produces from an installer's table (100 % of the rest)."""
    rows = []
    for number, row in enumerate(statement.get("rows") or [], 1):
        left = float(row.get("remaining_qty") or 0)
        rows.append({
            "number": number, "name": row.get("name"), "unit": row.get("unit"),
            "plan_qty": row.get("planned_qty"), "rate": row.get("rate"),
            "plan_amount": round(float(row.get("planned_qty") or 0) * float(row.get("rate") or 0), 2),
            "previous_qty": row.get("accepted_qty"), "current_qty": left,
            "current_amount": round(float(row.get("remaining_amount") or 0), 2),
            "cumulative_qty": float(row.get("planned_qty") or 0), "remaining_qty": 0,
            "work_item_id": row.get("work_item_id"),
            # If more of the statement is accepted before the manager approves, the plan
            # stops and asks for a recount instead of accruing the old remainder twice.
            "accepted_baseline": row.get("accepted_qty"),
        })
    return rows


def guess_deal(item, remainders, taken):
    """The only open statement whose remainder equals the line's amount, else None."""
    amount = item.get("amount")
    if amount is None:
        return None
    matches = [deal for deal, total in (remainders or {}).items()
               if deal not in taken and float(total or 0) > 0 and abs(float(total) - float(amount)) < TOLERANCE]
    return matches[0] if len(matches) == 1 else None


def waive(session, remaining, remainders=None):
    """Mark table lines whose amount equals the statement's open remainder as 100 %.

    ``remaining(deal_id)`` returns the statement (``remaining_total``, ``rows``) or None.
    ``remainders()`` — open remainder per deal of objects handed to installers; used only
    for a line without a deal (the report parser could not map its object, 20.11): a single
    deal with exactly that remainder is taken, two or more — the line still needs a file.
    Returns the waived exceptions; ``required_tables`` and ``table_requests`` keep only
    the lines that still need a file."""
    waived = []
    cache = {}
    open_totals = None
    taken = {str(item.get("deal_id")) for item in session.get("exceptions") or [] if item.get("deal_id")}
    for item in session.get("exceptions") or []:
        if item.get("type") != "table" or item.get("table_path") or item.get("table_waived"):
            continue
        if not item.get("deal_id") and remainders is not None:
            if open_totals is None:
                open_totals = remainders() or {}
            guessed = guess_deal(item, open_totals, taken)
            if guessed:
                item["deal_id"] = guessed
                item["deal_guessed_by_remainder"] = True
                taken.add(guessed)
        deal_id = str(item.get("deal_id") or "")
        if not deal_id or item.get("amount") is None:
            continue
        if deal_id not in cache:
            cache[deal_id] = remaining(deal_id)
        statement = cache[deal_id]
        if not statement or not statement.get("rows"):
            continue
        open_total = float(statement.get("remaining_total") or 0)
        if open_total <= 0 or abs(float(item["amount"]) - open_total) >= TOLERANCE:
            continue
        rows = statement_rows(statement)
        item.update({
            "table_waived": True,
            "table_file": "Монтажная ведомость сделки — 100 %, файл не прикладывался",
            "table_rows": rows, "table_rows_count": len(rows),
            "table_calculated_total": statement.get("plan_total"),
            "completion_column": "остаток ведомости", "completion_sum": open_total,
            "completion_footer": open_total, "completion_matches_report": True,
            "table_match_confidence": 1.0,
            "resolution": "выполнение принято по таблице — 100 % остатка ведомости, без файла",
            "reason": ("сумма совпадает с остатком монтажной ведомости — выполнение 100 % "
                       "без файла таблицы; руководитель подтвердит при утверждении"
                       + ("; сделка определена по совпадению суммы с остатком ведомости"
                          if item.get("deal_guessed_by_remainder") else "")),
        })
        waived.append(item)
        # One line closes the statement; a second identical line would be a duplicate.
        cache[deal_id] = None
    still = [item for item in session.get("exceptions") or []
             if item.get("type") == "table" and not item.get("table_path") and not item.get("table_waived")]
    session["required_tables"] = len(still)
    session["table_requests"] = [{"object": item["object"], "source": item["source"], "deal_id": item.get("deal_id")}
                                 for item in still]
    session["waived_tables"] = [{"object": item["object"], "source": item["source"], "deal_id": item.get("deal_id"),
                                 "amount": item.get("amount")} for item in session.get("exceptions") or []
                                if item.get("table_waived")]
    return waived


def waived_text(session):
    lines = [f"• {item['object']}: «{item['source']}» → сделка №{item['deal_id']} — 100 % по ведомости, файл не нужен"
             for item in session.get("waived_tables") or []]
    return ("Сумма совпала с остатком монтажной ведомости, приняты как 100 %:\n" + "\n".join(lines)) if lines else ""
