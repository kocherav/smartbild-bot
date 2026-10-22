#!/usr/bin/env python3
"""Persistent contract signatory profiles keyed by the Megaplan payer ID."""
import fcntl
import json
import os
from pathlib import Path


STORE_PATH = Path(__file__).resolve().parent / "payer_signatories.json"
LOCK_PATH = Path(__file__).resolve().parent / ".payer_signatories.lock"


def _read(path):
    try:
        with open(path, encoding="utf-8") as source:
            value = json.load(source)
            return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_signatory(payer_id, path=None):
    data = _read(Path(path) if path else STORE_PATH)
    profile = data.get(str(payer_id)) or {}
    return {key: str(profile.get(key) or "").strip()
            for key in ("name", "position", "authority")}


def save_signatory(payer_id, name, position, authority, path=None, lock_path=None):
    payer_id = str(payer_id or "").strip()
    profile = {"name": str(name or "").strip(),
               "position": str(position or "").strip(),
               "authority": str(authority or "").strip()}
    if not payer_id or not all(profile.values()):
        raise ValueError("для профиля подписанта нужны плательщик, ФИО, должность и основание полномочий")
    target = Path(path) if path else STORE_PATH
    lock = Path(lock_path) if lock_path else LOCK_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "w", encoding="utf-8") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        data = _read(target)
        data[payer_id] = profile
        temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        with open(temporary, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    return profile
