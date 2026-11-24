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
    t = _normalise(_without_models(_without_brackets(text)))
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


def _without_brackets(text):
    """«Воздуховод(Пр) - 300x400 - 1250 (оц. ст. 0.50/100 - Шина R20х95О)» → sizes 300, 400, 1250 only."""
    return re.sub(r"\([^()]*\)", " ", str(text or ""))


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


RECT_PIECE_MM, ROUND_PIECE_MM = 1250, 3000   # owner 24.11: прямоугольные — штуки по 1250 мм, круглые — по 3 м или метрами


def rectangular(text):
    return bool(re.search(r"\d\s*[x×х*]\s*\d", _without_brackets(text))) or "прямоуг" in str(text).lower() or "(пр)" in str(text).lower()


def duct_length(query, name, unit=""):
    """A duct sold as a piece priced against a duct counted in metres: the piece length, else None.
    The length is read from the name (L=1250, «- 3000»); a piece without it is 1250 mm when
    rectangular and 3000 mm when round."""
    if kind(query) != "воздуховод" or kind(name) != "воздуховод":
        return None
    if str(unit).lower().startswith("шт") and set(numbers(name)) == set(numbers(query)):
        return RECT_PIECE_MM if rectangular(name) else ROUND_PIECE_MM
    extra = set(numbers(name)) - set(numbers(query))
    long = [n for n in extra if n >= 500]
    return long[0] if len(extra) == 1 and long and set(numbers(query)) <= set(numbers(name)) else None


def _duct_piece(a, b):
    return duct_length(a, b) is not None


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


SERVICE = re.compile(r"^\s*то\b|обслуживан|монтаж|демонтаж|пусконалад|диагностик|ремонт|работ[аы]?\b|услуг", re.I)


def is_service(text):
    return bool(SERVICE.search(str(text or "")))


def similarity(a, b):
    """0..1 for two names of the same kind and the same sizes, else 0.

    Kind and sizes decide; the remaining words only grade the confidence (overlap of
    5-letter stems, so «оцинк.» = «оцинкованный»), unless they name a different
    material or shape («оцинкованный» vs «нержавеющий», «круглый» vs «прямоугольный»)."""
    ka, kb = kind(a), kind(b)
    if not ka or ka != kb:
        return 0.0
    if is_service(a) != is_service(b):      # «ТО внешнего блока VRV» is not a VRV unit
        return 0.0
    if numbers(a) != numbers(b) and not _duct_piece(a, b):
        return 0.0
    sa, sb = _stems(a), _stems(b)
    if _conflict(sa, sb):
        return 0.0
    # Model codes and series decide when both names carry them: FXSQ20A ≠ FXAQ20A, SMART ≠ AESTH.
    ma, mb = models(a), models(b)
    if ma and not ma & mb:
        # 24.11 (deal 907): «блок Daikin FXSQ20A» took the price of a whole VRV outdoor set
        # that named no model. A named model is matched only by the same model.
        return 0.0
    xa, xb = series(a), series(b)
    if (xa or xb) and not ma & mb and (not (xa and xb) or ((xa - xb) and (xb - xa))):
        # A branded item (AirGlass, Invisiline) never takes the price of a plain one (ДВК).
        return 0.0
    overlap = len(sa & sb) / min(len(sa), len(sb)) if sa and sb else 0.0
    return round(0.5 + 0.5 * overlap, 3)


MIN_SIMILARITY = 0.5   # same kind, same sizes, no conflicting material or shape


def cbr_rate(code):
    """Roubles per unit of a currency today (CBR); None when unknown — such rows are skipped."""
    try:
        import datetime
        import currency_planning
        return float(currency_planning.fetch_cbr_rate(code, datetime.date.today())["rate"])
    except Exception:  # noqa: BLE001
        return None


def _rub(value, currency, rate):
    """24.11 (deal 907): a USD/EUR catalog price must never be read as roubles."""
    code = str(currency or "RUB").upper()
    if value is None or code == "RUB":
        return value
    factor = rate(code)
    return round(value * factor, 2) if factor else None


def load_history(offer_cache=OFFER_CACHE, registry=REGISTRY, document_index=None, rate=cbr_rate):
    """[{name, price, cost, source, ref, order}] from the Offer catalog and supplier invoices."""
    rows = []
    rates, fetch = {}, rate

    def rate_cached(code):
        if code not in rates:
            rates[code] = fetch(code)
        return rates[code]
    rate = rate_cached
    try:
        with open(offer_cache, encoding="utf-8") as f:
            offers = json.load(f).get("offers") or []
    except (OSError, ValueError):
        offers = []
    for o in offers:
        price = _rub(_num(o.get("price")), o.get("price_currency"), rate)
        cost = _rub(_num(o.get("cost_material")), o.get("cost_currency"), rate)
        if price or cost:
            note = "" if str(o.get("price_currency") or "RUB").upper() == "RUB" else \
                f", цена в {o.get('price_currency')} пересчитана по курсу ЦБ"
            rows.append({"name": o.get("name") or "", "price": price, "cost": cost,
                         "source": "сделки", "ref": f"номенклатура {o.get('id')}{note}", "order": int(o.get("id") or 0)})
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
                             "source": "счёт поставщика", "ref": label, "order": 0,
                             "unit": line.get("unit") or line.get("source_unit") or ""})
    try:  # owner 24.11: the invoices themselves (PDF/XLSX text), not only what finance allocated
        import invoice_lines
        rows.extend(invoice_lines.history_rows(document_index))
    except Exception:  # noqa: BLE001 — a bonus source; the catalog still answers without it
        pass
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
    result = {k: round(statistics.median(v), 3) for k, v in by_kind.items() if k and len(v) >= 3}
    # TASK-20261124-06: отвод/переход/ниппель had purchase prices but no own markup. Fittings
    # share one markup; anything else falls back to the median over all our sales.
    for group in GROUPS:
        values = [r for k, v in by_kind.items() if k in group for r in v]
        if len(values) >= 3:
            result.setdefault("группа:" + group[0], round(statistics.median(values), 3))
    every = [r for v in by_kind.values() for r in v]
    if len(every) >= 10:
        result["все"] = round(statistics.median(every), 3)
    return result


GROUPS = [("воздуховод", "отвод", "переход", "тройник", "ниппель", "муфта", "заглушка", "врезка", "колено",
           "утка", "адаптер", "дроссель", "клапан", "фланец", "шина", "уголок"),
          ("диффузор", "решетка", "анемостат")]


def ratio_for(name, ratios):
    k = kind(name)
    if not ratios:
        return None, ""
    if k in ratios:
        return ratios[k], "обычная наценка на этот вид"
    for group in GROUPS:
        if k in group and "группа:" + group[0] in ratios:
            return ratios["группа:" + group[0]], "обычная наценка на вентиляционные изделия"
    if "все" in ratios:
        return ratios["все"], "наша средняя наценка"
    return None, ""


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


def section(text):
    """(a, b) in mm of a rectangular section «400×150», else None."""
    m = re.search(r"(\d{2,4})\s*[x×х*]\s*(\d{2,4})", _without_brackets(text).lower())
    return (int(m.group(1)), int(m.group(2))) if m else None


def rect_duct_estimate(name, history, ratios=None):
    """A rectangular duct size we never bought: price per metre ∝ perimeter of the section,
    from our earlier rectangular ducts (sale prices first, else purchase × markup)."""
    if kind(name) != "воздуховод" or not section(name) or is_service(name):
        return None
    a, b = section(name)
    _, sb = _stems(name), None
    sell_rates, cost_rates = [], []
    for r in history:
        if kind(r["name"]) != "воздуховод" or is_service(r["name"]) or not section(r["name"]):
            continue
        if _conflict(_stems(name), _stems(r["name"])):
            continue
        ra, rb = section(r["name"])
        extra = [n for n in numbers(r["name"]) if n >= 500 and n not in (ra, rb)]
        unit = str(r.get("unit") or "").lower()
        length = extra[0] if extra else (RECT_PIECE_MM if unit.startswith("шт") or r["source"] == "сделки" else 1000)
        perimeter = 2 * (ra + rb) / 1000
        if r["price"]:
            sell_rates.append(r["price"] * 1000 / length / perimeter)
        if r["cost"]:
            cost_rates.append(r["cost"] * 1000 / length / perimeter)
    perimeter = 2 * (a + b) / 1000
    if len(sell_rates) >= 3:
        rate = statistics.median(sell_rates)
        cost = round(statistics.median(cost_rates) * perimeter, 2) if len(cost_rates) >= 3 else None
        return (round(rate * perimeter, 2), cost,
                f"проверить: расчёт за 1 м по периметру сечения из {len(sell_rates)} прошлых продаж прямоугольных воздуховодов")
    ratio, why = ratio_for(name, ratios)
    if len(cost_rates) >= 3 and ratio:
        cost = round(statistics.median(cost_rates) * perimeter, 2)
        return (round(cost * ratio, 2), cost,
                f"проверить: расчёт за 1 м по периметру сечения из {len(cost_rates)} прошлых закупок × {why} {ratio:g}")
    return None


def price_from_history(name, history, ratios=None):
    """(sell, cost, mark) or None. A purchase-only match is sold at the kind's usual markup."""
    match = best_match(name, history)
    if not match:
        return rect_duct_estimate(name, history, ratios)
    word = "очень похоже" if match["score"] >= 0.8 else "похоже"
    length = duct_length(name, match["name"], match.get("unit", ""))
    if length:
        per_metre = 1000.0 / length
        match = {**match, "price": match["price"] and round(match["price"] * per_metre, 2),
                 "cost": match["cost"] and round(match["cost"] * per_metre, 2),
                 "ref": f"{match['ref']}, пересчитано за 1 м из штуки L={length:g} мм"}
    if match["price"] and not match["cost"]:
        bought = best_match(name, [r for r in history if r["cost"] and not r["price"]])
        if bought:
            length = duct_length(name, bought["name"], bought.get("unit", ""))
            factor = 1000.0 / length if length else 1.0
            match = {**match, "cost": round(bought["cost"] * factor, 2),
                     "ref": f"{match['ref']}; закупка — {bought['ref']}"}
    if match["price"]:
        return (match["price"], match["cost"],
                f"проверить: цена из прошлых сделок ({word}: «{match['name']}», {match['ref']})")
    ratio, why = ratio_for(name, ratios)
    if not ratio:
        return None
    return (round(match["cost"] * ratio, 2), match["cost"],
            f"проверить: закупка из {match['ref']} ({word}: «{match['name']}») × {why} {ratio:g}")


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
