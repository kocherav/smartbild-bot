#!/usr/bin/env python3
"""Immutable OneDrive archive for documents that affect a deal's finances.

The module deliberately knows nothing about Telegram.  Call it from any workflow
with a local file and an explicit document kind.  Source documents are copied once
(same content is de-duplicated by SHA-256); generated reports are retained as dated
versions.  It never replaces an original supplier or client document.
"""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from megaplan_api import MegaplanAPI

BASE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(BASE, "financial_archive.json")
LOCK = REGISTRY + ".lock"
ONEDRIVE_ROOT = "onedrive:SmartBild/Сделки"

CATEGORIES = {
    "contract_client": "01_Договоры_с_клиентом",
    "invoice_client": "02_Счета_клиенту",
    "supplier_invoice": "03_Закупки_и_счета_поставщиков",
    "supplier_closing": "04_Закрывающие_документы_поставщиков",
    "client_closing": "05_Закрывающие_документы_клиенту",
    "economics": "06_Экономика_и_реестры/Экономика",
    "accounting_register": "06_Экономика_и_реестры/Реестры",
}


def clean(value):
    return " ".join(str(value or "").split())


def safe(value):
    value = re.sub(r'[<>:"/\\|?*]+', " ", clean(value)).strip(" .")
    return value[:120] or "Без названия"


def brief_essence(subject, address=""):
    value = clean(subject)
    value = re.sub(r"(?i)^(?:проектирование,?\s*)?(?:поставка|поставку)(?:\s*,?\s*(?:монтаж|установка|пусконаладка|пусконаладочные работы|и\s+монтаж))*\s+", "", value)
    value = re.sub(r"(?i)^и\s+монтаж\s+", "", value)
    value = re.sub(r"(?i)^систем(?:ы|а)\s+", "", value)
    replacements = {
        "электроснабжения": "электроснабжение",
        "кондиционирования": "кондиционирование",
        "вентиляции": "вентиляция",
        "отопления": "отопление",
    }
    for source, target in replacements.items():
        value = re.sub(rf"(?i)\b{source}\b", target, value)
    tail = ""
    match = re.search(r"(?i)(\d+(?:-й|-я|-е)?\s+этаж(?:\s+[A-Za-zА-Яа-яЁё0-9.-]+)*)", address or "")
    if match:
        tail = re.sub(r"(?i)этаж", "эт", clean(match.group(1)))
    if tail and tail.casefold() not in value.casefold():
        value = f"{value} {tail}"
    return clean(value)


def deal_folder_name(deal):
    contractor = deal.get("contractor") or {}
    client = contractor.get("name") or "Клиент"
    subject = (deal.get("Category1000068CustomFieldPredmetDogovora")
               or deal.get("name") or "Сделка")
    address = deal.get("Category1000068CustomFieldAdresObEkta") or ""
    return safe(f"Сделка №{deal.get('id')} - {client} - {brief_essence(subject, address)}")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_registry():
    try:
        with open(REGISTRY, encoding="utf-8") as source:
            return json.load(source)
    except FileNotFoundError:
        return {"documents": []}


def save_registry(data):
    temporary = f"{REGISTRY}.{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as target:
        json.dump(data, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.flush(); os.fsync(target.fileno())
    os.replace(temporary, REGISTRY)


def rclone_copy(path, remote):
    result = subprocess.run(
        ["rclone", "copyto", path, remote, "--immutable", "--retries", "3", "--low-level-retries", "5"],
        capture_output=True, text=True, timeout=90,
    )
    if result.returncode:
        raise ValueError("OneDrive: " + (result.stderr or "ошибка загрузки")[-500:])
    check = subprocess.run(["rclone", "lsjson", remote, "--stat"],
                           capture_output=True, text=True, timeout=60)
    if check.returncode:
        raise ValueError("OneDrive: файл отправлен, но проверка удалённой копии не выполнена")
    remote_info = json.loads(check.stdout)
    if remote_info.get("IsDir") or remote_info.get("Size") != os.path.getsize(path):
        raise ValueError("OneDrive: размер сохранённого файла не совпадает с оригиналом")


def archive_document(deal_id, path, category, document_number="", display_name="", api=None, copier=rclone_copy):
    """Archive one local document and return its stable OneDrive remote path."""
    deal_id = str(deal_id)
    path = os.path.realpath(path)
    if category not in CATEGORIES:
        raise ValueError("неизвестный тип финансового документа")
    if not os.path.isfile(path):
        raise ValueError("файл для архива не найден")
    digest = sha256(path)
    with open(LOCK, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        registry = load_registry()
        for item in registry.get("documents") or []:
            if item.get("deal_id") == deal_id and item.get("sha256") == digest and item.get('category')==category:
                if item.get('status','uploaded')!='uploaded':
                    copier(path,item['onedrive_remote'])
                    item['status']='uploaded'; save_registry(registry)
                return {**item, "ok": True, "duplicate": True}

        api = api or MegaplanAPI()
        deal = api._call("GET", f"/deal/{deal_id}")["data"]
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        extension = os.path.splitext(path)[1]
        title = safe(display_name) if clean(display_name) else safe(os.path.basename(path))
        known_extensions = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".zip")
        filename = title if os.path.splitext(title)[1].casefold() in known_extensions else title + extension
        # A date prefix makes generated versions sortable and originals immutable.
        remote_name = f"{stamp} - {digest[:16]} - {filename}"
        remote = f"{ONEDRIVE_ROOT}/{deal_folder_name(deal)}/{CATEGORIES[category]}/{remote_name}"
        item = {
            "deal_id": deal_id,
            "category": category,
            "document_number": clean(document_number),
            "filename": filename,
            "onedrive_remote": remote,
            "sha256": digest,
            "archived_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            'status':'pending',
        }
        registry.setdefault("documents", []).append(item)
        save_registry(registry)
        copier(path, remote)
        item['status']='uploaded'; save_registry(registry)
        return {**item, "ok": True, "duplicate": False}


def main():
    request = json.load(sys.stdin)
    if request.get("action") != "archive":
        raise ValueError("поддерживается только действие archive")
    result = archive_document(
        request["deal_id"], request["path"], request["category"],
        request.get("document_number") or "", request.get("display_name") or "",
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        raise
