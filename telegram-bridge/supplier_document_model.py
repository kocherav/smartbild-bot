"""Supplier КП / invoice tables read by the document model, then checked by arithmetic.

TASK-20261124-15 (real КП Liechty D4055, 16 scanned pages): OCR + regular expressions
read «704» for a quantity of 3, mixed price and quantity and merged alternative sets of
equipment. A table like this is read by the same model that parsed the 53-row project
specification; its answer is never trusted as is — every row must satisfy
qty × price = amount, the currency and the set (variant) are shown to the owner.
"""
import json
import re

PROMPT = """Ты читаешь документ поставщика (КП или счёт) для подбора цен в сделку. Файл: {path}
{text_block}
Верни ТОЛЬКО JSON без пояснений:
{{"kind": "kp" | "invoice" | null, "supplier": "название поставщика", "brand": "марка оборудования латиницей, если одна на весь документ (Liechty, Daikin…), иначе пусто",
  "currency": "RUB" | "USD" | "EUR",
  "rows": [{{"name": "наименование как в документе", "qty": число, "unit": "шт|м|компл|…", "price": цена за единицу,
            "amount": сумма строки, "variant": "название варианта/комплектации или пусто"}}]}}
Правила: kind — «kp», если это коммерческое предложение/прайс, «invoice», если счёт на оплату; иначе null.
Валюта — по заголовкам колонок и значкам ($, USD, €, EUR); по умолчанию RUB. Бери строки ТОЛЬКО из таблиц
товаров с колонками цены и количества; не бери итоги, НДС, доставку как отдельную строку не выдумывай.
Если в документе несколько вариантов комплектации (Вариант 1/2, опции, альтернативы) — укажи для каждой строки
её вариант в "variant". Числа — как в документе, без пересчёта. Если чего-то не видно — не придумывай строку."""


def prompt(path, text=""):
    block = f"Текст документа (может быть неполным для сканов — тогда открой файл сам):\n{text[:40000]}\n" if text else \
        "Текст не извлекается (скан) — открой и прочитай файл сам.\n"
    return PROMPT.format(path=path, text_block=block)


def _number(value):
    try:
        return float(str(value).replace(" ", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_answer(answer):
    """The model's JSON → {ok, kind, supplier, currency, rows, rejected, variants}; only consistent rows."""
    match = re.search(r"\{.*\}", answer or "", re.S)
    if not match:
        return {"ok": False, "error": "модель не вернула таблицу"}
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return {"ok": False, "error": "модель вернула неразборчивый ответ"}
    rows, rejected = [], []
    for r in data.get("rows") or []:
        qty, price, amount = _number(r.get("qty")), _number(r.get("price")), _number(r.get("amount"))
        name = str(r.get("name") or "").strip()
        if not name or not qty or not price:
            rejected.append({"name": name, "reason": "нет количества или цены"})
            continue
        if amount is None:
            amount = qty * price
        if abs(qty * price - amount) > max(0.02, amount * 0.01):
            rejected.append({"name": name, "reason": f"{qty:g} × {price:g} ≠ {amount:g}"})
            continue
        rows.append({"name": name, "qty": qty, "unit": str(r.get("unit") or ""), "price": round(price, 2),
                     "amount": round(amount, 2), "variant": str(r.get("variant") or "").strip()})
    currency = str(data.get("currency") or "RUB").upper()
    kind = data.get("kind") if data.get("kind") in ("kp", "invoice") else None
    variants = sorted({r["variant"] for r in rows if r["variant"]})
    return {"ok": bool(rows), "kind": kind, "supplier": str(data.get("supplier") or ""),
            "brand": str(data.get("brand") or "").strip(),
            "currency": currency if currency in ("RUB", "USD", "EUR") else "RUB",
            "rows": rows, "rejected": rejected, "variants": variants,
            **({} if rows else {"error": "в ответе модели нет ни одной строки, где кол-во × цена = сумма"})}


def only_variant(doc, variant):
    """Keep the rows of one set of equipment (plus rows common to all sets)."""
    return {**doc, "rows": [r for r in doc["rows"] if not r.get("variant") or r["variant"] == variant],
            "variant": variant}
