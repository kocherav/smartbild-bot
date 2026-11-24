#!/usr/bin/env python3
"""Prices for specification rows that came without them (owner 22.11, «подобрать по каталогам»).

A project PDF (e.g. Cliwell, Лаврушинский) lists equipment and quantities but no prices; the bot
could not create a deal. Each row without a price is looked up by its article in Hogart (exact
article) and Daichi (model code); the retail price becomes the sale price, the purchase price —
the cost. Rows not found keep price 0 and are reported — nothing is invented. Read-only.

stdin: {"items": [{"name": ..., "sku": optional, "qty": ..., "unit_price": optional}, ...]}
stdout: {"ok": true, "items": [...], "found": n, "missing": [names]}
"""
import json
import os
import re
import sys

ARTICLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/\.]{3,}")


def has_price(row):
    try:
        return float(str(row.get("unit_price")).replace(" ", "").replace(",", ".")) > 0
    except (TypeError, ValueError):
        return False


def candidates(row):
    """Article-like tokens: the explicit sku first, then codes in the name that carry a digit
    and a letter (AS25S2SF3FA-B, ECO07AN/LETTA07AN), longest first."""
    found = []
    if row.get("sku"):
        found.append(str(row["sku"]).strip())
    tokens = [t.strip(".-/") for t in ARTICLE.findall(str(row.get("name") or ""))]
    tokens = [t for t in tokens if re.search(r"\d", t) and re.search(r"[A-Za-z]", t)]
    found += sorted(set(tokens), key=len, reverse=True)
    return list(dict.fromkeys(found))


def _history():
    """Owner 24.11: our own earlier deals and supplier invoices (megaplan-crm/price_history)."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "megaplan-crm"))
        import price_history
        rows = price_history.load_history()
        ratios = price_history.markups(rows)
        return lambda name: price_history.price_from_history(name, rows, ratios)
    except Exception:  # noqa: BLE001 — history is a bonus tier; catalogs still work without it
        return lambda name: None


def price_rows(items, hogart=None, daichi=None, kemiks=None, history=None):
    """``hogart(article)`` → (retail, purchase) or None; ``daichi(article)`` → the same;
    ``kemiks(name)`` — pipes, insulation, cable by the row's description (КЕМИКС rules of
    price_spec_items.py, the route the investigation TASK-20261122-27 found 5 of 53 with)."""
    if hogart is None or daichi is None:
        import generate_kp as kp
        hogart = hogart or _hogart(kp)
        daichi = daichi or _daichi(kp)
    if kemiks is None:
        from price_spec_items import kemiks_lookup as kemiks
    if history is None:
        history = _history()
    priced, missing, found, from_history = [], [], 0, 0
    for row in items:
        row = dict(row)
        if has_price(row):
            priced.append(row)
            continue
        total = row.get("line_total", row.get("total"))
        if has_price({"unit_price": total}) and has_price({"unit_price": row.get("qty")}):
            # The spec carries only the line sum: the unit price follows from it, no lookup.
            qty = float(str(row["qty"]).replace(" ", "").replace(",", "."))
            row["unit_price"] = round(float(str(total).replace(" ", "").replace(",", ".")) / qty, 2)
            priced.append(row)
            continue
        hit = None
        for article in candidates(row):
            for source, lookup in (("Hogart", hogart), ("Daichi", daichi)):
                result = lookup(article)
                if result and result[0]:
                    hit = (source, article, result)
                    break
            if hit:
                break
        if not hit:
            result = kemiks(str(row.get("name") or ""))
            if result and result[0]:
                hit = ("КЕМИКС", "", result)
        if not hit:
            past = history(str(row.get("name") or ""))
            if past:
                sell, cost, mark = past
                row.update(unit_price=round(float(sell), 2), price_source=mark, price_needs_check=True)
                if cost:
                    row["cost_material"] = round(float(cost), 2)
                found += 1
                from_history += 1
                priced.append(row)
                continue
        if hit:
            source, article, (retail, purchase) = hit
            row.update(unit_price=round(float(retail), 2), price_source=f"{source} {article}".strip())
            if purchase:
                row["cost_material"] = round(float(purchase), 2)
            found += 1
        else:
            row.update(unit_price=0, price_source="цена не найдена в каталогах")
            missing.append(str(row.get("name") or ""))
        priced.append(row)
    return {"ok": True, "items": priced, "found": found, "from_history": from_history, "missing": missing}


def _hogart(kp):
    def lookup(article):
        product = kp.live_lookup(article)
        return (kp.full_price_of(product), kp.contract_price_of(product)) if product else None
    return lookup


def daichi_name_matches(name, article):
    """Owner 24.11: Daikin FXSQ20A is in Daichi as «FXSQ20A2VEB» (or «FXSQ20A/BRC…»). The article
    matches a name part equal to it, or a part that is it plus a short letter/digit suffix of the
    version (≤ 5 signs) — never a longer model: after a final digit the suffix must start with a
    letter (FXSQ20 ≠ FXSQ200A); after a final letter any version suffix is fine (FXSQ20A2VEB)."""
    article = article.casefold()
    if len(article) < 4:
        return False
    for part in re.split(r"[/\s+,;]+", name.casefold()):
        if part == article:
            return True
        if part.startswith(article) and len(part) - len(article) <= 5 and \
                re.fullmatch(r"[a-z0-9\-]+", part[len(article):]) and \
                (article[-1].isalpha() or not part[len(article)].isdigit()):
            return True
    return False


def _daichi(kp):
    def lookup(article):
        wanted = article.casefold()
        catalog = kp.get_daichi_catalog() or {}
        best = None
        for item in (catalog.values() if isinstance(catalog, dict) else catalog):
            if daichi_name_matches(str(item.get("name") or ""), wanted) and item.get("sell_price"):
                exact = str(item.get("name") or "").casefold() == wanted
                if best is None or exact:
                    best = item
                if exact:
                    break
        return (best.get("sell_price"), best.get("cost_price")) if best else None
    return lookup


def catalog_lookup():
    """name → (sell, cost, mark) from Hogart (exact article) and Daichi (model), else None."""
    import generate_kp as kp
    hogart, daichi = _hogart(kp), _daichi(kp)

    def lookup(name):
        for article in candidates({"name": name}):
            for source, find in (("Daichi", daichi), ("Hogart", hogart)):
                try:
                    hit = find(article)
                except Exception:  # noqa: BLE001 — one supplier being down must not stop the rest
                    hit = None
                if hit and hit[0]:
                    return (round(float(hit[0]), 2), hit[1] and round(float(hit[1]), 2),
                            f"проверить: прайс {source}, модель {article} (продажа — розница поставщика, закупка — наша цена)")
        return None
    return lookup


def main():
    try:
        print(json.dumps(price_rows(json.load(sys.stdin).get("items") or []), ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 — the bridge shows the reason, never a traceback
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
