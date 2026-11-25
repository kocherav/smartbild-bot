#!/usr/bin/env python3
"""Rows of supplier invoices (and our own invoices) read from their text.

Owner 24.11: «смотреть не только в каталоге CRM, но и в счетах поставщиков по предыдущим
сделкам». The finance pipeline keeps the text of every collected document in
hogart-scraper/finance/evidence/document_index.json (PDF via pdftotext, XLSX as cells).
A row is taken only when its own numbers agree — quantity × price = amount (±1 %, ±1 ₽) —
so headers, totals and wrapped text never become a price. Who sold is read from the
«Поставщик/Продавец» block: our own companies' INNs mean a sale price, anyone else a
purchase price.
"""
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_CANDIDATES = (os.path.join(BASE_DIR, "document_index.json"),
                    os.path.join(os.path.dirname(BASE_DIR), "hogart-scraper", "finance", "evidence", "document_index.json"))


def newest_index():
    """The freshest of the bot-owned and the old evidence index (24.11: the old one was not writable)."""
    present = [p for p in INDEX_CANDIDATES if os.path.exists(p)]
    return max(present, key=os.path.getmtime) if present else INDEX_CANDIDATES[0]


DOCUMENT_INDEX = None  # resolved per call: newest_index()
UNITS = r"(?:шт|шт\.|м|м\.|м2|м²|кв\.?\s?м|п\.?\s?м|пм|кг|компл|компл\.|к-т|упак|уп|пар|л|рул)"
NUMBER = re.compile(r"(?<![\w.,])\d{1,3}(?:[  ]\d{3})*(?:[.,]\d+)?(?![\w])|(?<![\w.,])\d+(?:[.,]\d+)?(?![\w])")
INVOICE_WORDS = re.compile(r"сч[её]т\s*(?:на\s+оплату|№|N|-\s*оферта)|товарная накладная|упд|спецификац", re.I)


def _value(token):
    return float(token.replace(" ", "").replace(" ", "").replace(",", "."))


def _own_inns():
    try:
        import own_companies
        return {c.get("inn") for c in own_companies.companies() if c.get("inn")}
    except Exception:  # noqa: BLE001
        return {"7743151323", "7743926877", "782093991468"}


def seller_is_us(text, own=None):
    """True when the «Поставщик/Продавец/Исполнитель» block carries one of our INNs."""
    own = own or _own_inns()
    block = re.search(r"(Поставщик|Продавец|Исполнитель)[^\n]{0,300}", text or "", re.I)
    if not block:
        return False
    return any(inn in block.group(0) for inn in own)


HEADER_QTY = re.compile(r"кол[-.\s]?во|количеств|\bкол\b|qty", re.I)
HEADER_PRICE = re.compile(r"цена|стоимость\s+ед|price", re.I)


def price_before_qty(text):
    """True when the table header puts «Цена» left of «Кол-во» (24.11, КП Liechty: the bot read
    the quantity as the price — qty × price = amount is true both ways)."""
    for line in (text or "").splitlines()[:200]:
        q, p = HEADER_QTY.search(line), HEADER_PRICE.search(line)
        if q and p:
            return p.start() < q.start()
    return False


CURRENCY_SIGNS = (("USD", re.compile(r"\$|\busd\b|долл|у\.\s?е\.", re.I)),
                  ("EUR", re.compile(r"€|\beur\b|евро", re.I)))


def _whole(value):
    return abs(value - round(value)) < 1e-9


def header_seen(text):
    return any(HEADER_QTY.search(l) and HEADER_PRICE.search(l) for l in (text or "").splitlines()[:200])


def currency(text):
    """'USD' / 'EUR' when the document says so, else 'RUB' (24.11: a dollar КП was read as roubles)."""
    for code, sign in CURRENCY_SIGNS:
        if sign.search(text or ""):
            return code
    return "RUB"


def rows(text):
    """[{name, qty, unit, price, amount}] — only rows whose qty × price equals the amount.
    Which of the two factors is the price comes from the table header (Цена left of Кол-во or not)."""
    found = []
    swap = price_before_qty(text)
    for raw in (text or "").splitlines():
        line = raw.replace("|", "  ").strip()
        if len(line) < 12 or re.search(r"итого|всего|в т\.?\s?ч|ндс\s*\(|к оплате|сумма прописью", line, re.I):
            continue
        tokens = [(m.start(), m.group(0)) for m in NUMBER.finditer(line)]
        if len(tokens) < 3:
            continue
        hit = _consistent(tokens, line)
        if not hit:
            continue
        start_qty, qty, price, amount, between = hit
        if swap or (not _whole(qty) and _whole(price) and not header_seen(text)):
            qty, price = price, qty          # without a header: a fractional «quantity» beside a whole «price»
        head = line[:start_qty]
        head = re.sub(r"^\s*\d{1,3}[.)]?\s+", "", head)               # row number
        unit = re.search(rf"\b{UNITS}\s*$", head, re.I)
        if unit:
            head = head[:unit.start()]
        unit = unit.group(0).strip() if unit else (re.search(rf"\b{UNITS}", between, re.I) or [""])[0]
        name = re.sub(r"\s{2,}", " ", head).strip(" .;-")
        if len(re.findall(r"[А-Яа-яA-Za-z]", name)) < 4:
            continue
        found.append({"name": name, "qty": qty, "unit": str(unit).strip(),
                      "price": round(price, 2), "amount": round(amount, 2)})
    return found


def _consistent(tokens, line=""):
    """(start of qty, qty, price, amount) for the first qty·price≈amount triple, amount last-ish."""
    line_of = [line]
    values = [(pos, _value(tok)) for pos, tok in tokens]
    n = len(values)
    for k in range(n - 1, max(n - 3, 1), -1):          # amount: last or second-to-last number
        amount = values[k][1]
        if amount <= 0:
            continue
        for j in range(k - 1, 0, -1):
            price = values[j][1]
            for i in range(j - 1, -1, -1):
                qty = values[i][1]
                if 0 < qty <= 100000 and price > 0 and abs(qty * price - amount) <= max(1.0, amount * 0.01):
                    if qty == amount or price == amount:
                        continue
                    between = line_of[0][values[i][0]:values[j][0]] if line_of else ""
                    return values[i][0], qty, price, amount, between
    return None


def history_rows(index_path=None):
    """History rows for price_history: purchases (cost) and our own invoices (sale price)."""
    index_path = index_path or newest_index()
    try:
        with open(index_path, encoding="utf-8") as f:
            documents = json.load(f)
    except (OSError, ValueError):
        return []
    own = _own_inns()
    out, seen = [], set()
    for doc in documents:
        text = doc.get("text") or ""
        if not INVOICE_WORDS.search(text):
            continue
        ours = seller_is_us(text, own)
        supplier = re.search(r"(?:Поставщик|Продавец|Исполнитель)\s*[:\-]?\s*([^\n,]{3,80})", text, re.I)
        label = (supplier.group(1).strip() if supplier else "счёт") + " — " + os.path.basename(doc.get("path") or "")
        for row in rows(text):
            key = (row["name"].casefold(), row["price"], ours)
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": row["name"], "price": row["price"] if ours else None,
                        "cost": None if ours else row["price"],
                        "source": "наш счёт" if ours else "счёт поставщика", "ref": label, "order": 0,
                        "unit": row["unit"]})
    return out


if __name__ == "__main__":
    found = history_rows()
    print(json.dumps({"ok": True, "rows": len(found),
                      "purchases": sum(1 for r in found if r["cost"]),
                      "sales": sum(1 for r in found if r["price"])}, ensure_ascii=False))
