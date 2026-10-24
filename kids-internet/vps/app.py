#!/usr/bin/env python3
"""SmartBild Kids Internet Bot.

Runs on a VPS, talks to Telegram via long polling, and exposes a small
mutually authenticated-by-secret HTTPS API polled by MikroTik RouterOS 6.
Only Python's standard library is used.
"""
from __future__ import annotations

import argparse
import html
import ipaddress
import http.server
import json
import logging
import os
import re
import secrets
import signal
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

VERSION = "2.1.0"
LOG = logging.getLogger("smartbild-kidsbot")
DB_LOCK = threading.RLock()
MAC_RE = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){5}$")
STOP = threading.Event()


@dataclass(frozen=True)
class ScheduleWindow:
    warning_at: datetime
    cutoff_at: datetime
    extension_end: datetime


def schedule_for_date(day: datetime) -> ScheduleWindow:
    """Return the schedule for the local calendar date containing *day*.

    Monday-Thursday and Sunday: 22:50 warning, 23:00 cutoff, 23:30 end.
    Friday-Saturday: 23:50 warning, 00:00 next-day cutoff, 00:30 end.
    """
    local = day
    weekday = local.weekday()  # Mon=0 ... Sun=6
    if weekday in (4, 5):
        warning = local.replace(hour=23, minute=50, second=0, microsecond=0)
        cutoff = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        warning = local.replace(hour=22, minute=50, second=0, microsecond=0)
        cutoff = local.replace(hour=23, minute=0, second=0, microsecond=0)
    return ScheduleWindow(warning, cutoff, cutoff + timedelta(minutes=30))


def current_or_recent_window(now: datetime) -> ScheduleWindow:
    """Return the schedule window relevant to a request made around midnight."""
    candidates = [schedule_for_date(now), schedule_for_date(now - timedelta(days=1))]
    valid = [w for w in candidates if w.warning_at - timedelta(minutes=5) <= now < w.extension_end]
    if valid:
        return max(valid, key=lambda w: w.warning_at)
    return schedule_for_date(now)


def format_hhmm(ts: int, tz: ZoneInfo) -> str:
    return datetime.fromtimestamp(ts, tz).strftime("%H:%M")


def duration_hms(seconds: int) -> str:
    seconds = max(0, min(int(seconds), 86399))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class Store:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def conn(self):
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _init_db(self) -> None:
        with DB_LOCK, self.conn() as con:
            con.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    tg_id INTEGER PRIMARY KEY,
                    role TEXT NOT NULL CHECK(role IN ('parent','child')),
                    first_name TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac TEXT NOT NULL UNIQUE,
                    ip TEXT NOT NULL DEFAULT '',
                    hostname TEXT NOT NULL DEFAULT '',
                    lease_status TEXT NOT NULL DEFAULT '',
                    child_tg_id INTEGER,
                    label TEXT NOT NULL DEFAULT '',
                    last_seen INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(child_tg_id) REFERENCES users(tg_id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    child_tg_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    requested_at INTEGER NOT NULL,
                    cutoff_ts INTEGER NOT NULL,
                    end_ts INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','approved','denied','expired')),
                    parent_message_id INTEGER,
                    child_message_id INTEGER,
                    UNIQUE(device_id, cutoff_ts),
                    FOREIGN KEY(child_tg_id) REFERENCES users(tg_id),
                    FOREIGN KEY(device_id) REFERENCES devices(id)
                );
                CREATE TABLE IF NOT EXISTS extensions (
                    device_id INTEGER PRIMARY KEY,
                    end_ts INTEGER NOT NULL,
                    request_id INTEGER NOT NULL,
                    approved_at INTEGER NOT NULL,
                    FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE,
                    FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    key TEXT PRIMARY KEY,
                    sent_at INTEGER NOT NULL
                );
                """
            )
            row = con.execute("SELECT value FROM settings WHERE key='state_version'").fetchone()
            if row is None:
                self.set_setting("state_version", "1", con=con)

    def get_setting(self, key: str) -> Optional[str]:
        with self.conn() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return None if row is None else str(row[0])

    def set_setting(self, key: str, value: str, con=None) -> None:
        if con is not None:
            con.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            return
        with DB_LOCK, self.conn() as own:
            self.set_setting(key, value, con=own)

    def bump_state(self, con=None) -> int:
        if con is None:
            with DB_LOCK, self.conn() as own:
                return self.bump_state(con=own)
        row = con.execute("SELECT value FROM settings WHERE key='state_version'").fetchone()
        value = int(row[0]) + 1 if row else 1
        self.set_setting("state_version", str(value), con=con)
        return value

    def parent_id(self) -> Optional[int]:
        value = self.get_setting("parent_id")
        return int(value) if value else None

    def claim_parent(self, tg_id: int, first_name: str, username: str) -> bool:
        with DB_LOCK, self.conn() as con:
            row = con.execute("SELECT value FROM settings WHERE key='parent_id'").fetchone()
            if row is not None and int(row[0]) != tg_id:
                return False
            now = int(time.time())
            con.execute(
                "INSERT INTO users(tg_id,role,first_name,username,created_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(tg_id) DO UPDATE SET role='parent',first_name=excluded.first_name,username=excluded.username",
                (tg_id, "parent", first_name, username, now),
            )
            self.set_setting("parent_id", str(tg_id), con=con)
            return True

    def upsert_child(self, tg_id: int, first_name: str, username: str) -> None:
        with DB_LOCK, self.conn() as con:
            con.execute(
                "INSERT INTO users(tg_id,role,first_name,username,created_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(tg_id) DO UPDATE SET role='child',first_name=excluded.first_name,username=excluded.username",
                (tg_id, "child", first_name, username, int(time.time())),
            )

    def user(self, tg_id: int):
        with self.conn() as con:
            return con.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()

    def children(self):
        with self.conn() as con:
            return con.execute("SELECT * FROM users WHERE role='child' ORDER BY first_name,tg_id").fetchall()

    def sync_leases(self, leases: Sequence[Tuple[str, str, str, str]], complete: bool = False) -> int:
        """Update the DHCP inventory received from MikroTik.

        A complete snapshot lets us clear stale addresses safely. Assigned devices
        bump the router state whenever their IPv4 address or lease state changes.
        """
        now = int(time.time())
        changed = False
        seen: set[str] = set()
        with DB_LOCK, self.conn() as con:
            for mac, ip, hostname, status in leases:
                mac = mac.upper().strip()
                ip = ip.strip()
                status = status.strip().lower()
                if not mac:
                    continue
                if ip:
                    try:
                        parsed = ipaddress.ip_address(ip)
                        if parsed.version != 4:
                            ip = ""
                    except ValueError:
                        ip = ""
                seen.add(mac)
                row = con.execute("SELECT ip,hostname,lease_status,child_tg_id FROM devices WHERE mac=?", (mac,)).fetchone()
                if row is None:
                    con.execute(
                        "INSERT INTO devices(mac,ip,hostname,lease_status,last_seen) VALUES(?,?,?,?,?)",
                        (mac, ip, hostname, status, now),
                    )
                else:
                    if row["child_tg_id"] is not None and (row["ip"] != ip or str(row["lease_status"]).lower() != status):
                        changed = True
                    con.execute(
                        "UPDATE devices SET ip=?,hostname=?,lease_status=?,last_seen=? WHERE mac=?",
                        (ip, hostname, status, now, mac),
                    )
            if complete:
                rows = con.execute("SELECT mac,ip,lease_status,child_tg_id FROM devices").fetchall()
                for row in rows:
                    if str(row["mac"]).upper() in seen:
                        continue
                    if row["child_tg_id"] is not None and (row["ip"] or row["lease_status"] != "missing"):
                        changed = True
                    con.execute(
                        "UPDATE devices SET ip='',lease_status='missing' WHERE mac=?",
                        (row["mac"],),
                    )
            if changed:
                self.bump_state(con=con)
        return len(leases)

    def all_devices(self):
        with self.conn() as con:
            return con.execute(
                "SELECT d.*,u.first_name AS child_name FROM devices d "
                "LEFT JOIN users u ON u.tg_id=d.child_tg_id "
                "ORDER BY CASE WHEN d.child_tg_id IS NULL THEN 0 ELSE 1 END, d.last_seen DESC, d.hostname"
            ).fetchall()

    def child_devices(self, child_id: int):
        with self.conn() as con:
            return con.execute(
                "SELECT * FROM devices WHERE child_tg_id=? ORDER BY hostname,ip", (child_id,)
            ).fetchall()

    def device(self, device_id: int):
        with self.conn() as con:
            return con.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()

    def assign_device(self, device_id: int, child_id: Optional[int]) -> None:
        with DB_LOCK, self.conn() as con:
            con.execute("UPDATE devices SET child_tg_id=? WHERE id=?", (child_id, device_id))
            self.bump_state(con=con)

    def managed_state(self) -> Tuple[int, List[str], List[Tuple[str, int]]]:
        now = int(time.time())
        with DB_LOCK, self.conn() as con:
            expired = con.execute("DELETE FROM extensions WHERE end_ts<=?", (now,)).rowcount
            if expired:
                self.bump_state(con=con)
            # Assigned devices stay managed regardless of DHCP state: a sleeping
            # device goes to `waiting` but wakes up with the same static lease.
            rows = con.execute(
                "SELECT DISTINCT ip FROM devices WHERE child_tg_id IS NOT NULL AND ip<>'' ORDER BY ip"
            ).fetchall()
            kids = [str(r[0]) for r in rows]
            ext_rows = con.execute(
                "SELECT d.ip,e.end_ts FROM extensions e JOIN devices d ON d.id=e.device_id "
                "WHERE e.end_ts>? AND d.ip<>'' ORDER BY d.ip",
                (now,),
            ).fetchall()
            exts = [(str(r[0]), int(r[1]) - now) for r in ext_rows]
            ver_row = con.execute("SELECT value FROM settings WHERE key='state_version'").fetchone()
            version = int(ver_row[0]) if ver_row else 1
            return version, kids, exts

    def managed_macs(self) -> List[str]:
        """MACs of all assigned devices; the router blocks them by L2 address,
        so neither DHCP state nor a manually configured IP lets them out."""
        with self.conn() as con:
            rows = con.execute(
                "SELECT DISTINCT upper(mac) FROM devices WHERE child_tg_id IS NOT NULL ORDER BY 1"
            ).fetchall()
        return [str(r[0]) for r in rows if MAC_RE.match(str(r[0]))]

    def notification_sent(self, key: str) -> bool:
        with self.conn() as con:
            return con.execute("SELECT 1 FROM notifications WHERE key=?", (key,)).fetchone() is not None

    def mark_notification(self, key: str) -> None:
        with DB_LOCK, self.conn() as con:
            con.execute("INSERT OR IGNORE INTO notifications(key,sent_at) VALUES(?,?)", (key, int(time.time())))

    def create_request(self, child_id: int, device_id: int, cutoff_ts: int, end_ts: int) -> Tuple[str, int]:
        now = int(time.time())
        with DB_LOCK, self.conn() as con:
            row = con.execute(
                "SELECT id,status FROM requests WHERE device_id=? AND cutoff_ts=?",
                (device_id, cutoff_ts),
            ).fetchone()
            if row:
                existing = str(row["status"])
                return ("already_pending" if existing == "pending" else existing), int(row["id"])
            cur = con.execute(
                "INSERT INTO requests(child_tg_id,device_id,requested_at,cutoff_ts,end_ts,status) "
                "VALUES(?,?,?,?,?,'pending')",
                (child_id, device_id, now, cutoff_ts, end_ts),
            )
            return "pending", int(cur.lastrowid)

    def request(self, request_id: int):
        with self.conn() as con:
            return con.execute(
                "SELECT r.*,d.ip,d.hostname,d.label,d.mac,u.first_name AS child_name "
                "FROM requests r JOIN devices d ON d.id=r.device_id "
                "JOIN users u ON u.tg_id=r.child_tg_id WHERE r.id=?",
                (request_id,),
            ).fetchone()

    def set_request_message(self, request_id: int, parent_message_id: int) -> None:
        with DB_LOCK, self.conn() as con:
            con.execute("UPDATE requests SET parent_message_id=? WHERE id=?", (parent_message_id, request_id))

    def decide_request(self, request_id: int, approve: bool) -> Tuple[str, Optional[sqlite3.Row]]:
        now = int(time.time())
        with DB_LOCK, self.conn() as con:
            row = con.execute(
                "SELECT r.*,d.ip,d.hostname,d.label,d.mac,u.first_name AS child_name "
                "FROM requests r JOIN devices d ON d.id=r.device_id "
                "JOIN users u ON u.tg_id=r.child_tg_id WHERE r.id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                return "missing", None
            if row["status"] != "pending":
                return str(row["status"]), row
            if now >= int(row["end_ts"]):
                con.execute("UPDATE requests SET status='expired' WHERE id=?", (request_id,))
                return "expired", row
            if not approve:
                con.execute("UPDATE requests SET status='denied' WHERE id=?", (request_id,))
                return "denied", row
            con.execute("UPDATE requests SET status='approved' WHERE id=?", (request_id,))
            con.execute(
                "INSERT INTO extensions(device_id,end_ts,request_id,approved_at) VALUES(?,?,?,?) "
                "ON CONFLICT(device_id) DO UPDATE SET end_ts=excluded.end_ts,request_id=excluded.request_id,approved_at=excluded.approved_at",
                (int(row["device_id"]), int(row["end_ts"]), request_id, now),
            )
            self.bump_state(con=con)
            return "approved", row

    def health_stats(self) -> Dict[str, int]:
        with self.conn() as con:
            devices = int(con.execute("SELECT COUNT(*) FROM devices").fetchone()[0])
            children = int(con.execute("SELECT COUNT(*) FROM users WHERE role='child'").fetchone()[0])
            parent = 1 if con.execute("SELECT 1 FROM settings WHERE key='parent_id'").fetchone() else 0
            active_extensions = int(con.execute("SELECT COUNT(*) FROM extensions WHERE end_ts>?", (int(time.time()),)).fetchone()[0])
            return {"devices": devices, "children": children, "parent": parent, "active_extensions": active_extensions}

    def status_lines(self, tz: ZoneInfo) -> List[str]:
        now = int(time.time())
        lines: List[str] = []
        with self.conn() as con:
            children = con.execute("SELECT * FROM users WHERE role='child' ORDER BY first_name").fetchall()
            for child in children:
                devices = con.execute(
                    "SELECT d.*,e.end_ts FROM devices d LEFT JOIN extensions e ON e.device_id=d.id AND e.end_ts>? "
                    "WHERE d.child_tg_id=? ORDER BY d.hostname,d.ip",
                    (now, int(child["tg_id"])),
                ).fetchall()
                lines.append(f"👤 {child['first_name'] or child['tg_id']}")
                if not devices:
                    lines.append("  — устройства не назначены")
                for d in devices:
                    name = device_name(d)
                    if d["end_ts"]:
                        state = f"продлено до {format_hhmm(int(d['end_ts']), tz)}"
                    else:
                        state = "по расписанию"
                    lines.append(f"  • {name} — {state}")
        if not lines:
            lines.append("Дети пока не зарегистрированы.")
        return lines


def device_name(row: sqlite3.Row) -> str:
    label = str(row["label"] or "").strip()
    host = str(row["hostname"] or "").strip()
    ip = str(row["ip"] or "").strip()
    mac = str(row["mac"] or "")
    return label or host or ip or mac


class Telegram:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 45) -> Any:
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base + method,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": f"SmartBildKidsBot/{VERSION}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not data.get("ok"):
            raise RuntimeError(data.get("description", "Telegram API error"))
        return data.get("result")

    def send(self, chat_id: int, text: str, keyboard: Optional[List[List[Dict[str, str]]]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        return self.call("sendMessage", payload)

    def edit(self, chat_id: int, message_id: int, text: str, keyboard=None) -> None:
        payload: Dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        try:
            self.call("editMessageText", payload)
        except Exception as exc:
            LOG.debug("editMessageText failed: %s", exc)

    def answer_callback(self, callback_id: str, text: str = "", alert: bool = False) -> None:
        try:
            self.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text, "show_alert": alert})
        except Exception as exc:
            LOG.debug("answerCallbackQuery failed: %s", exc)


class KidsBot:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.tz = ZoneInfo(config.get("timezone", "Europe/Moscow"))
        self.store = Store(config["db_path"])
        self.telegram = Telegram(config["bot_token"])
        self.bot_username = config["bot_username"]
        self.owner_token = config["owner_token"]
        self.child_invite = config["child_invite"]
        self.router_secret = config["router_secret"]

    def owner_link(self) -> str:
        return f"https://t.me/{self.bot_username}?start=owner_{self.owner_token}"

    def child_link(self) -> str:
        return f"https://t.me/{self.bot_username}?start=child_{self.child_invite}"

    def run(self) -> None:
        threading.Thread(target=self.scheduler_loop, name="scheduler", daemon=True).start()
        threading.Thread(target=self.serve_http, name="http-api", daemon=True).start()
        try:
            self.telegram.call("deleteWebhook", {"drop_pending_updates": False})
        except Exception as exc:
            LOG.warning("Could not delete Telegram webhook at startup: %s", exc)
        self.poll_loop()

    def poll_loop(self) -> None:
        offset = int(self.store.get_setting("update_offset") or "0")
        LOG.info("Telegram polling started at offset %s", offset)
        while not STOP.is_set():
            try:
                updates = self.telegram.call(
                    "getUpdates",
                    {"offset": offset, "timeout": 30, "allowed_updates": ["message", "callback_query"]},
                    timeout=40,
                )
                for update in updates:
                    update_id = int(update["update_id"])
                    try:
                        self.handle_update(update)
                    except Exception:
                        LOG.exception("Failed to handle update %s", update_id)
                    offset = max(offset, update_id + 1)
                    self.store.set_setting("update_offset", str(offset))
            except Exception as exc:
                LOG.warning("Telegram polling error: %s", exc)
                STOP.wait(5)

    @staticmethod
    def sender(update_obj: Dict[str, Any]) -> Tuple[int, str, str]:
        user = update_obj.get("from", {})
        return int(user.get("id", 0)), str(user.get("first_name", "")), str(user.get("username", ""))

    def handle_update(self, update: Dict[str, Any]) -> None:
        if "message" in update:
            self.handle_message(update["message"])
        elif "callback_query" in update:
            self.handle_callback(update["callback_query"])

    def handle_message(self, message: Dict[str, Any]) -> None:
        chat = message.get("chat", {})
        if chat.get("type") != "private":
            return
        chat_id = int(chat["id"])
        sender = message.get("from", {})
        tg_id = int(sender.get("id", 0))
        text = str(message.get("text", "")).strip()
        first_name = str(sender.get("first_name", ""))
        username = str(sender.get("username", ""))
        if text.startswith("/start"):
            arg = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
            self.handle_start(chat_id, tg_id, first_name, username, arg)
            return
        user = self.store.user(tg_id)
        if user is None:
            self.telegram.send(chat_id, "Этот бот работает только по семейной ссылке. Попросите ссылку у родителя.")
            return
        if user["role"] == "parent":
            self.send_parent_menu(chat_id)
        else:
            self.send_child_status(chat_id, tg_id)

    def handle_start(self, chat_id: int, tg_id: int, first_name: str, username: str, arg: str) -> None:
        if arg == f"owner_{self.owner_token}":
            if self.store.claim_parent(tg_id, first_name, username):
                self.telegram.send(
                    chat_id,
                    "✅ Вы зарегистрированы как родитель-администратор SmartBild Kids Internet.\n\n"
                    "Базовое расписание работает на MikroTik, а бот отвечает за предупреждения и продления.",
                )
                self.send_parent_menu(chat_id)
            else:
                self.telegram.send(chat_id, "Родитель-администратор уже зарегистрирован.")
            return
        if arg == f"child_{self.child_invite}":
            parent = self.store.parent_id()
            if parent is None:
                self.telegram.send(chat_id, "Сначала родитель должен завершить регистрацию.")
                return
            if parent == tg_id:
                self.send_parent_menu(chat_id)
                return
            self.store.upsert_child(tg_id, first_name, username)
            self.telegram.send(
                chat_id,
                "✅ Вы подключены к семейному контролю интернета.\n"
                "За 10 минут до отключения здесь появится кнопка запроса продления.",
            )
            keyboard = [[{"text": "📱 Назначить устройства", "callback_data": f"p:assign:{tg_id}"}]]
            self.telegram.send(parent, f"👤 Подключился ребёнок: {first_name or tg_id}", keyboard)
            return
        user = self.store.user(tg_id)
        if user is not None:
            if user["role"] == "parent":
                self.send_parent_menu(chat_id)
            else:
                self.send_child_status(chat_id, tg_id)
            return
        self.telegram.send(chat_id, "Откройте персональную ссылку регистрации, полученную при установке или от родителя.")

    def send_parent_menu(self, chat_id: int) -> None:
        keyboard = [
            [{"text": "👨‍👩‍👧 Дети и устройства", "callback_data": "p:children"}],
            [
                {"text": "🔗 Пригласить ребёнка", "callback_data": "p:invite"},
                {"text": "📊 Статус", "callback_data": "p:status"},
            ],
            [{"text": "📱 Все устройства", "callback_data": "p:devices"}],
        ]
        self.telegram.send(chat_id, "SmartBild Kids Internet — управление", keyboard)

    def send_child_status(self, chat_id: int, child_id: int) -> None:
        devices = self.store.child_devices(child_id)
        if not devices:
            self.telegram.send(chat_id, "Устройства пока не назначены. Родителю уже доступна кнопка назначения.")
            return
        names = "\n".join(f"• {device_name(d)} ({d['ip']})" for d in devices)
        self.telegram.send(chat_id, "Ваши устройства:\n" + names)

    def handle_callback(self, callback: Dict[str, Any]) -> None:
        cb_id = str(callback.get("id", ""))
        tg_id, first_name, username = self.sender(callback)
        data = str(callback.get("data", ""))
        message = callback.get("message") or {}
        chat_id = int((message.get("chat") or {}).get("id", tg_id))
        message_id = int(message.get("message_id", 0))
        user = self.store.user(tg_id)
        if data.startswith("p:"):
            if user is None or user["role"] != "parent" or self.store.parent_id() != tg_id:
                self.telegram.answer_callback(cb_id, "Только родитель может выполнить это действие.", True)
                return
            self.handle_parent_callback(cb_id, chat_id, message_id, data)
            return
        if data.startswith("c:"):
            if user is None or user["role"] != "child":
                self.telegram.answer_callback(cb_id, "Кнопка доступна только ребёнку.", True)
                return
            self.handle_child_callback(cb_id, chat_id, tg_id, data)
            return
        self.telegram.answer_callback(cb_id, "Неизвестная команда.")

    def handle_parent_callback(self, cb_id: str, chat_id: int, message_id: int, data: str) -> None:
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        if action == "invite":
            self.telegram.answer_callback(cb_id)
            self.telegram.send(
                chat_id,
                "Отправьте ребёнку эту персональную ссылку:\n\n" + self.child_link() +
                "\n\nПосле нажатия Start вы сможете назначить ему устройства.",
            )
        elif action == "status":
            self.telegram.answer_callback(cb_id)
            self.telegram.send(chat_id, "📊 Текущий статус\n\n" + "\n".join(self.store.status_lines(self.tz)))
        elif action == "children":
            self.telegram.answer_callback(cb_id)
            children = self.store.children()
            if not children:
                self.telegram.send(chat_id, "Дети пока не подключены.\n\nСсылка:\n" + self.child_link())
                return
            keyboard = [
                [{"text": f"👤 {c['first_name'] or c['tg_id']}", "callback_data": f"p:assign:{c['tg_id']}"}]
                for c in children
            ]
            self.telegram.send(chat_id, "Выберите ребёнка для назначения устройств:", keyboard)
        elif action == "devices":
            self.telegram.answer_callback(cb_id)
            devices = self.store.all_devices()
            if not devices:
                self.telegram.send(chat_id, "MikroTik ещё не передал DHCP-устройства. Подождите около минуты.")
                return
            lines = []
            for d in devices[:60]:
                owner = f" → {d['child_name']}" if d["child_name"] else ""
                lines.append(f"• {device_name(d)} | {d['ip']} | {d['mac']}{owner}")
            self.telegram.send(chat_id, "📱 Устройства MikroTik\n\n" + "\n".join(lines))
        elif action == "assign" and len(parts) == 3:
            self.telegram.answer_callback(cb_id)
            self.show_assignment(chat_id, int(parts[2]))
        elif action == "toggle" and len(parts) == 4:
            child_id, device_id = int(parts[2]), int(parts[3])
            device = self.store.device(device_id)
            if device is None:
                self.telegram.answer_callback(cb_id, "Устройство не найдено.", True)
                return
            new_owner = None if device["child_tg_id"] == child_id else child_id
            self.store.assign_device(device_id, new_owner)
            self.telegram.answer_callback(cb_id, "Назначение обновлено")
            self.show_assignment(chat_id, child_id)
        elif action == "approve" and len(parts) == 3:
            request_id = int(parts[2])
            state, row = self.store.decide_request(request_id, approve=True)
            if row is None:
                self.telegram.answer_callback(cb_id, "Запрос не найден.", True)
                return
            if state == "approved":
                end_text = format_hhmm(int(row["end_ts"]), self.tz)
                name = device_name(row)
                self.telegram.answer_callback(cb_id, f"Продлено до {end_text}")
                self.telegram.edit(chat_id, message_id, f"✅ {row['child_name']}: {name} продлён до {end_text}.")
                self.telegram.send(int(row["child_tg_id"]), f"✅ Интернет для «{name}» продлён до {end_text}.")
            elif state == "expired":
                self.telegram.answer_callback(cb_id, "Срок продления уже закончился.", True)
                self.telegram.edit(chat_id, message_id, "⌛ Запрос просрочен.")
            else:
                self.telegram.answer_callback(cb_id, f"Запрос уже обработан: {state}", True)
        elif action == "deny" and len(parts) == 3:
            request_id = int(parts[2])
            state, row = self.store.decide_request(request_id, approve=False)
            if row is None:
                self.telegram.answer_callback(cb_id, "Запрос не найден.", True)
                return
            if state == "denied":
                name = device_name(row)
                self.telegram.answer_callback(cb_id, "Отказ отправлен")
                self.telegram.edit(chat_id, message_id, f"❌ Запрос отклонён: {row['child_name']} — {name}.")
                self.telegram.send(int(row["child_tg_id"]), f"❌ Продление для «{name}» не одобрено.")
            else:
                self.telegram.answer_callback(cb_id, f"Запрос уже обработан: {state}", True)
        else:
            self.telegram.answer_callback(cb_id, "Команда устарела.")

    def show_assignment(self, chat_id: int, child_id: int) -> None:
        child = self.store.user(child_id)
        if child is None or child["role"] != "child":
            self.telegram.send(chat_id, "Ребёнок не найден.")
            return
        devices = self.store.all_devices()
        if not devices:
            self.telegram.send(chat_id, "MikroTik ещё не передал DHCP-устройства. Подождите около минуты.")
            return
        keyboard: List[List[Dict[str, str]]] = []
        for d in devices[:45]:
            if d["child_tg_id"] == child_id:
                mark = "✅"
            elif d["child_tg_id"] is not None:
                mark = "👤"
            else:
                mark = "▫️"
            title = f"{mark} {device_name(d)} • {d['ip']}"
            keyboard.append([{"text": title[:60], "callback_data": f"p:toggle:{child_id}:{d['id']}"}])
        keyboard.append([{"text": "Готово", "callback_data": "p:children"}])
        self.telegram.send(
            chat_id,
            f"Назначение устройств: {child['first_name'] or child_id}\n"
            "✅ — назначено этому ребёнку; 👤 — назначено другому. Нажатие переключает назначение.",
            keyboard,
        )

    def handle_child_callback(self, cb_id: str, chat_id: int, child_id: int, data: str) -> None:
        parts = data.split(":")
        if len(parts) != 4 or parts[1] != "request":
            self.telegram.answer_callback(cb_id, "Кнопка устарела.")
            return
        device_id, cutoff_ts = int(parts[2]), int(parts[3])
        device = self.store.device(device_id)
        if device is None or device["child_tg_id"] != child_id:
            self.telegram.answer_callback(cb_id, "Это устройство вам не назначено.", True)
            return
        now = int(time.time())
        end_ts = cutoff_ts + 1800
        if now >= end_ts or now < cutoff_ts - 3600:
            self.telegram.answer_callback(cb_id, "Срок этой кнопки закончился.", True)
            return
        status, request_id = self.store.create_request(child_id, device_id, cutoff_ts, end_ts)
        if status != "pending":
            messages = {
                "already_pending": "Запрос уже отправлен родителю.",
                "approved": "Продление уже одобрено.",
                "denied": "По этому запросу уже получен отказ.",
                "expired": "Запрос уже просрочен.",
            }
            self.telegram.answer_callback(cb_id, messages.get(status, "Запрос уже обработан."), True)
            return
        row = self.store.request(request_id)
        parent = self.store.parent_id()
        if row is None or parent is None:
            self.telegram.answer_callback(cb_id, "Родитель ещё не зарегистрирован.", True)
            return
        end_text = format_hhmm(end_ts, self.tz)
        cutoff_text = format_hhmm(cutoff_ts, self.tz)
        name = device_name(row)
        keyboard = [[
            {"text": f"✅ Продлить до {end_text}", "callback_data": f"p:approve:{request_id}"},
            {"text": "❌ Отказать", "callback_data": f"p:deny:{request_id}"},
        ]]
        sent = self.telegram.send(
            parent,
            "🙏 Запрос на продление интернета\n\n"
            f"Ребёнок: {row['child_name']}\n"
            f"Устройство: {name} ({row['ip']})\n"
            f"Базовое отключение: {cutoff_text}\n"
            f"Запрошено продление: до {end_text}",
            keyboard,
        )
        self.store.set_request_message(request_id, int(sent["message_id"]))
        self.telegram.answer_callback(cb_id, "Запрос отправлен родителю")
        self.telegram.send(chat_id, f"✅ Запрос отправлен. Если его одобрят, «{name}» будет работать до {end_text}.")

    def scheduler_loop(self) -> None:
        while not STOP.is_set():
            try:
                now = datetime.now(self.tz)
                window = schedule_for_date(now)
                if window.warning_at <= now < window.cutoff_at:
                    self.send_warnings(window)
                # Also catch Friday/Saturday windows shortly after midnight only for cleanup; no new warnings.
                self.store.managed_state()
            except Exception:
                LOG.exception("Scheduler loop failed")
            STOP.wait(15)

    def send_warnings(self, window: ScheduleWindow) -> None:
        cutoff_ts = int(window.cutoff_at.timestamp())
        end_text = window.extension_end.strftime("%H:%M")
        cutoff_text = window.cutoff_at.strftime("%H:%M")
        for child in self.store.children():
            child_id = int(child["tg_id"])
            devices = [
                d for d in self.store.child_devices(child_id)
                if str(d["ip"] or "").strip()
            ]
            if not devices:
                continue
            key = f"warn:{child_id}:{cutoff_ts}"
            if self.store.notification_sent(key):
                continue
            keyboard = [
                [{"text": f"🙏 {device_name(d)}: просить +30 мин", "callback_data": f"c:request:{d['id']}:{cutoff_ts}"}]
                for d in devices
            ]
            remaining = max(1, int((window.cutoff_at - datetime.now(self.tz)).total_seconds() // 60) + 1)
            self.telegram.send(
                child_id,
                f"⏳ Интернет будет отключён примерно через {remaining} мин.\n"
                f"Плановое отключение: {cutoff_text}.\n"
                f"При одобрении доступ будет продлён строго до {end_text}.",
                keyboard,
            )
            self.store.mark_notification(key)

    def serve_http(self) -> None:
        """Serve the router API on loopback HTTP.

        TLS is terminated by the existing Caddy instance. Router endpoints
        additionally require a constant-time checked API key header.
        """
        bot = self

        class Handler(http.server.BaseHTTPRequestHandler):
            server_version = "SmartBildKidsBot/" + VERSION

            def log_message(self, fmt: str, *args: Any) -> None:
                LOG.debug("API %s - %s", self.address_string(), fmt % args)

            def send_body(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def authorized(self) -> bool:
                supplied = self.headers.get("X-SmartBild-Key", "")
                return secrets.compare_digest(supplied, bot.router_secret)

            def do_GET(self) -> None:
                path = urllib.parse.urlsplit(self.path).path
                if path == "/health":
                    payload = {"ok": True, "version": VERSION, **bot.store.health_stats()}
                    body = json.dumps(payload, separators=(",", ":")).encode()
                    self.send_body(200, body, "application/json")
                    return
                if path == "/router/state":
                    if not self.authorized():
                        self.send_body(403, b"forbidden\n")
                        return
                    version, kids, exts = bot.store.managed_state()
                    macs = bot.store.managed_macs()
                    ext_text = ",".join(f"{ip}|{duration_hms(seconds)}" for ip, seconds in exts if seconds > 0)
                    # Routers running the 2.0.0 script read only the first three lines.
                    text = f"VERSION={version}\nKIDS={','.join(kids)}\nEXT={ext_text}\nMACS={','.join(macs)}\n"
                    self.send_body(200, text.encode("ascii"))
                    return
                self.send_body(404, b"not found\n")

            def do_POST(self) -> None:
                path = urllib.parse.urlsplit(self.path).path
                if path != "/router/leases":
                    self.send_body(404, b"not found\n")
                    return
                if not self.authorized():
                    self.send_body(403, b"forbidden\n")
                    return
                try:
                    requested = int(self.headers.get("Content-Length", "0") or "0")
                except ValueError:
                    requested = 0
                if requested < 0 or requested > 65536:
                    self.send_body(413, b"payload too large\n")
                    return
                raw = self.rfile.read(requested).decode("utf-8", "replace")
                leases: List[Tuple[str, str, str, str]] = []
                for line in raw.splitlines():
                    parts = line.split("|", 3)
                    if len(parts) != 4:
                        continue
                    mac, ip, host, status = (part.strip() for part in parts)
                    if mac:
                        leases.append((mac, ip, host if host != "-" else "", status))
                complete = any(line.strip() == "#COMPLETE=1" for line in raw.splitlines())
                count = bot.store.sync_leases(leases, complete=complete)
                self.send_body(200, f"OK {count}\n".encode("ascii"))

        bind_host = self.config.get("bind_host", "127.0.0.1")
        bind_port = int(self.config["bind_port"])
        server = http.server.ThreadingHTTPServer((bind_host, bind_port), Handler)
        server.timeout = 1
        LOG.info("Router API listening on http://%s:%s", bind_host, bind_port)
        while not STOP.is_set():
            server.handle_request()


def self_test() -> None:
    import tempfile

    tz = ZoneInfo("Europe/Moscow")
    expected = {
        0: ("22:50", "23:00", "23:30"),
        1: ("22:50", "23:00", "23:30"),
        2: ("22:50", "23:00", "23:30"),
        3: ("22:50", "23:00", "23:30"),
        4: ("23:50", "00:00", "00:30"),
        5: ("23:50", "00:00", "00:30"),
        6: ("22:50", "23:00", "23:30"),
    }
    base = datetime(2026, 10, 5, 12, 0, tzinfo=tz)  # Monday
    for offset in range(7):
        day = base + timedelta(days=offset)
        window = schedule_for_date(day)
        got = (
            window.warning_at.strftime("%H:%M"),
            window.cutoff_at.strftime("%H:%M"),
            window.extension_end.strftime("%H:%M"),
        )
        assert got == expected[day.weekday()], (day, got, expected[day.weekday()])
    assert duration_hms(1834) == "00:30:34"

    with tempfile.TemporaryDirectory(prefix="sbkb-selftest-") as temp_dir:
        store = Store(str(Path(temp_dir) / "test.db"))
        assert store.claim_parent(1001, "Parent", "parent")
        store.upsert_child(2002, "Child", "child")
        assert store.sync_leases([("AA:BB:CC:DD:EE:FF", "192.168.10.50", "kid-phone", "bound")], complete=True) == 1
        device = store.all_devices()[0]
        store.assign_device(int(device["id"]), 2002)
        version, kids, extensions = store.managed_state()
        assert version >= 2
        assert kids == ["192.168.10.50"]
        assert extensions == []
        store.sync_leases([("AA:BB:CC:DD:EE:FF", "192.168.10.50", "kid-phone", "waiting")], complete=True)
        _version, waiting_kids, _extensions = store.managed_state()
        assert waiting_kids == ["192.168.10.50"]
        assert store.managed_macs() == ["AA:BB:CC:DD:EE:FF"]
        store.sync_leases([("AA:BB:CC:DD:EE:FF", "192.168.10.77", "kid-phone", "bound")], complete=True)
        _version, moved_kids, _extensions = store.managed_state()
        assert moved_kids == ["192.168.10.77"]
        cutoff = int(time.time()) + 120
        state, request_id = store.create_request(2002, int(device["id"]), cutoff, cutoff + 1800)
        assert state == "pending"
        decision, row = store.decide_request(request_id, approve=True)
        assert decision == "approved" and row is not None
        _version, _kids, active = store.managed_state()
        assert active and active[0][0] == "192.168.10.77"
        assert 1880 <= active[0][1] <= 1920
        # A sleeping device keeps both its block and an approved extension.
        store.sync_leases([("AA:BB:CC:DD:EE:FF", "192.168.10.77", "kid-phone", "waiting")], complete=True)
        _version, waiting_kids, waiting_ext = store.managed_state()
        assert waiting_kids == ["192.168.10.77"]
        assert waiting_ext and waiting_ext[0][0] == "192.168.10.77"
        # A lease that vanished from the router drops the IP but keeps the MAC block.
        store.sync_leases([], complete=True)
        _version, gone_kids, _ext = store.managed_state()
        assert gone_kids == []
        assert store.managed_macs() == ["AA:BB:CC:DD:EE:FF"]

    print("SELF_TEST_OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.config:
        parser.error("--config is required")
    with open(args.config, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    logging.basicConfig(
        level=getattr(logging, str(config.get("log_level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = KidsBot(config)

    def stop_handler(signum, frame):
        LOG.info("Signal %s received; stopping", signum)
        STOP.set()

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    bot.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
