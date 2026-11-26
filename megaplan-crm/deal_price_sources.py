#!/usr/bin/env python3
"""Prices of a deal from the owner's supplier documents (owner 24.11).

The owner sends supplier КП and invoices — for this object or for others with similar
items. An invoice gives our purchase cost. A КП gives the supplier's list price, which is
our sale price; the owner tells the bot our discount for that КП (0…40 %), and the cost is
list × (1 − discount). Every deal row is matched against these rows by the same rules as
price history (kind, model, sizes, unit; ducts per metre). Galvanised fittings that no
document names are priced by the area of metal (fitting_area), sold at +200 %.

Commands (stdin JSON, stdout JSON):
  read      {"path"} → {"ok", "kind": "kp"|"invoice"|null, "supplier", "rows": [...]}
  propose   {"ledger": [...], "documents": [{"kind","discount","label","rows","this_object"}],
             "overwrite_priced": bool, "fitting_markup": 3.0} → {"ok", "proposals": [...], "skipped": [...]}
Nothing here writes to Megaplan; megaplan_api.py apply-price-proposals does, after the owner's button.
"""
import json
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import invoice_lines   # noqa: E402
import price_history   # noqa: E402

KP_WORDS = re.compile(r"коммерческое\s+предложение|\bкп\b\s*№?|прайс|предложение\s*№", re.I)
INVOICE_WORDS = re.compile(r"сч[её]т\s+на\s+оплату|сч[её]т\s*№|сч[её]т-оферта|счет-договор", re.I)
DISCOUNTS = list(range(0, 45, 5))     # owner 24.11: 0…40 % step 5, or his own figure


def classify(text):
    """'invoice' / 'kp' / None (the owner decides)."""
    # TASK-20261126-02: in the Вентрешения .xls «Счет № …» comes after 3000 characters of bank details.
    head = (text or "")[:15000]
    invoice, kp = bool(INVOICE_WORDS.search(head)), bool(KP_WORDS.search(head))
    if invoice and not kp:
        return "invoice"
    if kp and not invoice:
        return "kp"
    return None


def supplier_of(text):
    m = re.search(r"(?:Поставщик|Продавец|Исполнитель|От\s*кого)\s*[:\-]?\s*([^\n,;]{3,80})", text or "", re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"((?:ООО|АО|ИП|ЗАО)\s*[«\"]?[^\n«»\"]{2,60}[»\"]?)", text or "")
    return m.group(1).strip() if m else ""


def text_of(path):
    """PDF/XLS/XLSX/DOCX via the finance extractor; photos via tesseract."""
    suffix = os.path.splitext(path)[1].lower()
    if suffix in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
        out = subprocess.run(["tesseract", path, "stdout", "-l", "rus+eng", "--psm", "6"],
                             capture_output=True, timeout=90)
        return out.stdout.decode(errors="replace")
    sys.path.insert(0, os.path.join(os.path.dirname(BASE_DIR), "hogart-scraper", "finance"))
    from procurement_intake import extract
    return extract(path)


def read(path):
    text = text_of(path)
    rows = invoice_lines.rows(text)
    return {"ok": True, "kind": classify(text), "supplier": supplier_of(text), "rows": rows,
            "currency": invoice_lines.currency(text), "file": os.path.basename(path)}


def history_rows(document, rate=None):
    """A document's rows in price-history shape: invoice → cost; КП → sale price and cost by discount.
    Prices in USD/EUR are converted by the CBR rate (24.11: a dollar КП was read as roubles)."""
    code = str(document.get("currency") or "RUB").upper()
    factor = 1.0
    if code != "RUB":
        factor = (rate or price_history.cbr_rate)(code)
        if not factor:
            return []
    label = " ".join(x for x in (document.get("supplier"), "КП" if document["kind"] == "kp" else "счёт",
                                 document.get("file")) if x)
    if code != "RUB":
        label += f", {code} по курсу ЦБ {factor:.2f}"
    discount = float(document.get("discount") or 0) / 100
    out = []
    # 25.11 (deal 907): «SV Активный бесшумный клапан» in a Liechty КП never names the brand per row, so the
    # brand rule refused «Активный бесшумный клапан Liechty SV». The document's brand belongs to every row.
    brands = {w for w in re.findall(r"[A-Za-z]{3,}", f"{document.get('brand') or ''} {document.get('supplier') or ''}")}
    for r in document.get("rows") or []:
        name = r["name"]
        missing = [b for b in brands if b.lower() not in name.lower()]
        r = {**r, "name": (name + " " + " ".join(missing)).strip(), "price": round(float(r["price"]) * factor, 2)}
        if document["kind"] == "kp":
            out.append({"name": r["name"], "price": r["price"], "cost": round(r["price"] * (1 - discount), 2),
                        "source": "КП поставщика", "unit": r.get("unit", ""), "order": 1 if document.get("this_object") else 0,
                        "ref": f"{label}, скидка {document.get('discount') or 0:g}%"})
        else:
            out.append({"name": r["name"], "price": None, "cost": r["price"], "source": "счёт поставщика",
                        "unit": r.get("unit", ""), "order": 1 if document.get("this_object") else 0, "ref": label})
    return out


def _zero(value):
    try:
        return not float(value or 0)
    except (TypeError, ValueError):
        return True


def invoice_cost(name, invoice_rows):
    """(None, cost, mark) only for a real pair in a supplier invoice — never an area estimate (26.11: an
    estimate was shown as «закупка по счёту»). Duct pieces are converted per metre."""
    match = price_history.best_match(name, invoice_rows) if invoice_rows else None
    if not match or not match.get("cost"):
        return None
    cost, ref = match["cost"], match["ref"]
    length = price_history.duct_length(name, match["name"], match.get("unit", ""))
    if length:
        cost, ref = round(cost * 1000.0 / length, 2), f"{ref}, пересчитано за 1 м из штуки L={length:g} мм"
    return (None, cost, f"проверить: «{match['name']}», {ref}")


def propose(ledger, documents, history=None, ratios=None, overwrite_priced=False, fitting_markup=3.0, catalog=None,
            rate=None):
    """Proposals for deal rows: the owner's documents first, then supplier catalogs (Daichi/Hogart,
    by model — owner 24.11 «неужели цены на блоки Дайкин нельзя найти в API Daichi»), then
    fittings by area (rates from history + documents)."""
    doc_rows = [r for d in documents for r in history_rows(d, rate)]
    invoice_rows = [r for d in documents if d.get("kind") == "invoice" for r in history_rows(d, rate)]
    history = list(history or [])
    proposals, skipped = [], []
    for row in ledger:
        name = row.get("name") or ""
        needs_price = _zero(row.get("sell_price")) or overwrite_priced
        needs_cost = _zero(row.get("cost_material"))
        # 26.11 (deal 907, счёт Вентрешения): a real supplier invoice replaces an estimated cost (area,
        # similar deals) — the owner sent it for exactly that. Only the cost; a set sale price stays.
        invoice_hit = invoice_cost(name, invoice_rows)
        if not needs_price and not needs_cost and not invoice_hit:
            continue
        if invoice_hit and not needs_price and not needs_cost:
            cost = invoice_hit[1]
            if cost and abs(cost - float(row.get("cost_material") or 0)) > max(1.0, cost * 0.01):
                proposals.append({"offer_row_id": row.get("offer_row_id"), "offer_id": row.get("offer_id"), "name": name,
                                  "unit": row.get("unit"), "qty": row.get("qty"), "old_price": row.get("sell_price"),
                                  "old_cost": row.get("cost_material"), "cost_material": cost, "replace_cost": True,
                                  "mark": "закупка по счёту поставщика вместо прежней: " + invoice_hit[2]})
            continue
        hit = price_history.price_from_history(name, doc_rows, ratios, fitting_markup) if doc_rows else None
        if not hit and catalog:
            hit = catalog(name)
            if hit and not hit[0] and hit[1]:
                ratio, why = price_history.ratio_for(name, ratios)
                hit = (round(hit[1] * ratio, 2), hit[1], f"{hit[2]}; продажа = закупка × {why} {ratio:g}") if ratio else \
                    (None, hit[1], hit[2])
        if not hit and history:
            # 25.11: Invisiline AESTH was in our past deals but the document route never looked there.
            hit = price_history.price_from_history(name, history, ratios, fitting_markup)
        if not hit and price_history.kind(name) in price_history.AREA_PRICED:
            hit = price_history.fitting_estimate(name, history + doc_rows, fitting_markup, ratios)
        if not hit:
            skipped.append({"name": name, "reason": "нет похожей строки в документах, прайсах Daichi/Hogart, прошлых сделках и счетах; не фасонка"})
            continue
        sell, cost, mark = hit
        proposal = {"offer_row_id": row.get("offer_row_id"), "offer_id": row.get("offer_id"), "name": name,
                    "unit": row.get("unit"), "qty": row.get("qty"), "old_price": row.get("sell_price"),
                    "old_cost": row.get("cost_material"), "mark": mark}
        if needs_price and sell:
            proposal["sell_price"] = sell
        if needs_cost and cost:
            proposal["cost_material"] = cost
        elif invoice_hit and invoice_hit[1]:
            proposal["cost_material"], proposal["replace_cost"] = invoice_hit[1], True
        if "sell_price" in proposal or "cost_material" in proposal:
            proposals.append(proposal)
        else:
            skipped.append({"name": name, "reason": "в документе нет нужной цены (продажа/закупка)"})
    return {"ok": True, "proposals": proposals, "skipped": skipped}


STORE = os.path.join(BASE_DIR, "price_documents.json")


def remember(documents, store=STORE):
    """Keep the owner's supplier documents for later deals (26.11: the Вентрешения invoice had the
    rectangular fittings the area method lacked). Same file + supplier is kept once."""
    try:
        with open(store, encoding="utf-8") as f:
            kept = json.load(f)
    except (OSError, ValueError):
        kept = []
    seen = {(d.get("file"), d.get("supplier")) for d in kept}
    for d in documents:
        if d.get("rows") and d.get("kind") in ("kp", "invoice") and (d.get("file"), d.get("supplier")) not in seen:
            kept.append({k: d.get(k) for k in ("file", "supplier", "brand", "kind", "currency", "discount", "rows")})
            seen.add((d.get("file"), d.get("supplier")))
    tmp = store + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False)
    os.replace(tmp, store)


def remembered_rows(store=STORE, rate=None):
    try:
        with open(store, encoding="utf-8") as f:
            return [r for d in json.load(f) for r in history_rows(d, rate)]
    except (OSError, ValueError):
        return []


def _catalog():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(BASE_DIR), "hogart-scraper"))
        import price_by_article
        return price_by_article.catalog_lookup()
    except Exception:  # noqa: BLE001 — documents and fittings still work without the catalogs
        return None


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        spec = json.load(sys.stdin)
        if command == "read":
            result = read(spec["path"])
        elif command == "propose":
            remember(spec.get("documents") or [])
            history = price_history.load_history() + remembered_rows()
            result = propose(spec.get("ledger") or [], spec.get("documents") or [], history,
                             price_history.markups(history), bool(spec.get("overwrite_priced")),
                             float(spec.get("fitting_markup") or 3.0), _catalog())
        else:
            result = {"ok": False, "error": "команда: read | propose"}
    except Exception as exc:  # noqa: BLE001 — the bridge shows a plain reason
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
