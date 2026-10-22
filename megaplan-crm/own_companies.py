#!/usr/bin/env python3
"""Canonical directory of the legal entities used by SmartBild.

INNs and bank accounts are identifiers; display-name matching is only a fallback.
Unknown identifiers are intentionally left blank instead of being guessed.
"""
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "own_companies.json")

DEFAULTS = {
    "default_selling_company": "cliwell",
    "companies": [
        {"id": "cliwell", "name": "ООО «КЛИВЭЛ»", "inn": "7743151323",
         "accounts": ["40702810902570001580"], "aliases": ["кливэл", "кливел", "cliwell"]},
        {"id": "insis", "name": "ООО «Инсис»", "inn": "7743926877",
         "accounts": ["40702810402570001572"], "aliases": ["инсис", "insis"]},
        {"id": "kocherzhinsky_ip", "name": "ИП Кочержинский А.В.", "inn": "782093991468",
         "accounts": ["40802810300007034866"],
         "bank": {"name": "АО «ТБанк»", "bik": "044525974",
                  "correspondent_account": "30101810145250000974"},
         "address": "123290, Россия, г. Москва, Шелепихинская наб., д. 34, корп. 2, кв. 221",
         "aliases": ["ип кочержинский", "кочержинский а.в."]},
    ],
}


def load_directory():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as source:
            configured = json.load(source)
        if configured.get("companies"):
            return configured
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULTS


def normalize_name(value):
    value = str(value or "").casefold().replace("ё", "е")
    return re.sub(r"[^0-9a-zа-я]", "", value)


def companies():
    return load_directory().get("companies") or []


def company_by_id(company_id):
    return next((x for x in companies() if x.get("id") == company_id), None)


def resolve_company(inn=None, account=None, name=None):
    inn = re.sub(r"\D", "", str(inn or ""))
    account = re.sub(r"\D", "", str(account or ""))
    if inn:
        found = next((x for x in companies() if x.get("inn") and x["inn"] == inn), None)
        if found:
            return found
    if account:
        found = next((x for x in companies() if account in (x.get("accounts") or [])), None)
        if found:
            return found
    normalized = normalize_name(name)
    if normalized:
        for item in companies():
            variants = [item.get("name"), *(item.get("aliases") or [])]
            if any(normalize_name(alias) and normalize_name(alias) in normalized for alias in variants):
                return item
    return None


def default_selling_company():
    data = load_directory()
    return company_by_id(data.get("default_selling_company"))
