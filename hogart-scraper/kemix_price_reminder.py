#!/usr/bin/env python3
"""
Checks kemix_prices.json staleness and nags the owner in Telegram if it's gotten old
(owner's rule, 2026-08-22: "раз в полтора месяца" -> 45 days). Meant to run frequently
(e.g. weekly, via the kemix-price-reminder.timer systemd unit) - the staleness check
inside decouples "how often we look" from "how often we actually message the owner", so
a manual price update in between naturally resets the clock without touching the timer.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipe_reference import kemix_prices_age_days

STALE_AFTER_DAYS = 45
ENV_FILE = os.path.expanduser("~/telegram-bridge/.env")


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


if __name__ == "__main__":
    age = kemix_prices_age_days()
    if age is not None and age < STALE_AFTER_DAYS:
        print(f"kemix prices are {age} days old (< {STALE_AFTER_DAYS}), nothing to do")
        sys.exit(0)

    env = load_env()
    token = env["TELEGRAM_BOT_TOKEN"]
    chat_id = env["TELEGRAM_CHAT_ID"]
    age_str = f"{age} дн." if age is not None else "неизвестно сколько (дата обновления не читается)"
    text = (
        "Пора обновить цены КЕМИКС для расчёта себестоимости фреоновой магистрали "
        f"(текущие данные — {age_str}). Пришли сюда свежий прайс-лист КЕМИКС (PDF) — "
        "я сам найду нужные позиции и обновлю расчёт."
    )
    resp = send_message(token, chat_id, text)
    print("sent:", resp.get("ok"), resp if not resp.get("ok") else "")
