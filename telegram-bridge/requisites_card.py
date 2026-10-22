#!/usr/bin/env python3
"""Deterministic extraction of Russian company requisites from PDF/Word text."""
import os
import re
import subprocess


LABELS = {
    "inn": (r"\bИНН\b",), "kpp": (r"\bКПП\b",), "ogrn": (r"\bОГРН\b",),
    "okpo": (r"\bОКПО\b",), "legalAddress": (r"Юридическ(?:ий|ого) адрес",),
    "address": (r"Фактическ(?:ий|ого) адрес", r"Почтов(?:ый|ого) адрес"),
    "director": (r"(?:Генеральный )?директор", r"Руководитель"),
    "currentAccount": (r"(?:Номер счета|Расч[её]тный сч[её]т|р/с)",),
    "bank": (r"(?:Наименование банка|Банк)",), "bik": (r"\bБИК\b",),
    "correspondentAccount": (r"(?:Корр\.?\s*сч[её]т|к/с)",),
}


def compact_digits(value):
    return re.sub(r"\D", "", value or "")


def document_text(path):
    if path.casefold().endswith(".md"):
        with open(path, encoding="utf-8") as source:
            return source.read()
    if path.casefold().endswith(".pdf"):
        result = subprocess.run(
            ["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=30,
        )
        return result.stdout if result.returncode == 0 else ""
    return ""


def value_after_label(text, patterns):
    joined = "|".join(patterns)
    # Handles Markdown table rows (including bold labels emitted by the office
    # converter) and ordinary `Label: value`/`Label value` lines.
    match = re.search(
        rf"(?im)^\s*\|?\s*(?:[*_`]+\s*)?(?:{joined})(?:\s*[*_`]+)?\s*"
        rf"\|?\s*[:—-]?\s*([^\n|]+)", text,
    )
    return match.group(1).strip(" |:—-\t*") if match else ""


def parse(text):
    values = {key: value_after_label(text, patterns) for key, patterns in LABELS.items()}
    for key in ("inn", "kpp", "ogrn", "okpo", "currentAccount", "bik", "correspondentAccount"):
        values[key] = compact_digits(values[key])

    # Some Word-to-Markdown conversions keep identifiers in a single heading
    # (`ИНН 123... КПП 456...`) rather than in their table rows.  These
    # fallbacks are deliberately limited to the expected identifier lengths.
    # Always prefer an exact number immediately following its label.  A heading
    # such as `ИНН ... КПП ... ОГРН ...` is one physical line after conversion;
    # compacting the entire tail would otherwise concatenate three identifiers.
    exact_identifiers = {
        "inn": r"(?i)\bИНН\D{0,12}(\d{10}|\d{12})(?!\d)",
        "kpp": r"(?i)\bКПП\D{0,12}(\d{9})(?!\d)",
        "ogrn": r"(?i)\bОГРН\D{0,12}(\d{13}|\d{15})(?!\d)",
        "okpo": r"(?i)\bОКПО\D{0,12}(\d{8}|\d{10})(?!\d)",
        "currentAccount": r"(?i)(?:расч[её]тный\s+сч[её]т|р/с)\D{0,18}(\d{20})(?!\d)",
        "correspondentAccount": r"(?i)(?:корреспондентский\s+сч[её]т|корр\.?\s*сч[её]т|к/с)\D{0,18}(\d{20})(?!\d)",
        "bik": r"(?i)\bБИК\D{0,12}(\d{9})(?!\d)",
    }
    for key, pattern in exact_identifiers.items():
        match = re.search(pattern, text)
        if match:
            values[key] = match.group(1)

    fallbacks = {
        "inn": r"(?i)\bИНН\D{0,12}(\d{10}|\d{12})\b",
        "kpp": r"(?i)\bКПП\D{0,12}(\d{9})\b",
        "ogrn": r"(?i)\bОГРН\D{0,12}(\d{13}|\d{15})\b",
        "currentAccount": r"(?i)(?:расч[её]тный\s+сч[её]т|р/с)\D{0,18}(\d{20})\b",
        "correspondentAccount": r"(?i)(?:корреспондентский\s+сч[её]т|корр\.?\s*сч[её]т|к/с)\D{0,18}(\d{20})\b",
        "bik": r"(?i)\bБИК\D{0,12}(\d{9})\b",
    }
    for key, pattern in fallbacks.items():
        if not values.get(key):
            match = re.search(pattern, text)
            if match:
                values[key] = match.group(1)

    full = value_after_label(text, (r"Полное наименование организации", r"Полное наименование"))
    short = value_after_label(text, (r"Сокращ[её]нное наименование",))
    if not full:
        match = re.search(r"(?im)^\s*((?:ООО|АО|ПАО|ИП)\s+[«\"].+?[»\"]|(?:ООО|АО|ПАО|ИП)\s+[^\n|]{2,80})\s*$", text)
        full = match.group(1).strip() if match else short
    values["name"] = full or short
    values = {key: value for key, value in values.items() if value}
    return values


def is_requisites_card(text, values=None):
    values = values or parse(text)
    bank_fields = sum(bool(values.get(key)) for key in ("currentAccount", "bik", "correspondentAccount"))
    title = bool(re.search(r"(?i)карт(?:а|очка)\s+(?:предприятия|организации)|банковские реквизиты", text))
    return bool(values.get("name") and values.get("inn") and bank_fields >= 2 and (title or values.get("kpp")))


def parse_document(path):
    text = document_text(path)
    return parse_document_from_text(text)


def parse_document_from_text(text):
    values = parse(text)
    return values if is_requisites_card(text, values) else None
