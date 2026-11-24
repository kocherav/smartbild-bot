#!/usr/bin/env python3
"""Prices for spec rows from our own history: earlier deals and supplier invoices.

Owner 24.11 (deal 907, project «Лаврушинский»): 48 of 53 rows went in at 0 ₽ although
slot diffusers, ducts and fittings were sold and bought many times before. Every deal
clones its positions into Megaplan's Offer catalog (see offer_catalog_cache.py), so the
catalog holds our past sale prices and purchase costs; supplier invoices allocated to
deals (finance/data/review_registry.json) hold purchase prices.

Matching is deliberately not character-exact — «Диффузор щелевой 2-щ. L=1000 щель 15мм»
and «щелевой диффузор, 2 щели, 1000 мм, 15 мм» are the same thing. Two rules keep it safe:
1. the kind of item must agree (its key noun lemma: диффузор, воздуховод, тройник …);
2. every size must agree (the multiset of numbers: lengths, slot widths, Ø, A×B), because
   a different size is a different price. Letters, spaces, punctuation and word order
   are free; brand and extra adjectives only lower the confidence.
Every price found here is marked «проверить» with its source; nothing is invented.
"""
import json
import os
import re
import statistics
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OFFER_CACHE = os.path.join(BASE_DIR, "offer_catalog_cache.json")
# TASK-20261124-05: supplier invoices live in megaplan-crm/procurement_registry.json (invoices[].lines /
# allocations[].source_lines); the finance review registry holds tasks, not invoices.
REGISTRY = os.path.join(BASE_DIR, "procurement_registry.json")

# Kinds of items: the first word of a name that is one of these lemmas is its key noun
# (TASK-20261124-05: «Фанкойл … с проводным пультом» is a fan-coil, not a remote).
KINDS = [
    "диффузор", "решетка", "анемостат", "воздуховод", "тройник", "переход", "отвод", "ниппель",
    "муфта", "заглушка", "врезка", "адаптер", "клапан", "шумоглушитель", "глушитель", "фильтр",
    "вентилятор", "установка", "кондиционер", "блок", "камера", "дроссель", "хомут", "кронштейн",
    "шпилька", "профиль", "изоляция", "теплоизоляция", "труба", "трубка", "кабель", "гильза",
    "форсунка", "наконечник", "пульт", "крепление", "насос", "увлажнитель", "регулятор", "датчик",
    "термостат", "лента", "скотч", "герметик", "зонт", "дефлектор", "колено", "утка", "фланец",
    "шина", "уголок", "панель", "сплит", "мультисплит", "дренаж", "помпа",
    "клей", "трубопровод", "гидрозатвор", "модуль", "штуцер", "фанкойл", "сифон", "заслонка",
]
STOP = {"и", "с", "для", "на", "в", "из", "мм", "м", "шт", "тип", "мод", "модель", "серия", "или", "под"}

try:  # same lemmatiser the contract generator uses; a prefix stem is the fallback
    import pymorphy3
    _MORPH = pymorphy3.MorphAnalyzer()
except Exception:  # noqa: BLE001
    _MORPH = None


def lemma(word):
    if _MORPH is not None and re.search("[а-я]", word):
        return _MORPH.parse(word)[0].normal_form.replace("ё", "е")
    return word[:6]


def _normalise(text):
    t = str(text or "").lower().replace("ё", "е")
    for word, digit in (("одно", "1"), ("двух", "2"), ("трех", "3"), ("четырех", "4"), ("пяти", "5")):
        t = re.sub(rf"\b{word}\s*-?\s*(?=щел)", digit + " ", t)   # двухщелевой → 2 щелевой
    t = re.sub(r"(?<=\d)[,](?=\d)", ".", t)                   # 6,35 → 6.35
    t = re.sub(r"(?<=\d)\s+(?=\d{3}\b)", "", t)               # 1 000 → 1000
    t = re.sub(r"(?<=\d)\s*[x×х*]\s*(?=\d)", " x ", t)        # 400×150, 400 х 150
    t = re.sub(r"[øф⌀]\s*(?=\d)", " ", t)                      # Ø125, ф125
    t = re.sub(r"\b[dl]\s*=?\s*(?=\d)", " ", t)                # L=1000, d125
    t = re.sub(r"(?<=\d)(?=[а-яa-z])|(?<=[а-яa-z])(?=\d)", " ", t)  # 2щ, 15мм
    return t


def numbers(text):
    """Sizes as a sorted tuple of distinct values; metres become millimetres with «м».

    TASK-20261124-05: sheet thickness (0,5 мм) is left out — catalog names rarely carry it;
    «Ø125–Ø125» equals «125» (a tee of one size); digits inside model codes are not sizes."""
    t = _normalise(_without_models(text))
    found = set()
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(мм|см|м\b)?", t):
        v = float(value)
        if unit == "м" and v < 20:
            v *= 1000
        elif unit == "см":
            v *= 10
        if v >= 2 or (v == 1 and "щел" in t):
            found.add(round(v, 2))
    return tuple(sorted(found))


MODEL = re.compile(r"\b(?=(?:[a-z0-9\-/]*[a-z]){2})(?=[a-z0-9\-/]*\d)[a-z0-9][a-z0-9\-/]{2,}\b")


def models(text):
    """Latin model codes with letters and digits: FXSQ20A, HS4-N, AESTH-40-B-2000-2."""
    return {m.strip("-/") for m in MODEL.findall(str(text or "").lower())}


def series(text):
    """Latin words without digits (brand, series): invisiline, aesth, smart, daikin."""
    return {w for w in re.findall(r"\b[a-z]{3,}\b", str(text or "").lower())}


def _without_models(text):
    return MODEL.sub(" ", str(text or "").lower())


def words(text):
    t = re.sub(r"[^a-zа-я ]", " ", _normalise(text))
    return {lemma(w) for w in t.split() if len(w) > 1 and w not in STOP}


def kind(text):
    t = re.sub(r"[^a-zа-я ]", " ", _normalise(text))
    for w in t.split():
        if len(w) > 1 and lemma(w) in KINDS:
            return lemma(w)
    return None


# Words that make two same-size items different products.
CONFLICTS = [("оцинк", "нерж", "черн", "пвх", "пластик", "алюмин", "медн"),
             ("кругл", "прямоуг", "овальн"), ("гибк", "жестк")]


def _stems(text):
    return {w[:5] for w in words(text)}


def _conflict(sa, sb):
    for group in CONFLICTS:
        ga = {g for g in group if any(w.startswith(g[:5]) for w in sa)}
        gb = {g for g in group if any(w.startswith(g[:5]) for w in sb)}
        if ga and gb and not ga & gb:
            return True
    return False


def similarity(a, b):
    """0..1 for two names of the same kind and the same sizes, else 0.

    Kind and sizes decide; the remaining words only grade the confidence (overlap of
    5-letter stems, so «оцинк.» = «оцинкованный»), unless they name a different
    material or shape («оцинкованный» vs «нержавеющий», «круглый» vs «прямоугольный»)."""
    ka, kb = kind(a), kind(b)
    if not ka or ka != kb:
        return 0.0
    if numbers(a) != numbers(b):
        return 0.0
    sa, sb = _stems(a), _stems(b)
    if _conflict(sa, sb):
        return 0.0
    # Model codes and series decide when both names carry them: FXSQ20A ≠ FXAQ20A, SMART ≠ AESTH.
    ma, mb = models(a), models(b)
    if ma and mb and not ma & mb:
        return 0.0
    xa, xb = series(a), series(b)
    if (xa or xb) and not ma & mb and (not (xa and xb) or ((xa - xb) and (xb - xa))):
        # A branded item (AirGlass, Invisiline) never takes the price of a plain one (ДВК).
        return 0.0
    overlap = len(sa & sb) / min(len(sa), len(sb)) if sa and sb else 0.0
    return round(0.5 + 0.5 * overlap, 3)


MIN_SIMILARITY = 0.5   # same kind, same sizes, no conflicting material or shape


def load_history(offer_cache=OFFER_CACHE, registry=REGISTRY):
    """[{name, price, cost, source, ref, order}] from the Offer catalog and supplier invoices."""
    rows = []
    try:
        with open(offer_cache, encoding="utf-8") as f:
            offers = json.load(f).get("offers") or []
    except (OSError, ValueError):
        offers = []
    for o in offers:
        price, cost = _num(o.get("price")), _num(o.get("cost_material"))
        if price or cost:
            rows.append({"name": o.get("name") or "", "price": price, "cost": cost,
                         "source": "сделки", "ref": f"номенклатура {o.get('id')}", "order": int(o.get("id") or 0)})
    try:
        with open(registry, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    for inv in data.get("invoices") or []:
        label = " ".join(str(x) for x in (inv.get("supplier"), "счёт", inv.get("number"), inv.get("date")) if x)
        lines = list(inv.get("lines") or [])
        if not lines:
            lines = [line for a in inv.get("allocations") or [] for line in a.get("source_lines") or []]
        for line in lines:
            name = line.get("name") or line.get("source_name")
            qty = _num(line.get("qty") or line.get("source_qty") or line.get("source_qty_used") or line.get("qty_used"))
            amount = (_num(line.get("amount_cents")) or 0) / 100 or _num(line.get("amount") or line.get("amount_used"))
            if name and qty and amount:
                rows.append({"name": name, "price": None, "cost": round(amount / qty, 2),
                             "source": "счёт поставщика", "ref": label, "order": 0})
    return rows


def _num(value):
    try:
        v = float(str(value).replace(" ", "").replace(",", "."))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def markups(history):
    """Median sale/purchase ratio per kind, from rows that carry both."""
    by_kind = {}
    for r in history:
        if r["price"] and r["cost"] and r["cost"] < r["price"] < r["cost"] * 5:
            by_kind.setdefault(kind(r["name"]), []).append(r["price"] / r["cost"])
    return {k: round(statistics.median(v), 3) for k, v in by_kind.items() if k and len(v) >= 3}


def best_match(name, history):
    """The closest history row of the same kind and sizes; ties go to the newest."""
    scored = [(similarity(name, r["name"]), r) for r in history]
    scored = [(s, r) for s, r in scored if s >= MIN_SIMILARITY]
    if not scored:
        return None
    # A sale price beats a bare purchase price; then similarity; then the newest entry.
    scored.sort(key=lambda sr: (sr[1]["price"] is not None, sr[0], sr[1]["order"]), reverse=True)
    score, row = scored[0]
    return {**row, "score": score}


def price_from_history(name, history, ratios=None):
    """(sell, cost, mark) or None. A purchase-only match is sold at the kind's usual markup."""
    match = best_match(name, history)
    if not match:
        return None
    word = "очень похоже" if match["score"] >= 0.8 else "похоже"
    if match["price"]:
        return (match["price"], match["cost"],
                f"проверить: цена из прошлых сделок ({word}: «{match['name']}», {match['ref']})")
    ratio = (ratios or {}).get(kind(name))
    if not ratio:
        return None
    return (round(match["cost"] * ratio, 2), match["cost"],
            f"проверить: закупка из {match['ref']} ({word}: «{match['name']}») × обычная наценка {ratio:g}")


def main():
    items = json.load(sys.stdin).get("items") or []
    history = load_history()
    ratios = markups(history)
    out = []
    for row in items:
        hit = price_from_history(str(row.get("name") or ""), history, ratios)
        out.append({"name": row.get("name"), "match": hit and {"sell": hit[0], "cost": hit[1], "mark": hit[2]}})
    print(json.dumps({"ok": True, "history_rows": len(history), "items": out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
