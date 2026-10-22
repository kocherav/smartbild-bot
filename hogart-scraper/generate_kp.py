#!/usr/bin/env python3
"""
Generate a Cliwell-letterhead commercial proposal (KP) PDF from a JSON spec.
(This script only ever produces AC-equipment KPs - owner's rule as of 2026-08-21: all
air-conditioner KPs go on Cliwell's letterhead now, not SmartBild's. Everything else
about this script - pricing, install/freon-line logic, signature block - is unchanged.)

Usage: generate_kp.py <spec.json>

Spec format (single configuration, the common case):
{
  "client": "Алёна Бородина",
  "date": "19.08.2026",
  "intro": "Предлагаю на Ваше рассмотрение ...",     (optional, has a default)
  "discount_pct": 5,
  "include_install": true,                          (optional, default false - adds a
                                                       "Стандартный монтаж" line per item)
  "items": [
    {"sku": "AS25S2SF3FA-B/1U25S2SM4FA", "source": "hogart",   (optional, default "hogart")
     "label": "Кондиционер Haier Flexis Super Match, 2,5 кВт",
     "qty": 2, "photo_url": "https://.../optional-high-res.webp",
     "line_length_m": 5},                           (optional - adds a "Дополнительная
                                                       фреоновая магистраль" line, this many
                                                       total meters, for this item)
    {"sku": "4b3d2e17-7073-11f1-af4c-345a601bbc1f", "source": "daichi",
     "label": "Ecoletta ECO07AN/LETTA07AN, 2,5 кВт", "qty": 1}
    ...
  ],
  "output": "/home/kocher.av/hogart-scraper/output/КП_....pdf"
}

Multi-variant spec (2026-08-26, owner's ask: "3 разных варианта... в одном файле, но
экономика 3 раза отдельно, не суммируя") - top-level "items" replaced by "variants", each
an independent alternative with its OWN price table/total/economics (never summed across
variants - these are options the client picks ONE of, not one combined order):
{
  "client": "...", "date": "...", "intro": "...",
  "discount_pct": 5, "include_install": true,        (still usable as the DEFAULT for any
                                                        variant that doesn't override them)
  "variants": [
    {"label": "Вариант 1: Haier Quantum Inverter", "items": [...]},
    {"label": "Вариант 2: Daichi Ecoletta", "items": [...], "discount_pct": 0},
    {"label": "Вариант 3: ...", "items": [...]}
  ],
  "output": "..."
}
Each variant renders as its own labeled section (price table + subtotal + specs gallery),
starting on a fresh page when there's more than one - never merged into a single grand
total. The economics .xlsx gets one table per variant the same way, see xlsx_report.py.
A bare top-level "items" (no "variants") is treated as exactly one unlabeled variant -
output is pixel-identical to the pre-2026-08-26 single-configuration format.

Two supplier sources per item (2026-08-26), same install/freon-line pricing logic -
`source: "hogart"` (default, `sku` = Hogart's `article`) or `source: "daichi"` (`sku` =
Daichi's `xml_id`, as returned by daichi_search.py / DAICHI_SEARCH). Mixing both sources
within one variant, or using different sources across variants, is expected and fine -
see daichi_lookup()/live_lookup() below for the per-source normalization into a common
shape.

Install price and freon-line price/cost are computed from pipe_reference.py (fixed tiers
by the equipment's own peak cooling capacity in kW, and a Kemix-priced material formula
respectively - see that module's docstring). Neither is affected by discount_pct - that
discount only applies to the equipment's own price. Capacity is read from each item's
own "Холодопроизводительность" feature - normalized the same way for both sources, so
this logic runs unchanged regardless of supplier.

For a Hogart item, live price/stock is fetched by querying the Hogart API and matching
the sku exactly (never trusts a price the caller supplies — always re-derives from the
live API so numbers can't drift or be hallucinated upstream). For a Daichi item, price/
stock/specs come from daichi_catalog_cache.py's cache (refreshed at most every 12h - see
that module for why a live per-item call isn't used here) - `sell_price` (МПРЦ) is the
real retail price, `cost_price` (the API's own `BASE`/"Розничная цена" field, mislabeled -
see project memory) is what WE pay Daichi, never the other way around.

Availability is deliberately collapsed to two states only (owner's rule):
"В наличии" if live stock is a plain number >= qty, else "Под заказ" for anything
else (numeric-but-insufficient, "Под заказ", "Уточняйте у нас", missing, etc).

Prints a JSON summary to stdout as the last line:
{"ok": true, "path": ..., "economics_xlsx_path": ..., "client": ...,
 "variants": [{"label": ..., "total": ..., "items": [...], "economics": {...}}, ...]}
or {"ok": false, "error": "..."}.
"""
import html
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "daichi-scraper"))
from hogart_api import HogartAPI, HogartAPIError, image_url as hogart_image_url
from pipe_reference import (
    install_price_for_capacity, freon_line_price_per_meter, parse_cooling_capacity_kw,
)
from daichi_api import DaichiAPI
import daichi_catalog_cache

HOGART_DIR = os.path.dirname(os.path.abspath(__file__))
# 2-page letterhead: page 0 = first-page chrome (44mm logo, blue rule, 3-column
# requisites footer), page 1 = continuation-page chrome (30mm logo, gray rule, single-
# line footer) - reused for every content page beyond the first. Built 2026-08-21 from
# the owner's new Cliwell 2026 design (blank-a4-2026.html/.docx, which is a *filled*
# mockup, not a blank background - the header/footer chrome was extracted from it into
# a proper empty-middle 2-page PDF; see project_hogart_scraper.md for how).
WORKSPACE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LETTERHEAD = os.path.join(WORKSPACE_PARENT, "sites/cliwell/pack/04-print/blank-a4-2026-letterhead.pdf")
WEASYPRINT_PY = os.path.join(WORKSPACE_PARENT, ".report-venv/bin/python3")
DEFAULT_INTRO = (
    "Предлагаю на Ваше рассмотрение коммерческое предложение от компании "
    "«Cliwell» на поставку и монтаж климатического оборудования."
)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
# Owner's rule (2026-08-22): "Монтажные работы" cost = 90% of its own KP price (10%
# margin on labour) - not tied to any real supplier invoice, just a flat ratio.
INSTALL_COST_RATIO = 0.9


def die(msg):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(1)


_hogart_api = None


def get_hogart_api():
    global _hogart_api
    if _hogart_api is None:
        _hogart_api = HogartAPI()
    return _hogart_api


def live_lookup(sku):
    """Query the official Hogart API for this exact article. Returns the raw product dict, or None."""
    try:
        items = get_hogart_api().search_products(keyword=sku)
    except HogartAPIError:
        return None
    for it in items:
        if it.get("article", "").strip() == sku.strip():
            return it
    return None


_daichi_catalog = None


def get_daichi_catalog():
    """Loaded from daichi_catalog_cache.py's cache (refreshed at most every 12h) - not a
    fresh live call per item like Hogart's live_lookup, since a single item there is a
    slow full-catalog-page-through operation (see that module's docstring). AC prices/
    stock don't move minute-to-minute, so the cache's staleness window is an acceptable
    tradeoff here, same as offer_catalog_cache.py's reasoning for Megaplan's catalog."""
    global _daichi_catalog
    if _daichi_catalog is None:
        _daichi_catalog = daichi_catalog_cache.load_or_refresh(DaichiAPI())
    return _daichi_catalog


def daichi_lookup(xml_id_or_id):
    """Find a Daichi item by xml_id (preferred - what daichi_search.py hands back) or
    bare numeric id, in the cached catalog. Returns the cache record or None."""
    for item in get_daichi_catalog().values():
        if item.get("xml_id") == xml_id_or_id or item.get("id") == xml_id_or_id:
            return item
    return None


def full_price_of(product):
    # defaultPrice is the undiscounted ("без скидки") price; always re-derived here, never
    # trusted from the caller.
    val = product.get("defaultPrice")
    return float(val) if val is not None else None


def contract_price_of(product):
    # contractPrice is SmartBild's own purchase/cost price - never shown in a KP, only
    # used here for the internal economics/profit summary. Often None (not every Hogart
    # SKU has a contract price set on this account - see the pipe/insulation accessory
    # SKUs used by pipe_reference.py, which don't).
    val = product.get("contractPrice")
    return float(val) if val is not None else None


def get_features(product):
    """Best-effort fetch of the full product detail (which has `features[]` - the list
    endpoint used by live_lookup() doesn't include it) for the technical-specs table.
    Never fails the whole KP if this one extra call breaks - just means no specs table
    for that item."""
    try:
        detail = get_hogart_api().get_product(product["id"])
    except HogartAPIError:
        return []
    return detail.get("features") or []


def total_stock(product):
    total = 0
    for s in product.get("stocks") or []:
        if s.get("inStock") and not s.get("isVirtual") and isinstance(s.get("amount"), (int, float)):
            total += s["amount"]
    return total


def availability_label(stock_n, qty):
    ok = stock_n >= qty
    return ("В наличии" if ok else "Под заказ"), ok


def _is_safe_public_host(hostname):
    """Basic SSRF guard: resolve the host and refuse anything private/loopback/link-local."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def download_image(url, item_sku_hint):
    """Download a product photo from anywhere on the public web (Claude found it via
    WebSearch), with basic safety: https only, must resolve to a public IP, and the
    response must actually be an image."""
    if not url or not url.startswith("https://"):
        return None
    host = urlparse(url).hostname
    if not host or not _is_safe_public_host(host):
        print(f"refusing to download image from unsafe host: {url}", file=sys.stderr)
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if not ctype.startswith("image/"):
                print(f"refusing non-image content-type {ctype!r} for {url}", file=sys.stderr)
                return None
            data = resp.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            return None
        ext = os.path.splitext(urlparse(url).path)[1][:5] or ".jpg"
        fd, path = tempfile.mkstemp(suffix=ext, prefix="kp-img-")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        print(f"failed to download {url}: {e}", file=sys.stderr)
        return None


def num_ru(n):
    return f"{n:,.2f}".replace(",", " ").replace(".", ",")


def num_qty(n):
    return str(int(n)) if float(n).is_integer() else num_ru(n)


def simple_row(label, unit, qty, unit_price):
    """A price-table row with no availability sub-row - for service/material line items
    (install, freon line) that aren't a stocked Hogart SKU."""
    line_total = round(unit_price * qty, 2)
    return f"""<tr>
  <td>{html.escape(label)}</td>
  <td>{unit}</td>
  <td>{num_qty(qty)}</td>
  <td class="num">{num_ru(unit_price)} руб.</td>
  <td class="num">{num_ru(line_total)} руб.</td>
</tr>""", line_total


def write_economics_xlsx(path, client, variant_results):
    """Per-variant price/cost/profit breakdown as a real .xlsx (owner's request,
    2026-08-22, extended 2026-08-26 for multiple independent variants in one file).
    Delegates to xlsx_report.py under ~/.report-venv (openpyxl isn't installed for the
    system python3 that runs this script, and it's Debian's externally-managed one -
    same reason WeasyPrint/pypdf are already invoked as subprocesses below). Spec goes
    via stdin, never argv (ARG_MAX)."""
    spec = {
        "path": path, "client": client,
        "variants": [
            {"label": v["label"], "summary_items": v["summary_items"], "economics": v["economics"]}
            for v in variant_results
        ],
    }
    r = subprocess.run(
        [WEASYPRINT_PY, os.path.join(HOGART_DIR, "xlsx_report.py")],
        input=json.dumps(spec, ensure_ascii=False),
        capture_output=True, text=True, timeout=30,
    )
    try:
        result = json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception:
        result = {"ok": False}
    if r.returncode != 0 or not result.get("ok"):
        die(f"xlsx report generation failed: {(r.stderr or r.stdout)[-800:]}")


def prepare_multisplit(items_spec, include_install):
    """Price installation per indoor connection, never again on the common outdoor unit.

    A total additional length on the common outdoor unit is a system total. In a
    preliminary quote it is apportioned evenly per indoor unit, explicitly labelled.
    Multiple outdoor systems require an explicit branch allocation, not guessing.
    """
    items = [dict(x) for x in items_spec]
    for item in items:
        item.pop("_multi_role", None); item.pop("_line_allocation_note", None)
    products = {}
    outdoor, indoor = [], []
    for it in items:
        if it.get("source", "hogart") != "hogart":
            continue
        sku = it["sku"]
        if sku not in products:
            products[sku] = live_lookup(sku)
        product = products[sku]
        if not product:
            continue  # existing exact-SKU error below
        section = product.get("section") or {}
        kind = str(section.get("name", "")).lower()
        if "мульти" in kind and "наруж" in kind:
            it["_multi_role"] = "outdoor"; outdoor.append(it)
        elif "мульти" in kind and "внутр" in kind:
            it["_multi_role"] = "indoor"; indoor.append(it)
    if not outdoor:
        return items, products
    if (include_install or any(float(x.get("line_length_m") or 0) for x in outdoor)) and not indoor:
        raise ValueError("Для монтажа мультисплита нужны модели и количество внутренних блоков; один наружный блок не определяет стоимость монтажа.")
    if indoor and include_install and sum(int(x.get("qty", 1)) for x in outdoor) != 1:
        raise ValueError("В КП несколько наружных блоков: укажите распределение внутренних блоков по системам для расчёта монтажа.")
    shared = sum(float(x.get("line_length_m") or 0) for x in outdoor)
    if shared:
        if len(outdoor) != 1 or int(outdoor[0].get("qty", 1)) != 1:
            raise ValueError("Для нескольких мультисплитов требуется распределение общей длины трассы по системам.")
        if any(float(x.get("line_length_m") or 0) for x in indoor):
            raise ValueError("Длина трассы указана одновременно на наружном и внутренних блоках. Укажите общий метраж один раз либо только метраж каждой ветки.")
        count = sum(int(x.get("qty", 1)) for x in indoor)
        if count <= 0 or shared < 0:
            raise ValueError("Количество блоков и длина трассы должны быть положительными.")
        remainder = shared
        for i, it in enumerate(indoor):
            meters = round(shared * int(it.get("qty", 1)) / count, 6) if i < len(indoor)-1 else remainder
            it["line_length_m"] = meters; remainder -= meters
            it["_line_allocation_note"] = f"Дополнительная трасса {num_qty(shared)} м суммарно по системе; для расчёта распределена поровну между {count} внутренними блоками. Фактические длины веток уточняются при монтаже."
        outdoor[0]["line_length_m"] = 0
    return items, products


def render_variant(items_spec, discount_pct, include_install):
    """Process one variant's item list into everything needed to render it (price-table
    rows, specs gallery, per-line summary records, subtotal, cost, unknown-cost SKUs).
    Fully independent of any other variant - never accumulates into a shared/global
    total, that's the whole point of the 2026-08-26 multi-variant feature."""
    if not items_spec:
        die("a variant has no items")

    rows_html = []
    gallery_html = []
    summary_items = []
    items_spec, prepared_products = prepare_multisplit(items_spec, include_install)
    total = 0.0
    cost_total = 0.0
    cost_unknown_skus = []

    for it in items_spec:
        source = it.get("source", "hogart")
        qty = int(it.get("qty", 1))

        # Arbitrary work/material rows supplied by the user or copied from a deal.
        # They are first-class KP lines and are intentionally not affected by the
        # equipment discount percentage.
        if source in ("manual", "service"):
            label = str(it.get("label") or it.get("name") or "Работы")
            unit = str(it.get("unit") or "шт.")
            unit_price = round(float(it.get("unit_price") or 0), 2)
            line_total = round(unit_price * qty, 2)
            cost_unit = it.get("cost_price")
            cost_line = (round(float(cost_unit) * qty, 2) if cost_unit is not None
                         else (round(float(it["cost_total"]), 2) if it.get("cost_total") is not None else None))
            row, _ = simple_row(label, unit, qty, unit_price)
            rows_html.append(row)
            total += line_total
            if cost_line is None:
                cost_unknown_skus.append(label)
            else:
                cost_total += cost_line
            summary_items.append({
                "type": "service", "label": label, "unit": unit, "qty": qty,
                "unit_price": unit_price, "line_total": line_total, "cost_total": cost_line,
            })
            continue

        sku = it["sku"]

        if source == "hogart":
            live = prepared_products.get(sku)
            if not live:
                die(f"could not find live Hogart data for sku {sku!r}")
            full_price = full_price_of(live)
            if full_price is None:
                die(f"could not read price for Hogart sku {sku!r}")
            equipment_cost = contract_price_of(live)
            stock_n = total_stock(live)
            features = get_features(live)
            display_code = sku
            default_photo_url = hogart_image_url(live, "750")
        elif source == "daichi":
            # `sku` here is a Daichi xml_id (or bare id) - what daichi_search.py hands
            # back, see daichi_catalog_cache.py. Prices are already normalized there:
            # sell_price = mprc (real retail), cost_price = BASE (our cost) - the API's
            # own field NAME calls BASE "Розничная цена" but that's backwards from real
            # usage (owner correction, 2026-08-26) - never re-derive from raw PRICES here.
            live = daichi_lookup(sku)
            if not live:
                die(f"could not find Daichi item for xml_id {sku!r}")
            full_price = live.get("sell_price")
            if full_price is None:
                die(f"no retail price (mprc) for Daichi item {sku!r}")
            equipment_cost = live.get("cost_price")
            stock_n = live.get("stock_total") or 0
            features = [dict(v) for v in (live.get("specs") or {}).values()]
            display_code = live.get("name") or sku
            default_photo_url = live.get("photo_url")
        else:
            die(f"unknown source {source!r} for item {sku!r} - must be 'hogart' or 'daichi'")

        label = it.get("label", display_code)

        unit_price = round(full_price * (1 - discount_pct / 100), 2)
        line_total = round(unit_price * qty, 2)
        total += line_total

        if equipment_cost is not None:
            cost_total += equipment_cost * qty
        else:
            cost_unknown_skus.append(sku)

        avail_label, in_stock = availability_label(stock_n, qty)

        rows_html.append(f"""<tr>
  <td>{label} ({display_code})</td>
  <td>шт.</td>
  <td>{qty}</td>
  <td class="num">{num_ru(unit_price)} руб.</td>
  <td class="num">{num_ru(line_total)} руб.</td>
</tr>
<tr>
  <td colspan="5" class="avail-row"><span class="{'avail-ok' if in_stock else 'avail-wait'}">{avail_label}</span></td>
</tr>""")

        capacity_kw = parse_cooling_capacity_kw(features)

        install_price = None
        if include_install and it.get("_multi_role") != "outdoor":
            if capacity_kw is None:
                die(f"could not determine cooling capacity for {sku!r} - can't price the install line")
            try:
                install_price = install_price_for_capacity(capacity_kw)
            except ValueError as exc:
                raise ValueError(f"Для {sku} (верхняя мощность {capacity_kw} кВт) не задан тариф монтажа. Нужна цена монтажа этой позиции; состав КП сохранён.") from exc
            install_row, install_total = simple_row(
                (f"Монтаж подключения внутреннего блока мультисплита, до {num_qty(capacity_kw)} кВт" if it.get("_multi_role")=="indoor" else f"Стандартный монтаж кондиционера, {num_qty(capacity_kw)} кВт"), "шт.", qty, install_price,
            )
            rows_html.append(install_row)
            total += install_total
            # Owner's rule (2026-08-22): cost of the install line = 90% of its own KP
            # price (10% margin on labour itself), not tracked against any real supplier
            # cost - it's a flat ratio of what's charged.
            install_cost_total = round(install_total * INSTALL_COST_RATIO, 2)
            cost_total += install_cost_total

        if it.get("_line_allocation_note") and not any(it["_line_allocation_note"] in row for row in rows_html):
            rows_html.append('<tr><td colspan="5" class="avail-row">'+html.escape(it["_line_allocation_note"])+'</td></tr>')
        line_length_m = float(it.get("line_length_m") or 0)
        freon = None
        if line_length_m > 0:
            if capacity_kw is None:
                die(f"could not determine cooling capacity for {sku!r} - can't price the freon line")
            freon = freon_line_price_per_meter(capacity_kw)
            freon_row, freon_total = simple_row(
                "Дополнительная фреоновая магистраль", "м.", line_length_m, freon["sell_price_per_m"],
            )
            rows_html.append(freon_row)
            total += freon_total
            freon_cost_total = round(freon["cost_basis_per_m"] * line_length_m, 2)
            cost_total += freon_cost_total

        # "sku"/"for_sku" here use display_code, not the raw `sku` variable - for Daichi
        # items `sku` is the xml_id (a UUID, meaningless in a report), display_code is
        # the readable model code ("ECO07AN/LETTA07AN"); for Hogart the two are the same
        # (sku already IS the readable article), so this is a no-op change there.
        summary_items.append({
            "type": "equipment", "sku": display_code, "qty": qty, "unit_price": unit_price,
            "line_total": line_total, "availability": avail_label,
            "capacity_kw": capacity_kw,
            "cost_total": round(equipment_cost * qty, 2) if equipment_cost is not None else None,
        })
        if install_price is not None:
            summary_items.append({
                "type": "install", "for_sku": display_code, "capacity_kw": capacity_kw,
                "qty": qty, "unit_price": install_price, "line_total": install_total,
                "cost_total": install_cost_total,
            })
        if freon is not None:
            summary_items.append({
                "type": "freon_line", "for_sku": display_code, "length_m": line_length_m,
                "unit_price_per_m": freon["sell_price_per_m"], "line_total": freon_total,
                "cost_total": freon_cost_total, "allocation_note": it.get("_line_allocation_note", ""),
            })

        photo_url = it.get("photo_url") or default_photo_url
        local_photo = download_image(photo_url, sku)
        photo_html = (
            f'<img src="{local_photo}">' if local_photo
            else '<div class="no-photo">Фото недоступно</div>'
        )

        if features:
            spec_rows = "".join(
                f"<tr><td>{html.escape(f.get('name') or '')}</td>"
                f"<td>{html.escape(str(f.get('value') or ''))}"
                f"{' ' + html.escape(f['unit']) if f.get('unit') else ''}</td></tr>"
                for f in features
            )
            specs_html = f'<table class="specs">{spec_rows}</table>'
        else:
            specs_html = '<div class="no-specs">Характеристики не переданы поставщиком</div>'

        gallery_html.append(f"""<div class="specs-row">
  <div class="specs-photo">
    {photo_html}
    <div class="caption">{label}<br>{display_code}</div>
  </div>
  <div class="specs-table-wrap">{specs_html}</div>
</div>""")

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'megaplan-crm'))
    from document_tax_policy import company_rate, vat, tax_label
    tax_rate=company_rate('cliwell')
    output_vat=float(vat(total,tax_rate)) if tax_rate is not None else 0
    revenue=total-output_vat
    profit = revenue - cost_total
    economics = {
        "gross_revenue": round(total,2), "output_vat": round(output_vat,2),
        "revenue": round(revenue, 2),
        "cost": round(cost_total, 2),
        "profit": round(profit, 2),
        "margin_pct": round(profit / revenue * 100, 2) if revenue else None,
        "cost_fully_known": not cost_unknown_skus,
        "cost_unknown_skus": cost_unknown_skus,
    }

    return {
        "rows_html": rows_html, "gallery_html": gallery_html,
        "summary_items": summary_items, "total": total, "economics": economics,
        "tax_note": tax_label(total,tax_rate) if tax_rate is not None else "",
    }


def build(spec):
    client = spec.get("client", "[Имя клиента]")
    date = spec.get("date", "19.08.2026")
    intro = spec.get("intro") or DEFAULT_INTRO
    default_discount_pct = float(spec.get("discount_pct", 0))
    default_include_install = bool(spec.get("include_install", False))

    variants_spec = spec.get("variants")
    if variants_spec:
        labeled = True
    else:
        items_spec = spec.get("items", [])
        if not items_spec:
            die("no items in spec")
        variants_spec = [{"label": None, "items": items_spec}]
        labeled = False

    variant_results = []
    for i, v in enumerate(variants_spec):
        label = v.get("label") or (f"Вариант {i + 1}" if labeled else None)
        discount_pct = float(v["discount_pct"]) if "discount_pct" in v else default_discount_pct
        include_install = bool(v["include_install"]) if "include_install" in v else default_include_install
        result = render_variant(v["items"], discount_pct, include_install)
        result["label"] = label
        variant_results.append(result)

    variant_blocks = []
    for i, v in enumerate(variant_results):
        heading_html = f'<h2 class="variant-title">{html.escape(v["label"])}</h2>' if v["label"] else ""
        page_break = "variant-block-break" if (i > 0 and len(variant_results) > 1) else "variant-block"
        variant_blocks.append(f"""<div class="{page_break}">
{heading_html}
<table>
<tr><th style="width:40%">Наименование товара</th><th style="width:10%">Ед. изм.</th><th style="width:10%">Кол-во</th><th class="num" style="width:20%">Цена</th><th class="num" style="width:20%">Сумма</th></tr>
{"".join(v["rows_html"])}
</table>

<div class="total">Стоимость варианта составляет: <b>{num_ru(v["total"])} руб.</b><br>{html.escape(v.get("tax_note", ""))}</div>

<div class="gallery">
{"".join(v["gallery_html"])}
</div>
</div>""")

    page_html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 40mm 20mm 28mm 20mm; }}
@page :first {{ margin: 48mm 20mm 60mm 20mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: "DejaVu Sans", sans-serif; font-size: 10pt; line-height: 1.48; color: #1c2126; margin: 0; }}
.date {{ margin-bottom: 10pt; }}
.greeting {{ font-weight: 700; margin: 4pt 0 10pt 0; }}
p {{ margin: 5pt 0; text-align: justify; }}
table {{ width: 100%; border-collapse: collapse; margin: 10pt 0 4pt 0; font-size: 9pt; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
th, td {{ border: 0.6pt solid #b9c0c6; padding: 5.5pt 6pt; text-align: left; vertical-align: top; }}
th {{ background: #0B0F10; color: #fff; font-weight: 700; font-size: 8.4pt; }}
td.num {{ text-align: right; white-space: nowrap; }}
th.num {{ text-align: right; }}
td.avail-row {{ background: #fafbfb; font-size: 8.6pt; }}
.avail-ok {{ color: #178a58; font-weight: 700; }}
.avail-wait {{ color: #b5790a; font-weight: 700; }}
.total {{ margin-top: 8pt; font-size: 10.5pt; }}
.total b {{ color: #0B0F10; }}
.clause {{ margin-top: 10pt; font-size: 8.4pt; color: #4b5560; }}
.gallery {{ margin-top: 12pt; }}
.specs-row {{ display: flex; gap: 10pt; border: 0.6pt solid #b9c0c6; border-radius: 4pt; padding: 8pt; margin-bottom: 10pt; page-break-inside: avoid; }}
.specs-photo {{ flex: 0 0 110pt; text-align: center; }}
.specs-photo img {{ max-width: 100%; max-height: 100pt; }}
.specs-photo .no-photo {{ font-size: 7.6pt; color: #8a939b; font-style: italic; padding: 30pt 0; }}
.specs-photo .caption {{ font-size: 7.6pt; color: #4b5560; margin-top: 4pt; }}
.specs-table-wrap {{ flex: 1; min-width: 0; }}
table.specs {{ width: 100%; border-collapse: collapse; margin: 0; font-size: 7.8pt; }}
table.specs td {{ border: none; border-bottom: 0.5pt solid #e3e7ea; padding: 2.2pt 5pt; }}
table.specs td:first-child {{ color: #4b5560; width: 55%; }}
table.specs td:last-child {{ font-weight: 700; }}
.no-specs {{ font-size: 8pt; color: #8a939b; font-style: italic; }}
.variant-title {{ font-size: 12.5pt; color: #0B0F10; border-bottom: 1.2pt solid #0B0F10; padding-bottom: 4pt; margin: 4pt 0 8pt 0; }}
.variant-block {{ }}
.variant-block-break {{ page-break-before: always; }}
.sign {{ margin-top: 18pt; }}
.sign .who {{ font-style: italic; }}
</style></head><body>

<div class="date">Дата: {date}</div>
<div class="greeting">Уважаемый(ая) {client}!</div>
<p>{intro}</p>

{"".join(variant_blocks)}

<div class="clause">В случае изменения курсов доллара США или ЕВРО к Рублю РФ более чем на 1% в большую сторону с даты выставления данного коммерческого предложения, стоимость отдельных позиций подлежит пересмотру.</div>

<div class="sign">
<div>С уважением, технический директор</div>
<div class="who">Кочержинский Артём</div>
<div class="who">Тел.: +7-909-996-72-71</div>
</div>

</body></html>"""

    fd, html_path = tempfile.mkstemp(suffix=".html", prefix="kp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(page_html)

    content_pdf = html_path.replace(".html", ".pdf")
    r = subprocess.run(
        [WEASYPRINT_PY, "-c", f"from weasyprint import HTML; HTML('{html_path}').write_pdf('{content_pdf}')"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        die(f"weasyprint failed: {r.stderr[-800:]}")

    output = spec.get("output") or os.path.join(HOGART_DIR, "output", f"KP_{re.sub(r'[^a-zA-Zа-яА-Я0-9]+', '_', client)}.pdf")
    os.makedirs(os.path.dirname(output), exist_ok=True)

    merge_script = f"""
from pypdf import PdfReader, PdfWriter
letterhead = PdfReader({LETTERHEAD!r})
content = PdfReader({content_pdf!r})
writer = PdfWriter()
last_bg = len(letterhead.pages) - 1
for i, page in enumerate(content.pages):
    lw = PdfWriter()
    lw.append(letterhead)
    lp = lw.pages[min(i, last_bg)]
    lp.merge_page(page)
    writer.add_page(lp)
with open({output!r}, 'wb') as f:
    writer.write(f)
"""
    r = subprocess.run([WEASYPRINT_PY, "-c", merge_script], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        die(f"pdf merge failed: {r.stderr[-800:]}")

    xlsx_path = os.path.splitext(output)[0] + ".xlsx"
    write_economics_xlsx(xlsx_path, client, variant_results)

    print(json.dumps({
        "ok": True, "path": output, "economics_xlsx_path": xlsx_path, "client": client,
        "variants": [
            {"label": v["label"], "total": round(v["total"], 2), "items": v["summary_items"], "economics": v["economics"]}
            for v in variant_results
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        die("usage: generate_kp.py <spec.json>")
    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)
    try:
        build(spec)
    except Exception as exc:
        import traceback
        traceback.print_exc(file=sys.stderr)
        die(str(exc) if isinstance(exc, ValueError) else "Не удалось сформировать файлы КП. Задание сохранено для повторной попытки.")
