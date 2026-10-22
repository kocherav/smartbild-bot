#!/usr/bin/env python3
"""
Apply a new КЕМИКС price snapshot to kemix_prices.json, with a diff report.

This is a FIXED, bridge-mediated script (same security pattern as generate_kp.py) -
Claude never gets Write/Bash access to update pricing itself. Instead: the owner sends
a fresh КЕМИКС price-list PDF to the Telegram bot; Claude reads it with its own Read
tool (already in ALLOWED_TOOLS, handles PDFs natively - confirmed reliable, this is how
the original prices were extracted); Claude then emits an UPDATE_KEMIX_PRICES_BEGIN/END
marker containing the prices it found for our fixed set of tracked SKUs; the bridge
extracts that JSON and runs this script on it. This script only ever writes
kemix_prices.json - a plain data file, not code - and only accepts a fixed schema.

Usage: update_kemix_prices.py <spec.json>

Spec format (what Claude is instructed to emit - see SYSTEM_PROMPT in bridge.py):
{
  "pipe_price_per_m": {"6.35": 175.20, "9.52": 290.00, ...},   (any subset of the 5 keys
                                                                 in kemix_prices.json;
                                                                 omit ones not found)
  "insulation_price_per_m": {"6": 38.00, ...},
  "cable_price_per_m": 160.00,
  "cable_price_per_m_gost": 215.00,
  "not_found": ["19.05mm pipe", ...]   (optional - labels of tracked items Claude could
                                         NOT find in the new price list, surfaced as a
                                         warning rather than silently keeping stale data)
}

Prints a JSON diff to stdout: {"ok": true, "changes": [{"item": ..., "old": ..., "new":
..., "pct": ...}], "unchanged": [...], "not_found": [...]} or {"ok": false, "error": ...}.
"""
import datetime
import json
import os
import sys
import math
import tempfile
import fcntl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_FILE = os.path.join(BASE_DIR, "kemix_prices.json")


def die(msg):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(1)


def load_current():
    with open(PRICES_FILE, encoding="utf-8") as f:
        return json.load(f)


def apply_update(current, new_spec):
    new_spec=dict(new_spec)
    for key in ('pipe_price_per_m','insulation_price_per_m','cable_price_per_m','cable_price_per_m_gost'):
        if key not in new_spec: continue
        values=new_spec[key]
        if isinstance(values,dict):
            values={k:float(v) for k,v in values.items()}
            prices=list(values.values())
        else:
            values=float(values); prices=[values]
        if any(not math.isfinite(v) or v<=0 for v in prices):
            raise ValueError('Цены должны быть конечными положительными числами')
        new_spec[key]=values
    changes = []
    unchanged = []

    for mm_str, new_price in (new_spec.get("pipe_price_per_m") or {}).items():
        entry = current.setdefault("pipe_price_per_m", {}).get(mm_str)
        if entry is None:
            continue  # unknown key, not one of our tracked diameters - ignore, don't invent
        old_price = entry["price"]
        entry["price"] = float(new_price)
        if abs(old_price - new_price) > 0.005:
            pct = round((new_price - old_price) / old_price * 100, 1) if old_price else None
            changes.append({"item": f"труба {mm_str}мм", "old": old_price, "new": new_price, "pct": pct})
        else:
            unchanged.append(f"труба {mm_str}мм")

    for id_str, new_price in (new_spec.get("insulation_price_per_m") or {}).items():
        entry = current.setdefault("insulation_price_per_m", {}).get(id_str)
        if entry is None:
            continue
        old_price = entry["price"]
        entry["price"] = float(new_price)
        if abs(old_price - new_price) > 0.005:
            pct = round((new_price - old_price) / old_price * 100, 1) if old_price else None
            changes.append({"item": f"изоляция ID{id_str}мм", "old": old_price, "new": new_price, "pct": pct})
        else:
            unchanged.append(f"изоляция ID{id_str}мм")

    cable = current.setdefault("cable", {})
    if "cable_price_per_m" in new_spec:
        old_price = cable.get("price_per_m")
        new_price = float(new_spec["cable_price_per_m"])
        cable["price_per_m"] = new_price
        if old_price is not None and abs(old_price - new_price) > 0.005:
            pct = round((new_price - old_price) / old_price * 100, 1) if old_price else None
            changes.append({"item": "кабель ВВГнг LS 5х2,5", "old": old_price, "new": new_price, "pct": pct})
        else:
            unchanged.append("кабель ВВГнг LS 5х2,5")
    if "cable_price_per_m_gost" in new_spec:
        old_price = cable.get("price_per_m_gost")
        new_price = float(new_spec["cable_price_per_m_gost"])
        cable["price_per_m_gost"] = new_price
        if old_price is not None and abs(old_price - new_price) > 0.005:
            pct = round((new_price - old_price) / old_price * 100, 1) if old_price else None
            changes.append({"item": "кабель ГОСТ", "old": old_price, "new": new_price, "pct": pct})
        else:
            unchanged.append("кабель ГОСТ")

    current["updated_at"] = datetime.date.today().isoformat()
    current["source_note"] = (
        f"Updated via Telegram bot (owner uploaded a fresh price-list PDF), "
        f"{datetime.date.today().isoformat()}."
    )
    return current, changes, unchanged


def save_update(spec):
    with open(PRICES_FILE+'.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        updated,changes,unchanged=apply_update(load_current(),spec)
        fd,path=tempfile.mkstemp(prefix='.kemix-',dir=os.path.dirname(PRICES_FILE))
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as target:
                json.dump(updated,target,ensure_ascii=False,indent=2,allow_nan=False)
                target.flush(); os.fsync(target.fileno())
            os.replace(path,PRICES_FILE)
        finally:
            if os.path.exists(path): os.unlink(path)
    return updated,changes,unchanged


if __name__ == "__main__":
    if len(sys.argv) != 2:
        die("usage: update_kemix_prices.py <spec.json>")
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as e:
        die(f"could not read spec: {e}")

    try:
        current = load_current()
    except Exception as e:
        die(f"could not read {PRICES_FILE}: {e}")

    updated, changes, unchanged = save_update(spec)

    print(json.dumps({
        "ok": True,
        "changes": changes,
        "unchanged": unchanged,
        "not_found": spec.get("not_found") or [],
        "updated_at": updated["updated_at"],
    }, ensure_ascii=False))
