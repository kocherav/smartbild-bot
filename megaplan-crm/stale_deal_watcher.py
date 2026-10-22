#!/usr/bin/env python3
"""
Daily digest of "stuck" bot-created deals - positions still unresolved ("[ЖДЁТ ЦЕНЫ]",
price_source == "unresolved") or only partially covered by supplier invoices so far
(consumed_qty < qty - see megaplan_api.py's _accumulate_position) on a deal that's been
open STALE_AFTER_DAYS+ without getting fully resolved. Owner's rule (2026-08-24): 3
days, checked once a day - same "check often, nag only when actually stale" decoupling
as hogart-scraper/kemix_price_reminder.py (a manual resolution in between naturally
stops that deal appearing next run, no watermark/timer state to manage here).

Purely a local-bookkeeping report - reads recent_deals.json (deal age) and each deal's
own ledger.json (position state), no live Мегаплан API calls needed.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deal_ledger

STALE_AFTER_DAYS = 3
ENV_FILE = os.path.expanduser("~/telegram-bridge/.env")
MAX_PROBLEMS_PER_DEAL = 10


def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def send_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    with urllib.request.urlopen(url, data=data, timeout=20) as resp:
        return json.loads(resp.read().decode())


def stuck_positions(entries):
    """Short description strings for positions still needing attention - unresolved
    (no price found anywhere yet) or partially covered by supplier invoices (real
    consumed quantity short of the original spec quantity)."""
    problems = []
    for e in entries:
        if e.get("price_source") == "unresolved":
            problems.append(f"«{e['name']}» — цена не найдена (0₽)")
            continue
        consumed = e.get("consumed_qty")
        qty = e.get("qty")
        if consumed is not None and qty and consumed < qty - 1e-9:
            problems.append(f"«{e['name']}» — покрыто {consumed:g} из {qty:g} по счетам поставщиков")
    return problems


def build_digest():
    now = time.time()
    lines = []
    for d in deal_ledger.list_recent_deals(n=deal_ledger.MAX_RECENT_DEALS):
        age_days = (now - d["created_at"]) / 86400
        if age_days < STALE_AFTER_DAYS:
            continue
        problems = stuck_positions(deal_ledger.load(d["deal_id"]))
        if not problems:
            continue
        lines.append(f"Сделка {d['deal_id']} ({d.get('client_name', '?')}, {age_days:.0f} дн.):")
        for p in problems[:MAX_PROBLEMS_PER_DEAL]:
            lines.append(f"  - {p}")
        if len(problems) > MAX_PROBLEMS_PER_DEAL:
            lines.append(f"  ...и ещё {len(problems) - MAX_PROBLEMS_PER_DEAL}")
    return lines


if __name__ == "__main__":
    digest_lines = build_digest()
    if not digest_lines:
        print("no stuck deals, nothing to send")
        sys.exit(0)

    env = load_env()
    token = env["TELEGRAM_BOT_TOKEN"]
    chat_id = env["TELEGRAM_CHAT_ID"]
    text = (
        f"Незакрытые позиции в сделках (открыты {STALE_AFTER_DAYS}+ дн.):\n\n"
        + "\n".join(digest_lines)
    )
    resp = send_message(token, chat_id, text)
    print("sent:", resp.get("ok"), resp if not resp.get("ok") else "")
