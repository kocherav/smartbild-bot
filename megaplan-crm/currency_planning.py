#!/usr/bin/env python3
"""Safe planning conversion for supplier invoices in a foreign currency.

The supplier document remains the source of truth in its original currency.  The
RUB amount here is explicitly a *plan* calculated from the CBR rate effective on
the invoice date and the supplier's written markup (``ЦБ + N%``).  It must never
be presented as a bank-payment fact.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime


class CurrencyPlanningError(ValueError):
    pass


def _number(value):
    try:
        return float(str(value).replace("\xa0", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise CurrencyPlanningError(f"некорректная сумма или курс: {value!r}") from exc


def invoice_date(value):
    try:
        return datetime.strptime(str(value or ""), "%d.%m.%Y").date()
    except ValueError as exc:
        raise CurrencyPlanningError("для валютного счёта нужна дата в формате ДД.ММ.ГГГГ") from exc


def parse_cbr_markup(note=""):
    """Return markup percent from a supplier note; an absent condition is CBR+0."""
    text = str(note or "").replace("\xa0", " ").casefold()
    # The supplier can write both ``ЦБ+3%`` and ``курс ЦБ РФ плюс 3 процента``.
    if not text or not re.search(r"\bцб\b|центральн\w*\s+банк", text):
        return 0.0
    match = re.search(r"(?:\+|плюс)\s*(\d+(?:[,.]\d+)?)\s*(?:%|процент\w*)?", text)
    return _number(match.group(1)) if match else 0.0


def fetch_cbr_rate(currency, on_date, opener=None):
    """Fetch one official CBR rate and return rate plus the effective CBR date.

    CBR returns the most recently established rate for weekends/holidays.  We
    preserve that effective date instead of pretending a non-existent daily rate.
    """
    code = str(currency or "").upper().strip()
    if code == "RUB":
        return {"currency": "RUB", "rate": 1.0, "nominal": 1, "effective_date": on_date.strftime("%d.%m.%Y")}
    if code not in {"EUR", "USD", "CNY", "GBP", "CHF", "JPY", "KZT", "BYN", "AED"}:
        raise CurrencyPlanningError(f"не поддержан валютный код {code}")
    date_value = invoice_date(on_date) if isinstance(on_date, str) else on_date
    url = "https://www.cbr.ru/scripts/XML_daily.asp?" + urllib.parse.urlencode(
        {"date_req": date_value.strftime("%d/%m/%Y")})
    try:
        response = (opener or urllib.request.urlopen)(url, timeout=15)
        raw = response.read()
    except Exception as exc:
        raise CurrencyPlanningError("не удалось получить курс ЦБ РФ; счёт не применён") from exc
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise CurrencyPlanningError("ЦБ РФ вернул некорректный ответ; счёт не применён") from exc
    for item in root.findall("Valute"):
        if (item.findtext("CharCode") or "").upper() != code:
            continue
        nominal = _number(item.findtext("Nominal") or 1)
        value = _number(item.findtext("Value"))
        return {"currency": code, "rate": value / nominal, "nominal": nominal,
                "effective_date": root.attrib.get("Date") or date_value.strftime("%d.%m.%Y")}
    raise CurrencyPlanningError(f"ЦБ РФ не вернул курс {code}; счёт не применён")


def _convert_value(value, multiplier):
    return round(_number(value) * multiplier, 2)


def plan_invoice_spec(spec, rate_fetcher=fetch_cbr_rate):
    """Convert an extracted foreign-currency invoice spec to a RUB planning spec.

    The function is idempotent: an already-normalised document has
    ``currency_plan_applied`` and is returned unchanged.
    """
    result = dict(spec)
    doc = dict(result.get("invoice") or {})
    if doc.get("currency_plan_applied"):
        return result
    currency = str(doc.get("currency") or "RUB").upper().strip()
    if currency in {"", "RUB", "RUR", "РУБ", "РУБ."}:
        doc["currency"] = "RUB"
        doc["currency_plan_applied"] = True
        result["invoice"] = doc
        return result
    original_total = _number(doc.get("foreign_total", doc.get("total")))
    date_text = doc.get("date")
    # Validate locally even when tests or a future provider inject a rate fetcher.
    invoice_date(date_text)
    rate_info = rate_fetcher(currency, date_text)
    markup = _number(doc.get("cbr_markup_pct", parse_cbr_markup(doc.get("payment_note") or doc.get("currency_note"))))
    if markup < 0 or markup > 100:
        raise CurrencyPlanningError("надбавка к курсу ЦБ должна быть от 0 до 100%")
    plan_rate = round(float(rate_info["rate"]) * (1 + markup / 100), 6)
    doc.update({
        "currency": currency,
        "foreign_total": original_total,
        "total": _convert_value(original_total, plan_rate),
        "plan_total_rub": _convert_value(original_total, plan_rate),
        "cbr_rate": round(float(rate_info["rate"]), 6),
        "cbr_effective_date": rate_info.get("effective_date") or date_text,
        "cbr_markup_pct": markup,
        "plan_rate": plan_rate,
        "rate_source": "ЦБ РФ" + (f" + {markup:g}%" if markup else ""),
        "currency_plan_applied": True,
    })
    for key in ("updates", "unallocated", "additional_expenses"):
        converted = []
        for source in result.get(key) or []:
            row = dict(source)
            for amount_key in ("source_total", "amount", "material_cost_used", "work_cost_used"):
                if row.get(amount_key) not in (None, ""):
                    foreign_key = "foreign_" + amount_key
                    row.setdefault(foreign_key, row[amount_key])
                    row[amount_key] = _convert_value(row[amount_key], plan_rate)
            converted.append(row)
        result[key] = converted
    converted_additions = []
    for source in result.get("additions") or []:
        row = dict(source)
        for amount_key in ("cost_material", "cost_work", "sell_price"):
            # Supplier invoice additions are costs. sell_price is only converted
            # when supplied by the parser, and never invented by this module.
            if row.get(amount_key) not in (None, ""):
                row.setdefault("foreign_" + amount_key, row[amount_key])
                row[amount_key] = _convert_value(row[amount_key], plan_rate)
        converted_additions.append(row)
    result["additions"] = converted_additions
    result["invoice"] = doc
    return result
