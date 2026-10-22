#!/usr/bin/env python3
"""Build a Cliwell deal contract from live Megaplan data.

Prototype boundary: reads CRM only and writes local DOCX/PDF files. It never uploads
files or edits the deal. JSON input is accepted on stdin.
"""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import hashlib
import math
from pathlib import Path

import pymorphy3
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from num2words import num2words

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from megaplan_api import MegaplanAPI, MegaplanAPIError
from payer_signatory_store import get_signatory

TEMPLATE = BASE_DIR / 'templates' / 'contracts' / 'no-vat-v1.docx'
LIBREOFFICE_APPIMAGE = Path("/home/kocher.av/.local/lib/libreoffice-appimage/LibreOffice.AppImage")
LIBREOFFICE_DEPS = Path("/home/kocher.av/.local/lib/libreoffice-appimage/deps/usr/lib/x86_64-linux-gnu")
WORK_WORDS = (
    "монтаж", "демонтаж", "работ", "услуг", "пусконалад", "вакуум", "опрессов",
    "подключение", "перевальцов", "восстановление", "заправка", "высотн",
)
MATERIAL_WORDS = (
    "труб", "кабел", "изоляц", "креп", "кронштейн", "расходн", "хладагент",
    "фреон", "дренаж", "короб", "канал", "материал", "лоток", "провод",
    "наконечник", "гильз", "стяжк", "перемычк",
)


def money_value(value):
    return float((value or {}).get("value", 0)) if isinstance(value, dict) else float(value or 0)


def rubles(value):
    rounded = round(float(value) + 1e-8, 2)
    whole = int(rounded)
    kop = int(round((rounded - whole) * 100))
    if kop == 100:
        whole += 1
        kop = 0
    return f"{whole:,}".replace(",", " ") + f" рублей {kop:02d} копеек"


def rubles_words(value):
    rounded = round(float(value) + 1e-8, 2)
    whole = int(rounded)
    kop = int(round((rounded - whole) * 100))
    return f"{num2words(whole, lang='ru')} рублей {kop:02d} копеек"


def classify(name):
    low = name.casefold()
    if re.search(r"\b(прокладка|бурение|сборка|огнезаделка|заземление|электроизмерения|доставка|погрузка|разгрузка)\b", low):
        return "work"
    if any(word in low for word in WORK_WORDS):
        return "work"
    if any(word in low for word in MATERIAL_WORDS):
        return "material"
    return "equipment"


def classify_position(row):
    """Use the CRM's exclusive labour cost before guessing from product names.

    These fields identify the kind of a row, not its selling amount. Delivery
    remains a service even when its supplier cost was entered as a purchase.
    Mixed or missing cost splits retain the name-based fallback.
    """
    name = row.get("name") or (row.get("offer") or {}).get("name") or ""
    if re.search(r"\b(доставка|погрузка|разгрузка)\b|погрузочно-разгрузоч", name.casefold()):
        return "work"
    offer = row.get("offer") or {}
    labour = money_value(offer.get("Category1000045CustomFieldSebesRabot"))
    purchase = money_value(offer.get("Category1000045CustomFieldTsenaZakupki"))
    if labour > 0 and purchase == 0:
        return "work"
    if purchase > 0 and labour == 0:
        return "material" if any(word in name.casefold() for word in MATERIAL_WORDS) else "equipment"
    return classify(name)


def lower_first(text):
    text = text.strip()
    return text[:1].lower() + text[1:] if text else text


def subject_for_title(subject):
    """Format the subject after the title's preposition `на`.

    The CRM stores the subject in nominative form. Russian feminine action nouns in
    a coordinated list need accusative here, while neuter/masculine nouns do not.
    Keep this deterministic: these are the contract vocabulary used by the bot, not
    an unconstrained language-model rewrite.
    """
    text = lower_first(subject)
    replacements = {
        "поставка": "поставку",
        "пусконаладка": "пусконаладку",
        "разработка": "разработку",
        "установка": "установку",
        "настройка": "настройку",
    }
    for source, target in replacements.items():
        text = re.sub(rf"\b{source}\b", target, text, flags=re.IGNORECASE)
    return text


def subject_for_body(subject):
    """Format the subject after `Предметом ... является` (lowercase nominative)."""
    return lower_first(subject)


def is_full_person_name(value):
    """A contract signatory must contain surname, first name and patronymic."""
    parts = re.findall(r"[A-Za-zА-Яа-яЁё-]+", str(value or ""))
    return len(parts) >= 3 and all(len(part.replace("-", "")) > 1 for part in parts[:3])


def contract_data(deal, spec):
    payer = deal.get("payer") or {}
    # Megaplan expands a Unit only once; subsequent rows carry its id alone.
    unit_names = {}
    for source_row in deal.get('positions') or []:
        for source in (source_row, source_row.get('offer') or {}):
            unit = source.get('unit') or {}
            if unit.get('id') is not None and unit.get('name'):
                unit_names[str(unit['id'])] = unit['name']
    positions = []
    totals = {"equipment": 0.0, "material": 0.0, "work": 0.0}
    overrides = spec.get("position_types") or {}
    for row in deal.get("positions") or []:
        name = row.get("name") or "Без названия"
        kind = overrides.get(str(row.get("id"))) or classify_position(row)
        if kind not in totals:
            raise ValueError(f"Неизвестный тип позиции {row.get('id')}: {kind}")
        qty = float(row.get("quantity") or 0)
        price = row.get('price') or {}; row_sum = row.get('sum') or {}
        if price.get('currency') not in (None,'RUB') or row_sum.get('currency') not in (None,'RUB'):
            raise ValueError('Для договора нужна зафиксированная рублёвая спецификация')
        if row_sum.get('value') is None and row.get('discount'):
            raise ValueError('У позиции со скидкой отсутствует итоговая сумма')
        total = money_value(row_sum) if row_sum.get('value') is not None else qty * money_value(price)
        if not math.isfinite(qty) or qty<=0 or not math.isfinite(total) or total<0:
            raise ValueError('Неверное количество или сумма позиции договора')
        unit_price = total / qty
        totals[kind] = totals.get(kind, 0) + total
        positions.append({
            "id": str(row.get("id")), "name": name, "kind": kind,
            "tax_rate": (row.get("tax") or (row.get("offer") or {}).get("tax") or {}).get("rate",-1),
            "unit": (row.get("unit") or {}).get("name") or unit_names.get(str((row.get("unit") or {}).get("id"))) or "шт.",
            "quantity": qty, "unit_price": unit_price, "total": total,
        })
    signatory = dict(spec.get("customer_signatory") or {})
    # The payer is the legal entity signing the contract, so its Megaplan custom
    # field is the canonical reusable source for the director's full name. A name
    # supplied by the Telegram wizard is usable only when it was collected for this
    # exact payer; otherwise an old deal/payer must never leak into a new contract.
    payer_id = str(payer.get("id") or "")
    stored_name = str(payer.get("Category715CustomFieldFioRukovoditelya") or "").strip()
    supplied_name = str(signatory.get("name") or "").strip()
    supplied_payer_id = str(spec.get("customer_signatory_payer_id") or "")
    if is_full_person_name(stored_name):
        signatory["name"] = stored_name
    elif supplied_payer_id == payer_id and is_full_person_name(supplied_name):
        signatory["name"] = supplied_name
    else:
        signatory["name"] = ""
    date = deal.get("Category1000068CustomFieldDataDogovora") or {}
    date_text = f"{int(date.get('day', 0)):02d}.{int(date.get('month', 0)) + 1:02d}.{int(date.get('year', 0)):04d}" if date else ""
    total = money_value(deal.get("price"))
    advance = totals["equipment"] + totals["material"]
    final = totals["work"]
    data = {
        "deal_id": str(deal.get("id")),
        "payer_id": payer_id,
        "number": deal.get("Category1000068CustomFieldNomerDogovora") or deal.get("number") or deal.get("name") or "",
        "date": date_text,
        "subject": deal.get("Category1000068CustomFieldPredmetDogovora") or deal.get("description") or "",
        "address": deal.get("Category1000068CustomFieldAdresObEkta") or "",
        "client": (deal.get("contractor") or {}).get("name") or payer.get("name") or "",
        "payer_name": payer.get("name") or "",
        "payer": payer,
        "signatory": signatory,
        "positions": positions,
        "equipment": totals["equipment"], "materials": totals["material"],
        "advance": advance, "works": final, "total": total,
        "tax_text": "НДС не облагается на основании п. 1 ст. 145 НК РФ",
    }
    missing = []
    for key, label in (("number", "номер договора"), ("date", "дата договора"),
                       ("subject", "предмет договора"), ("address", "адрес объекта")):
        if not data[key]: missing.append(label)
    for key, label in (("name", "наименование плательщика"), ("inn", "ИНН"),
                       ("legalAddress", "юридический адрес"), ("currentAccount", "расчётный счёт"),
                       ("bank", "банк"), ("bik", "БИК"), ("correspondentAccount", "корреспондентский счёт")):
        if not payer.get(key): missing.append(label)
    for key, label in (("name", "ФИО подписанта"), ("position", "должность подписанта"),
                       ("authority", "основание полномочий подписанта")):
        if not signatory.get(key): missing.append(label)
    if not positions: missing.append("позиции спецификации")
    difference = round(total - advance - final, 2)
    if abs(difference) > 0.01:
        missing.append(f"суммы позиций не сходятся с суммой сделки (разница {difference:.2f} ₽)")
    data["missing"] = missing
    from document_tax_policy import decorate
    return decorate(data)


def all_paragraphs(document):
    yield from document.paragraphs
    yield from table_paragraphs(document.tables)


def table_paragraphs(tables):
    for table in tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
                yield from table_paragraphs(cell.tables)


def set_paragraph_text(paragraph, text):
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def replace_in_runs(paragraph, old, new, occurrence=1):
    """Replace split Word text while preserving the formatting of nearby runs."""
    runs = paragraph.runs
    full = "".join(run.text for run in runs)
    start = -1
    cursor_from = 0
    for _ in range(occurrence):
        start = full.find(old, cursor_from)
        if start < 0:
            return
        cursor_from = start + len(old)
    end = start + len(old)
    cursor = 0
    first = last = None
    for index, run in enumerate(runs):
        next_cursor = cursor + len(run.text)
        if first is None and start < next_cursor:
            first, first_offset = index, start - cursor
        if end <= next_cursor:
            last, last_offset = index, end - cursor
            break
        cursor = next_cursor
    if first is None or last is None:
        return
    prefix = runs[first].text[:first_offset]
    suffix = runs[last].text[last_offset:]
    runs[first].text = prefix + new + (suffix if first == last else "")
    for index in range(first + 1, last):
        runs[index].text = ""
    if last != first:
        runs[last].text = suffix


def replace_text(document, replacements):
    for paragraph in all_paragraphs(document):
        for old, new in replacements.items():
            replace_in_runs(paragraph, old, new)


def inflect_full_name_genitive(full_name):
    morph = pymorphy3.MorphAnalyzer()
    words = full_name.split()
    female = len(words) >= 3 and words[2].casefold().endswith(("вна", "чна"))
    result = []
    for index, word in enumerate(words):
        low = word.casefold()
        if index == 0 and not female and low.endswith(("ов", "ев", "ин")):
            value = low + "а"
        elif index == 0 and female and low.endswith(("ова", "ева", "ина")):
            value = low[:-1] + "ой"
        else:
            parsed = morph.parse(word)[0]
            inflected = parsed.inflect({"gent"})
            value = inflected.word if inflected else word
        result.append(value[:1].upper() + value[1:] if word[:1].isupper() else value)
    return " ".join(result)


def surname_initials(full_name):
    parts = full_name.split()
    return parts[0] + (" " + "".join(f"{part[0].upper()}." for part in parts[1:3]) if len(parts) > 1 else "") if parts else ""


def truncate_filename_utf8(value, max_bytes):
    """Trim a filename stem by bytes, not characters (Linux limit is 255 bytes)."""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", "ignore").rstrip(" .,—-")


def safe_filename_stem(value, max_bytes=170):
    """Return one portable filename component, never a path.

    Product models routinely contain slashes (for example HSU-07HQJ103/R3-W).
    They are valid contract text but must not become directory separators.
    """
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "-", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip(" .,—-")
    return truncate_filename_utf8(value, max_bytes)


def contract_filename_stem(number, payer, subject):
    """Build a human filename from the deal essence, never from offer names/SKUs."""
    essence = re.sub(r"\s+", " ", str(subject or "")).strip()
    payer = re.sub(r'"([^"\r\n]+)"', r'«\1»', str(payer or ""))
    return safe_filename_stem(
        f"Договор №{number} — КЛИВЭЛ — {payer} — {essence}", 170,
    )


def rebuild_payment_paragraph(paragraph, prefix, bold_text, suffix):
    for run in paragraph.runs:
        run.text = ""
    paragraph.add_run(prefix)
    bold_run = paragraph.add_run(bold_text)
    bold_run.bold = True
    paragraph.add_run(suffix)


def keep_row_on_one_page(row):
    """Set Word's `cantSplit`: a two-party signature row must never cross pages."""
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def compact_signature_tables(document):
    """Keep signature rows intact and remove artificial customer-side blank lines.

    Do not change paragraph spacing here: the signature and stamp are floating
    template objects whose coordinates are calibrated against the original text.
    """
    for table_index in (0, 2):
        if table_index >= len(document.tables):
            continue
        table = document.tables[table_index]
        for row in table.rows:
            keep_row_on_one_page(row)
        if table_index == 0 and table.rows:
            supplier_cell = table.rows[0].cells[0]
            supplier_paragraphs = list(supplier_cell.paragraphs)
            for paragraph in supplier_paragraphs:
                if not paragraph.text.strip():
                    paragraph._element.getparent().remove(paragraph._element)
            supplier_paragraphs = list(supplier_cell.paragraphs)
            start = next(
                (index for index, p in enumerate(supplier_paragraphs) if p.text.strip() == "ООО «КЛИВЭЛ»"),
                None,
            )
            position_index = next(
                (index for index, p in enumerate(supplier_paragraphs) if p.text.strip() == "Генеральный директор"),
                None,
            )
            if start is not None and position_index is not None:
                for paragraph in supplier_paragraphs[start:position_index]:
                    if paragraph.text.strip():
                        paragraph.paragraph_format.space_before = Pt(0)
                        paragraph.paragraph_format.space_after = Pt(0)
                        paragraph.paragraph_format.line_spacing = 1.0
                    else:
                        paragraph._element.getparent().remove(paragraph._element)
                supplier_paragraphs[position_index].paragraph_format.space_before = Pt(0)
        if table.rows and len(table.rows[0].cells) > 1:
            customer_cell = table.rows[0].cells[1]
            outer_paragraphs = list(customer_cell.paragraphs)
            for paragraph in outer_paragraphs[:-1]:
                if not paragraph.text.strip():
                    paragraph._element.getparent().remove(paragraph._element)
            for nested_table in customer_cell.tables:
                for nested_row in nested_table.rows:
                    for nested_cell in nested_row.cells:
                        paragraphs = list(nested_cell.paragraphs)
                        for index, paragraph in enumerate(paragraphs):
                            if paragraph.text.strip():
                                continue
                            paragraph._element.getparent().remove(paragraph._element)
                        if table_index == 0:
                            for paragraph in nested_cell.paragraphs:
                                if paragraph.text.strip() == "Директор":
                                    paragraph.paragraph_format.space_before = Pt(0)
                                    break

    # The main signature/stamp group is a floating object anchored to the
    # requisites heading. Move the object itself after compacting the text;
    # never recreate vertical alignment with empty paragraphs.
    drawings = document.element.xpath(".//w:drawing")
    if drawings:
        offset_nodes = drawings[0].xpath(".//wp:positionV/wp:posOffset")
        if offset_nodes:
            offset_nodes[0].text = str(int(offset_nodes[0].text) - 1860000)
    for paragraph in document.paragraphs:
        if paragraph.text.strip() == "11.Реквизиты сторон":
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            previous = paragraph._p.getprevious()
            if previous is not None and previous.tag.endswith("}p") and not "".join(previous.itertext()).strip():
                previous.getparent().remove(previous)
            break


def compact_specification_table(table):
    """Let position rows follow their actual text height, without a blank line."""
    for row in table.rows[1:]:
        tr_pr = row._tr.get_or_add_trPr()
        height = tr_pr.find(qn("w:trHeight"))
        if height is not None:
            tr_pr.remove(height)
        for cell in row.cells:
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_mar = tc_pr.first_child_found_in("w:tcMar")
            if tc_mar is None:
                tc_mar = OxmlElement("w:tcMar")
                tc_pr.append(tc_mar)
            for side in ("top", "bottom"):
                margin = tc_mar.find(qn(f"w:{side}"))
                if margin is None:
                    margin = OxmlElement(f"w:{side}")
                    tc_mar.append(margin)
                margin.set(qn("w:w"), "15")
                margin.set(qn("w:type"), "dxa")
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_before = Pt(0)
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.0
    trailing_rows = 16
    if len(table.rows) > trailing_rows + 1:
        break_row = table.rows[len(table.rows) - trailing_rows]
        break_row.cells[0].paragraphs[0].paragraph_format.page_break_before = True


def format_appendix_heading(paragraph):
    """Appendix 1 always starts on a new page with stable top spacing."""
    paragraph.paragraph_format.space_before = Pt(50)
    paragraph.paragraph_format.page_break_before = True


def generate(data):
    document = Document(str(TEMPLATE))
    payer, signer = data["payer"], data["signatory"]
    title_subject = subject_for_title(data["subject"])
    for paragraph in document.paragraphs:
        if paragraph.text.strip().startswith("на {{ Предмет Договора }}"):
            replace_in_runs(paragraph, "{{ Предмет Договора }}", title_subject)
            break
    body_subject = subject_for_body(data["subject"])
    for paragraph in document.paragraphs:
        if "Предметом настоящего договора является {{ Предмет Договора }}" in paragraph.text:
            replace_in_runs(paragraph, "{{ Предмет Договора }}", body_subject)
            break
    position = signer["position"].strip()
    position_genitive = {
        "генеральный директор": "Генерального директора",
        "директор": "Директора",
    }.get(position.casefold(), position)
    authority = signer["authority"].strip()
    authority_genitive = {"устав": "Устава", "доверенность": "доверенности"}.get(authority.casefold(), authority)
    signer_genitive = inflect_full_name_genitive(signer["name"])
    signer_short = surname_initials(signer["name"])
    replacements = {
        "{{ Номер Договора }}": data["number"],
        "{{ Предмет Договора }}": data["subject"],
        "{{ Дата Договора }}": data["date"],
        "{{ Адрес объекта }}": data["address"],
        "{{ Сумма.Значение }}": f"{data['total']:,.2f}".replace(",", " ").replace(".", ","),
        "{{ Сумма.Прописью }}": rubles_words(data["total"]),
        "{{ Плательщик.Название }}": payer.get("name", ""),
        "{{ Плательщик }}": payer.get("name", ""),
        "{{ Плательщик.Юр. адрес }}": payer.get("legalAddress", ""),
        "{{ Плательщик.ОГРН }}": payer.get("ogrn", ""),
        "{{ Плательщик.ИНН }}": payer.get("inn", ""),
        "{{ Плательщик.КПП }}": payer.get("kpp", ""),
        "{{ Плательщик.р/с }}": payer.get("currentAccount", ""),
        "{{ Плательщик.Банк }}": payer.get("bank", ""),
        "{{ Плательщик.БИК }}": payer.get("bik", ""),
        "{{ Плательщик.к/с }}": payer.get("correspondentAccount", ""),
        "именуемый в дальнейшем «Заказчик»": "именуемое в дальнейшем «Заказчик»",
    }
    replace_text(document, replacements)

    for paragraph in all_paragraphs(document):
        if "совместно в дальнейшем" in paragraph.text:
            replace_in_runs(paragraph, "{{ Плательщики.ФИО руководителя }}", signer_genitive)
            # The preamble contains two parties. The first title/authority belongs to
            # fixed supplier ООО «КЛИВЭЛ»; only the SECOND occurrences belong to the
            # customer and may be replaced from the deal's signatory details.
            replace_in_runs(paragraph, "Генерального директора", position_genitive, occurrence=2)
            replace_in_runs(paragraph, "на основании Устава", f"на основании {authority_genitive}", occurrence=2)
        else:
            replace_in_runs(paragraph, "{{ Плательщики.ФИО руководителя }}", signer_short)
            replace_in_runs(paragraph, "{{ Клиент.Плательщики.ФИО руководителя }}", signer_short)

    # Customer signature blocks are the right-hand cells; do not change Cliwell's
    # fixed signatory in the left-hand cells.
    for table_index in (0, 2):
        customer_cell = document.tables[table_index].cell(0, 1)
        for paragraph in list(customer_cell.paragraphs) + list(table_paragraphs(customer_cell.tables)):
            if paragraph.text.strip() == "Генеральный директор":
                set_paragraph_text(paragraph, position)

    # Keep Cliwell's signature rule and the signatory name on one line in both
    # requisites blocks (main contract and Appendix 1).
    for table_index in (0, 2):
        supplier_cell = document.tables[table_index].cell(0, 0)
        for paragraph in list(supplier_cell.paragraphs) + list(table_paragraphs(supplier_cell.tables)):
            if "Кочержинская С.В." in paragraph.text:
                replace_in_runs(
                    paragraph,
                    paragraph.text,
                    "__________ /Кочержинская С.В./",
                )

    compact_signature_tables(document)

    # Replace the two payment clauses as complete paragraphs to avoid fragile blank lines.
    for paragraph in all_paragraphs(document):
        if paragraph.text.strip().startswith("Общая стоимость поставляемой Продукции"):
            rebuild_payment_paragraph(
                paragraph,
                "Общая стоимость поставляемой Продукции и работ по монтажу по настоящему Договору (далее — Цена договора), составляет:  ",
                f"{data['total']:,.2f}".replace(",", " ").replace(".", ",") + f" руб. ({rubles_words(data['total'])})",
                f", {data['tax_text']}.",
            )
        elif paragraph.text.strip().startswith("6.4.1"):
            rebuild_payment_paragraph(
                paragraph,
                "6.4.1 Заказчик перечисляет на расчётный счёт Поставщика предоплату в размере ",
                f"100% от общей стоимости оборудования и материалов, что составляет {rubles(data['advance'])} ({rubles_words(data['advance'])})",
                ", в течение 3 (трёх) календарных дней с даты подписания настоящего Договора, в соответствии с предоставленным Поставщиком счетом.",
            )
        elif paragraph.text.strip().startswith("6.4.2"):
            rebuild_payment_paragraph(
                paragraph,
                "6.4.2 Окончательный расчёт за выполненные работы и оказанные услуги в размере ",
                f"{rubles(data['works'])} ({rubles_words(data['works'])})",
                " Заказчик перечисляет в течение 3 (трёх) календарных дней с даты подписания актов выполненных работ.",
            )
        if "НДС не облагается." in paragraph.text:
            set_paragraph_text(paragraph, paragraph.text.replace("НДС не облагается.", data["tax_text"] + "."))

    # Appendix 1 always starts on a clean page at the normal top margin.
    for paragraph in document.paragraphs:
        if paragraph.text.startswith("Приложение № 1"):
            format_appendix_heading(paragraph)
            # The source template contains spacer paragraphs around the appendix.
            # Word hides their effect reasonably well, while PDF renderers turn
            # them into a large top gap (and, at the end, an empty extra page).
            node = paragraph._p.getprevious()
            while node is not None and node.tag.endswith("}p") and not "".join(node.itertext()).strip():
                previous = node.getprevious()
                node.getparent().remove(node)
                node = previous
            node = paragraph._p.getnext()
            while node is not None and node.tag.endswith("}p") and not "".join(node.itertext()).strip():
                following = node.getnext()
                node.getparent().remove(node)
                node = following
            break

    # Replace the single placeholder row in Appendix 1 with one row per live deal item.
    table = document.tables[1]
    template_row = table.rows[1]._tr
    table._tbl.remove(template_row)
    for item in data["positions"]:
        row_xml = copy.deepcopy(template_row)
        table._tbl.append(row_xml)
        cells = table.rows[-1].cells
        values = [
            item["name"], item["unit"], f"{item['quantity']:g}",
            f"{item['unit_price']:,.2f}".replace(",", " ").replace(".", ","),
            f"{item['total']:,.2f}".replace(",", " ").replace(".", ","),
        ]
        for cell, value in zip(cells, values):
            set_paragraph_text(cell.paragraphs[0], value)
    compact_specification_table(table)

    # Remove the trailing empty body paragraph left after the appendix signature
    # table; LibreOffice otherwise exports it as a completely blank last page.
    body = document.element.body
    for node in list(body)[-2::-1]:
        if node.tag.endswith("}p") and not "".join(node.itertext()).strip():
            body.remove(node)
            continue
        break

    from seller_documents import selected_seller, apply_ip_supplier
    seller = data.get('_seller') or selected_seller(data['deal_id'])
    apply_ip_supplier(document, seller)
    stem = contract_filename_stem(data["number"], data["payer_name"], data["subject"])
    if seller['id'] != 'cliwell':
        stem = stem.replace('КЛИВЭЛ', seller['name'])
    out_dir = Path(tempfile.mkdtemp(prefix=f"contract-{data['deal_id']}-"))
    docx_path = out_dir / f"{stem}.docx"
    pdf_path = out_dir / f"{stem}.pdf"
    signed_source_path = out_dir / f"{stem} — источник с подписью.docx"

    # PDF is made from the signed template version. The intermediary DOCX is
    # never sent to Telegram and is removed immediately after conversion.
    document.save(signed_source_path)

    # The customer-facing editable Word version must remain unsigned and
    # unstamped, so strip the embedded scans only from this second version.
    for node in document.element.xpath(".//w:drawing | .//w:pict"):
        node.getparent().remove(node)
    document.save(docx_path)

    profile_dir = Path(tempfile.mkdtemp(prefix="libreoffice-profile-"))
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(LIBREOFFICE_DEPS) + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    from document_renderer import office_command
    executable = office_command(env)
    result = subprocess.run(
        [
            executable, "--headless", "--nologo", "--nodefault", "--nolockcheck",
            f"-env:UserInstallation=file://{profile_dir}", "--convert-to", "pdf",
            "--outdir", str(out_dir), str(signed_source_path),
        ],
        capture_output=True, text=True, timeout=120, env=env,
    )
    try:
        __import__("shutil").rmtree(profile_dir, ignore_errors=True)
    except OSError:
        pass
    converted_pdf_path = signed_source_path.with_suffix(".pdf")
    if result.returncode != 0 or not converted_pdf_path.exists():
        raise RuntimeError(f"LibreOffice не сформировал PDF: {(result.stderr or result.stdout)[-500:]}")
    converted_pdf_path.replace(pdf_path)
    signed_source_path.unlink(missing_ok=True)
    return str(docx_path), str(pdf_path)


def preview(data):
    return {
        "deal_id": data["deal_id"], "payer_id": data["payer_id"],
        "number": data["number"], "date": data["date"],
        "client": data["client"], "address": data["address"], "subject": data["subject"],
        "payer_name": data["payer_name"],
        "equipment": data["equipment"], "materials": data["materials"],
        "advance": data["advance"], "works": data["works"], "total": data["total"],
        "tax_text": data["tax_text"], "positions_count": len(data["positions"]),
        "missing": data["missing"], "positions": data["positions"],
        "signatory": data["signatory"],
    }


def data_fingerprint(data, seller):
    return hashlib.sha256(json.dumps({'data':data,'seller':seller},sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def main():
    spec = json.load(sys.stdin)
    api = MegaplanAPI()
    deal = api._call("GET", f"/deal/{spec['deal_id']}")["data"]
    from document_tax_policy import require_document_tax
    rates=require_document_tax(deal,api)
    # Embedded payer references omit custom fields. Hydrate the selected payer so the
    # saved director can actually be reused by future contracts.
    payer_ref = deal.get("payer") or {}
    if payer_ref.get("id"):
        deal["payer"] = api._call("GET", f"/payer/{payer_ref['id']}")["data"]
        payer_id = str(payer_ref["id"])
        saved_signatory = get_signatory(payer_id)
        supplied = (spec.get("customer_signatory") or {}) if str(spec.get("customer_signatory_payer_id") or "") == payer_id else {}
        spec["customer_signatory"] = {
            key: str(supplied.get(key) or saved_signatory.get(key) or "").strip()
            for key in ("name", "position", "authority")
        }
        spec["customer_signatory_payer_id"] = payer_id
    data = contract_data(deal, spec)
    from document_tax_policy import decorate
    decorate(data,rates)
    from seller_documents import selected_seller
    seller=selected_seller(data['deal_id'])
    fingerprint=data_fingerprint(data,seller)
    if spec.get("action", "preview") == "preview":
        print(json.dumps({"ok": True, "preview": {**preview(data),'fingerprint':fingerprint,'seller_name':seller['name']}}, ensure_ascii=False))
        return
    if spec.get('expected_fingerprint') and spec['expected_fingerprint'] != fingerprint:
        print(json.dumps({'ok':False,'no_effect':True,'error':'Данные договора или наша организация изменились после просмотра. Проверьте договор заново.'},ensure_ascii=False)); return
    if data["missing"]:
        print(json.dumps({"ok": False, "error": "не заполнены обязательные данные", "missing": data["missing"]}, ensure_ascii=False))
        return
    data['_seller']=seller
    docx_path, pdf_path = generate(data)
    print(json.dumps({"ok": True, "preview": preview(data), "docx_path": docx_path, "pdf_path": pdf_path}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, RuntimeError, OSError, MegaplanAPIError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
