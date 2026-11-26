#!/usr/bin/env python3
"""Galvanised duct fittings priced by the area of metal (owner 24.11).

Fittings come in a million sizes, are cheap and tedious to quote. Our Вентрешения invoices
give real prices for many of them; each known fitting gives a price per m² of metal, and a
missing fitting gets area × that rate. The owner sells fittings at +200…250 %, so a few
per cent of geometry error is acceptable — every such price is marked «расчёт по площади».

Areas follow the usual sheet development (ВСН 353-86 tabulates elbows, straight runs and
caps; tees and transitions are developed the same way):
  duct          πD·L                  |  2(A+B)·L
  elbow α°      πD · R·α             |  2(A+B) · R·α        R = D (round), A/2+0.1 m (rect)
  transition    mean perimeter · L    (L = 0.3 m when the name gives none)
  tee           main D·(d+0.2) + branch d·(0.1 + D/2)  (each as its perimeter × length)
  nipple        πD · 0.1
  cap           end area + 30 mm rim
  saddle tap    πd·0.1 + (d+0.1)² plate
Sizes in mm in the name; the result is m².
"""
import math
import re
import statistics

# Calibrated 26.11 on the Вентрешения invoice ПКБ-00005189, which states each item's m² (area within 7 %):
DEFAULT_TRANSITION_M = 0.3        # rectangular ones; round-to-round are shorter:
ROUND_TRANSITION_M = 0.22
TRANSITION_COLLAR = 0.065         # flanges/collars: × the larger perimeter (rectangular transitions)
NIPPLE_M = 0.08
RIM_M = 0.03
ELBOW_ROUND_R = 1.8               # × D — centre-line radius of round elbows
ELBOW_RECT_R = 0.15               # + A/2 — rectangular elbows («р.ш.150»)
ELBOW_ENDS_ROUND = 0.05           # straight ends, m (both together)
ELBOW_ENDS_RECT = 0.10


def _sizes(name):
    """('rect', a, b) / ('round', d) groups in order of appearance, in metres."""
    text = re.sub(r"\([^()]*\)", " ", str(name or "").lower().replace("ё", "е"))
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    # «L=1250» is a length, «р.ш.150» a bend parameter, «исп.5» a version — none of them is a section.
    text = re.sub(r"\bl\s*=\s*\d+|р\.?\s*ш\.?\s*\d+|исп\.?\s*\d+", " ", text)
    groups = []
    for m in re.finditer(r"(\d{2,4})\s*[x×х*]\s*(\d{2,4})|(?:[øфd⌀]\s*)?(\d{2,4})(?!\s*[x×х*°])", text):
        if m.group(1):
            groups.append(("rect", int(m.group(1)) / 1000, int(m.group(2)) / 1000))
        elif m.group(3):
            value = int(m.group(3))
            if 60 <= value <= 2000:
                groups.append(("round", value / 1000))
    return groups


VR_HEAD = re.compile(r"^\s*([а-яё]+)\s*\(\s*(кр|пр|пркр|крпр|сп)\s*\)", re.I)
ANGLES = {15, 30, 45, 60, 90}


def parse_vr(name):
    """Вентрешения naming: «Отвод(Кр) - 90 - 125», «Переход(ПрКр) - 1 - 400x300 - 315 - 334 - 25x34»,
    «Переход(Кр) - 1 - 250x200 - 99 / 169 - 43x27», «Воздуховод(Пр) - 300x400 - 1250 (…)».
    Returns {kind, groups, angle, length} or None when the name is not in that format."""
    text = str(name or "")
    head = VR_HEAD.match(text)
    if not head:
        return None
    typ = head.group(2).lower()
    body = re.sub(r"\([^()]*\)", " ", text[head.end():]).replace("х", "x").replace("Х", "x").replace("×", "x")
    parts = [p.strip() for p in body.split(" - ") if p.strip()]
    nums = [p for p in parts]
    kind = kind_of(head.group(1))
    groups, angle, length = [], None, None
    for i, part in enumerate(nums):
        pair = re.fullmatch(r"(\d{2,4})\s*x\s*(\d{2,4})", part)
        single = re.fullmatch(r"(\d{1,4})", part)
        if pair:
            a, b = int(pair.group(1)) / 1000, int(pair.group(2)) / 1000
            if a < 0.05 and b < 0.05:
                continue                                   # offsets like 25x34
            if typ == "кр" and kind in ("переход", "тройник"):
                groups += [("round", a), ("round", b)]
            else:
                groups.append(("rect", a, b))
        elif single:
            v = int(single.group(1))
            if kind == "отвод" and angle is None and v in ANGLES and not groups:
                angle = v
            elif i == 0 and kind in ("переход", "тройник") and v < 10:
                continue                                   # variant number
            elif v >= 60 and (len(groups) < (2 if kind in ("переход", "тройник") else 1)):
                groups.append(("round", v / 1000))
            elif v >= 50 and length is None:
                length = v / 1000
        else:
            first = re.match(r"(\d{2,4})\s*/", part)       # «99 / 169» — lengths of an offset transition
            if first and length is None:
                length = int(first.group(1)) / 1000
    return {"kind": kind, "groups": groups, "angle": angle or 90, "length": length}


def _angle(name):
    m = re.search(r"(\d{2,3})\s*(?:°|гр|град)", str(name).lower())
    if m:
        return int(m.group(1))
    m = re.search(r"\b(15|30|45|60|90)\b", str(name))
    return int(m.group(1)) if m else 90


def _perimeter(g):
    return 2 * (g[1] + g[2]) if g[0] == "rect" else math.pi * g[1]


def _section_area(g):
    return g[1] * g[2] if g[0] == "rect" else math.pi * g[1] ** 2 / 4


def kind_of(name):
    t = str(name).lower().replace("ё", "е")
    for word, k in (("дроссел", "дроссель"), ("отвод", "отвод"), ("колено", "отвод"), ("переход", "переход"), ("тройник", "тройник"),
                    ("ниппель", "ниппель"), ("муфта", "ниппель"), ("заглушк", "заглушка"), ("врезк", "врезка"),
                    ("воздуховод", "воздуховод")):
        if word in t:
            return k
    return None


def _length(name):
    m = re.search(r"\bl\s*=\s*(\d{2,5})", str(name or "").lower())
    return int(m.group(1)) / 1000 if m else None


def area(name, length_m=None):
    """m² of metal for a fitting named like «Отвод 90° Ø125», «Переход 400×150–300×150»; None if unknown."""
    length_m = length_m or _length(name)
    vr = parse_vr(name)
    if vr:
        k, g, angle = vr["kind"], vr["groups"], vr["angle"]
        length_m = length_m or vr["length"]
    else:
        k, g, angle = kind_of(name), _sizes(name), _angle(name)
        if k == "отвод" and len(g) > 1 and g[0][0] == "round" and round(g[0][1] * 1000) in ANGLES:
            g = g[1:]                                      # «Отвод 90 - 125»: the 90 is the angle
    if not k or not g:
        return None
    first = g[0]
    if k == "воздуховод":
        return round(_perimeter(first) * (length_m or 1.0), 4)
    if k == "отвод":
        if first[0] == "round":
            radius, ends = first[1] * ELBOW_ROUND_R, ELBOW_ENDS_ROUND
        else:
            radius, ends = first[1] / 2 + ELBOW_RECT_R, ELBOW_ENDS_RECT
        return round(_perimeter(first) * (radius * math.radians(angle) + ends), 4)
    if k == "переход":
        second = g[1] if len(g) > 1 else first
        mean = (_perimeter(first) + _perimeter(second)) / 2
        if first[0] == "round" and second[0] == "round":
            return round(mean * (length_m or ROUND_TRANSITION_M), 4)
        return round(mean * (length_m or DEFAULT_TRANSITION_M)
                     + max(_perimeter(first), _perimeter(second)) * TRANSITION_COLLAR, 4)
    if k == "тройник":
        branch = g[1] if len(g) > 1 else first
        main_d, branch_d = _span(first), _span(branch)
        return round(_perimeter(first) * (branch_d + 0.2) + _perimeter(branch) * (0.1 + main_d / 2), 4)
    if k == "ниппель":
        return round(_perimeter(first) * NIPPLE_M, 4)
    if k == "заглушка":
        return round(_section_area(first) + _perimeter(first) * RIM_M, 4)
    if k == "дроссель":
        # 25.11 (deal 907): a damper is a short duct body (0.25 m) plus its blade (the section).
        return round(_perimeter(first) * 0.25 + _section_area(first), 4)
    if k == "врезка":
        d = _span(first)
        return round(_perimeter(first) * 0.1 + (d + 0.1) ** 2, 4)
    return None


def _span(g):
    return g[1] if g[0] == "round" else max(g[1], g[2])


def shape(name):
    vr = parse_vr(name)
    g = vr["groups"] if vr else _sizes(name)
    return g[0][0] if g else None


NEIGHBOURS = 3


def rates(rows, supplier_words=("вентреш",)):
    """Known fittings of the supplier: {(kind, shape): [(area, ₽/m², name), …]}.

    TASK-20261124-14: one median ₽/m² per kind under-priced small fittings by 72–80 % — a
    Ø125 elbow carries the same seams, flanges and handling as a big one. The rate is taken
    from the fittings of the nearest size instead (see price)."""
    found = {}
    for r in rows:
        ref = str(r.get("ref") or "").lower()
        if not r.get("cost") or not any(w in ref for w in supplier_words):
            continue
        k, a = kind_of(r["name"]), area(r["name"])
        if not k or not a:
            continue
        unit = str(r.get("unit") or "").lower().replace(" ", "")
        rate = r["cost"] if unit.startswith(("м2", "м²", "кв")) else r["cost"] / a   # a price per m² is the rate
        found.setdefault((k, shape(r["name"])), []).append((a, rate, r["name"]))
    return found


def nearest_rate(table, k, sh, a):
    """Median ₽/m² of the NEIGHBOURS known fittings closest in area: same kind and shape, else same kind
    any shape, else any fitting of that shape. Returns (rate, basis) or (None, '')."""
    for key, basis in (((k, sh), ""), ((k, "round" if sh == "rect" else "rect"), "по изделиям другой формы"),
                       (None, "по фасонке других видов")):
        # Ducts and fittings are priced differently per m²: the «any fitting» pool never mixes them.
        pool = table.get(key, []) if key else [x for (kk, _), v in table.items()
                                                if (kk == "воздуховод") == (k == "воздуховод") for x in v]
        if len(pool) >= NEIGHBOURS:
            near = sorted(pool, key=lambda x: abs(math.log(x[0] / a)))[:NEIGHBOURS]
            return statistics.median(r for _, r, _ in near), basis + (": " if basis else "") + ", ".join(n for _, _, n in near)
    return None, ""


def price(name, rate_table, markup=3.0):
    """(sell, cost, mark) by area for a fitting, else None. markup 3.0 = +200 %, 3.5 = +250 %."""
    k, a = kind_of(name), area(name)
    if not k or not a:
        return None
    rate, basis = nearest_rate(rate_table, k, shape(name), a)
    if not rate:
        return None
    cost = round(a * rate, 2)
    per = " за 1 м" if k == "воздуховод" else ""
    return (round(cost * markup, 2), cost,
            f"проверить: расчёт{per} по площади {a:g} м² × {rate:.0f} ₽/м² (ближайшие по размеру изделия Вентрешения — "
            f"{basis}) × наценка {round((markup - 1) * 100):g}%")
