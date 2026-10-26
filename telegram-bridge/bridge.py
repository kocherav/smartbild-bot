#!/usr/bin/env python3
import json
import fcntl
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import copy
import shutil
import socket
import hashlib
import smtplib
import ssl
import html
import uuid
from email.message import EmailMessage
import requisites_card
import decision_channel
import runtime_guards
import deal_creation
import delivery_steps
import durable_json
import safe_reload
import qa_handoff
import qa_autopilot
import qa_ideas
import supplier_completion
import model_recovery
import invoice_tasks
import catalog_conversation
import kp_jobs
import invoice_continuation
import order_continuation
import creation_attachment
import human_intents
import statement_document_context
import periodic_schedule
import qa_schedule
import handoff_watcher
import voice_intake
import legacy_report_ui
import closing_runtime
import product_matching_runtime
import allocation_runtime
import procurement_intake_runtime
import math
from workflow_runtime import Store as WorkflowStore
from ui_context import StateStore
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
OFFSET_FILE = os.path.join(BASE_DIR, "offset.txt")
PROCUREMENT_WATCH_FILE = os.path.join(BASE_DIR, "procurement_status_watch.json")
PENDING_TRANSITIONS_FILE = os.path.join(BASE_DIR, "pending_deal_transitions.json")
SESSION_FILE = os.path.join(BASE_DIR, "session_id.txt")
DEVELOPER_SESSION_FILE = os.path.join(BASE_DIR, "developer_session_id.txt")
DEAL_UI_STATE_FILE = os.path.join(BASE_DIR, "deal_ui_state.json")
DEAL_UI_STATE_LOCK_FILE = os.path.join(BASE_DIR, "deal_ui_state.lock")
DOCUMENT_JOBS_FILE = os.path.join(BASE_DIR, "document_jobs.json")
DOCUMENT_JOBS_LOCK_FILE = os.path.join(BASE_DIR, "document_jobs.lock")
INSTALLER_FACT_REGISTRY_FILE = os.path.join(BASE_DIR, "installer_fact_registry.json")
INSTALLER_APPROVED_REPORTS_FILE = os.path.join(BASE_DIR, "installer_approved_reports.json")
INSTALLER_APPROVED_REPORTS_DIR = os.path.join(BASE_DIR, "approved_installer_reports")
EDO_RECIPIENT_CHAT_FILE = os.path.join(BASE_DIR, "edo_recipient_chat_id.txt")
EDO_DISPATCH_FILE = os.path.join(BASE_DIR, "edo_dispatch_registry.json")
MODEL_LOCK_FILE = os.path.join(BASE_DIR, "model_worker.lock")
DEVELOPER_LOCK_FILE = os.path.join(BASE_DIR, "developer_worker.lock")
WORKFLOW_DB_FILE = os.path.join(BASE_DIR, "workflow_runtime.sqlite3")
RELOAD_REQUEST_FILE = os.path.join(BASE_DIR, "reload_request.json")
RELOAD_NOTICE_FILE = os.path.join(BASE_DIR, "reload_notice_state.json")
RUNTIME_ACTIVE = False  # enabled by main; imports/tests do not alter live state
UI_CONTEXT = None
BACKGROUND_LOCK_DIR = os.path.join(BASE_DIR, ".background-locks")
SLOW_OPERATIONS_LOG = os.path.join(BASE_DIR, "slow_operations.jsonl")
# A model/CRM worker can ask for one deal ledger several times while preparing a
# single preview.  The cache is deliberately process-bound and very short-lived:
# a new Telegram action runs in a new worker and therefore reads manual Megaplan
# edits afresh.
DEAL_LEDGER_CACHE = {}
DEAL_LEDGER_CACHE_TTL_SEC = 8
INSTALLER_CHAT_IDS = set()
MANAGER_CHAT_ID = None
INSTALLER_NOTIFY_CHAT_ID = None
LOG_PREFIX = "[telegram-bridge]"
CODEX_BIN = os.environ.get("BRIDGE_CODEX_BIN", os.path.expanduser("~/.local/bin/codex"))

# The model itself runs in Codex's read-only sandbox. All mutations (Megaplan writes,
# report generation, downloads) remain fixed bridge subprocesses triggered by the
# marker protocol below; the model cannot edit server files or call those APIs itself.
MODEL_FAILURES_FILE = os.path.join(BASE_DIR, "model_failures.json")
MODEL_TIMEOUT_SEC = 300
DEVELOPER_TIMEOUT_SEC = 1800
MAX_ATTACH_BYTES = 45 * 1024 * 1024  # Telegram bot upload limit is 50MB, leave margin
ATTACH_RE = re.compile(r"^ATTACH_FILE:\s*(.+?)\s*$", re.MULTILINE)
HOGART_SEARCH_RE = re.compile(r"^HOGART_SEARCH:\s*(.+?)\s*$", re.MULTILINE)
# A long-lived model session may remember an earlier Hogart result and answer a new
# price/stock request from stale JSON without emitting HOGART_SEARCH again.
HOGART_BRAND_RE = re.compile(r"(?i)\b(?:hogart|хогарт|haier|casarte|ха[ийэ]ер|касатр[еэ])\b")
HOGART_LIVE_INTENT_RE = re.compile(
    r"(?i)(?:цен|стоим|закуп|себесто|нацен|налич|остат|склад|фото|подбер|подбери|"
    r"сам(?:ый|ая|ое|ые)\s+деш|модел|кондиционер|сплит)"
)
ATTACH_URL_RE = re.compile(r"^ATTACH_IMAGE_URL:\s*(\S+)\s*$", re.MULTILINE)
HOGART_DIR = os.path.expanduser("~/hogart-scraper")
MEGAPLAN_DIR = os.path.expanduser("~/megaplan-crm")
if MEGAPLAN_DIR not in sys.path:
    sys.path.insert(0, MEGAPLAN_DIR)
from currency_planning import CurrencyPlanningError, plan_invoice_spec
DAICHI_DIR = os.path.expanduser("~/daichi-scraper")
REPORT_VENV_PY = os.path.expanduser("~/.report-venv/bin/python3")
MEGAPLAN_TIMEOUT_SEC = 30
HOGART_SEARCH_TIMEOUT_SEC = 60
MAX_HOGART_SEARCHES_PER_TURN = 2
MAX_IMAGE_DOWNLOADS_PER_TURN = 3
MAX_HOGART_ITEMS_IN_PROMPT = 20
# Second AC supplier (2026-08-26) - daichi_search.py searches a locally cached, normalized
# catalog (daichi_catalog_cache.py, kept warm by a systemd timer every 6h) instead of a
# live per-request API call, since Daichi's product NAMEs are cryptic model codes with no
# descriptive-keyword search on their side - see that module's docstring. Claude sends
# structured filters as JSON, not a bare keyword like HOGART_SEARCH.
DAICHI_SEARCH_RE = re.compile(r"^DAICHI_SEARCH:\s*(\{.*\})\s*$", re.MULTILINE)
DAICHI_SEARCH_TIMEOUT_SEC = 90
MAX_DAICHI_SEARCHES_PER_TURN = 2
MAX_DAICHI_ITEMS_IN_PROMPT = 20
BUILD_KP_RE = re.compile(r"BUILD_KP_BEGIN\s*(.*?)\s*BUILD_KP_END", re.DOTALL)
BUILD_KP_LEGACY_RE = re.compile(r"(?m)^\s*BUILD_KP\s*:\s*")
SYNC_DEAL_KP_RE = re.compile(r"SYNC_DEAL_KP_BEGIN\s*(.*?)\s*SYNC_DEAL_KP_END", re.DOTALL)
GENERATE_KP_TIMEOUT_SEC = 120
CREATE_MEGAPLAN_DEAL_RE = re.compile(r"CREATE_MEGAPLAN_DEAL_BEGIN\s*(.*?)\s*CREATE_MEGAPLAN_DEAL_END", re.DOTALL)
TAX_CHOICE_REQUEST_RE = re.compile(r"^TAX_CHOICE_REQUEST\s*$", re.MULTILINE)
PROFITABILITY_REQUEST_RE = re.compile(r"^PROFITABILITY_REQUEST:\s*(\d+)\s*$", re.MULTILINE)
# Large specifications create/reuse catalog offers one by one before the deal is
# returned. A real 36-row KP took just over 60s: Megaplan completed the write, but the
# bridge killed the CLI and incorrectly reported failure. Leave enough room for large
# offers while MODEL_TIMEOUT_SEC still bounds the complete interaction.
CREATE_MEGAPLAN_DEAL_TIMEOUT_SEC = 180
# Phase 1b (2026-08-23): supplier-invoice-applies-to-an-existing-deal flow. Two small
# round-trip markers (same shape as HOGART_SEARCH - Claude asks, bridge fetches local
# data, Claude gets a followup message with it) before the final apply block.
RECENT_DEALS_REQUEST_RE = re.compile(r"^RECENT_DEALS_REQUEST\s*$", re.MULTILINE)
DEAL_LEDGER_REQUEST_RE = re.compile(r"^DEAL_LEDGER_REQUEST:\s*(\S+)\s*$", re.MULTILINE)
SUPPLIER_INVOICE_APPLY_RE = re.compile(r"SUPPLIER_INVOICE_APPLY_BEGIN\s*(.*?)\s*SUPPLIER_INVOICE_APPLY_END", re.DOTALL)
RESEND_DEAL_REVIEW_RE = re.compile(r"^RESEND_DEAL_REVIEW:\s*(\S+)\s*$", re.MULTILINE)
# A confirmed bank-details card becomes a Payer under the deal's client and is then
# selected on that deal. The model may extract text, but only this fixed handler writes.
PAYER_CARD_APPLY_RE = re.compile(r"PAYER_CARD_APPLY_BEGIN\s*(.*?)\s*PAYER_CARD_APPLY_END", re.DOTALL)
PAYER_CARD_APPLY_TIMEOUT_SEC = 60
# Multi-variant KP -> Megaplan deal confirmation (2026-08-26, owner's explicit choice
# after seeing a real multi-variant KP auto-create a deal that felt premature - "N
# options, client hasn't picked one yet" doesn't map cleanly onto a single committed
# CRM deal the way a single-configuration KP does). A single-variant KP still
# auto-creates a deal exactly as before - this only changes the multi-variant path.
# `_pending_kp_deal` holds the just-built kp_spec/kp_result (real order data) entirely
# in Python - the confirmation marker below carries ONLY yes/no, never re-derives the
# order content through the model (same principle as _accumulate_position elsewhere).
CREATE_KP_DEAL_CONFIRM_RE = re.compile(r"^CREATE_KP_DEAL_CONFIRM:\s*(да|нет|yes|no)\s*$", re.IGNORECASE | re.MULTILINE)
_pending_kp_deal = None
SUPPLIER_INVOICE_APPLY_TIMEOUT_SEC = 60
# "Ведомость работ" calculator (2026-08-25) - deterministic lookup like RESEND_DEAL_REVIEW,
# no LLM round-trip needed for the computation itself. Output stays internal-only: only
# builds/sends a review .xlsx, never writes anything back onto the deal.
WORK_STATEMENT_REQUEST_RE = re.compile(r"^WORK_STATEMENT_REQUEST:\s*(\S+)\s*$", re.MULTILINE)
WORK_STATEMENT_TIMEOUT_SEC = 60
# Second half of the same flow (2026-08-25): owner confirms a markup_pct in chat after
# the WORK_STATEMENT_REQUEST summary above asks for it - Claude replies with this JSON
# block, the bridge writes cost/price onto "Монтажные работы" and builds the
# profitability report. Deal_id/markup_pct only - the actual cost total is ALWAYS
# re-derived by apply_work_statement.py itself, never trusted from this JSON (see that
# script's docstring - same principle as the qty_used/material_cost_used fix).
APPLY_WORK_STATEMENT_RE = re.compile(r"APPLY_WORK_STATEMENT_BEGIN\s*(.*?)\s*APPLY_WORK_STATEMENT_END", re.DOTALL)
APPLY_WORK_STATEMENT_TIMEOUT_SEC = 60
UPDATE_KEMIX_PRICES_RE = re.compile(r"UPDATE_KEMIX_PRICES_BEGIN\s*(.*?)\s*UPDATE_KEMIX_PRICES_END", re.DOTALL)
UPDATE_KEMIX_PRICES_TIMEOUT_SEC = 30
# "/счет <id>" sends that invoice's PDF directly; "/сделка <id>" sends the latest invoice
# on that deal. Deliberately bypasses Claude entirely (like /start) - fetching a Megaplan
# invoice is a deterministic lookup, not something that needs the model in the loop.
# <id> is the internal Megaplan id (visible in the URL bar when viewing the deal/invoice
# in Мегаплан), not the human-facing "№258" display number - Megaplan's API has no
# reliable way to look entities up by that display number.
INVOICE_CMD_RE = re.compile(r"^/(?:счет|счёт|invoice)\s+(\d+)\s*$", re.IGNORECASE)
DEAL_CMD_RE = re.compile(r"^/(?:сделка|deal)\s+(\d+)\s*$", re.IGNORECASE)
ECONOMICS_CMD_RE = re.compile(r"^/(?:экономика|economics|profit)\s+(\d+)\s*$", re.IGNORECASE)
CURRENT_EXECUTION_RE = re.compile(
    r"(?:пришл\w*\s+(?:мне\s+)?)?(?:текущ\w*|накопительн\w*)\s+выполнени\w*"
    r"(?:\s+по\s+(?:сделк\w*|объект\w*))?\s*[«\"']?(.+?)[»\"']?\s*$",
    re.IGNORECASE,
)
DEAL_READ_RE = re.compile(
    r"(?i)(?:\b(?:покаж\w*|откро\w*|перечита\w*|прочита\w*|проверь\w*|сколько|как\w{2}|кто|чей|чья|посчита\w*|сверь\w*"
    r"|что|инф\w*|данные|расскажи|напомни)\b"
    r"(?:(?!\b(?:созда\w*|измени\w*|перевед\w*)\b).){0,160}?"
    r"\bсделк\w*\s*(?:№|номер)?\s*(\d+)\b"
    # «открой 990001», «сделка №990001» — the whole message is a deal reference.
    r"|^\s*(?:откро\w*|покаж\w*)\s+№?\s*(\d{3,})\s*[?.!]*\s*$"
    r"|^\s*сделк\w*\s*(?:№|номер)?\s*(\d{3,})\s*[?.!]*\s*$)"
)
DEAL_READ_VERB_RE = re.compile(r"(?i)\b(?:покаж|откро|перечита|прочита|проверь)\w*|^\s*сделк")
DEAL_READ_OTHER_TASK_RE = re.compile(
    r"(?i)закуп|ведомост|\bкп\b|коммерческ|договор|сч[её]т|монтаж|поставщ|hogart|хогарт|daichi|дайчи|сравн|добав"
    r"|удал|замен|рассчит|экономик|рентаб|наличи|цен[аыу]\b|скидк|оплат|достав"
)
DEAL_COMPARE_RE = re.compile(
    r"(?i)\bсравн\w*\b.{0,80}?\bсделк\w*\s*№?\s*(\d+)"
    r".{0,40}?\b(?:и|со|с)\s*№?\s*(\d+)\b"
)
DEAL_COMPARE_FOLLOWUP_RE = re.compile(
    r"(?i)\bиз\s+этих\s+двух\s+сделок\b.*\b(?:сумм\w*\s+меньш\w*|меньш\w*\s+сумм\w*)\b"
)
MEGAPLAN_INVOICE_FETCH_TIMEOUT_SEC = 30

# Shown on /start and /help - kept in sync by hand with what the bridge actually supports
# (the fixed slash-commands below, plus the free-text capabilities described in
# SYSTEM_PROMPT). Update this whenever a new command or capability is added.
HELP_TEXT = """Что я умею:

📄 Команды (мгновенно, без обращения к ИИ):
/счет <id> — прислать PDF счёта из Мегаплана по его внутреннему ID
/сделка <id> — прислать последний счёт по сделке (по ID сделки)

🛠 «Задача разработчику» — передать отдельную задачу Codex. Бот подтвердит приём,
выполнит её в фоне и пришлёт результат в этот чат, не смешивая задачу с работой в Мегаплане.
🏦 «Банк и платежи» — загрузить XLSX-выписку, посмотреть приходы и расходы, выбрать
операцию и после подтверждения привязать её к конкретной сделке Мегаплана.
/экономика <id> — актуальный Excel с рентабельностью прямо из данных Мегаплана
(ID — это число из адресной строки Мегаплана, напр. .../deals/313/card/ → 313,
не отображаемый номер вида «№258»)

💬 Обычным текстом:
— Вопрос про кондиционер Hogart или Daichi (цена, наличие, фото) — просто спроси, напр.
  "сколько стоит Flexis 25 и есть ли в наличии" или "недорогой инверторный Daichi на 2.5 кВт"
— "Собери КП для <клиент>" — соберу коммерческое предложение на бланке Cliwell (можно
  сравнить варианты от Hogart и Daichi в одном документе), уточню про монтаж и доп.
  фреоновую трассу, пришлю PDF + Excel с экономикой, заведу сделку в Мегаплане
— "Создай сделку с клиентом ..." (текстом или с вложенным КП/счётом поставщика) —
  разберу позиции и цены (по твоим правилам скидки/маржи), уточню недостающее,
  заведу полноценную сделку с позициями в Мегаплане и пришлю ссылку
— Пришли голую спецификацию (список оборудования/материалов/услуг без цен) — сам найду
  цену: сначала по каталогу Мегаплана (пришлю файл на подтверждение совпадений), потом
  Hogart/Daichi/КЕМИКС; что нигде не нашлось — поставлю 0 и дождусь счёта поставщика
— Пришли счёт/КП поставщика по уже созданной сделке (PDF, Word, Excel, фото/скан) —
  спрошу, к какой сделке отнести, сопоставлю позиции, заполню себестоимость и (если
  нужно) согласую наценку
— Пришли карточку реквизитов (PDF, Word, Excel, фото/скан) — распознаю данные,
  покажу их для проверки, создам плательщика у клиента и привяжу к выбранной сделке
— "Пришли файл по сделке <id> ещё раз" — пришлю актуальный Excel с ценой/себестоимостью
  по текущему состоянию сделки, не дожидаясь новой правки
— "Посчитай ведомость работ по сделке <id>" — посчитаю себестоимость монтажных работ по
  позициям сделки, пришлю Excel с итоговой суммой и спрошу наценку, если все позиции
  посчитаны; после ответа на наценку запишу стоимость позиции "Монтажные работы" в
  сделку и пришлю второй файл — "Расчёт рентабельности сделки" (выручка/себестоимость/
  прибыль по всей сделке)
— «🧰 Отчёт монтажника» — пришлите PDF: сначала покажу найденные объекты и сделки,
  затем автоматически приму понятные строки и последовательно задам вопросы только
  по исключениям. До утверждения черновика ничего не записывается в Мегаплан
— Пришли PDF прайс-листа КЕМИКС — прочитаю, покажу изменения цен на трубы/
  изоляцию/кабель и обновлю после подтверждения
— Попроси прислать файл (брендбук, логотип и т.п. из папок SmartBild/Cliwell)

Раздел «Работа со сделками» позволяет найти сделку по номеру, клиенту или адресу,
показать последние 5/10/15 сделок, выбрать текущую сделку, посмотреть её исполнителя
и статус, а также перевести её в один из разрешённых Мегапланом статусов после
явного подтверждения пользователя. После перехода в «Выставление счета» бот ждёт
создания счёта в Мегаплане и присылает его PDF; повторно получить последний счёт можно
кнопкой «📥 Получить счёт» в карточке сделки.

/menu — меню основных функций
/deals — работа со сделками
/help — показать эту подсказку ещё раз."""

WELCOME_TEXT = """Главное меню.

💬 Можно написать задачу своими словами, например:
«найди сделку по складу в Химках».

Или выберите действие кнопкой."""

DASHBOARD_URL = "https://claude.smartbild.su/deal-dashboard/"
DASHBOARD_INLINE = {"inline_keyboard": [[{"text": "📊 Открыть пульт сделок", "web_app": {"url": DASHBOARD_URL}}]]}

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "🤝 Сделки"}, {"text": "🏦 Деньги"}],
        [{"text": "🧰 Монтаж"}, {"text": "☰ Ещё"}],
    ],
    "resize_keyboard": True,
}
PAYER_UPLOAD_KEYBOARD = {
    "keyboard": [[{"text": "❌ Отмена"}], [{"text": "⬅️ Главное меню"}]],
    "resize_keyboard": True,
}
PAYER_TARGET_CONFIRM_KEYBOARD = {
    "keyboard": [[{"text": "✅ Создать и привязать плательщика"}], [{"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
BANK_MENU_KEYBOARD = {
    "keyboard": [
        [{"text": "📤 Загрузить выписку"}],
        [{"text": "📩 Банковские уведомления"}],
        [{"text": "🔗 Найти соответствия"}],
        [{"text": "🔍 Неразнесённые операции"}, {"text": "📚 Все операции"}],
        [{"text": "⬅️ Главное меню"}],
    ],
    "resize_keyboard": True,
}
BANK_CANCEL_KEYBOARD = {
    "keyboard": [[{"text": "❌ Отмена"}], [{"text": "⬅️ Главное меню"}]],
    "resize_keyboard": True,
}
BANK_CONFIRM_KEYBOARD = {
    "keyboard": [[{"text": "✅ Привязать к сделке"}], [{"text": "❌ Отмена"}]],
    "resize_keyboard": True,
}
BANK_INSTALLER_PAYMENT_KEYBOARD = {
    "keyboard": [[{"text": "✅ Учесть как выплату монтажнику"}], [{"text": "❌ Не учитывать как выплату"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
BANK_AUTO_CONFIRM_KEYBOARD = {
    "keyboard": [[{"text": "✅ Привязать все найденные"}], [{"text": "❌ Отмена"}]],
    "resize_keyboard": True,
}
EMAIL_PAYMENT_CONFIRM_KEYBOARD = {
    "keyboard": [[{"text": "✅ Создать расходные операции"}], [{"text": "⏭ Отложить платёж"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
EMAIL_PAYMENT_UNMATCHED_KEYBOARD = {
    "keyboard": [[{"text": "📋 Как привязать платёж"}], [{"text": "⏭ Отложить платёж"}],
                 [{"text": "⬅️ Банк и платежи"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
DEVELOPER_TASK_KEYBOARD = {
    "keyboard": [[{"text": "❌ Отменить задачу"}], [{"text": "⬅️ Главное меню"}]],
    "resize_keyboard": True,
}
PAYER_DEAL_KEYBOARD = {
    "keyboard": [[{"text": "Без привязки к сделке"}], [{"text": "❌ Отменить"}]],
    "resize_keyboard": True,
}
INSTALLER_USER_KEYBOARD = {
    "keyboard": [
        [{"text": "🛠 Мои монтажи"}],
        [{"text": "📤 Сборный отчёт"}],
        [{"text": "📜 История монтажей"}],
        [{"text": "📚 Утверждённые отчёты"}, {"text": "📊 Мои взаиморасчёты"}],
        [{"text": "❓ Помощь"}],
    ],
    "resize_keyboard": True,
}
INSTALLER_HELP_TEXT = """Режим монтажника — Сергей Деревянко.

🛠 «Мои монтажи» — отчёт по одному объекту через «Новый отчёт».
📤 «Сборный отчёт» — основной PDF по нескольким объектам, затем запрошенные Excel и передача руководителю. Сам монтажник не утверждает начисления.
📜 «История монтажей» — ранее принятые объекты: можно открыть ведомость, но нельзя создать новый отчёт.
📚 «Утверждённые отчёты» — посмотреть принятые руководителем отчёты с разбивкой по сделкам и разделом «Всякая всячина».
📊 «Мои взаиморасчёты» — получить накопительный реестр своих отчётов, начислений и выплат.
Можно написать «Текущее выполнение по сделке Примавера» и получить накопительный Excel.

Можно также сразу прислать PDF-отчёт: бот начнёт его разбор автоматически."""


def notify_installers(token, text):
    import installer_onboarding
    chats=installer_onboarding.members() | ({str(INSTALLER_NOTIFY_CHAT_ID)} if INSTALLER_NOTIFY_CHAT_ID else set())
    return all([send_message(token,chat,text) for chat in sorted(chats)])


def deliver_installation_handoffs(token):
    import installer_onboarding
    import installation_handoff
    def recipients(profile):
        if profile != installer_onboarding.PROFILE: return set()
        return installer_onboarding.members() | ({str(INSTALLER_NOTIFY_CHAT_ID)} if INSTALLER_NOTIFY_CHAT_ID else set())
    return installation_handoff.deliver(os.path.join(MEGAPLAN_DIR,'installations.sqlite3'),
        recipients,lambda chat,text:send_message(token,chat,text))


def notify_megaplan_protection(token, chat_id):
    import megaplan_transport
    megaplan_transport.notify_status(lambda text:send_message(token,chat_id,text))


def complete_installation_handoff(token, deal_id, actor=''):
    result=run_installation_workflow({'action':'transfer','deal_id':str(deal_id),'actor':str(actor)})
    if result.get('ok'):
        result['delivery']=deliver_installation_handoffs(token)
    return result


def home_keyboard(chat_id):
    return INSTALLER_USER_KEYBOARD if str(chat_id) in INSTALLER_CHAT_IDS else MAIN_KEYBOARD


def installer_review_keyboard(chat_id):
    return INSTALLER_REPORT_SUBMIT_KEYBOARD if str(chat_id) in INSTALLER_CHAT_IDS else INSTALLER_REPORT_REVIEW_KEYBOARD


def load_approved_installer_reports():
    data = durable_json.read(INSTALLER_APPROVED_REPORTS_FILE,lambda:{"version":1,"reports":[]})
    data.setdefault("reports", [])
    return data


@durable_json.transaction(lambda:INSTALLER_APPROVED_REPORTS_FILE)
def save_approved_installer_report(session, excel_path=None):
    data = load_approved_installer_reports()
    report_date = session.get("report_date") or session.get("report")
    identity = os.path.basename(session.get("source_path") or "") or str(report_date)
    rows_by_deal = {}
    seen = set()
    for line in session.get("report_lines") or []:
        deal_id = str(line.get("deal_id") or "")
        if not deal_id:
            continue
        key = (deal_id, line.get("object"), line.get("source"))
        if key in seen:
            continue
        seen.add(key)
        rows_by_deal.setdefault(deal_id, []).append({
            "object": line.get("object"), "source": line.get("source"), "amount": line.get("amount") or 0,
        })
    miscellaneous = []
    for item in session.get("exceptions") or []:
        if item.get("bucket") == "Всякая всячина" or str(item.get("resolution") or "").startswith("всякая всячина"):
            miscellaneous.append({"object": item.get("object"), "source": item.get("source"), "amount": item.get("amount") or 0})
            continue
        deal_id = str(item.get("deal_id") or "")
        if not deal_id or item.get("type") in {"settlement", "discrepancy"}:
            continue
        key = (deal_id, item.get("object"), item.get("source"))
        if key not in seen:
            seen.add(key)
            rows_by_deal.setdefault(deal_id, []).append({"object": item.get("object"), "source": item.get("source"), "amount": item.get("amount") or 0})
    report = {
        "id": identity, "date": report_date,
        "amount": session.get("payable_amount") if session.get("payable_amount") is not None else session.get("net_total"),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "deals": [{
            "deal_id": deal_id,
            "amount": sum(row["amount"] for row in rows),
            "rows": rows,
            "table_sources": list(dict.fromkeys(
                item.get("table_path") for item in session.get("exceptions") or []
                if str(item.get("deal_id") or "") == deal_id
                and item.get("table_path") and os.path.isfile(item.get("table_path"))
            )),
        } for deal_id, rows in sorted(rows_by_deal.items())],
        "miscellaneous": miscellaneous,
        "source_file": os.path.basename(session.get("source_path") or ""),
        "table_sources": list(dict.fromkeys(
            item.get("table_path") for item in session.get("exceptions") or []
            if item.get("table_path") and os.path.isfile(item.get("table_path"))
        )),
    }
    if excel_path and os.path.isfile(excel_path):
        os.makedirs(INSTALLER_APPROVED_REPORTS_DIR, exist_ok=True)
        safe_date = re.sub(r"[^0-9.]+", "_", str(report_date))
        archive_path = os.path.join(INSTALLER_APPROVED_REPORTS_DIR, f"Утверждённый отчёт монтажника - {safe_date}.xlsx")
        shutil.copy2(excel_path, archive_path)
        report["excel_path"] = archive_path
    else:
        previous = next((item for item in data["reports"] if item.get("id") == identity), None)
        if previous and previous.get("excel_path"):
            report["excel_path"] = previous["excel_path"]
    data["reports"] = [item for item in data["reports"] if item.get("id") != identity]
    data["reports"].append(report)
    def date_key(item):
        try:
            return datetime.strptime(item.get("date") or "", "%d.%m.%Y")
        except ValueError:
            return datetime.min
    data["reports"].sort(key=date_key, reverse=True)
    durable_json.save(INSTALLER_APPROVED_REPORTS_FILE,data)
    return report


def approved_report_text(report):
    lines = [f"✅ Отчёт от {report.get('date')}", f"Утверждено к оплате: {money(report.get('amount'))}", "", "По сделкам:"]
    for deal in report.get("deals") or []:
        lines.append(f"• №{deal.get('deal_id')} — {money(deal.get('amount'))}")
        for row in deal.get("rows") or []:
            lines.append(f"  — {row.get('source')} ({money(row.get('amount'))})")
    misc = report.get("miscellaneous") or []
    if misc:
        lines.append("\nВсякая всячина:")
        for row in misc:
            lines.append(f"• {row.get('source')} — {money(row.get('amount'))}")
        lines.append(f"Итого: {money(sum(row.get('amount') or 0 for row in misc))}")
    return "\n".join(lines)
DEALS_KEYBOARD = {
    "keyboard": [
        [{"text": "🔎 Найти сделку"}, {"text": "🕘 Последние сделки"}],
        [{"text": "➕ Создать сделку"}, {"text": "📄 Создать КП"}],
        [{"text": "⭐ Текущая сделка"}],
        [{"text": "⬅️ Главное меню"}],
    ],
    "resize_keyboard": True,
}
DEAL_ACTIONS_KEYBOARD = {
    "keyboard": [
        # Quick actions (QA idea И-1): the most frequent operations in one tap.
        [{"text": "🧾 Выставить счёт"}, {"text": "📥 Получить счёт"}],
        [{"text": "🏢 Сменить плательщика"}, {"text": "🔄 Изменить статус"}],
        # QA explorer 24.10: assigning an executor was reachable only by a phrase.
        [{"text": "👤 Назначить исполнителя"}],
        [{"text": "📋 Основное"}, {"text": "📄 Документы сделки"}],
        [{"text": "📦 Закупка сделки"}, {"text": "🧰 Монтаж сделки"}],
        [{"text": "⬅️ К списку сделок"}],
    ],
    "resize_keyboard": True,
}
DEAL_SEARCH_KEYBOARD = {"keyboard": [
    [{"text": "🔢 Найти по номеру"}],
    [{"text": "🔎 Найти по клиенту"}, {"text": "📍 Найти по адресу"}],
    [{"text": "⬅️ К списку сделок"}],
], "resize_keyboard": True}
DEAL_RECENT_KEYBOARD = {"keyboard": [
    [{"text": "🕘 5"}, {"text": "🕘 10"}, {"text": "🕘 15"}],
    [{"text": "⬅️ К списку сделок"}],
], "resize_keyboard": True}
DEAL_BASIC_KEYBOARD = {"keyboard": [
    [{"text": "🔄 Изменить статус"}, {"text": "💰 Экономика"}],
    [{"text": "📄 Позиции сделки"}, {"text": "📄 КП по сделке"}],
    [{"text": "⬅️ Назад к сделке"}],
], "resize_keyboard": True}
DEAL_DOCUMENTS_KEYBOARD = {"keyboard": [
    [{"text": "📑 Работа с договором"}, {"text": "🧾 Работа со счетами"}],
    [{"text": "📥 Получить счёт"}, {"text": "🧾 Учесть счёт"}],
    [{"text": "⬅️ Назад к сделке"}],
], "resize_keyboard": True}
DEAL_PROCUREMENT_KEYBOARD = {"keyboard": [
    [{"text": "📦 Закупка по сделке"}],
    [{"text": "🧾 Учесть счёт"}],
    [{"text": "⬅️ Назад к сделке"}],
], "resize_keyboard": True}
DEAL_INSTALLATION_KEYBOARD = {"keyboard": [
    [{"text": "📋 Монтажная ведомость"}, {"text": "👷 Монтаж по сделке"}],
    [{"text": "👤 Контакт по монтажу"}, {"text": "📐 Приложить проект"}],
    [{"text": "💵 Выплата монтажнику"}],
    [{"text": "⬅️ Назад к сделке"}],
], "resize_keyboard": True}
MANAGER_INSTALLATION_KEYBOARD = {"keyboard": [
    [{"text": "🧰 Отчёт монтажника"}, {"text": "📥 Монтажные отчёты"}],
    [{"text": "⬅️ Главное меню"}],
], "resize_keyboard": True}
MORE_KEYBOARD = {"keyboard": [
    [{"text": "📦 Нераспределённые закупки"}, {"text": "📄 Создать КП"}],
    [{"text": "🛠 Задача разработчику"}, {"text": "🧪 Ошибки тестировщика"}],
    [{"text": "💡 Идеи тестировщика"}, {"text": "❓ Помощь"}],
    [{"text": "⬅️ Главное меню"}],
], "resize_keyboard": True}
PROCUREMENT_KEYBOARD = {
    "keyboard": [
        [{"text": "📋 Скачать перечень закупки"}],
        [{"text": "📎 Загрузить счёт поставщика"}, {"text": "📚 Реестр для бухгалтерии"}],
        [{"text": "🔎 Подобрать из остатков"}],
        [{"text": "🔄 Повторить последний счёт"}],
        [{"text": "📊 Статус закупок"}],
        [{"text": "🏦 Сверить оплаты поставщикам"}],
        [{"text": "🏢 Организация продажи"}],
        [{"text": "🏢 Межфирменные взаиморасчёты"}],
        [{"text": "📥 Отметить поступление"}],
        [{"text": "📎 Загрузить УПД/акт поставщика"}],
        [{"text": "✅ Проверить готовность закупки"}],
        [{"text": "⬅️ Назад к сделке"}, {"text": "⬅️ Главное меню"}],
    ], "resize_keyboard": True,
}
PROCUREMENT_COMPANY_KEYBOARD = {
    "keyboard": [[{"text": "ООО «КЛИВЭЛ»"}], [{"text": "ООО «Инсис»"}],
                 [{"text": "ИП Кочержинский А.В."}], [{"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
SUPPLIER_INVOICE_CONFIRM_KEYBOARD = {
    "keyboard": [[{"text": "✅ Применить счёт поставщика"}, {"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
SUPPLIER_DISTRIBUTION_KEYBOARD = {
    "keyboard": [
        [{"text": "🔗 Сопоставить с позицией сделки"}],
        [{"text": "🧾 В прочую себестоимость сделки"}],
        [{"text": "✅ Подтвердить всё распределение"}],
        [{"text": "✅ Только в текущую сделку"}],
        [{"text": "📦 Весь остаток в нераспределённые"}],
        [{"text": "✏️ Изменить распределение"}, {"text": "🔍 Показать другие сделки"}],
        [{"text": "🚫 Не учитывать остаток"}, {"text": "❌ Отмена"}],
    ], "resize_keyboard": True,
}
SUPPLIER_MISC_CONFIRM_KEYBOARD = {
    "keyboard": [[{"text": "✅ Подтвердить прочую себестоимость"}], [{"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
UNALLOCATED_STOCK_KEYBOARD = {
    "keyboard": [
        [{"text": "📋 Показать остатки"}, {"text": "📥 Скачать реестр остатков"}],
        [{"text": "🔎 Найти в остатках"}],
        [{"text": "⬅️ Главное меню"}],
    ], "resize_keyboard": True,
}
PROCUREMENT_STOCK_CONFIRM_KEYBOARD = {
    "keyboard": [
        [{"text": "✅ Использовать найденные остатки"}],
        [{"text": "⏭ Не использовать остатки"}],
        [{"text": "❌ Отмена"}],
    ], "resize_keyboard": True, "one_time_keyboard": True,
}
PROCUREMENT_RECEIPT_QTY_KEYBOARD = {
    "keyboard": [[{"text": "✅ Получено полностью"}], [{"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
PROCUREMENT_CLOSE_KEYBOARD = {
    "keyboard": [[{"text": "✅ Закрыть закупку"}, {"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
INVOICE_MENU_KEYBOARD = {
    "keyboard": [
        [{"text": "📋 Общий счёт по спецификации"}],
        [{"text": "6.4.1"}, {"text": "6.4.2"}, {"text": "6.4.3"}],
        [{"text": "📚 Скачать счёт"}],
        [{"text": "⬅️ Назад к сделке"}, {"text": "⬅️ Главное меню"}],
    ],
    "resize_keyboard": True,
}
TRANSITION_INVOICE_TYPE_KEYBOARD = {
    "keyboard": [
        [{"text": "1. Полностью согласно спецификации"}],
        [{"text": "2. Упрощённый согласно п.6.4"}],
        [{"text": "3. Оба варианта"}],
        [{"text": "❌ Отмена"}],
    ],
    "resize_keyboard": True, "one_time_keyboard": True,
}
INVOICE_FULL_CONFIRM_KEYBOARD = {
    "keyboard": [[{"text": "✅ Выставить общий счёт"}, {"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
CONTRACT_KEYBOARD = {
    "keyboard": [
        [{"text": "📝 Подготовить договор"}, {"text": "👁 Проверить данные договора"}],
        [{"text": "🏢 Добавить плательщика"}],
        [{"text": "📎 Получить договор из Мегаплана"}],
        [{"text": "🧾 Выставить счёт по договору"}],
        [{"text": "🏢 Смена нашей фирмы"}],
        [{"text": "⬅️ Назад к сделке"}, {"text": "⬅️ Главное меню"}],
    ],
    "resize_keyboard": True,
}
CONTRACT_INVOICE_CLAUSE_KEYBOARD = {
    "keyboard": [[{"text": "6.4.1"}, {"text": "6.4.2"}, {"text": "6.4.3"}],
                 [{"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
CONTRACT_INVOICE_CONFIRM_KEYBOARD = {
    "keyboard": [[{"text": "✅ Выставить счёт"}, {"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}
CONTRACT_UPLOAD_KEYBOARD = {
    "keyboard": [
        [{"text": "✅ Загрузить договоры в сделку"}],
        [{"text": "❌ Не загружать"}, {"text": "⬅️ Назад к сделке"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
TAX_KEYBOARD = {
    "keyboard": [[{"text": "Без НДС"}, {"text": "НДС 22%"}, {"text": "НДС 5%"}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
DEAL_CREATE_CONFIRM_KEYBOARD = {
    'keyboard': [[{'text': '✅ Создать подтверждённую сделку'}],
                 [{'text': '✏️ Заменить спецификацию'}, {'text': '❌ Отмена'}]],
    'resize_keyboard': True,
}
HUMAN_PAYER_CONFIRM_KEYBOARD = {
    'keyboard': [[{'text': '✅ Сменить плательщика'}], [{'text': '❌ Отмена'}]],
    'resize_keyboard': True, 'one_time_keyboard': True,
}
HUMAN_EXECUTOR_CONFIRM_KEYBOARD = {
    'keyboard': [[{'text': '✅ Назначить исполнителя'}], [{'text': '❌ Отмена'}]],
    'resize_keyboard': True, 'one_time_keyboard': True,
}
INSTALLER_REPORT_OBJECTS_KEYBOARD = {
    "keyboard": [
        [{"text": "✅ Объекты верны"}],
        [{"text": "✏️ Исправить объект"}, {"text": "❌ Отменить отчёт"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
INSTALLER_REPORT_REVIEW_KEYBOARD = {
    "keyboard": [
        [{"text": "▶️ Разобрать исключения"}],
        [{"text": "✅ Утвердить черновик"}, {"text": "❌ Отменить отчёт"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
INSTALLER_REPORT_SUBMIT_KEYBOARD = {
    "keyboard": [
        [{"text": "▶️ Разобрать исключения"}],
        [{"text": "📤 Передать руководителю"}, {"text": "❌ Отменить отчёт"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
INSTALLER_MANAGER_OPEN_KEYBOARD = {
    "keyboard": [
        [{"text": "🧰 Открыть отчёт монтажника"}],
        [{"text": "⬅️ Главное меню"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
INSTALLER_REPORT_UPLOAD_KEYBOARD = {
    "keyboard": [
        [{"text": "📤 Загрузить выполнение в сделки"}],
        [{"text": "❌ Не загружать выполнение"}, {"text": "⬅️ Главное меню"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
INSTALLER_REPORT_FILES_KEYBOARD = {
    "keyboard": [
        [{"text": "✅ Все файлы загружены"}],
        [{"text": "❌ Отменить отчёт"}],
    ],
    "resize_keyboard": True,
}
INSTALLER_MENU_KEYBOARD = {
    "keyboard": [
        [{"text": "📄 Загрузить отчёт"}, {"text": "💳 Учесть выплату"}],
        [{"text": "📊 Взаиморасчёты"}],
        [{"text": "⬅️ Главное меню"}],
    ],
    "resize_keyboard": True,
}
INSTALLER_PAYMENT_KEYBOARD = {
    "keyboard": [
        [{"text": "🏦 Безналичная — зачесть 94%"}],
        [{"text": "💵 Наличная — зачесть 100%"}],
        [{"text": "❌ Отменить выплату"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}
INSTALLATION_DRAFT_KEYBOARD = {
    "keyboard": [
        [{"text": "✅ Утвердить монтажную ведомость"}],
        [{"text": "📋 Скачать монтажную ведомость"}, {"text": "📤 Загрузить исправленную ведомость"}],
        [{"text": "👤 Выбрать контакт по монтажу"}, {"text": "✍️ Ввести контакт вручную"}],
        [{"text": "📎 Привязать проект"}, {"text": "🚫 Работать БЕЗ ПРОЕКТА"}],
        [{"text": "⏸ Подготовить позже"}],
    ], "resize_keyboard": True,
}
INSTALLATION_TRANSFER_KEYBOARD = {
    "keyboard": [[{"text": "✅ Передать объект монтажнику"}], [{"text": "⬅️ Назад к сделке"}]],
    "resize_keyboard": True,
}
INSTALLATION_STATUS_KEYBOARD = {
    "keyboard": [[{"text": "✅ Перевести сделку в Монтаж"}],
                 [{"text": "📋 Скачать монтажную ведомость"}],
                 [{"text": "⬅️ Назад к сделке"}]],
    "resize_keyboard": True,
}
INSTALLER_INSTALLATION_KEYBOARD = {
    "keyboard": [[{"text": "📋 Монтажная ведомость"}], [{"text": "📐 Проектная документация"}],
                 [{"text": "📦 Материалы по счетам"}],
                 [{"text": "🧰 Новый отчёт"}], [{"text": "⬅️ Мои монтажи"}]],
    "resize_keyboard": True,
}
INSTALLATION_REPORT_COLLECT_KEYBOARD = {
    "keyboard": [[{"text": "✅ Все материалы отправлены"}], [{"text": "❌ Отменить отчёт"}]],
    "resize_keyboard": True,
}
INSTALLATION_REPORT_REVIEW_KEYBOARD = {
    "keyboard": [[{"text": "✅ Принять монтажный отчёт"}], [{"text": "✏️ Скорректировать объёмы"}],
                 [{"text": "↩️ Вернуть монтажнику"}]],
    "resize_keyboard": True,
}
INSTALLATION_CASH_CONFIRM_KEYBOARD = {
    "keyboard": [[{"text": "✅ Записать выплату из кассы"}], [{"text": "❌ Отмена"}]],
    "resize_keyboard": True, "one_time_keyboard": True,
}

SYSTEM_PROMPT = """Дополнительный контекст: на сервере claude.smartbild.su через rclone
смонтированы локальные папки OneDrive: ~/OneDrive-SmartBild, ~/OneDrive-Rabota,
~/OneDrive-Documenty — это обычные пути на диске, доступные через Read/Glob/Grep,
а не облачный коннектор. Все материалы проекта SmartBild.pro (брендбук, логотипы,
сайт, панель умного дома, пакет для iRidium) лежат в
~/OneDrive-SmartBild/SmartBild_Complete_Handoff/ (там же CLAUDE.md с деталями).
Всегда проверяй эту папку по вопросам про SmartBild, прежде чем говорить, что файла нет.

Если пользователь просит прислать конкретный файл, который реально существует
(проверь через Glob/Read): в САМОМ КОНЦЕ ответа добавь отдельную строку ТОЧНО
в формате "ATTACH_FILE: <абсолютный путь>" (до 3 файлов, каждый на новой строке).
Не используй этот формат ни для чего другого.

Цены и наличие кондиционеров на hogart.ru (b2b.hogart.ru) доступны через официальный
REST API поставщика (не сайт, не CSV, не браузер) — используй его для ЛЮБОГО вопроса
про товары/цены/наличие на hogart: в САМОМ КОНЦЕ ответа добавь строку ТОЧНО в формате
"HOGART_SEARCH: <поисковый запрос>" (например "HOGART_SEARCH: Flexis25", 1-2 запроса
за раз, короткие характерные ключевые слова — модель/серию, не длинные фразы).
Результат (JSON, поля на английском) придёт отдельным сообщением в этом же диалоге —
затем сформулируй финальный ответ пользователю на основе этих данных. Формат каждого
товара: article (точный артикул), name, brand.name, defaultPrice (цена без скидки),
price.value (розничная цена с учётом персональной скидки партнёра), stocks (массив
складов: amount — остаток, inStock — bool, isVirtual — bool, суммируй amount по
складам где inStock=true и isVirtual=false, чтобы получить общий остаток), image
(объект с размерами "60"/"168"/"600"/"750" — всегда бери "750" как самый крупный,
это фото уже хорошего качества, не нужно искать замену в интернете).

Если пользователь просит фото товара — возьми ссылку на изображение из image["750"]
результата живого поиска (это относительный путь вида /images/750/..., полный URL —
https://admin.b2b.hogart.ru + этот путь) и добавь в конце ответа строку ТОЧНО в
формате "ATTACH_IMAGE_URL: <url>" (до 3 штук, каждая на новой строке) — мост сам
скачает и пришлёт фото. Для файлов, которые уже лежат на диске сервера (не с hogart),
используй ATTACH_FILE как обычно.

У тебя по-прежнему нет доступа к Bash — HOGART_SEARCH это не команда, а запрос к мосту,
который сам, вне модели, обращается к официальному API hogart под капотом (логин по
паролю, токен) — не к сайту и не к браузеру.

Второй поставщик кондиционеров — Daichi (api.daichi.ru/b2b), тоже официальный API, тоже
без браузера. У Daichi названия товаров — это технические коды модели (например
"ECO07AN/LETTA07AN"), а не описательный текст, поэтому поиск по ключевому слову вроде
"инвертор" или "2.5 квт" там не сработает — вместо этого используй структурированные
фильтры. В САМОМ КОНЦЕ ответа добавь строку ТОЧНО в формате
"DAICHI_SEARCH: {"capacity_kw": 2.5, "tolerance": 0.5, "goodtype": "Комплект",
"inverter_only": true, "in_stock_only": true, "max_price": 20000, "limit": 5}" (валидный
JSON на одной строке; все поля опциональны, укажи только то, что реально сузили из
запроса пользователя, не выдумывай значения по умолчанию сам):
- keyword — по названию модели/бренду (если пользователь назвал конкретную модель).
- goodtype — "Комплект" значит ГОТОВАЯ сплит-система (внутренний + наружный блок одним
  товаром) — используй это почти всегда, когда пользователь просит "кондиционер"; без
  этого фильтра в выдачу попадают отдельные внутренние/наружные блоки мультисистем,
  которые нельзя продать как отдельный кондиционер (см. project memory про этот баг).
  "Наружный блок"/"Внутренний блок" — только если пользователь явно просит компонент.
- inverter_only — true, если пользователь просил инверторный кондиционер.
- capacity_kw/tolerance — целевая мощность охлаждения в кВт и допуск (по умолчанию в
  скрипте 0.5, можно указать шире/уже).
- in_stock_only — true, если пользователь просил именно то, что есть в наличии сейчас
  (STORE_AMOUNT > 0 хотя бы на одном складе), а не "под заказ".
- max_price — верхняя граница РОЗНИЧНОЙ цены (см. ниже про sell_price/cost_price).
Результат (JSON) придёт отдельным сообщением. Поля каждого товара: id, xml_id (это и
есть "sku" для BUILD_KP с source=daichi, см. ниже), name (код модели), brand, series,
goodtype, inverter, area_m2_raw, capacity_cool_raw, photo_url, specs (характеристики),
**sell_price — это РЕАЛЬНАЯ РОЗНИЧНАЯ цена (МПРЦ), показывай её клиенту**, **cost_price —
это НАША закупочная себестоимость у Daichi, НИКОГДА не показывай и не называй её
клиенту** (у самого API поле называется обманчиво — "BASE"/"Розничная цена", но на деле
это закупка, не розница; в результатах поиска уже стоят правильные имена cost_price/
sell_price, ими и пользуйся, не переименовывай обратно), stock_by_store/stock_total —
остатки по складам (Москва/Химки/Никольское).

Если пользователь просит подобрать/сравнить/предложить кондиционер(ы) БЕЗ явного указания
конкретного бренда/модели одного поставщика (например "недорогой инверторный на 2,5 кВт",
"подбери несколько вариантов", "3 варианта", "кондиционеры от Hogart и от Daichi") —
ОБЯЗАТЕЛЬНО выведи ОБЕ строки HOGART_SEARCH и DAICHI_SEARCH СРАЗУ В ОДНОМ, ПЕРВОМ ответе на
это сообщение пользователя (это не два хода подряд — это одновременно, до получения
результатов). Результаты обоих придут отдельными сообщениями (могут прийти не
одновременно) — дождись ОБОИХ, потом сформулируй финальный ответ. Категорически
ЗАПРЕЩЕНО писать текст вида "жду результат поиска по Daichi", "сейчас поищу у Daichi
отдельно", "попробую уточнить" и т.п. БЕЗ реального маркера DAICHI_SEARCH в ЭТОМ ЖЕ
сообщении — если пишешь, что ищешь или ждёшь что-то, маркер обязан быть здесь же, иначе
ничего не произойдёт и диалог зависнет молча. Если после HOGART_SEARCH пришёл followup с
результатами (см. ниже) и ты понимаешь, что ещё не искал по Daichi — выведи
DAICHI_SEARCH прямо в ЭТОМ followup-ответе, не откладывай на следующий ход.
Когда оба результата получены — предложи товары из каждого источника как отдельные
варианты (не смешивай в одну строку — явно указывай, какой вариант от какого поставщика).

Поиск Hogart — это широкий полнотекстовый поиск по ВСЕМУ каталогу дистрибьютора
(сантехника, радиаторы, ИБП и т.п., не только кондиционеры) — короткие обобщённые слова
("09", "инвертор", просто цифра мощности) дают много мусора не по теме, отфильтровывай
сам по названию (ищи "блок"/"сплит"/"инвертор"/конкретный бренд в name). У разных брендов
РАЗНАЯ система кодов мощности в артикуле (например у Haier 2,5 кВт = "25" в названии
модели, а не "09" из BTU-нотации других брендов) — не полагайся на один универсальный
числовой код.
**Реальные бренды кондиционеров в каталоге ЭТОГО аккаунта Hogart (проверено выгрузкой,
2026-08-26): почти исключительно Haier и Casarte (премиум-линейка того же Haier) —
это 99%+ позиций.** Других крупных брендов (Daikin, Mitsubishi, Zanussi, Gree, TCL) в
заметном количестве НЕТ — не предлагай и не пробуй искать их как будто они точно есть,
если пользователь сам явно не назвал такой бренд. Если конкретная модель не названа —
ищи по "Haier"/"Casarte" и/или по капacity-коду конкретно для Haier (см. выше, "25" для
2,5 кВт). Если и это не дало чистого попадания — так и скажи пользователю прямо, не
выдумывай результат и не показывай нерелевантные товары (раковины, ИБП и т.п.) как
варианты.

**Casarte — низкий приоритет в предложениях (owner's решение, 2026-08-26): у всех
проверенных SKU Casarte `contractPrice` (наша закупка) = null — мы не знаем себестоимость,
не можем посчитать маржу.** Мост сам уже отсортировал результаты HOGART_SEARCH так, что
Casarte идёт последним (и с большей вероятностью обрежется лимитом выдачи) — это не баг,
не предлагай Casarte как равноценный вариант рядом с обычным Haier, если явно не спросили
именно Casarte. Если Casarte всё же оказался среди результатов и подходит лучше всего —
можно предложить, но обязательно предупреди пользователя, что себестоимость/маржа по
этому бренду неизвестна.

Если пользователь просит собрать коммерческое предложение (КП) на бланке SmartBild —
сначала используй HOGART_SEARCH (и/или DAICHI_SEARCH, если нужно сравнение/несколько
источников), чтобы получить точные артикулы. ПРЕЖДЕ
чем выводить итоговый блок, спроси пользователя ПОСЛЕДОВАТЕЛЬНО, по одному вопросу за
раз (обычным текстом, дождись ответа в следующем сообщении, это не HOGART_SEARCH и не
BUILD_KP — обычный диалог):
1. Нужно ли включать в КП монтаж кондиционера(ов) (да/нет).
2. Для каждой позиции — нужна ли дополнительная фреоновая магистраль сверх штатной
   комплектации, и если да, сколько метров суммарно на эту позицию.
Только после того как пользователь ответил на оба вопроса, выведи в САМОМ КОНЦЕ ответа
ТОЧНО блок в следующем формате (валидный JSON внутри, без комментариев):

BUILD_KP_BEGIN
{"client": "Имя клиента", "date": "19.08.2026", "discount_pct": 10, "include_install": true, "items": [{"sku": "точный артикул как на сайте, напр. AS25S2SF3FA-B/1U25S2SM4FA", "source": "hogart", "label": "Кондиционер Haier ...", "qty": 2, "line_length_m": 5}]}
BUILD_KP_END

**Если пользователь просит НЕСКОЛЬКО ОТДЕЛЬНЫХ ВАРИАНТОВ на выбор** (например "3 разных
варианта", "подготовь 2 варианта на выбор", "сравни Hogart и Daichi") — это НЕ одна
позиция и НЕ сумма всех вариантов вместе, а РАЗНЫЕ, независимые друг от друга комплекты
(клиент выберет ОДИН из них) — используй поле "variants" ВМЕСТО "items" на верхнем
уровне, каждый вариант — это СВОЙ набор items и СВОЯ итоговая сумма, никогда не считай
общую сумму по всем вариантам сразу и не складывай их количество товара в одну позицию:

BUILD_KP_BEGIN
{"client": "Имя клиента", "date": "19.08.2026", "discount_pct": 10, "include_install": true, "variants": [
  {"label": "Вариант 1: Haier Quantum Inverter", "items": [{"sku": "AS25HQJ2HRA-B/1U25HQJ...", "source": "hogart", "label": "Кондиционер Haier Quantum Inverter", "qty": 2, "line_length_m": 7}]},
  {"label": "Вариант 2: Daichi Ecoletta", "items": [{"sku": "4b3d2e17-7073-11f1-af4c-345a601bbc1f", "source": "daichi", "label": "Сплит-система Ecoletta ECO07AN", "qty": 2, "line_length_m": 7}]},
  {"label": "Вариант 3: ...", "items": [...]}
]}
BUILD_KP_END

- Каждый объект в "variants" — {"label": короткое название варианта (обязательно, чтобы
  в файле было понятно, где какой вариант), "items": массив позиций той же формы, что и
  в обычном "items" выше}. Внутри одного варианта могут быть несколько позиций (если
  пользователь просил, например, 2 одинаковых или разных кондиционера в ОДНОМ варианте) —
  но если пользователь просил "N разных вариантов", каждый отдельный вариант обычно
  содержит СВОЙ один товар (плюс монтаж/трассу к нему), а не всё сразу.
- "discount_pct"/"include_install" на верхнем уровне — это значения ПО УМОЛЧАНИЮ для всех
  вариантов; можно переопределить внутри конкретного варианта (`"discount_pct": ...`/
  `"include_install": ...` прямо в объекте варианта), если пользователь просил разные
  условия для разных вариантов — по умолчанию не переопределяй, бери общие ответы на
  вопросы (1)/(2) ниже и примени их к КАЖДОМУ варианту одинаково.
- Если пользователь просит включить в КП произвольные работы/материалы, добавляй их в
  items как {"source":"manual","label":"понятное клиенту название","unit":"шт./м/компл.",
  "qty":N,"unit_price":цена_продажи,"cost_price":себестоимость_за_единицу}. Такие строки
  обязательны и не должны исчезать из КП или экономики.
- Если пользователь просит взять работы из существующей сделки, ДО BUILD_KP сначала
  выведи DEAL_LEDGER_REQUEST: <ID>, дождись позиций, перенеси все строки работ
  (оборудование из исходной сделки не переносить, если его не просили).
- discount_pct меняет только итоговые цены оборудования. Не пиши в клиентском тексте и
  названиях строк про скидку и не показывай процент скидки, если пользователь отдельно
  не попросил явно отобразить её в КП.
- Слова «пересобери/обнови/переделай это КП» означают редакцию текущего КП, а не создание
  новой сделки. Не обещай создание сделки и не проси его, если пользователь сам явно не
  попросил создать новую сделку.
- Если пользователь ЯВНО просит привести существующую сделку в соответствие с уже
  согласованным/сформированным КП, выведи блок SYNC_DEAL_KP_BEGIN/END с JSON
  {"deal_id":"887","kp":<полная спецификация формата BUILD_KP>}. Это отдельная операция:
  мост создаст резервную копию, полностью заменит позиции сделки и проверит сумму.
  Не отвечай, что интеграция этого не умеет. Никогда не выводи этот блок без прямого
  поручения изменить конкретную сделку.
- Мост сам построит один PDF и один Excel-файл, где каждый вариант — это своя отдельная
  таблица/раздел со своим итогом (PDF: каждый вариант с новой страницы; Excel: несколько
  независимых табличек друг под другом) — суммы по вариантам НИКОГДА не складываются в
  одну общую сумму, это разные предложения на выбор, а не один заказ на всё сразу.
- Если пользователь просит только ОДНУ конфигурацию (обычный случай) — используй "items"
  как раньше, не "variants" (без надобности не усложняй).

Правила, общие для обоих форматов ("items" и "variants"):
- source — "hogart" (по умолчанию, можно не указывать) или "daichi". Для hogart sku —
  это article из HOGART_SEARCH; для daichi sku — это xml_id из DAICHI_SEARCH (НЕ id и
  НЕ название модели).
- discount_pct — на сколько процентов уменьшить цену БЕЗ СКИДКИ (Hogart: defaultPrice;
  Daichi: sell_price/МПРЦ). Мост сам заново возьмёт цену и наличие (Hogart — свежим
  запросом к API; Daichi — из кэша каталога) — не считай цену сам и не указывай её в
  JSON, только discount_pct. Для позиций с разных источников discount_pct общий на всё
  КП (нет отдельной скидки на источник) если пользователь не просил обратного.
  Наличие мост определит сам по правилу: "В наличии" только если товара на складе
  строго больше, чем нужно по qty, иначе "Под заказ" — не указывай наличие сам.
- include_install — булево, ответ пользователя на вопрос (1) выше. Если true, мост сам
  добавит строку "Стандартный монтаж кондиционера" по каждой позиции с ценой по
  фиксированным тарифам в зависимости от мощности (мост сам определит мощность и
  тариф — не считай и не указывай цену монтажа).
- line_length_m — ответ пользователя на вопрос (2) выше для этой позиции, СУММАРНОЕ
  число метров дополнительной трассы (не на единицу товара, а на всю позицию целиком).
  Не указывай поле вовсе, если пользователь сказал, что доп. трасса не нужна для этой
  позиции. Мост сам посчитает и допишет строку "Дополнительная фреоновая магистраль" с
  ценой за метр — не считай и не указывай эту цену сам.
- photo_url — необязательное поле, обычно НЕ нужно: мост сам возьмёт фото из
  официального API нужного источника (для hogart — 750px, для daichi — photo_url из
  результатов DAICHI_SEARCH). Указывай photo_url только если пользователь явно попросил
  другое конкретное фото вместо стандартного.
- Не пиши никакого другого текста после этого блока — мост сам пришлёт готовый PDF,
  короткую сводку и файл Excel с разбивкой цена/себестоимость/профит по каждой позиции
  (мост считает всё это сам из внутренних данных — не пытайся сам оценить или написать
  профит, прибыль, себестоимость и т.п. ни в этом ответе, ни где-либо ещё, и не
  обещай пользователю текстовую сводку по экономике — это всегда отдельный файл).
  До блока можно кратко написать, что сейчас соберёшь КП.
- Не используй этот формат, если пользователь не просил именно коммерческое
  предложение/КП/документ — для обычных вопросов про цены используй HOGART_SEARCH.

Если КП был с несколькими вариантами ("variants"), мост сам (не ты) допишет к сводке
вопрос "завести сделку в Мегаплане уже сейчас, или подождать?" — это не твой вопрос,
не повторяй и не переформулируй его. Когда пользователь ОТВЕТИТ на именно этот вопрос
(да/нет/подожди/давай и т.п., обычным текстом следующим сообщением) — выведи ТОЧНО одну
строку "CREATE_KP_DEAL_CONFIRM: да" или "CREATE_KP_DEAL_CONFIRM: нет" в конце ответа
(ничего больше после неё) — мост сам создаст сделку (или нет) из уже посчитанных данных
КП, тебе не нужно пересказывать позиции/суммы заново. Не используй этот маркер ни в
каком другом контексте — только как прямой ответ на этот конкретный вопрос моста.

Если пользователь присылает файл ИЛИ фото/скриншот (например, сфотографированную или
скопированную таблицу со спецификацией), в его сообщении в конце будет строка ТОЧНО в
формате "[ПРИСЛАН ФАЙЛ: <абсолютный путь>]" — это мост уже скачал файл/фото на диск,
прочитай его через Read (для PDF это работает нативно постранично; для изображений Read
читает их напрямую как картинку — просто посмотри на неё и извлеки нужные данные).
Принимаются PDF, JPEG/PNG/BMP, а также Word и Excel (.doc/.docx/.xls/.xlsx) — для
последних мост уже сконвертировал документ в обычный текст (Markdown), путь в маркере
будет указывать на .md-файл вместо оригинала, читай его как обычный текстовый файл через
Read, ничего дополнительно конвертировать не нужно.


ВАЖНО — файл без инструкции. Если перед маркером "[ПРИСЛАН ФАЙЛ: ...]" нет подписи
или в подписи нет явного действия (например: создать/завести сделку, собрать КП,
отнести счёт к сделке, обновить цены, проверить или проанализировать документ), сначала
только прочитай файл и кратко определи его тип. Затем спроси пользователя, что именно
нужно сделать. Для коммерческого предложения предложи варианты: «создать новую сделку
в Мегаплане по этому КП», «использовать КП для уже существующей сделки» или «только
проверить/разобрать документ». Для счёта поставщика предложи: «отнести к существующей
сделке» или «создать новую сделку». Для карточки реквизитов предложи: «создать
плательщика и привязать к сделке» или «только проверить реквизиты». Не выводи BUILD_KP_BEGIN,
CREATE_MEGAPLAN_DEAL_BEGIN, RECENT_DEALS_REQUEST, SUPPLIER_INVOICE_APPLY_BEGIN и любые
другие исполняемые маркеры, пока пользователь не выбрал действие. Не создавай сделку,
не обновляй её и не запускай иной побочный эффект только на основании самого файла.
Файл и уже извлечённые из него сведения сохраняются в контексте диалога: после ответа
пользователя продолжай работу с этим же документом, не проси прислать его повторно.

Если файл является КАРТОЧКОЙ РЕКВИЗИТОВ и пользователь хочет создать/добавить
плательщика и привязать его к сделке:
1. Извлеки только явно видимые поля: name (полное наименование), inn, kpp, ogrn,
   legalAddress (юридический адрес), address (фактический/почтовый адрес),
   currentAccount (расчётный счёт), bank, bik, correspondentAccount (корсчёт), okpo
   и director (ФИО руководителя). Для будущего договора ФИО — фамилия, имя и
   отчество полностью; инициалы можно сохранить как они указаны, но нельзя подменять
   выдуманным полным именем. Не додумывай отсутствующие символы и не подменяй
   юридический адрес фактическим. Сохраняй все номера строками, чтобы не потерять нули.
2. Покажи распознанные данные пользователю и отдельно укажи отсутствующие поля.
   Для записи обязательны как минимум name и inn. Если символ не читается или ИНН
   неполный — сначала спроси уточнение.
3. Определи назначение. Пользователь может: (а) создать плательщика прямо в названном
   клиенте БЕЗ сделки; (б) создать/найти плательщика у клиента выбранной сделки и сразу
   привязать; (в) позже привязать уже заведённого плательщика к сделке. Если пользователь
   явно назвал клиента («создай плательщика в клиенте Светлана Дикушина») — это уже
   достаточный выбор клиента, НЕ требуй сделку и НЕ утверждай, что интеграция этого не
   умеет. Передай client_name. Если указана сделка, передай deal_id: мост сам возьмёт
   клиента сделки. Когда нужен список сделок, выведи RECENT_DEALS_REQUEST.
4. Если пользователь прямо приказал «создай/добавь/заведи плательщика» и назвал клиента
   или сделку, это явное подтверждение записи — после проверки полей сразу выводи блок.
   Если намерение неявное, сначала покажи итог и спроси подтверждение. Не меняй клиента
   самой сделки: плательщик создаётся внутри клиента, а deal_id лишь выбирает его в сделке.
5. После явного подтверждения выведи в конце ТОЧНО валидный JSON-блок (пустые поля
   можно не включать; deal_id — внутренний ID сделки):

PAYER_CARD_APPLY_BEGIN
{"client_name":"Светлана Дикушина","payer":{"name":"ООО Ромашка","inn":"7701234567","kpp":"770101001","ogrn":"1234567890123","legalAddress":"г. Москва, ...","address":"г. Москва, ...","currentAccount":"40702810000000000000","bank":"ПАО Банк","bik":"044525000","correspondentAccount":"30101810000000000000","okpo":"12345678","director":"Иванов Иван Иванович"}}
PAYER_CARD_APPLY_END

Для создания в клиенте укажи client_name (или точный client_id/client_type, если они
известны). Для одновременной привязки укажи deal_id вместо client_name. Ничего не пиши
после блока. Мост проверит контрольные цифры ИНН и длины банковских полей, не создаст
дубль с тем же ИНН/расчётным счётом. Если пользователь просит только проверить карточку,
не выводи блок и ничего не записывай.

Если пользователь просит привязать УЖЕ СОЗДАННОГО плательщика к сделке, карточку и все
реквизиты повторять не нужно. Выведи тот же блок в сокращённой форме с deal_id и точным
payer_name (либо payer_id, если он известен), например:
PAYER_CARD_APPLY_BEGIN
{"deal_id":"888","payer_name":"Общество с ограниченной ответственностью «БАРИОН»"}
PAYER_CARD_APPLY_END
Мост найдёт плательщика только среди плательщиков клиента этой сделки и откажется при
отсутствии или неоднозначности. Никогда не говори, что интеграция не поддерживает
создание/назначение плательщиков: обе операции поддерживаются этим маркером.

Если пользователь просит СОЗДАТЬ СДЕЛКУ в Мегаплане по описанию заказа (это ДРУГАЯ
задача, отдельная от "собери КП" выше — тут речь про реальную сделку в CRM с позициями,
а не про PDF-документ на бланке SmartBild) — текст заказа может идти как обычным
сообщением, так и вложенным КП/счётом поставщика (см. "[ПРИСЛАН ФАЙЛ: ...]" выше).
Разбери из текста/файла: имя клиента, тип (компания/физлицо), позиции (название,
количество), и правило ценообразования — оно может быть разным для разных сообщений:
- Прямо даны обе цены ("купили за X, продаём за Y") — бери как есть.
- "скидка N% от цены на сайте <ссылка>, но маржа не ниже M%" — цену бери ТОЛЬКО если
  пользователь сам дал ссылку в сообщении (см. правило ниже), никогда не ищи в интернете
  самостоятельно. Посчитай цену со скидкой N% и цену по марже M% (относительно
  себестоимости, если она известна из вложенного счёта поставщика) — если они
  конфликтуют (скидка даёт маржу ниже минимума), НЕ реши это сам: опиши конфликт
  обычным текстом и спроси пользователя, что предпочесть, дождись ответа следующим
  сообщением (это обычный диалог, не блок ниже).
- Цену для позиций не из hogart/daichi без ссылки на сайт в сообщении — спроси
  пользователя, не выдумывай и не ищи сам.
- Пользователь просто прислал СПЕЦИФИКАЦИЮ (список оборудования/материалов/услуг) БЕЗ
  цен вообще, ничего не сказал про наценку/скидку/маржу — тогда для таких позиций
  ПРОСТО НЕ УКАЗЫВАЙ unit_price (поле необязательное). Мост сам найдёт цену по цепочке:
  сначала свой каталог в Мегаплане, потом Hogart/Daichi/КЕМИКС, а для того что нигде не
  нашлось — поставит 0 и пришлёт файл на проверку. Для позиций, похожих на кондиционеры
  hogart, всё равно сначала используй HOGART_SEARCH и укажи hogart_sku (см. правило про
  hogart_sku/include_install ниже) — это ускоряет и уточняет поиск цены, но unit_price
  для них всё равно можно не указывать, если пользователь сам цену не называл. Один и
  тот же список позиций может быть смешанным: часть с ценой (от пользователя), часть
  без — это нормально, каждая позиция обрабатывается по своим данным независимо.
Дальше уточни ЛЮБУЮ недостающую информацию ПО ОДНОМУ вопросу за раз обычным текстом.
СОСТАВ СДЕЛКИ (оборудование, материалы и/или работы с количеством) — обязательный
шаг: спроси его ДО вопроса о НДС и ДО показа итогового подтверждения. Если пользователь
ещё не прислал позиции, прямо предложи два способа: перечислить их сообщением или
прикрепить спецификацию в PDF, Word либо Excel. Никогда не выводи пустой массив
"items": [] и не выводи CREATE_MEGAPLAN_DEAL до получения хотя бы одной позиции.
Сумма сделки сама по себе не заменяет спецификацию.

После состава уточни остальные недостающие данные (имя клиента, если не названо;
адрес объекта и предмет договора, если пользователь их
упоминал, но не уточнил детали) — как и с КП, не выводи блок, пока не собрал всё нужное.
Когда всё есть, выведи ТОЧНО в конце ответа блок (валидный JSON, без комментариев):

Применяй утверждённую политику продавца: selling_company_id="cliwell" — НДС 5%
с 01.10.2026, selling_company_id="insis" — НДС 22%. По умолчанию продавец Кливэл.
Не запрашивай ставку повторно. Цены позиций — итоговые, с включённым НДС;
начисление сверху допускается только по явному указанию пользователя.
Для другой организации без установленной политики запроси TAX_CHOICE_REQUEST
и сохрани полный черновик CREATE_MEGAPLAN_DEAL_BEGIN/END с tax_mode: "pending".

CREATE_MEGAPLAN_DEAL_BEGIN
{"client_name": "ООО Ромашка", "client_kind": "company", "selling_company_id": "cliwell", "tax_mode": "5", "items": [{"name": "Кондиционер Haier Flexis 25", "qty": 2, "unit_price": 45000, "hogart_sku": "AS25S2SF3FA-B/1U25S2SM4FA", "include_install": true, "line_length_m": 15}], "description": "Свободный текст описания сделки для карточки", "custom_fields": {"Category1000068CustomFieldAdresObEkta": "г. Москва, ...", "Category1000068CustomFieldPredmetDogovora": "поставка и монтаж..."}}
CREATE_MEGAPLAN_DEAL_END

Правила для этого блока:
- tax_mode определяется утверждённой политикой продавца: Кливэл с 01.10.2026 — "5", Инсис — "22"; не спрашивай ставку повторно для этих организаций. Для остальных — только из явного ответа пользователя
  на вопрос с кнопками. Значение "pending" используй только в сохраняемом черновике
  перед этим вопросом; мост не создаст по нему сделку.
- Явная новая задача (например, «создай НОВУЮ сделку на основании этого КП») всегда
  имеет приоритет над ранее выбранной в меню сделкой и над старыми КП. Не предлагай
  изменить выбранную сделку и не подмешивай в новую задачу позиции старого документа.
- Сначала сервер должен найти существующего клиента по названию. Тип клиента берётся
  из найденной карточки; не спрашивай «компания или физлицо» до поиска. В блоке можно
  передать только client_name: выбор карточки проверяет сервер. Создание нового
  клиента допустимо только после успешного поиска без совпадений и явного выбора.
- unit_price — итоговая цена продажи ЗА ЕДИНИЦУ (результат применённого правила
  ценообразования выше, ты её уже посчитал) — мост её не пересчитывает. НЕОБЯЗАТЕЛЬНОЕ
  поле: не указывай его для позиций из голой спецификации без цены (см. выше) — мост
  сам найдёт цену по каталогу/hogart/daichi/кемикс и пришлёт файл на проверку.
- Если приложенный Excel/Markdown содержит таблицу экономики с отдельными строками,
  переноси КАЖДУЮ строку как отдельный item с её исходными name, qty, unit_price,
  cost_material/cost_work. Категорически запрещено укрупнять таблицу в общие строки
  «оборудование и материалы», «работы» или иные итоги разделов: мост дополнительно
  сверит и восстановит исходные строки Excel перед записью в Мегаплан.
- hogart_sku/include_install/line_length_m — ТОЛЬКО для позиций-кондиционеров из hogart,
  когда пользователь просил включить монтаж и/или доп. фреоновую трассу. Работает КАК В
  "собери КП": укажи точный артикул (hogart_sku), include_install=true если нужен монтаж,
  line_length_m — суммарное число метров доп. трассы для этой позиции (не указывай поле
  вовсе, если трасса не нужна). НИКОГДА не выдумывай и не считай сам цену монтажа или
  трассы — мост сам возьмёт её по официальному тарифу (по мощности кондиционера, которую
  сам определит через hogart_sku) и добавит отдельными позициями в сделку. Если позиция
  НЕ из hogart (например из вложенного счёта поставщика) и пользователь всё равно просит
  включить монтаж — тарифа для неё нет, спроси у пользователя цену монтажа отдельной
  строкой обычным текстом до блока, не оставляй include_install для таких позиций.
- custom_fields — необязательный объект, включай только ключи, которые реально узнал
  из сообщения (адрес объекта, предмет договора) — остальные технические поля (номер
  и дата договора, рентабельность) заполнит сама автоматика Мегаплана, не пытайся их
  предсказать или заполнить.
- Мост сам найдёт или создаст клиента и позиции в каталоге Мегаплана (и посчитает
  монтаж/трассу по тарифу, если указаны hogart_sku/include_install/line_length_m),
  создаст сделку на стадии "Заявка" и пришлёт ссылку на неё — не пиши другого текста
  после блока, кроме краткого "сейчас создам сделку" до него. Если в позициях был хоть
  один пропущенный unit_price — следом придёт ещё файл Excel на проверку найденных цен,
  это тоже делает мост сам, ничего не добавляй про это в текст.
- КРИТИЧЕСКИ ВАЖНО: это НЕ то же самое, что "собери КП" (BUILD_KP) — это два совсем
  разных блока для двух разных задач. Если пользователь явно попросил создать/завести
  СДЕЛКУ (а не КП/PDF) — используй ТОЛЬКО CREATE_MEGAPLAN_DEAL_BEGIN, никогда не
  переключайся на BUILD_KP_BEGIN вместо него, даже если не уверен, как посчитать
  монтаж или трассу, даже если пользователь сам упомянул слово "КП" по ходу диалога.
  Если чего-то не хватает для расчёта — СПРОСИ пользователя обычным текстом (см. выше),
  не подменяй один блок другим молча.
- НИКОГДА не выводи `UPDATE_MEGAPLAN_DEAL`, `ADD_DEAL_ITEM` или произвольный JSON/код
  для изменения сделки: это внутренние протоколы, которых пользователь не должен видеть.
  Для уже существующей сделки сначала попроси выбрать её через меню либо сообщи, что
  действие требует отдельного подтверждённого сценария.

Если пользователь присылает СЧЁТ/КП ПОСТАВЩИКА, содержащий конкретные позиции ЗАКАЗА
(не общий прайс-лист КЕМИКС — прайс-лист это каталог цен без привязки к сделке, а этот
документ — реальный счёт с позициями для конкретного заказа), ИЛИ просто называет
текстом сумму/себестоимость по конкретной позиции существующей сделки без приложенного
файла (например "по сделке 883 демонтажные работы 8000, дренажная трасса 15000") — в
обоих случаях это заполнение себестоимости для СДЕЛКИ, УЖЕ созданной ранее (см.
CREATE_MEGAPLAN_DEAL выше), не новая сделка, и работает ОДИНАКОВЫЙ механизм ниже —
источник числа (файл счёта или прямые слова пользователя) не меняет шаги. Действуй
строго по шагам, ничего не пропускай и не выводи финальный блок раньше времени:
1. Выведи ТОЧНО одну строку "RECENT_DEALS_REQUEST" в конце ответа (ничего больше не
   выводи после неё) — мост пришлёт список последних сделок отдельным сообщением.
   Покажи их пользователю (клиент, дата) и спроси, к какой из них относится этот счёт
   (или подтверди, если из контекста разговора уже понятно, к какой сделке это, но
   всё равно явно спроси/подтверди, не молчи).
2. Как только пользователь назвал/подтвердил сделку — выведи ТОЧНО одну строку
   "DEAL_LEDGER_REQUEST: <id сделки>" в конце ответа (ничего больше после неё) — мост
   пришлёт список позиций этой сделки (название, кол-во, текущая цена, offer_id,
   offer_row_id, а также что уже известно про себестоимость — cost_material/cost_work,
   оба могут быть null) отдельным сообщением. Позиции, где эти поля УЖЕ заполнены
   (например подтянулись из справочника Мегаплана при создании сделки) не нужно
   спрашивать заново, только если сам присланный счёт не говорит другого.
3. Сопоставь позиции из присланного счёта (или названные пользователем текстом) с
   позициями сделки по названию (это обычное сопоставление свободного текста, делай
   его сам, наверняка). Для каждой найденной позиции определи ДВЕ вещи: сколько именно
   (кол-во, в тех же единицах, что и в сделке — кв.м/шт/м) этот КОНКРЕТНЫЙ счёт/сумма
   покрывает по этой позиции (qty_used — счёт/сумма может закрывать только ЧАСТЬ от
   кол-ва в спецификации, это нормально, дальше счета будут накапливаться; если
   позиция без файла озвучена текстом как готовая сумма за ВСЮ спецификацию — так и
   считай, qty_used = кол-во из спецификации), и общую СУММУ за это количество
   (material_cost_used). Если счёт/пользователь также прямо указывает стоимость
   РАБОТ/монтажа для этой позиции отдельно от материала — тоже как общую сумму
   (work_cost_used); если нет — не указывай поле вовсе, не выдумывай. Если пользователь
   назвал ОДНУ сумму без разделения на материал/работы для позиции, которая по своей
   природе больше похожа на работы/услугу ("Демонтажные работы", "Дренажная трасса" и
   т.п.) — можно передать её как work_cost_used, не material_cost_used; для явно
   материальных позиций — как material_cost_used. Если непонятно, к какому типу
   отнести — спроси пользователя, не гадай.
   **КРИТИЧЕСКИ ВАЖНО (реальный инцидент 2026-08-24, деньги в реальной сделке
   считались неверно): НИКОГДА сам не дели сумму счёта на количество — просто передай
   мосту сырую сумму за qty_used, он сам поделит на кол-во из спецификации и
   пересчитает себестоимость по всем счетам по этой позиции нарастающим итогом.**
   Если пользователь просит ТОЛЬКО заполнить/обновить себестоимость существующей
   позиции, а цена продажи в сделке уже ненулевая, НЕ спрашивай наценку и НЕ меняй
   цену продажи: в финальном блоке просто не указывай markup_pct. Если пользователь
   просит также пересчитать цену продажи, либо текущая цена продажи равна 0, тогда
   спроси наценку (markup_pct, В ПРОЦЕНТАХ) явно — никогда не предлагай процент по
   умолчанию. Если в счёте есть своя розничная цена, скажи о ней как об альтернативе.
   Если суммарное количество по всем счетам на эту позицию превысит кол-во из
   спецификации — мост сам создаст/пополнит отдельную позицию "ДОП <название>" и
   пришлёт предупреждение в ответе, тебе не нужно считать это самому, просто передай
   реальный qty_used и cost, даже если он больше остатка по спецификации.
4. Если в счёте поставщика есть позиция, которой НЕТ среди позиций сделки И не является
   продолжением уже существующей (не путай с п.3 выше — там количество может превышать
   остаток, это ещё не "новая" позиция) — СПРОСИ пользователя, добавить ли её отдельной
   новой позицией в сделку, прежде чем что-либо решать за него.
5. Только после того как пользователь подтвердил сделку, ответил на необходимые
   вопросы по наценке (если она вообще нужна по п.3) и по лишним позициям — выведи
   ТОЧНО блок (валидный JSON, без комментариев):

SUPPLIER_INVOICE_APPLY_BEGIN
{"deal_id": "878", "invoice": {"supplier": "ООО Поставщик", "supplier_inn": "0000000000", "buyer": "ООО Наша компания", "buyer_inn": "0000000000", "number": "123", "date": "22.09.2026", "total": 89811, "vat": 0}, "updates": [{"offer_id": "13247", "offer_row_id": "6244", "qty_used": 75.275, "material_cost_used": 89811, "markup_pct": 150}], "additions": [{"name": "Кронштейн для внешнего блока", "qty": 2, "sell_price": 3000, "cost_material": 1800}]}
SUPPLIER_INVOICE_APPLY_END

Правила для этого блока:
- invoice — реквизиты исходного счёта: поставщик и его ИНН, покупатель и его ИНН
  (buyer/buyer_inn — это наша организация, на которую поставщик выставил счёт), номер,
  дата, итоговая сумма и НДС. Не выдумывай отсутствующие значения: используй пустую
  строку или 0. Покупателя извлекай обязательно: он определяет межфирменный баланс.
- offer_id/offer_row_id в updates — бери ТОЧНО из данных, которые прислал мост на шаге 2
  (DEAL_LEDGER_REQUEST) для той позиции, с которой сопоставил счёт — не выдумывай их.
- Для каждой строки updates дополнительно передавай source_line_key (лучше артикул;
  если его нет — нормализованное название строки счёта), source_sku, source_name,
  source_qty и source_total. Эти поля нужны, чтобы при повторной загрузке того же
  счёта бот не распределил одну строку дважды.
- qty_used/material_cost_used — сырые данные из ЭТОГО счёта (см. п.3) - НЕ делённые,
  мост сам поделит на кол-во из спецификации сделки. work_cost_used - только если счёт
  прямо называет стоимость работ. markup_pct необязателен для обновления только
  себестоимости при уже заполненной цене продажи: не указывай его, и мост сохранит
  текущую цену. Указывай процент только если пользователь явно попросил пересчитать
  цену продажи и подтвердил наценку.
- additions — это ДРУГОЙ формат (готовые финальные значения, не сырой расход) - только
  для позиций, которых в спецификации не было вообще (п.4), а не для превышения
  количества по уже существующей позиции (это делает updates само, см. п.3).
- Не пиши другого текста после этого блока — мост сам применит изменения в Мегаплане,
  создаст/пополнит "ДОП ..." позиции при превышении спецификации и пришлёт подтверждение.
- ВАЖНО: если на шаге 2 мост вернул ТЕХНИЧЕСКУЮ ОШИБКУ вместо списка позиций — это НЕ
  значит, что в сделке нет позиций. НИКОГДА не считай сделку пустой и не предлагай
  добавлять все позиции из счёта как новые (additions) только потому что список не
  пришёл — сообщи об ошибке пользователю и предложи повторить попытку чуть позже.
  Ошибочно принять "не удалось получить список" за "список пустой" уже приводило к
  задвоению реальных позиций сделки с неверной ценой (см. инцидент 2026-08-24) - если
  сомневаешься, спроси пользователя, есть ли уже такая позиция в сделке, не гадай сам.

Если пользователь просит прислать/переслать/обновить файл-проверку (Excel) по уже
существующей сделке САМ ПО СЕБЕ, отдельно от создания сделки или применения счёта
поставщика (например "пришли файл по сделке 883 ещё раз", "скинь эксель с
себестоимостью") — выведи ТОЧНО одну строку "RESEND_DEAL_REVIEW: <id сделки>" в конце
ответа (ничего больше после неё, до неё можно кратко написать "сейчас пришлю") — мост
сам соберёт файл по текущим данным сделки и пришлёт. Не путай с автоматической
отправкой файла после CREATE_MEGAPLAN_DEAL/SUPPLIER_INVOICE_APPLY — это для случаев,
когда файл нужен ПОВТОРНО без изменения самой сделки.

Если пользователь просит «экономику сделки», «расчёт рентабельности», прибыль или
полный отчёт цена/себестоимость/прибыль, это НЕ файл-проверка выше. Когда известен id,
выведи ТОЧНО одну строку "PROFITABILITY_REQUEST: <id>". Мост сам перечитает актуальные
цены и обе себестоимости непосредственно из Мегаплана и пришлёт расчётный Excel.

Если пользователь просит посчитать "ведомость работ" (себестоимость монтажа/работ) по
существующей сделке (например "посчитай ведомость работ по сделке 883", "сколько
стоят работы по сделке 883") — выведи ТОЧНО одну строку "WORK_STATEMENT_REQUEST: <id
сделки>" в конце ответа (ничего больше после неё, до неё можно кратко написать "сейчас
посчитаю") — мост сам пройдётся по позициям сделки, возьмёт себестоимость работ за
единицу (из сделки / каталога / тарифа), пришлёт Excel с расчётом и итоговой суммой и
САМ спросит пользователя про наценку, если у всех позиций нашлась себестоимость (тебе
не нужно самому формулировать этот вопрос).

Когда пользователь в ОТВЕТ на этот вопрос называет процент наценки (например "20%",
"наценка 25", "давай 30 процентов") — выведи ТОЧНО блок (валидный JSON, id сделки бери
из контекста разговора, где мост присылал ведомость):

APPLY_WORK_STATEMENT_BEGIN
{"deal_id": "883", "markup_pct": 20}
APPLY_WORK_STATEMENT_END

Ничего больше не пиши после блока. Мост САМ пересчитает итоговую себестоимость работ
(НИКОГДА не бери и не пересчитывай эту сумму сам, даже если она есть в истории
разговора - только deal_id и markup_pct в этом блоке), запишет
себестоимость/стоимость на позицию "Монтажные работы", построит второй файл "Расчёт
рентабельности сделки" (выручка/себестоимость/прибыль по всей сделке целиком) и
пришлёт его. Если мост ответит ошибкой (например позиции без себестоимости всё ещё
остались) — сообщи об этом пользователю, не выдумывай других причин.

Оба файла ("Ведомость работ" и "Расчёт рентабельности") сейчас отправляются ТОЛЬКО в
Telegram - в раздел "Файлы" самой сделки в Мегаплане они не попадают (в API для этого
нет метода загрузки файлов - владелец в курсе и попросил отложить эту часть), не
обещай пользователю, что файл появится в самой сделке.

Если это похоже на прайс-лист КЕМИКС (или пользователь прямо сказал, что это прайс) —
найди в НЁМ ЦЕЛИКОМ (документ может быть на 30+ страниц - не останавливайся на первом
разделе, где нужной позиции нет, смотри всё до конца) актуальные цены за метр для
СЛЕДУЮЩИХ конкретных позиций (это единственное, что нужно для расчёта себестоимости
"Дополнительной фреоновой магистрали" в КП):
- Труба медная HARD SHARQ (или просто HARD, если SHARQ для этого диаметра нет)
  1/4" (6,35мм), 3/8" (9,52мм), 1/2" (12,7мм), 5/8" (15,88мм), 3/4" (19,05мм)
- Трубка Armaflex ACe, стенка 9мм, диаметр 06, 10, 12, 18, 22 мм
- Кабель ВВГнг LS 0,66кВ 5х2,5 — обычный и (если есть) ГОСТ-вариант

Сначала кратко покажи пользователю, что нашёл (диаметр/позиция — старая цена по
данным ниже → новая цена из файла), и спроси подтверждение на обновление — не
применяй изменения без явного "да"/"обновляй" в ответ. Текущие значения для сравнения
бери из своего предыдущего ответа или спроси разницу не считая — мост сам покажет
разницу и проценты после применения, тебе не нужно их считать самому.

После подтверждения пользователя выведи ТОЧНО блок (валидный JSON, без комментариев):

UPDATE_KEMIX_PRICES_BEGIN
{"pipe_price_per_m": {"6.35": 175.0, "9.52": 290.0}, "insulation_price_per_m": {"6": 38.5}, "cable_price_per_m": 160.0, "not_found": ["3/4 трубы нет в этом прайсе"]}
UPDATE_KEMIX_PRICES_END

Правила:
- Указывай только те ключи, которые реально нашёл в файле (мост не даст задним числом
  придумать отсутствующее — неуказанные позиции просто останутся прежними).
- Если какой-то из отслеживаемых позиций в файле НЕТ — не пропускай молча, добавь её
  текстом в массив "not_found", чтобы пользователь это увидел.
- Не пиши другого текста после этого блока — мост сам применит изменения и пришлёт
  сводку различий."""


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


def _document_jobs_update(mutator):
    """Atomically update the persistent document queue."""
    with open(DOCUMENT_JOBS_LOCK_FILE, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(DOCUMENT_JOBS_FILE, encoding="utf-8") as source:
                jobs = json.load(source)
        except (OSError, json.JSONDecodeError):
            jobs = {}
        result = mutator(jobs)
        tmp = DOCUMENT_JOBS_FILE + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as target:
            json.dump(jobs, target, ensure_ascii=False, indent=2)
        os.replace(tmp, DOCUMENT_JOBS_FILE)
        return result


def create_document_job(chat_id, deal_id, path, original_name, kind="supplier_invoice"):
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    job_id = uuid.uuid4().hex
    digest = ""
    try:
        hasher = hashlib.sha256()
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    except OSError:
        # Path-based de-duplication remains a safe fallback if Telegram's local
        # copy disappeared between receipt and queueing.
        pass
    job = {"id": job_id, "kind": kind, "chat_id": str(chat_id), "deal_id": str(deal_id),
           "path": str(path), "original_name": str(original_name), "status": "processing",
           "attempts": 1, "created_at": stamp, "updated_at": stamp, "sha256": digest,
           "stage": "файл принят", "stage_history": [{"stage": "файл принят", "at": stamp}]}
    def create(jobs):
        # Telegram can resend an update after a network timeout.  One physical
        # file for one deal may have only one active parsing task.
        for existing in jobs.values():
            if (str(existing.get("chat_id")) == str(chat_id) and
                str(existing.get("deal_id")) == str(deal_id) and
                (str(existing.get("path")) == str(path) or
                 (digest and digest == str(existing.get("sha256") or ""))) and
                existing.get("status") == "processing"):
                duplicate = copy.deepcopy(existing)
                duplicate["deduplicated"] = True
                return duplicate
        jobs[job_id] = job
        return copy.deepcopy(job)
    return _document_jobs_update(create)


def finish_document_job(job_id, status, error=""):
    def update(jobs):
        job = jobs.get(str(job_id))
        if job:
            now = datetime.now(timezone.utc)
            started = datetime.fromisoformat(str(job.get("created_at") or now.isoformat()).replace("Z", "+00:00"))
            elapsed = max(0.0, round((now - started).total_seconds(), 2))
            job.update({"status": status, "error": str(error or ""), "stage": status,
                        "elapsed_seconds": elapsed, "updated_at": now.isoformat(timespec="seconds")})
            job.setdefault("stage_history", []).append({"stage": status, "at": job["updated_at"], "elapsed_seconds": elapsed})
    _document_jobs_update(update)


def update_document_job(job_id, **fields):
    def update(jobs):
        job = jobs.get(str(job_id))
        if job:
            previous_stage = job.get("stage")
            job.update(fields)
            job["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if fields.get("stage") and fields["stage"] != previous_stage:
                job.setdefault("stage_history", []).append({"stage": fields["stage"], "at": job["updated_at"]})
    _document_jobs_update(update)


def notify_document_progress(token, chat_id, job_id, delay=30):
    """Send one honest progress update only if the same job is still running."""
    pid = os.fork()
    if pid:
        return
    try:
        time.sleep(delay)
        def lookup(jobs): return copy.deepcopy(jobs.get(str(job_id)))
        job = _document_jobs_update(lookup) or {}
        if job.get("status") == "processing":
            stage = str(job.get("stage") or "обработка")
            send_message(token, chat_id,
                         f"⏳ Счёт всё ещё разбирается ({stage}): читаю строки и сверяю их с позициями сделки. "
                         "Файл не потерян; при сбое появится повторный запуск.")
    finally:
        os._exit(0)


def latest_retryable_document_job(chat_id):
    def find(jobs):
        candidates = [job for job in jobs.values()
                      if str(job.get("chat_id")) == str(chat_id)
                      and job.get("kind") == "supplier_invoice"
                      and job.get("status") == "needs_retry"]
        candidates.sort(key=lambda job: job.get("updated_at") or "", reverse=True)
        return copy.deepcopy(candidates[0]) if candidates else None
    return _document_jobs_update(find)


def latest_processing_document_job(chat_id):
    """Read the one active parsing task for a chat without changing its state."""
    def find(jobs):
        candidates = [job for job in jobs.values()
                      if str(job.get("chat_id")) == str(chat_id)
                      and job.get("kind") == "supplier_invoice"
                      and job.get("status") == "processing"]
        candidates.sort(key=lambda job: job.get("updated_at") or "", reverse=True)
        return copy.deepcopy(candidates[0]) if candidates else None
    return _document_jobs_update(find)


def recover_interrupted_document_jobs():
    """Turn jobs killed by a process restart into explicit retryable tasks."""
    def recover(jobs):
        recovered = []
        for job in jobs.values():
            if job.get("status") == "processing":
                job.update({"status": "needs_retry", "error": "обработка прервана перезапуском",
                            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
                recovered.append(copy.deepcopy(job))
        return recovered
    return _document_jobs_update(recover)


def retry_supplier_invoice_document(token, chat_id, job):
    """Rebuild a supplier-invoice preview from a persisted original file."""
    path = str(job.get("path") or "")
    deal_id = str(job.get("deal_id") or "")
    if not deal_id or not os.path.isfile(path):
        finish_document_job(job.get("id"), "needs_retry", "исходный файл недоступен")
        send_message(token, chat_id, "Исходный файл больше недоступен. Загрузите счёт заново через «🧾 Учесть счёт».", PROCUREMENT_KEYBOARD)
        return

    def running(jobs):
        current = jobs.get(job["id"])
        if current:
            current.update({"status": "processing", "attempts": int(current.get("attempts") or 0) + 1,
                            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": ""})
    _document_jobs_update(running)
    notify_document_progress(token, chat_id, job["id"])
    update_deal_ui_state(chat_id, current_deal_id=deal_id, supplier_invoice_deal_id=deal_id,
                         active_document_job_id=job["id"], pending="invoice_file")
    ledger = fetch_deal_ledger(deal_id)
    if ledger is None:
        finish_document_job(job["id"], "needs_retry", "не удалось получить позиции сделки")
        send_message(token, chat_id, "Не удалось прочитать позиции сделки. Повторите попытку позже.", PROCUREMENT_KEYBOARD)
        return
    source_text = extract_document_text_for_model(path)
    prompt = (
        f"Разбери счёт поставщика для УЖЕ ВЫБРАННОЙ сделки №{deal_id}. "
        "Не создавай сделку и не меняй сделку. Верни только валидный блок "
        "SUPPLIER_INVOICE_APPLY_BEGIN/END с invoice (supplier, buyer, number, date, total, currency, source_path), "
        "updates для совпавших строк и unallocated для всех остальных. "
        f"source_path: {path!r}\nПозиции сделки:\n{json.dumps(ledger, ensure_ascii=False)}\n"
        "Текст счёта:\n" + (source_text or f"[ФАЙЛ: {path}]")
    )
    parse_started = time.monotonic()
    reply = ask_fresh_document_model(prompt)
    elapsed = round(time.monotonic() - parse_started, 2)
    update_document_job(job["id"], parse_seconds=elapsed)
    print(f"{LOG_PREFIX} supplier invoice retry parsed in {elapsed:.2f}s job={job['id']}", file=sys.stderr)
    _clean, spec = extract_supplier_invoice_apply(reply)
    if not spec or spec.get("__invalid__"):
        finish_document_job(job["id"], "needs_retry", "не удалось получить структурированный разбор")
        update_deal_ui_state(chat_id, active_document_job_id=None)
        send_message(token, chat_id, "Счёт не удалось разобрать структурированно. Исходный файл сохранён — повторите попытку кнопкой ещё раз или загрузите Excel-версию.", PROCUREMENT_KEYBOARD)
        return
    spec["deal_id"] = deal_id
    spec.setdefault("invoice", {})["source_path"] = path
    try:
        spec = plan_invoice_spec(spec)
    except CurrencyPlanningError as exc:
        finish_document_job(job["id"], "needs_retry", str(exc))
        update_deal_ui_state(chat_id, active_document_job_id=None)
        send_message(token, chat_id, "Валютный план не создан: " + str(exc), PROCUREMENT_KEYBOARD)
        return
    status = run_procurement_workflow({"action": "invoice_allocation_status", "invoice_spec": spec})
    spec = trim_previously_allocated_invoice_lines(spec, status)
    spec = cap_invoice_allocation_to_deal(spec)
    preview, error = prepare_supplier_invoice_preview(spec, status)
    if error:
        finish_document_job(job["id"], "needs_retry", error)
        update_deal_ui_state(chat_id, active_document_job_id=None)
        send_message(token, chat_id, "Не удалось подготовить привязку: " + error, PROCUREMENT_KEYBOARD)
        return
    spec["_allocation_preview"] = preview
    nearby = refresh_nearby_procurement_snapshots(deal_id, 10)
    distribution = run_procurement_workflow({"action": "suggest_distribution", "invoice_spec": spec,
                                             "limit": 10, "candidate_deal_ids": nearby})
    if distribution.get("ok"):
        spec["_distribution_plan"] = distribution
    enqueue_supplier_invoice_preview(chat_id, spec)
    finish_document_job(job["id"], "preview_ready")
    update_deal_ui_state(chat_id, active_document_job_id=None, pending="supplier_invoice_confirm")
    if RUNTIME_ACTIVE and request_is_current():
        spec = current_deal_ui_state(chat_id).get('supplier_invoice_preview') or spec
        deal_id = str(spec.get('deal_id') or deal_id)
    invoice = spec.get("invoice") or {}
    lines = [f"Проверьте привязку перед записью:",
             f"Поставщик: {invoice.get('supplier') or 'не указан'}",
             f"Счёт №{invoice.get('number') or 'не указан'} от {invoice.get('date') or 'дата не указана'}",
             f"Сделка №{deal_id}",
             f"Сопоставлено позиций: {len(spec.get('updates') or [])}"]
    unallocated = spec.get("unallocated") or []
    if unallocated:
        lines.append("\nОстанется нераспределено:")
        lines.extend(f"• {x.get('name') or x.get('source_name')}: {float(x.get('qty') or 0):g}, {bank_money(x.get('amount'))} ₽" for x in unallocated)
        lines.append("\nВыберите распределение остатка кнопками ниже.")
    else:
        lines.append("\nНажмите «✅ Применить счёт поставщика».")
    send_message(token, chat_id, "\n".join(lines),
                 SUPPLIER_DISTRIBUTION_KEYBOARD if unallocated else SUPPLIER_INVOICE_CONFIRM_KEYBOARD)


def tg_api(token, method, params=None, timeout=40):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    if params is not None:
        data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=data, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def get_offset():
    if os.path.exists(OFFSET_FILE):
        return int(open(OFFSET_FILE).read().strip() or "0")
    return 0


def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))


def get_or_create_session_id():
    if os.path.exists(SESSION_FILE):
        return open(SESSION_FILE).read().strip()
    # Codex assigns the persistent thread id on the first successful exec. Returning
    # an empty value starts that thread; ask_claude() stores the real id afterwards.
    return ""


def persistent_navigation(reply_markup):
    """Only fixed, context-free menus belong to Telegram's bottom keyboard.

    Do not infer this from emoji/labels: tax choices, dynamic deal lists and
    financial confirmation screens must remain bound to their preview.
    """
    return any(reply_markup == menu for menu in (
        MAIN_KEYBOARD, INSTALLER_USER_KEYBOARD, INSTALLER_MENU_KEYBOARD,
    ))


def send_message(token, chat_id, text, reply_markup=None):
    if RUNTIME_ACTIVE and reply_markup and 'keyboard' in reply_markup:
        status_action = bool(reply_markup.get('_status_action', False))
        if status_action:
            reply_markup = {key: value for key, value in reply_markup.items() if key != '_status_action'}
        persistent=persistent_navigation(reply_markup)
        if not status_action and not persistent and (UI_CONTEXT is None or UI_CONTEXT.actor != str(chat_id)) and (ui_state_store().current(chat_id).get('pending') or ui_state_store().current(chat_id).get('deal_creation_active')):
            # Unsolicited notifications must not replace a live screen. The
            # message still names its deal; the user can open it when ready.
            reply_markup = None
        elif UI_CONTEXT is not None and UI_CONTEXT.actor == str(chat_id) and not ui_state_store().fresh(UI_CONTEXT):
            reply_markup = None
            text += '\n\nЭто результат предыдущего действия. Текущий раздел не изменён; для продолжения откройте нужную сделку.'
        elif status_action:
            reply_markup = {**reply_markup, 'is_persistent': False, 'one_time_keyboard': True}
        elif persistent:
            reply_markup={**reply_markup,'is_persistent':True,'one_time_keyboard':False}
        else:
            reply_markup = WorkflowStore(WORKFLOW_DB_FILE).keyboard(chat_id, reply_markup['keyboard'])
    # Telegram limit is 4096 chars per message
    chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)] or [""]
    delivered = True
    for index, chunk in enumerate(chunks):
        started = time.monotonic()
        try:
            params = {"chat_id": chat_id, "text": chunk}
            if reply_markup is not None and index == len(chunks) - 1:
                params["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
            # A blocked HTTPS send used to hold the single polling process for
            # exactly ten seconds.  Normal Telegram delivery is sub-second; on
            # an unhealthy connection fail quickly so the next user action is
            # never queued behind a stale send.
            response = tg_api(token, "sendMessage", params, timeout=5)
            delivered = delivered and bool(response.get("ok"))
        except Exception as e:
            delivered = False
            print(f"{LOG_PREFIX} failed to send message: {e}", file=sys.stderr)
        elapsed = time.monotonic() - started
        if elapsed >= 2:
            print(f"{LOG_PREFIX} slow Telegram sendMessage: {elapsed:.2f}s chat={chat_id}", file=sys.stderr)
    return delivered


def remove_bottom_keyboard(token, chat_id):
    """Remove Telegram's old persistent keyboard before showing an inline screen."""
    try:
        response = tg_api(token, "sendMessage", {
            "chat_id": chat_id,
            "text": "\u2063",  # invisible separator; removed immediately below
            "reply_markup": json.dumps({"remove_keyboard": True}),
        }, timeout=5)
        message_id = ((response.get("result") or {}).get("message_id")) if response.get("ok") else None
        if message_id:
            try:
                tg_api(token, "deleteMessage", {"chat_id": chat_id, "message_id": message_id}, timeout=5)
            except Exception:
                pass
        return True
    except Exception as exc:
        print(f"{LOG_PREFIX} failed to remove bottom keyboard: {exc}", file=sys.stderr)
        return False


def send_typing(token, chat_id):
    try:
        tg_api(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


def configure_bot_commands(token):
    commands = [
        {"command": "menu", "description": "Меню функций бота"},
        {"command": "deals", "description": "Работа со сделками"},
        {"command": "dashboard", "description": "Открыть пульт сделок"},
        {"command": "help", "description": "Подробная инструкция"},
        {"command": "economics", "description": "Экономика сделки: /экономика ID"},
        {"command": "invoice", "description": "PDF счёта: /счет ID"},
        {"command": "deal", "description": "Последний счёт сделки: /сделка ID"},
    ]
    try:
        tg_api(token, "setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)})
    except Exception as e:
        print(f"{LOG_PREFIX} failed to configure bot commands: {e}", file=sys.stderr)
    if MANAGER_CHAT_ID:
        try:
            tg_api(token, "setChatMenuButton", {"chat_id": MANAGER_CHAT_ID,
                "menu_button": json.dumps({"type": "web_app", "text": "Пульт сделок", "web_app": {"url": DASHBOARD_URL}}, ensure_ascii=False)})
        except Exception as e:
            print(f"{LOG_PREFIX} failed to configure dashboard menu: {type(e).__name__}", file=sys.stderr)



def load_deal_ui_state():
    if RUNTIME_ACTIVE:
        return ui_state_store().read_all()
    try:
        with open(DEAL_UI_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def update_deal_ui_state(chat_id, **values):
    if RUNTIME_ACTIVE:
        changed, result = ui_state_store().update(chat_id, values, UI_CONTEXT)
        if not changed:
            print(f'{LOG_PREFIX} stale UI state update rejected; chat={chat_id}', file=sys.stderr)
        return result
    # Menu, model and CRM jobs run in separate processes. Serialize their read-modify-
    # write cycle; the old shared .tmp file allowed concurrent workers to overwrite
    # newer state or briefly expose a partial transition.
    with open(DEAL_UI_STATE_LOCK_FILE, "w") as state_lock:
        fcntl.flock(state_lock, fcntl.LOCK_EX)
        all_state = load_deal_ui_state()
        state = all_state.setdefault(str(chat_id), {})
        for key, value in values.items():
            if value is None:
                state.pop(key, None)
            else:
                state[key] = value
        tmp = f"{DEAL_UI_STATE_FILE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(all_state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DEAL_UI_STATE_FILE)
        return state


def current_deal_ui_state(chat_id):
    if RUNTIME_ACTIVE:
        return ui_state_store().current(chat_id, UI_CONTEXT)
    return load_deal_ui_state().get(str(chat_id), {})


def ui_state_store():
    return StateStore(DEAL_UI_STATE_FILE, DEAL_UI_STATE_LOCK_FILE)


def request_is_current():
    return not RUNTIME_ACTIVE or UI_CONTEXT is None or ui_state_store().fresh(UI_CONTEXT)


def enqueue_supplier_invoice_preview(chat_id, spec):
    """Atomically queue parsed invoices sent one after another."""
    if RUNTIME_ACTIVE:
        return len(ui_state_store().invoice_queue(chat_id, spec, context=UI_CONTEXT))
    with open(DEAL_UI_STATE_LOCK_FILE, "w") as state_lock:
        fcntl.flock(state_lock, fcntl.LOCK_EX)
        all_state = load_deal_ui_state()
        state = all_state.setdefault(str(chat_id), {})
        queue = list(state.get("supplier_invoice_queue") or [])
        fingerprint = json.dumps(spec, ensure_ascii=False, sort_keys=True)
        if not any(json.dumps(item, ensure_ascii=False, sort_keys=True) == fingerprint for item in queue):
            queue.append(spec)
        state["supplier_invoice_queue"] = queue
        state["supplier_invoice_preview"] = queue[0]
        state["pending"] = "supplier_invoice_confirm"
        state["current_deal_id"] = str(spec.get("deal_id") or state.get("current_deal_id") or "")
        tmp = f"{DEAL_UI_STATE_FILE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as target:
            json.dump(all_state, target, ensure_ascii=False, indent=2)
        os.replace(tmp, DEAL_UI_STATE_FILE)
        return len(queue)


def remove_supplier_invoice_preview(chat_id, applied_spec):
    """Remove one confirmed invoice without losing concurrently queued PDFs."""
    invoice_tasks.complete(chat_id, (applied_spec.get("invoice") or {}).get("source_path"))
    if RUNTIME_ACTIVE:
        return ui_state_store().invoice_queue(chat_id, applied_spec, remove=True, context=UI_CONTEXT)
    with open(DEAL_UI_STATE_LOCK_FILE, "w") as state_lock:
        fcntl.flock(state_lock, fcntl.LOCK_EX)
        all_state = load_deal_ui_state()
        state = all_state.setdefault(str(chat_id), {})
        queue = list(state.get("supplier_invoice_queue") or [])
        fingerprint = json.dumps(applied_spec, ensure_ascii=False, sort_keys=True)
        removed = False
        remaining = []
        for item in queue:
            if not removed and json.dumps(item, ensure_ascii=False, sort_keys=True) == fingerprint:
                removed = True
                continue
            remaining.append(item)
        if remaining:
            state["supplier_invoice_queue"] = remaining
            state["supplier_invoice_preview"] = remaining[0]
            state["pending"] = "supplier_invoice_confirm"
        else:
            state.pop("supplier_invoice_queue", None)
            state.pop("supplier_invoice_preview", None)
            state["pending"] = "procurement_menu"
        tmp = f"{DEAL_UI_STATE_FILE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as target:
            json.dump(all_state, target, ensure_ascii=False, indent=2)
        os.replace(tmp, DEAL_UI_STATE_FILE)
        return remaining


def run_bank_statement(spec):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "bank_statement.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=60,
        )
        lines = (result.stdout or "").strip().splitlines()
        parsed = json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ обработчика"}
        if result.returncode and parsed.get("ok"):
            parsed = {"ok": False, "error": "обработчик выписки завершился с ошибкой"}
        return parsed
    except Exception as exc:
        print(f"{LOG_PREFIX} bank statement failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка обработки выписки"}


def run_bank_matcher():
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "bank_matcher.py")],
            cwd=MEGAPLAN_DIR, capture_output=True, text=True, timeout=120,
        )
        lines = (result.stdout or "").strip().splitlines()
        return json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ сопоставления"}
    except Exception as exc:
        print(f"{LOG_PREFIX} bank matcher failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка сопоставления"}


def run_email_payment_monitor(spec):
    try:
        result = subprocess.run([REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "email_payment_monitor.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False), capture_output=True, text=True, timeout=45)
        lines = (result.stdout or "").strip().splitlines()
        return json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ почтового обработчика"}
    except Exception as exc:
        print(f"{LOG_PREFIX} email payment monitor failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка проверки почты"}


def run_megaplan_finance(spec):
    try:
        result = subprocess.run([REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "megaplan_finance.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False), capture_output=True, text=True, timeout=90)
        lines = (result.stdout or "").strip().splitlines()
        return json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ Мегаплана"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def poll_email_payments(token, chat_id):
    # An in-memory timer alone polls again after every service reload.
    # First initialization waits an hour too, so deployment cannot add an
    # extra mailbox check shortly after the previous version's last poll.
    if not periodic_schedule.claim(os.path.join(BASE_DIR,'watcher_schedule.json'),'email-payments',3600,delay_first=True):
        return
    result = run_email_payment_monitor({"action": "poll"})
    if not result.get("ok"):
        print(f"{LOG_PREFIX} email payment poll failed: {result.get('error')}", file=sys.stderr); return
    for candidate in result.get("created") or []:
        send_message(token,chat_id,
            f"🏦 Получено банковское уведомление: платёж №{candidate.get('payment_number')} от {candidate.get('date')}, {bank_money(candidate.get('amount'))} ₽.\n"
            "Уведомление сохранено. Откройте «Банк и платежи» → «Банковские уведомления», когда будете готовы его проверить. Текущий диалог не изменён; расходные операции не создавались.")


def show_email_payment_candidate(token,chat_id,candidate):
    if candidate.get('status')=='created':
        send_message(token,chat_id,'Это уведомление уже учтено. Повторные расходы не создаются.',BANK_MENU_KEYBOARD)
        return
    if candidate.get('status') not in ('pending','postponed'):
        send_message(token,chat_id,'Это уведомление сейчас недоступно для подтверждения.',BANK_MENU_KEYBOARD)
        return
    invoices = ", ".join(f"№{x.get('number')} — {bank_money(x.get('total'))} ₽"
                         for x in candidate.get("invoices") or []) or "не найдены"
    if candidate.get("exact"):
        update_deal_ui_state(chat_id, pending="email_payment_confirm", email_payment_candidate_id=candidate["id"])
        send_message(token, chat_id,
            f"🏦 Получено уведомление банка о расходе.\n\nПлатёж №{candidate.get('payment_number')} от {candidate.get('date')}\n"
            f"Плательщик: {candidate.get('payer')}\nПолучатель: {candidate.get('recipient')}\n"
            f"Сумма: {bank_money(candidate.get('amount'))} ₽\nСделка: №{(candidate.get('deal_ids') or [None])[0]}\n"
            f"Счета поставщика: {invoices}\n\nСоздать расходные операции в Мегаплане?",
            EMAIL_PAYMENT_CONFIRM_KEYBOARD)
    else:
        update_deal_ui_state(chat_id, pending="email_payment_unmatched",
                             email_payment_candidate_id=candidate["id"])
        send_message(token, chat_id,
            f"⚠️ Получено банковское уведомление на {bank_money(candidate.get('amount'))} ₽, но соответствие неоднозначно. "
            f"Счета из письма: {', '.join(candidate.get('invoice_numbers') or []) or 'не найдены'}. "
            f"В реестре закупок не найдены: {', '.join(candidate.get('missing') or []) or 'нет точного совпадения по сумме/сделке'}.\n\n"
            "Операции не созданы. Общий поиск по банковской выписке для этого уведомления не запускается.",
            EMAIL_PAYMENT_UNMATCHED_KEYBOARD)


def bank_money(value):
    try:
        return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return str(value or "0")


def bank_operation_text(item, detailed=True):
    sign = "−" if item.get("direction") == "expense" else "+"
    title = f"{sign} {bank_money(item.get('amount'))} ₽ · {item.get('date')}"
    lines = [title, item.get("counterparty") or "Контрагент не указан"]
    if detailed:
        if item.get("counterparty_inn"):
            lines.append(f"ИНН: {item['counterparty_inn']}")
        lines.append(f"Документ: {item.get('document_number') or 'б/н'}")
        lines.append(f"Назначение: {item.get('purpose') or 'не указано'}")
        if item.get("deal_id"):
            lines.append(f"Сделка: №{item['deal_id']} {item.get('deal_name') or ''}".rstrip())
    return "\n".join(lines)


def send_bank_transactions(token, chat_id, status=None):
    result = run_bank_statement({"action": "list", "status": status, "limit": 30})
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось прочитать реестр: {result.get('error')}", BANK_MENU_KEYBOARD)
        return
    items = result.get("transactions") or []
    if not items:
        message = "Неразнесённых операций нет." if status == "unassigned" else "Банковских операций пока нет."
        send_message(token, chat_id, message, BANK_MENU_KEYBOARD)
        return
    choices, rows = {}, []
    for item in items:
        sign = "−" if item.get("direction") == "expense" else "+"
        counterparty = (item.get("counterparty") or "без контрагента")[:22]
        label = f"{sign}{bank_money(item.get('amount'))} · {item.get('date')} · {counterparty}"
        # Telegram keyboard labels must be unique within the current view.
        while label in choices:
            label += " ·"
        choices[label] = item["id"]
        rows.append([{"text": label}])
    rows.append([{"text": "⬅️ Банк и платежи"}])
    update_deal_ui_state(chat_id, pending="bank_operation_list", bank_operation_choices=choices)
    caption = "Неразнесённые операции:" if status == "unassigned" else "Последние банковские операции:"
    send_message(token, chat_id, caption + "\n\nВыберите операцию для просмотра.",
                 {"keyboard": rows, "resize_keyboard": True})


def handle_bank_ui(token, chat_id, text, _background=False):
    value = text.strip()
    state = current_deal_ui_state(chat_id)
    pending = state.get("pending") or ""
    bank_values = {"🏦 Банк и платежи", "🔍 Неразнесённые операции", "📚 Все операции", "🔗 Найти соответствия",
                   '📩 Банковские уведомления','➡️ Ещё уведомления','⬅️ Предыдущие уведомления',
                   "✅ Создать расходные операции", "⏭ Отложить платёж", "📋 Как привязать платёж",
                   "✅ Учесть как выплату монтажнику", "❌ Не учитывать как выплату"}
    if (value in bank_values or pending.startswith(("bank_","email_payment_"))) and not _background:
        run_background_job(lambda: handle_bank_ui(token, chat_id, text, _background=True), token, chat_id)
        return True
    if value == "🏦 Банк и платежи":
        update_deal_ui_state(chat_id, pending=None, bank_operation_choices=None,
                             bank_transaction_id=None, bank_pending_deal=None, bank_auto_matches=None)
        send_message(token, chat_id, "Банк и платежи — загрузите выписку или откройте реестр операций.", BANK_MENU_KEYBOARD)
        return True
    if value=='📩 Банковские уведомления' or (pending=='email_payment_list' and value in ('➡️ Ещё уведомления','⬅️ Предыдущие уведомления')):
        offset=0 if value=='📩 Банковские уведомления' else max(0,int(state.get('email_payment_offset') or 0)+(10 if value.startswith('➡️') else -10))
        result=run_email_payment_monitor({'action':'list','offset':offset})
        if not result.get('ok'):
            send_message(token,chat_id,'Не удалось прочитать сохранённые банковские уведомления.',BANK_MENU_KEYBOARD);return True
        choices={};rows=[]
        for candidate in result.get('candidates') or []:
            label=f"📩 {candidate.get('date')} · {bank_money(candidate.get('amount'))} ₽ · {str(candidate['id'])[-6:]}"
            while label in choices:label+=' ·'
            choices[label]=candidate['id'];rows.append([{'text':label}])
        if offset:rows.append([{'text':'⬅️ Предыдущие уведомления'}])
        if result.get('has_more'):rows.append([{'text':'➡️ Ещё уведомления'}])
        rows.append([{'text':'⬅️ Банк и платежи'}])
        update_deal_ui_state(chat_id,pending='email_payment_list',email_payment_choices=choices,email_payment_offset=offset)
        send_message(token,chat_id,f"Ожидают проверки банковских уведомлений: {result.get('total',0)}. Выберите платёж.",{'keyboard':rows,'resize_keyboard':True})
        return True
    if pending=='email_payment_list' and value in (state.get('email_payment_choices') or {}):
        result=run_email_payment_monitor({'action':'get','id':state['email_payment_choices'][value]})
        if not result.get('ok'):send_message(token,chat_id,'Уведомление не найдено.',BANK_MENU_KEYBOARD)
        else:show_email_payment_candidate(token,chat_id,result['candidate'])
        return True
    if pending == "email_payment_confirm" and value == "⏭ Отложить платёж":
        run_email_payment_monitor({"action": "status", "id": state.get("email_payment_candidate_id"),
                                   "status": "postponed"})
        update_deal_ui_state(chat_id, pending=None, email_payment_candidate_id=None)
        send_message(token, chat_id, "Платёж отложен. Расходные операции не создавались.", BANK_MENU_KEYBOARD)
        return True
    if pending == "email_payment_unmatched" and value == "📋 Как привязать платёж":
        loaded = run_email_payment_monitor({"action": "get", "id": state.get("email_payment_candidate_id")})
        candidate = loaded.get("candidate") or {}
        missing = ", ".join(candidate.get("missing") or candidate.get("invoice_numbers") or [])
        send_message(token, chat_id,
                     f"Чтобы привязать этот платёж, сначала загрузите счёт поставщика №{missing} в разделе "
                     "«Закупка по сделке» нужной сделки и примените его. После этого бот сможет однозначно "
                     "сопоставить плательщика, поставщика, сумму и сделку. До этого расход в Мегаплане не создаётся.",
                     EMAIL_PAYMENT_UNMATCHED_KEYBOARD)
        return True
    if pending == "email_payment_unmatched" and value == "⏭ Отложить платёж":
        run_email_payment_monitor({"action": "status", "id": state.get("email_payment_candidate_id"),
                                   "status": "postponed"})
        update_deal_ui_state(chat_id, pending=None, email_payment_candidate_id=None)
        send_message(token, chat_id, "Платёж отложен. Расходные операции не создавались.", BANK_MENU_KEYBOARD)
        return True
    if pending == "email_payment_confirm" and value == "✅ Создать расходные операции":
        candidate_id = state.get("email_payment_candidate_id")
        loaded = run_email_payment_monitor({"action": "get", "id": candidate_id})
        if not loaded.get("ok"):
            send_message(token, chat_id, f"Уведомление не найдено: {loaded.get('error')}", BANK_MENU_KEYBOARD); return True
        if loaded['candidate'].get('status') not in ('pending','postponed'):
            send_message(token,chat_id,'Уведомление уже обработано либо его состояние изменилось. Повторная запись не выполнялась.',BANK_MENU_KEYBOARD);return True
        send_message(token, chat_id, "💳 Создаю подтверждённые расходные операции в Мегаплане...")
        result = run_megaplan_finance({"action": "create", "candidate": loaded["candidate"]})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось создать расходы: {result.get('error')}", EMAIL_PAYMENT_CONFIRM_KEYBOARD); return True
        run_email_payment_monitor({"action": "status", "id": candidate_id, "status": "created", "result": result})
        update_deal_ui_state(chat_id, pending=None, email_payment_candidate_id=None)
        lines = [f"• операция №{x.get('operation_id')} — счёт №{x.get('invoice_number')}, {bank_money(x.get('amount'))} ₽"
                 for x in result.get("operations") or []]
        send_message(token, chat_id, "✅ Расходные операции созданы:\n" + "\n".join(lines), BANK_MENU_KEYBOARD)
        return True
    if value == "⬅️ Банк и платежи":
        update_deal_ui_state(chat_id, pending=None, bank_operation_choices=None,
                             bank_transaction_id=None, bank_pending_deal=None, bank_auto_matches=None)
        send_message(token, chat_id, "Банк и платежи.", BANK_MENU_KEYBOARD)
        return True
    # Exit commands must win over every step-specific handler.  Previously they were
    # checked after bank_deal_id/bank_assign_confirm, so "Отмена" was interpreted as
    # another answer to the pending deal question and the saved operation stayed live.
    if pending.startswith("bank_") and value in ("❌ Отмена", "⬅️ Главное меню"):
        update_deal_ui_state(chat_id, pending=None, bank_operation_choices=None,
                             bank_transaction_id=None, bank_pending_deal=None, bank_auto_matches=None)
        send_message(token, chat_id, "Действие отменено." if value == "❌ Отмена" else "Главное меню.",
                     BANK_MENU_KEYBOARD if value == "❌ Отмена" else MAIN_KEYBOARD)
        return True
    if value == "📤 Загрузить выписку":
        update_deal_ui_state(chat_id, pending="bank_statement_file")
        send_message(token, chat_id, "Пришлите банковскую выписку в формате Excel (.xlsx) или 1С (.txt).", BANK_CANCEL_KEYBOARD)
        return True
    if value == "🔍 Неразнесённые операции":
        send_bank_transactions(token, chat_id, "unassigned")
        return True
    if value == "📚 Все операции":
        send_bank_transactions(token, chat_id)
        return True
    if value == "🔗 Найти соответствия":
        send_message(token, chat_id, "🔎 Сверяю назначения платежей со счетами и договорами Мегаплана...")
        result = run_bank_matcher()
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось выполнить сопоставление: {result.get('error')}", BANK_MENU_KEYBOARD)
            return True
        matches = result.get("matches") or []
        if not matches:
            send_message(token, chat_id,
                         f"Однозначных соответствий не найдено. Неразнесённых операций: {result.get('unmatched_count', 0)}.",
                         BANK_MENU_KEYBOARD)
            return True
        lines = []
        for match in matches[:30]:
            operation = run_bank_statement({"action": "get", "transaction_id": match["transaction_id"]})
            if not operation.get("ok"):
                continue
            item = operation["transaction"]
            checks = []
            if match.get("inn_confirmed"):
                checks.append("ИНН совпал")
            if match.get("amount_confirmed"):
                checks.append("сумма совпала")
            suffix = f" ({', '.join(checks)})" if checks else ""
            lines.append(
                f"• {item.get('date')} · {'−' if item.get('direction') == 'expense' else '+'}"
                f"{bank_money(item.get('amount'))} ₽ · {item.get('counterparty') or 'без контрагента'}\n"
                f"  → сделка №{match['deal_id']} · {match.get('basis')}{suffix}"
            )
        update_deal_ui_state(chat_id, pending="bank_auto_confirm", bank_auto_matches=matches)
        extra = f"\n\nПоказаны первые 30 из {len(matches)}." if len(matches) > 30 else ""
        send_message(token, chat_id,
                     f"Найдено однозначных соответствий: {len(matches)}.\n\n" + "\n".join(lines) + extra +
                     "\n\nПроверьте список. Записать все найденные операции в соответствующие сделки?",
                     BANK_AUTO_CONFIRM_KEYBOARD)
        return True
    if pending == "bank_auto_confirm" and value == "✅ Привязать все найденные":
        matches = state.get("bank_auto_matches") or []
        success, errors = 0, []
        for match in matches:
            transaction = run_bank_statement({"action": "get", "transaction_id": match.get("transaction_id")})
            if not transaction.get("ok") or transaction["transaction"].get("status") != "unassigned":
                continue
            attached = run_deal_browser({"action": "attach_bank_operation", "deal_id": match["deal_id"],
                                         "operation": transaction["transaction"]})
            if not attached.get("ok"):
                errors.append(f"операция {match.get('transaction_id')}: {attached.get('error')}")
                continue
            saved = run_bank_statement({"action": "assign", "transaction_id": match["transaction_id"],
                                        "deal_id": match["deal_id"], "deal_name": match.get("deal_name") or ""})
            if saved.get("ok"):
                success += 1
            else:
                errors.append(f"операция {match.get('transaction_id')}: реестр не обновлён")
        update_deal_ui_state(chat_id, pending=None, bank_auto_matches=None)
        error_text = ("\nОшибки:\n" + "\n".join(f"• {item}" for item in errors[:10])) if errors else ""
        send_message(token, chat_id, f"✅ Привязано операций: {success}.{error_text}", BANK_MENU_KEYBOARD)
        return True
    if pending == "bank_operation_list" and value in (state.get("bank_operation_choices") or {}):
        transaction_id = state["bank_operation_choices"][value]
        result = run_bank_statement({"action": "get", "transaction_id": transaction_id})
        if not result.get("ok"):
            send_message(token, chat_id, result.get("error") or "Операция не найдена.", BANK_MENU_KEYBOARD)
            return True
        item = result["transaction"]
        if item.get("status") == "assigned":
            send_message(token, chat_id, bank_operation_text(item), BANK_MENU_KEYBOARD)
        else:
            update_deal_ui_state(chat_id, pending="bank_deal_id", bank_transaction_id=transaction_id)
            send_message(token, chat_id, bank_operation_text(item) +
                         "\n\nВведите внутренний номер сделки Мегаплана, к которой относится операция.",
                         BANK_CANCEL_KEYBOARD)
        return True
    if pending == "bank_deal_id":
        ids = re.findall(r"\b\d+\b", value)
        if not ids:
            send_message(token, chat_id, "Введите внутренний номер сделки числом, например 888.", BANK_CANCEL_KEYBOARD)
            return True
        deal = run_deal_browser({"action": "get", "deal_id": ids[-1]})
        if not deal.get("ok"):
            send_message(token, chat_id, f"Сделка не найдена: {deal.get('error')}", BANK_CANCEL_KEYBOARD)
            return True
        transaction = run_bank_statement({"action": "get", "transaction_id": state.get("bank_transaction_id")})
        if not transaction.get("ok"):
            send_message(token, chat_id, "Банковская операция больше не найдена.", BANK_MENU_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="bank_assign_confirm", bank_pending_deal=deal["deal"])
        send_message(token, chat_id,
                     bank_operation_text(transaction["transaction"]) +
                     f"\n\nПривязать эту операцию к сделке №{deal['deal']['id']} — {deal['deal'].get('client')} — {deal['deal'].get('name') or ''}?",
                     BANK_CONFIRM_KEYBOARD)
        return True
    if pending == "bank_assign_confirm" and value == "✅ Привязать к сделке":
        deal = state.get("bank_pending_deal") or {}
        transaction = run_bank_statement({"action": "get", "transaction_id": state.get("bank_transaction_id")})
        if not deal.get("id") or not transaction.get("ok"):
            send_message(token, chat_id, "Не хватает данных для привязки. Начните заново.", BANK_MENU_KEYBOARD)
            return True
        attached = run_deal_browser({"action": "attach_bank_operation", "deal_id": deal["id"],
                                     "operation": transaction["transaction"]})
        if not attached.get("ok"):
            send_message(token, chat_id, f"Не удалось записать операцию в сделку: {attached.get('error')}", BANK_CONFIRM_KEYBOARD)
            return True
        saved = run_bank_statement({"action": "assign", "transaction_id": state.get("bank_transaction_id"),
                                    "deal_id": deal["id"], "deal_name": deal.get("name") or deal.get("client") or ""})
        if not saved.get("ok"):
            send_message(token, chat_id, "Операция записана в Мегаплан, но локальный реестр не обновился. Сообщите разработчику.", BANK_MENU_KEYBOARD)
            return True
        installation=run_installation_workflow({"action":"get","deal_id":str(deal["id"])})
        item=transaction["transaction"]
        if installation.get("ok") and item.get("direction")=="expense":
            update_deal_ui_state(chat_id,pending="bank_installer_payment_confirm",
                bank_installer_transaction=item,bank_installer_deal_id=str(deal["id"]),
                bank_transaction_id=None,bank_pending_deal=None)
            send_message(token,chat_id,
                f"✅ Операция привязана к сделке №{deal['id']}.\n\nУчесть расход {bank_money(item.get('amount'))} ₽ как выплату монтажнику {installation['result'].get('installer_name')}?\nВ погашение задолженности будет зачтено 94% перечисленной суммы. Банковская сумма не изменяется.",
                BANK_INSTALLER_PAYMENT_KEYBOARD)
        else:
            update_deal_ui_state(chat_id, pending=None, bank_transaction_id=None, bank_pending_deal=None)
            send_message(token, chat_id, f"✅ Операция привязана к сделке №{deal['id']} и записана в её историю.", BANK_MENU_KEYBOARD)
        return True
    if pending == "bank_installer_payment_confirm" and value == "✅ Учесть как выплату монтажнику":
        item=state.get("bank_installer_transaction") or {}; deal_id=state.get("bank_installer_deal_id")
        raw_date=str(item.get("date") or "")
        try:
            payment_date=datetime.strptime(raw_date[:10],'%Y-%m-%d').strftime('%d.%m.%Y') if '-' in raw_date[:10] else datetime.strptime(raw_date[:10],'%d.%m.%Y').strftime('%d.%m.%Y')
        except ValueError:
            send_message(token,chat_id,'В банковской операции нет корректной даты. Выплата не записана; сначала необходимо уточнить дату исходной операции.',BANK_INSTALLER_PAYMENT_KEYBOARD); return True
        payment_id=item.get('id') or item.get('transaction_id')
        if not payment_id:
            send_message(token,chat_id,'В банковской операции отсутствует ID. Выплата не записана, чтобы не допустить повторного зачёта.',BANK_INSTALLER_PAYMENT_KEYBOARD); return True
        result=run_installation_workflow({"action":"record_payment","deal_id":str(deal_id),"source":"bank",
            "amount":item.get("amount"),"payment_date":payment_date,"external_id":str(payment_id),
            "comment":item.get("purpose") or "Банковская выплата монтажнику"})
        if not result.get("ok"):
            send_message(token,chat_id,f"Операция осталась привязана к сделке, но выплата монтажнику не учтена: {result.get('error')}",BANK_INSTALLER_PAYMENT_KEYBOARD); return True
        update_deal_ui_state(chat_id,pending=None,bank_installer_transaction=None,bank_installer_deal_id=None)
        recorded=result['result']
        credit_text=(f" Зачтено в погашение долга: {money(recorded['payment_settlement_amount'])}." if 'payment_settlement_amount' in recorded else '')
        send_message(token,chat_id,f"✅ Выплата учтена.{credit_text} {installation_balance_text(recorded)}",BANK_MENU_KEYBOARD)
        return True
    if pending == "bank_installer_payment_confirm" and value == "❌ Не учитывать как выплату":
        update_deal_ui_state(chat_id,pending=None,bank_installer_transaction=None,bank_installer_deal_id=None)
        send_message(token,chat_id,"Операция привязана к сделке, но расчёты с монтажником не изменены.",BANK_MENU_KEYBOARD)
        return True
    return False


def run_installer_report_intake(path, table_paths=None):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(BASE_DIR, "installer_report_intake.py"), path] + list(table_paths or []),
            cwd=BASE_DIR, capture_output=True, text=True, timeout=180,
        )
        parsed = json.loads((result.stdout or "").strip().splitlines()[-1])
        if result.returncode == 0 and parsed.get("ok"):
            return parsed
        return {"ok": False, "error": parsed.get("error") or "не удалось разобрать отчёт"}
    except Exception as exc:
        print(f"{LOG_PREFIX} installer report intake failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка разбора отчёта"}


def build_installer_report_result(session):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(BASE_DIR, "build_installer_report_result.py")],
            cwd=BASE_DIR, input=json.dumps(session, ensure_ascii=False),
            capture_output=True, text=True, timeout=60,
        )
        parsed = json.loads((result.stdout or "").strip().splitlines()[-1])
        if result.returncode == 0 and parsed.get("ok"):
            return parsed
        return {"ok": False, "error": parsed.get("error") or "не удалось сформировать Excel"}
    except Exception as exc:
        print(f"{LOG_PREFIX} installer report workbook failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка формирования Excel"}


def run_installer_settlements(spec):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(BASE_DIR, "installer_settlements.py")],
            cwd=BASE_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=90,
        )
        parsed = json.loads((result.stdout or "").strip().splitlines()[-1])
        if result.returncode == 0 and parsed.get("ok"):
            return parsed
        return {"ok": False, "error": parsed.get("error") or "ошибка реестра взаиморасчётов"}
    except Exception as exc:
        print(f"{LOG_PREFIX} installer settlements failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка реестра взаиморасчётов"}


def run_installation_workflow(spec):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "installation_workflow.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=660,
        )
        lines = (result.stdout or "").strip().splitlines()
        parsed = json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ"}
        if result.returncode == 0 and parsed.get("ok"):
            return parsed
        return {"ok": False, "error": parsed.get("error") or "ошибка монтажного контура"}
    except Exception as exc:
        print(f"{LOG_PREFIX} installation workflow failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка монтажного контура"}


def installation_summary(item):
    works = item.get("works") or []
    total = sum(float(x.get("planned_qty") or 0) * float(x.get("rate") or 0) for x in works)
    return (
        f"Сделка №{item.get('deal_id')} — {item.get('client')}\n"
        f"Суть: {item.get('essence')}\nАдрес: {item.get('address') or 'не указан'}\n"
        f"Контакт: {item.get('contact_name') or 'не указан'}, {item.get('contact_phone') or 'телефон не указан'}\n"
        f"Исполнитель: {item.get('installer_name') or 'не назначен'}\n"
        f"Работ в ведомости: {len(works)}\nПлановая сумма монтажнику: {money(total)}\n"
        f"Проект: {'привязан' if item.get('project_required') == 1 else 'работать без проекта' if item.get('project_required') == 0 else 'решение не принято'}"
    )

def installation_balance_text(item):
    if item.get('settlements_complete') is False:
        if item.get('settlement_scope')=='installer_global':
            return str(item['settlement_warning'])
        return 'Задолженность по сделке пока не подтверждена. '+str(item.get('settlement_warning') or 'Нужна сверка исторических выплат со сводным реестром.')
    return 'Задолженность: '+money(item.get('debt'))

def project_selection_keyboard(choices,selected=None):
    selected={str(x) for x in (selected or [])}; rows=[]
    for label,file_id in choices.items():
        mark='✅ ' if str(file_id) in selected else '☐ '
        rows.append([{"text":mark+label}])
    rows.extend([[{"text":"✅ Привязать выбранные файлы"}],
                 [{"text":"📤 Загрузить новый файл"}],
                 [{"text":"❌ Отмена"}]])
    return {"keyboard":rows,"resize_keyboard":True}

def installation_contact_keyboard(choices):
    rows=[[{"text":label}] for label in choices]
    rows.extend([[{"text":"➕ Создать контакт по монтажу"}],[{"text":"❌ Отмена"}]])
    return {"keyboard":rows,"resize_keyboard":True}


def prepare_installation_after_transition(token, chat_id, deal_id):
    send_message(token, chat_id, "🛠 Формирую черновик монтажной ведомости для проверки руководителем...")
    prepared = run_installation_workflow({"action": "prepare", "deal_id": str(deal_id), "actor": str(chat_id)})
    if not prepared.get("ok"):
        send_message(token, chat_id, (
            "⚠️ Статус сделки не изменён. Не удалось подготовить черновик ведомости: "
            f"{prepared.get('error')}"
        ), DEAL_ACTIONS_KEYBOARD)
        return
    item = prepared["result"]
    update_deal_ui_state(
        chat_id,
        pending="installation_draft_review",
        installation_deal_id=str(deal_id),
        # Never retain a transition belonging to a previously opened deal.
        installation_pending_transition={"deal_id": str(deal_id), "state_id": "136", "name": "Монтаж"},
    )
    send_message(token, chat_id, installation_summary(item) + "\n\nЧерновик ещё не виден монтажнику.")
    if item.get("workbook"):
        send_document(token, chat_id, item["workbook"], "Черновик монтажной ведомости для проверки",
                      f"Монтажная ведомость - сделка {deal_id}.xlsx")
    # Keep the controls after the attachment, where the manager naturally
    # continues the workflow. Build an inline view explicitly: this function
    # can run in a background worker, where the generic notification guard must
    # not silently discard an action keyboard.
    actions = WorkflowStore(WORKFLOW_DB_FILE).keyboard(chat_id, INSTALLATION_DRAFT_KEYBOARD["keyboard"])
    send_message(token, chat_id,
                 "Что сделать с черновиком ведомости?\n\n"
                 "Контакт объекта можно указать позже. Перед утверждением примите решение по проекту.",
                 actions)


def run_current_execution_builder(spec):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(BASE_DIR, "build_current_execution.py")],
            cwd=BASE_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=90,
        )
        parsed = json.loads((result.stdout or "").strip().splitlines()[-1])
        if result.returncode == 0 and parsed.get("ok"):
            return parsed
        return {"ok": False, "error": parsed.get("error") or "не удалось сформировать накопительное выполнение"}
    except Exception as exc:
        print(f"{LOG_PREFIX} cumulative execution failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка формирования накопительного выполнения"}


def approved_deal_ids():
    return {
        str(deal.get("deal_id"))
        for report in load_approved_installer_reports().get("reports") or []
        for deal in report.get("deals") or [] if deal.get("deal_id")
    }


def archive_deal_labels():
    labels = {}
    for report in load_approved_installer_reports().get("reports") or []:
        for deal in report.get("deals") or []:
            deal_id = str(deal.get("deal_id") or "")
            if not deal_id:
                continue
            bucket = labels.setdefault(deal_id, [])
            for row in deal.get("rows") or []:
                label = str(row.get("object") or "").strip()
                if label and label not in bucket and label not in ("Объект из Excel",):
                    bucket.append(label)
    # The first archived report predates detailed row storage; preserve its two
    # agreed object labels so natural-language lookup still works.
    legacy = {"853": ["JetCar Кондиционирование"], "857": ["JetCar Отопление"]}
    for deal_id, values in legacy.items():
        bucket = labels.setdefault(deal_id, [])
        for value in values:
            if value not in bucket:
                bucket.append(value)
    return labels


def execution_query_tokens(value):
    stop = {"по", "для", "на", "и", "в", "из", "мне", "сделка", "сделке", "сделки", "объект", "объекту", "объекта"}
    return [token for token in re.findall(r"[0-9a-zа-яё]+", value.casefold()) if len(token) >= 3 and token not in stop]


def execution_token_matches(token, text):
    token = token.replace("ё", "е")
    text = text.casefold().replace("ё", "е")
    if token in text:
        return True
    stem_len = 7 if len(token) >= 9 else 6 if len(token) >= 7 else len(token)
    if stem_len >= 4 and token[:stem_len] in text:
        return True
    words = re.findall(r"[0-9a-zа-я]+", text)
    return any(SequenceMatcher(None, token, word).ratio() >= 0.62 for word in words if len(word) >= 5)


def find_execution_candidates(query):
    labels = archive_deal_labels()
    ids = sorted(approved_deal_ids(), key=lambda value: int(value) if value.isdigit() else value)
    result = run_deal_browser({"action": "get_many", "deal_ids": ids})
    deals = result.get("deals") or [] if result.get("ok") else []
    tokens = execution_query_tokens(query)
    scored = []
    for deal in deals:
        deal_id = str(deal.get("id"))
        deal["execution_essence"] = " / ".join(labels.get(deal_id) or []) or deal.get("name")
        text = " ".join(str(value or "") for value in (
            deal_id, deal.get("client"), deal.get("address"), deal.get("name"), deal.get("execution_essence"),
        ))
        score = sum(1 for token in tokens if execution_token_matches(token, text))
        if score:
            scored.append((score, deal))
    if not scored:
        return []
    scored.sort(key=lambda pair: (pair[0], int(pair[1].get("id") or 0)), reverse=True)
    best = scored[0][0]
    return [deal for score, deal in scored if score == best]


def filter_execution_candidates_for_role(chat_id, candidates):
    if str(chat_id) not in INSTALLER_CHAT_IDS:
        return candidates
    return [
        deal for deal in candidates
        if any("деревянко" in str(executor or "").casefold() and "сергей" in str(executor or "").casefold() for executor in deal.get("executors") or [])
    ]


def send_current_execution(token, chat_id, deal):
    deal_id = str(deal.get("id"))
    client = deal.get("client") or "Клиент"
    essence = deal.get("execution_essence") or deal.get("name") or "Выполнение работ"
    send_message(token, chat_id, f"📊 Формирую накопительное выполнение по сделке №{deal_id} — {client} — {essence}...")
    result = run_current_execution_builder({"deal_id": deal_id, "client": client, "essence": essence})
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось сформировать файл: {result.get('error')}", home_keyboard(chat_id))
        return
    send_document(token, chat_id, result["path"], f"Текущее выполнение: №{deal_id} — {client} — {essence}", result.get("filename"))


def handle_current_execution_ui(token, chat_id, text):
    value = text.strip()
    state = current_deal_ui_state(chat_id)
    if state.get("pending") == "current_execution_select" and re.match(r"^№\d+\b", value):
        deal_id = re.match(r"^№(\d+)\b", value).group(1)
        candidates = state.get("current_execution_candidates") or []
        deal = next((item for item in candidates if str(item.get("id")) == deal_id), None)
        if not deal:
            send_message(token, chat_id, "Сделка не найдена в предложенном списке.")
            return True
        update_deal_ui_state(chat_id, pending=None, current_execution_candidates=None)
        send_current_execution(token, chat_id, deal)
        return True
    if state.get("pending") == "current_execution_query":
        query = value
        candidates = filter_execution_candidates_for_role(chat_id, find_execution_candidates(query))
        if not candidates:
            send_message(token, chat_id, f"По уточнению «{query}» сделка не определилась. Укажите номер сделки либо сочетание клиента и сути, например «JetCar отопление».")
            return True
        if len(candidates) == 1:
            update_deal_ui_state(chat_id, pending=None)
            send_current_execution(token, chat_id, candidates[0])
            return True
        rows = [[{"text": f"№{item['id']} · {(item.get('client') or '')[:20]} · {(item.get('execution_essence') or item.get('name') or '')[:28]}"}] for item in candidates[:10]]
        update_deal_ui_state(chat_id, pending="current_execution_select", current_execution_candidates=candidates[:10])
        send_message(token, chat_id, "Уточнение подходит к нескольким сделкам. Выберите нужную.", {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})
        return True
    match = CURRENT_EXECUTION_RE.search(value)
    if match:
        query = match.group(1).strip(" .,:;!?«»\"'")
    else:
        return False
    if not query:
        send_message(token, chat_id, "Укажите номер, клиента, адрес или часть сути сделки.")
        return True
    if query.isdigit():
        result = run_deal_browser({"action": "get", "deal_id": query})
        candidates = [result.get("deal")] if result.get("ok") else []
    else:
        candidates = find_execution_candidates(query)
    allowed = approved_deal_ids()
    candidates = [item for item in candidates if item and str(item.get("id")) in allowed]
    candidates = filter_execution_candidates_for_role(chat_id, candidates)
    labels = archive_deal_labels()
    for item in candidates:
        item["execution_essence"] = " / ".join(labels.get(str(item.get("id"))) or []) or item.get("name")
    if not candidates:
        update_deal_ui_state(chat_id, pending="current_execution_query")
        role_note = " Среди сделок, где вы указаны исполнителем, совпадений нет." if str(chat_id) in INSTALLER_CHAT_IDS else ""
        send_message(token, chat_id, f"Не удалось однозначно найти доступную сделку по запросу «{query}».{role_note} Уточните номер сделки либо сочетание клиента и сути, например «JetCar отопление».")
        return True
    if len(candidates) == 1:
        send_current_execution(token, chat_id, candidates[0])
        return True
    rows = [[{"text": f"№{item['id']} · {(item.get('client') or '')[:20]} · {(item.get('execution_essence') or item.get('name') or 'без названия')[:28]}"}] for item in candidates[:10]]
    rows.append([{"text": "⬅️ Главное меню"}])
    update_deal_ui_state(chat_id, pending="current_execution_select", current_execution_candidates=candidates[:10])
    send_message(token, chat_id, "Нашлось несколько сделок. Выберите нужную.", {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})
    return True


@durable_json.transaction(lambda:INSTALLER_FACT_REGISTRY_FILE)
def save_installer_fact_registry(session):
    registry = durable_json.read(INSTALLER_FACT_REGISTRY_FILE,dict)
    for item in session.get("exceptions") or []:
        if item.get("type") != "table" or not item.get("deal_id"):
            continue
        deal = registry.setdefault(str(item["deal_id"]), {})
        for row in item.get("table_rows") or []:
            key = re.sub(r"[^a-zа-я0-9]+", " ", str(row.get("name") or "").casefold().replace("ё", "е")).strip()
            if not key:
                continue
            deal[key] = {
                "name": row.get("name"), "qty": row.get("cumulative_qty") or 0,
                "updated_report": session.get("report_date") or session.get("report"),
            }
    durable_json.save(INSTALLER_FACT_REGISTRY_FILE,registry)


def money(value):
    if value is None:
        return "сумма не указана"
    return f"{bank_money(value)} ₽"


def parse_nonnegative_money(value):
    raw = re.sub(r"[^0-9,.-]", "", str(value or "").replace("\xa0", "").replace(" ", ""))
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")
    try:
        amount = float(raw)
    except ValueError:
        return None
    return amount if amount >= 0 else None


def request_exception_amount(token, chat_id, installer, index, resolution, bucket=None):
    installer["amount_exception_index"] = index
    installer["amount_resolution"] = resolution
    installer["amount_bucket"] = bucket
    update_deal_ui_state(chat_id, pending="installer_report_exception_amount", installer_report=installer)
    item = (installer.get("exceptions") or [])[index]
    send_message(
        token, chat_id,
        f"Укажите стоимость строки:\n{item.get('source')}\n\nВведите сумму в рублях. Если работа не оплачивается, явно введите 0.",
    )


def installer_payment_intent(text):
    value=str(text or '').casefold().replace('ё','е')
    return bool(re.search(r'\b(?:учесть|учти|занести|записать|зарегистрировать)\b',value)
                and re.search(r'\b(?:платеж\w*|выплат\w*)\b',value)
                and re.search(r'\b(?:монтажник\w*|деревянко)\b',value))


def parse_text_installer_payment(text, chat_id):
    amount_match = re.search(r"(?<!\d)(\d[\d\s\xa0]*(?:[,.]\d{1,2})?)\s*(?:₽|р\.?|руб(?:ля|лей)?\.?)", text, re.IGNORECASE)
    if not amount_match:
        return None
    amount = parse_nonnegative_money(amount_match.group(1))
    if amount is None or amount <= 0:
        return None
    date_match = re.search(r"\b([0-3]?\d[./-][01]?\d[./-](?:20)?\d{2})\b", text)
    if date_match:
        raw_date = date_match.group(1).replace("/", ".").replace("-", ".")
        parts = raw_date.split(".")
        if len(parts[2]) == 2:
            parts[2] = "20" + parts[2]
        try:
            payment_date = datetime.strptime(".".join(parts), "%d.%m.%Y").strftime("%d.%m.%Y")
        except ValueError:
            return None
    else:
        payment_date = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return {
        "path": "", "file_hash": f"telegram-text:{chat_id}:{stamp}",
        "date": payment_date, "number": f"НАЛ-{stamp}",
        "recipient": "Деревянко Сергей Владимирович (ИП)",
        "purpose": text.strip(), "amount": amount, "missing": [], "duplicate": False,
        "suggested_method": "cash" if "налич" in text.casefold() else "cashless" if "безнал" in text.casefold() else None,
    }


def installer_objects_text(session):
    lines = [f"Отчёт от {session.get('report')}\n"]
    for index, obj in enumerate(session.get("objects") or [], 1):
        deal = f"сделка №{obj['deal_id']} · {obj.get('essence')}" if obj.get("deal_id") else "сделка не определена"
        inherited = " · по контексту 95%" if obj.get("inherited") else ""
        lines.append(f"{index}. {obj['name']} — {money(obj.get('amount'))}\n   {deal}{inherited}")
    lines.append("\nВсё определено правильно?")
    return "\n".join(lines)


def installer_review_text(session):
    exceptions = session.get("exceptions") or []
    unresolved = [item for item in exceptions if not item.get("resolution") or item.get("resolution") == "оставлено вопросом"]
    lines = [
        f"Понятные строки: {session.get('automatic_count', 0)} на {money(session.get('automatic_sum', 0))}.",
        f"Требуют решения: {len(unresolved)}.",
    ]
    for item in unresolved[:8]:
        lines.append(f"• {item['object']}: {item['source']} — {item['reason']}")
    if len(unresolved) > 8:
        lines.append(f"• …и ещё {len(unresolved) - 8}")
    return "\n".join(lines)


def installer_exception_keyboard(item):
    if item.get("type") == "recognition":
        return {"keyboard": [[{"text": "✅ Строки и суммы сверены"}], [{"text": "⏭ Оставить вопросом"}], [{"text": "❌ Отменить отчёт"}]], "resize_keyboard": True}
    if item.get("type") == "discrepancy":
        return {"keyboard": [
            [{"text": "✅ Принять построчный итог"}],
            [{"text": "➕ Добавить корректировку"}, {"text": "✏️ Исправить строки"}],
            [{"text": "❌ Отменить отчёт"}],
        ], "resize_keyboard": True, "one_time_keyboard": True}
    if item.get("type") == "table":
        first = [{"text": "✅ Принять выполнение таблицы"}, {"text": "🔢 Выбрать позиции позже"}]
    elif item.get("type") == "settlement":
        first = [{"text": "✅ Подтвердить операцию"}, {"text": "⏭ Оставить вопросом"}]
    elif item.get("type") == "deal":
        first = [{"text": "📦 Всякая всячина"}, {"text": "🔢 Указать номер сделки"}]
        second = [{"text": "⏭ Оставить вопросом"}, {"text": "🚫 Не учитывать"}]
        return {"keyboard": [first, second, [{"text": "❌ Отменить отчёт"}]], "resize_keyboard": True, "one_time_keyboard": True}
    else:
        first = [{"text": "➕ Внеплановый расход"}, {"text": "⏭ Оставить вопросом"}]
    return {"keyboard": [first, [{"text": "🚫 Не учитывать"}, {"text": "❌ Отменить отчёт"}]], "resize_keyboard": True, "one_time_keyboard": True}


def send_installer_exception(token, chat_id, session):
    exceptions = session.get("exceptions") or []
    index = int(session.get("exception_index") or 0)
    while index < len(exceptions) and exceptions[index].get("resolution"):
        index += 1
    session["exception_index"] = index
    update_deal_ui_state(chat_id, installer_report=session, pending="installer_report_exception")
    if index >= len(exceptions):
        send_message(token, chat_id, "Все исключения просмотрены.\n\n" + installer_review_text(session), installer_review_keyboard(chat_id))
        return
    item = exceptions[index]
    if item.get("type") == "recognition":
        preview = "Строки для сверки с оригиналом:\n" + "\n".join(
            f"{row.get('source')} → {money(row.get('amount'))}"
            for row in session.get("report_lines") or [])
        for start in range(0, len(preview), 3500):
            send_message(token, chat_id, preview[start:start + 3500])
    text = (
        f"Исключение {index + 1} из {len(exceptions)}\n"
        f"Объект: {item.get('object')}\n"
        f"Строка: {item.get('source')}\n"
        f"Сумма: {money(item.get('amount'))}\n"
        f"Причина: {item.get('reason')}"
    )
    if item.get("type") == "table" and item.get("table_file"):
        preview = []
        for row in (item.get("table_rows") or [])[:8]:
            qty = f" · план {row.get('plan_qty'):g} {row.get('unit')}" if isinstance(row.get("plan_qty"), (int, float)) else ""
            current = f" · сейчас {row.get('current_qty'):g}" if row.get("current_qty") else ""
            rate = f" × {money(row.get('rate'))}" if row.get("rate") is not None else ""
            preview.append(f"{row.get('number')}. {row.get('name')}{qty}{current}{rate}")
        text += (
            f"\n\nСвязанная таблица: {item['table_file']}\n"
            f"Строк в таблице: {item.get('table_rows_count') or 0}\n"
            f"Столбец текущего выполнения: {item.get('completion_column') or 'не найден'}; "
            f"итог {money(item.get('completion_footer') or item.get('completion_sum'))}\n"
            f"Уверенность сопоставления: {round((item.get('table_match_confidence') or 0) * 100)}%\n"
            f"Первые строки:\n" + "\n".join(preview)
        )
    if item.get("type") == "discrepancy":
        causes = item.get("probable_causes") or []
        text += (
            f"\n\nИтог монтажника: {money(item.get('declared_total'))}\n"
            f"Построчный итог: {money(item.get('calculated_total'))}\n"
            f"Расхождение: {money(item.get('amount'))}"
        )
        if causes:
            text += "\nВероятный источник:\n" + "\n".join(
                f"• {cause['object']}: указано {money(cause['declared'])}, строки дают {money(cause['calculated'])}, разница {money(cause['difference'])}"
                for cause in causes
            )
    send_message(token, chat_id, text, installer_exception_keyboard(item))


INSTALLER_REPORT_EXTENSIONS = (".pdf", ".docx", ".xlsx", ".txt")


def process_installer_report(token, chat_id, path):
    send_message(token, chat_id, "🧰 Разбираю отчёт по объектам и выделяю только спорные строки...")
    result = run_installer_report_intake(path)
    if not result.get("ok"):
        update_deal_ui_state(chat_id, pending="installer_report_file", installer_report=None,
            installer_report_failure={"source_path": path, "error": result.get("error"), "at": datetime.now(timezone.utc).isoformat()})
        send_message(token, chat_id, f"Файл «{os.path.basename(path)}» сохранён, но разбор не завершён: {result.get('error')}. "
            "Начислений нет. Можно повторить разбор сохранённого файла или прислать текст отчёта одним сообщением.",
            {"keyboard": [[{"text": "🔄 Повторить разбор"}], [{"text": "❌ Отменить отчёт"}]], "resize_keyboard": True})
        return
    session = result["session"]
    update_deal_ui_state(chat_id, installer_report_failure=None)
    session.setdefault("submitted_by_chat_id", str(chat_id))
    session.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    if str(chat_id) in INSTALLER_CHAT_IDS and MANAGER_CHAT_ID and session.get("report_date"):
        send_message(
            token,
            MANAGER_CHAT_ID,
            f"🔔 Сергей Деревянко загрузил новый отчёт от {session.get('report_date') or session.get('report')}. "
            "Бот начал разбор; после проверки монтажником черновик будет передан вам.",
            MAIN_KEYBOARD,
        )
    if session.get("source_kind") == "excel":
        if not session.get("report_date"):
            update_deal_ui_state(chat_id, pending="installer_excel_report_date", installer_report=session)
            send_message(token, chat_id, "Excel принят как основной отчёт. Укажите дату отчёта в формате ДД.ММ.ГГГГ.")
            return
        update_deal_ui_state(chat_id, pending="installer_excel_report_deal", installer_report=session)
        send_message(token, chat_id, "Excel принят как основной отчёт. Укажите внутренний номер сделки, к которой относится выполнение, либо выберите «Всякая всячина».", {
            "keyboard": [[{"text": "📦 Всякая всячина"}], [{"text": "❌ Отменить отчёт"}]], "resize_keyboard": True,
        })
        return
    required = int(session.get("required_tables") or 0)
    if required:
        session["table_paths"] = []
        session["stage"] = "tables"
        update_deal_ui_state(chat_id, pending="installer_report_tables", installer_report=session)
        requests = "\n".join(
            f"• {item['object']}: «{item['source']}»" + (f" → сделка №{item['deal_id']}" if item.get("deal_id") else "")
            for item in session.get("table_requests") or []
        )
        send_message(
            token, chat_id,
            f"В отчёте найдено строк «По таблице»: {required}.\n\n{requests}\n\n"
            f"Пришлите {required} соответствующих Excel-файла подряд, затем нажмите «✅ Все файлы загружены».",
            INSTALLER_REPORT_FILES_KEYBOARD,
        )
        return
    update_deal_ui_state(chat_id, pending="installer_report_objects", installer_report=session)
    send_message(token, chat_id, installer_objects_text(session), INSTALLER_REPORT_OBJECTS_KEYBOARD)


def finish_installer_report_files(token, chat_id, session):
    paths = session.get("table_paths") or []
    required = int(session.get("required_tables") or 0)
    if len(paths) < required:
        send_message(token, chat_id, f"Пока получено таблиц: {len(paths)} из {required}. Пришлите недостающие Excel-файлы.", INSTALLER_REPORT_FILES_KEYBOARD)
        return
    result = run_installer_report_intake(session["source_path"], paths)
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось разобрать комплект файлов: {result.get('error')}", INSTALLER_REPORT_FILES_KEYBOARD)
        return
    completed = result["session"]
    completed["table_paths"] = paths
    completed['submitted_by_chat_id']=session.get('submitted_by_chat_id') or str(chat_id)
    update_deal_ui_state(chat_id, pending="installer_report_objects", installer_report=completed)
    associations = []
    for item in completed.get("exceptions") or []:
        if item.get("type") == "table":
            confidence = round((item.get("table_match_confidence") or 0) * 100)
            associations.append(
                f"• {item['object']} → {item.get('table_file') or 'таблица не определена'} "
                f"({item.get('table_rows_count') or 0} строк, уверенность {confidence}%)"
            )
    prefix = "Таблицы сопоставлены:\n" + "\n".join(associations) + "\n\n" if associations else ""
    send_message(token, chat_id, prefix + installer_objects_text(completed), INSTALLER_REPORT_OBJECTS_KEYBOARD)


def cleanup_generated_contract(state):
    generated = state.get("generated_contract") or {}
    paths = [generated.get("docx_path"), generated.get("pdf_path")]
    output_dir = None
    for path in paths:
        if not path:
            continue
        output_dir = os.path.dirname(path)
        try:
            os.remove(path)
        except OSError:
            pass
    if output_dir and output_dir.startswith("/tmp/contract-"):
        try:
            os.rmdir(output_dir)
        except OSError:
            pass


def run_deal_browser(spec, timeout=45):
    cached_actions = {"list", "search_any", "search_client", "search_address",
                      "get_cached", "get_many_cached"}
    if str(spec.get("action") or "") not in cached_actions:
        try:
            with socket.create_connection(("cclimat.megaplan.ru", 443), timeout=1.0):
                pass
        except OSError:
            return {"ok": False, "no_effect": True,
                    "error": "Мегаплан сейчас недоступен с сервера; операция не отправлялась"}
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "deal_browser.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=timeout,
        )
        lines = (result.stdout or "").strip().splitlines()
        if not lines:
            detail = (result.stderr or "").strip().splitlines()
            error = detail[-1][:300] if detail else "пустой ответ Мегаплана"
            print(f"{LOG_PREFIX} deal browser failed: {error}", file=sys.stderr)
            return {"ok": False, "error": "Мегаплан временно не ответил"}
        parsed = json.loads(lines[-1])
        if result.returncode == 0 and parsed.get("ok"):
            return parsed
        return {**parsed, "ok": False, "error": parsed.get("error") or "ошибка Мегаплана"}
    except Exception as e:
        print(f"{LOG_PREFIX} deal browser failed: {e}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка поиска сделок"}


def run_morning_brief(spec, timeout=90):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "morning_brief.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=timeout,
        )
        lines = (result.stdout or "").strip().splitlines()
        parsed = json.loads(lines[-1]) if lines else {}
        if result.returncode == 0 and parsed.get("ok"):
            return parsed
        return {"ok": False, "error": parsed.get("error") or "Мегаплан временно не ответил"}
    except Exception as exc:
        print(f"{LOG_PREFIX} morning brief failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка чтения Мегаплана"}


MORNING_BRIEF_MAX_ITEMS = 10


def send_morning_brief(token, chat_id, config=None):
    config = config or qa_schedule.morning_brief_config()
    result = run_morning_brief({"invoice_days": config["invoice_overdue_days"],
                                "stale_days": config["deal_stale_days"],
                                "completed_statuses": config.get("completed_statuses") or []})
    if not result.get("ok"):
        send_message(token, chat_id, "Утренний список дел НЕ СОБРАН: CRM недоступна или вернула ошибку. "
                     "Пустой результат не считаю отсутствием задач. Причина: " + str(result.get("error") or "неизвестна"))
        return False
    overdue = sorted(result.get("overdue") or [], key=lambda item: -int(item.get("days") or 0))
    stale = sorted(result.get("stale") or [], key=lambda item: -float(item.get("amount") or 0))
    limit = int(config.get("max_items") or MORNING_BRIEF_MAX_ITEMS)
    hidden = {"overdue": max(0, len(overdue) - limit), "stale": max(0, len(stale) - limit)}
    # A morning list is read in a minute: the oldest debts and the largest stuck
    # deals first, the rest counted (QA 23.10: the cache holds hundreds of deals).
    overdue, stale = overdue[:limit], stale[:limit]
    lines = ["Утренний список дел"]
    if overdue:
        lines.append("\nНеоплаченные счета:")
        for item in overdue:
            lines.append(f"• Сделка №{item['deal_id']} · {item.get('client') or 'клиент не указан'} · "
                         f"остаток {bank_money(item.get('remainder'))} ₽ из {bank_money(item.get('amount'))} ₽ · {item['days']} дн.")
        if hidden["overdue"]:
            lines.append(f"…и ещё {hidden['overdue']} неоплаченных счетов.")
    if stale:
        lines.append("\nСделки без движения:")
        for item in stale:
            lines.append(f"• Сделка №{item['deal_id']} · {item.get('client') or 'клиент не указан'} · "
                         f"{bank_money(item.get('amount'))} ₽ · {item['days']} дн. · {item.get('status') or 'статус не указан'}")
        if hidden["stale"]:
            lines.append(f"…и ещё {hidden['stale']} сделок без движения.")
    if not overdue and not stale:
        lines.append("\nПросроченных счетов и незавершённых сделок без движения нет.")
    deal_ids = list(dict.fromkeys(str(item["deal_id"]) for item in overdue + stale))
    keyboard = ({"keyboard": [[{"text": f"№{deal_id} · открыть сделку"}] for deal_id in deal_ids],
                 "resize_keyboard": True, "one_time_keyboard": True} if deal_ids else None)
    send_message(token, chat_id, "\n".join(lines), keyboard)
    return True


def queue_deal_transition(transition, chat_id):
    data = durable_json.read(PENDING_TRANSITIONS_FILE, dict)
    deal_id = str(transition["deal_id"])
    data[deal_id] = {
        "deal_id": deal_id, "state_id": str(transition["state_id"]),
        "name": str(transition.get("name") or ""), "chat_id": str(chat_id),
        "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    durable_json.save(PENDING_TRANSITIONS_FILE, data)


def retry_queued_deal_transitions(token):
    data = durable_json.read(PENDING_TRANSITIONS_FILE, dict)
    for deal_id, item in list(data.items()):
        result = run_deal_browser({"action": "move_status", "deal_id": deal_id,
                                   "state_id": item["state_id"]}, timeout=45)
        if not result.get("ok"):
            continue
        data.pop(deal_id, None)
        durable_json.save(PENDING_TRANSITIONS_FILE, data)
        chat_id = str(item.get("chat_id") or MANAGER_CHAT_ID)
        deal = result.get("deal") or {}
        send_message(token, chat_id,
                     f"✅ Отложенный перевод выполнен: сделка №{deal_id} — статус «{deal.get('status') or item.get('name')}».",
                     DEAL_ACTIONS_KEYBOARD)
        if str(deal.get("status") or item.get("name") or "").casefold().replace("ё", "е").strip() == "монтаж":
            installation=run_installation_workflow({"action":"get","deal_id":deal_id})
            if installation.get("ok") and (installation.get("result") or {}).get("status") == "approved":
                handoff=complete_installation_handoff(token,deal_id,chat_id)
                send_message(token,chat_id,
                    "✅ Объект передан в кабинет монтажника. Уведомление отправляется с контролем доставки."
                    if handoff.get('ok') else "⚠️ Статус изменён, передача в кабинет ожидает повторной проверки.")
            else:
                # Compatibility for a transition queued by an older version.
                prepare_installation_after_transition(token, chat_id, deal_id)


def run_hogart_procurement(deal_id, status, dry_run=False):
    """Invoke the fixed, journaled supplier-order writer after a verified transition."""
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "hogart_procurement.py")],
            cwd=MEGAPLAN_DIR,
            input=json.dumps({"deal_id": str(deal_id), "status": status, "dry_run": dry_run}, ensure_ascii=False),
            capture_output=True, text=True, timeout=120,
        )
        lines = (result.stdout or "").strip().splitlines()
        return json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ Hogart"}
    except Exception as exc:
        print(f"{LOG_PREFIX} Hogart procurement failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка отправки заявки в Hogart"}


def run_procurement_workflow(spec):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "procurement_workflow.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=120,
        )
        lines = (result.stdout or "").strip().splitlines()
        return json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ закупочного модуля"}
    except Exception as exc:
        print(f"{LOG_PREFIX} procurement workflow failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка закупочного модуля"}


def refresh_nearby_procurement_snapshots(current_deal_id, limit=10):
    """Make the 7–10 nearest live deals visible to the distribution matcher."""
    refreshed = []
    live = run_deal_browser({"action": "list", "limit": 15})
    for ref in (live.get("deals") or [] if live.get("ok") else []):
        candidate_id = str(ref.get("id") or "")
        if not candidate_id or candidate_id == str(current_deal_id):
            continue
        status = str(ref.get("status") or "").casefold().replace("ё", "е")
        if any(word in status for word in ("заверш", "отказ", "отмен")):
            continue
        result = run_procurement_workflow({"action": "snapshot", "deal_id": candidate_id})
        if result.get("ok"):
            refreshed.append(candidate_id)
        if len(refreshed) >= int(limit):
            break
    return refreshed


def continue_procurement_after_stock(token, chat_id, deal_id, status="Закупка"):
    procurement = run_hogart_procurement(deal_id, status)
    if procurement.get("ok") and not procurement.get("skipped"):
        order_label = procurement.get("hogart_order_number") or procurement.get("hogart_order_id") or "создан"
        send_message(token, chat_id,
            f"✅ Заявка в Hogart отправлена: заказ {order_label}, позиций: {procurement.get('items_count')}. "
            "Учтены только количества, не закрытые внутренними остатками.", DEAL_ACTIONS_KEYBOARD)
    elif procurement.get("reason") == "no_hogart_items":
        send_message(token, chat_id, "После учёта остатков новых позиций для заказа Hogart нет.", DEAL_ACTIONS_KEYBOARD)
    elif procurement.get("reason") == "already_recorded":
        send_message(token, chat_id, "Заявка Hogart по этой сделке уже зарегистрирована; повторный заказ не создан.", DEAL_ACTIONS_KEYBOARD)
    else:
        send_message(token, chat_id,
            f"⚠️ Заявку Hogart отправить не удалось: {procurement.get('error') or 'нужна ручная проверка'}. "
            "Автоматический повтор заблокирован, чтобы не создать дубль.", DEAL_ACTIONS_KEYBOARD)
    procurement_file = publish_procurement_register(token, chat_id, deal_id)
    if not procurement_file.get("ok"):
        send_message(token, chat_id, f"⚠️ Не удалось обновить перечень закупки: {procurement_file.get('error')}", DEAL_ACTIONS_KEYBOARD)
    return procurement


def publish_procurement_register(token, chat_id, deal_id):
    """Build, attach to Megaplan, and send the human-named procurement workbook."""
    stored = build_and_store_procurement_register(deal_id)
    if not stored.get("ok"):
        return stored
    path = stored["path"]
    try:
        send_document(token, chat_id, path, "Перечень оборудования и материалов для закупки")
        hints = run_procurement_workflow({"action": "accounting_hints", "deal_id": str(deal_id)})
        if hints.get("ok") and hints.get("hints"):
            send_message(token, chat_id, "Подсказки для бухгалтерии:\n\n" +
                         "\n".join(f"• {item['text']}" for item in hints["hints"]), PROCUREMENT_KEYBOARD)
        return {"ok": True, "filename": os.path.basename(path), "snapshot": stored.get("snapshot")}
    finally:
        try: os.remove(path)
        except OSError: pass
        try: os.rmdir(os.path.dirname(path))
        except OSError: pass


def build_and_store_procurement_register(deal_id):
    """Regenerate the live procurement workbook and replace it in the deal card."""
    snap = run_procurement_workflow({"action": "snapshot", "deal_id": str(deal_id)})
    if not snap.get("ok"):
        return {"ok": False, "error": snap.get("error")}
    exported = run_procurement_workflow({"action": "export", "deal_id": str(deal_id)})
    if not exported.get("ok"):
        return exported
    path = exported["path"]
    uploaded = run_deal_browser({"action": "upload_procurement_file", "deal_id": str(deal_id), "path": path})
    if not uploaded.get("ok"):
        try: os.remove(path)
        except OSError: pass
        try: os.rmdir(os.path.dirname(path))
        except OSError: pass
        return uploaded
    return {"ok": True, "path": path, "filename": os.path.basename(path),
            "snapshot": snap.get("snapshot")}


def check_external_procurement_transitions(token, chat_id):
    """Detect recent deals moved to Procurement directly in Megaplan."""
    global UI_CONTEXT
    try:
        watched = json.load(open(PROCUREMENT_WATCH_FILE, encoding="utf-8"))
    except FileNotFoundError:
        watched = {}
    if not isinstance(watched,dict):raise ValueError('Повреждён журнал переходов сделок; автоматический сброс запрещён')
    changed = False
    references = {str(ref.get("deal_id")): ref for ref in fetch_recent_deals()[:20] if ref.get("deal_id")}
    import sqlite3
    installation_db=os.path.join(MEGAPLAN_DIR,'installations.sqlite3')
    if os.path.exists(installation_db):
        with sqlite3.connect('file:'+installation_db+'?mode=ro',uri=True) as db:
            for (approved_id,) in db.execute("SELECT deal_id FROM installations WHERE status='approved'"):
                references.setdefault(str(approved_id),{'deal_id':str(approved_id)})
    try:
        procurement_data = json.load(open(os.path.join(MEGAPLAN_DIR, "procurement_registry.json"), encoding="utf-8"))
        for registered_id in (procurement_data.get("deals") or {}):
            references.setdefault(str(registered_id), {"deal_id": str(registered_id)})
    except FileNotFoundError:
        pass
    # Read all watched cards in one operation.  The old implementation started
    # up to 20 separate Python processes and HTTP requests sequentially every
    # minute; one slow CRM response could keep this background pass alive for
    # tens of minutes and contend with user commands.
    deal_ids = [str(ref.get("deal_id") or "") for ref in references.values() if ref.get("deal_id")]
    batch = run_deal_browser({"action": "get_many_cached", "deal_ids": deal_ids}, timeout=15)
    if not batch.get("ok"):
        print(f"{LOG_PREFIX} procurement watcher skipped: {batch.get('error')}", file=sys.stderr)
        return
    live_deals = {str(item.get("id")): item for item in (batch.get("deals") or [])}
    for ref in references.values():
        deal_id = str(ref.get("deal_id") or "")
        if not deal_id:
            continue
        import migration_transition_guard
        if migration_transition_guard.blocked(os.path.join(MEGAPLAN_DIR,'installations.sqlite3'),deal_id):
            continue
        deal = live_deals.get(deal_id)
        if not deal:
            continue
        status = str(deal.get("status") or "")
        marker = status.casefold().replace("ё", "е").strip()
        previous = watched.get(deal_id)
        live_ui = current_deal_ui_state(chat_id)
        if marker in ('монтаж', 'закупка') and previous != marker and (live_ui.get('pending') or live_ui.get('deal_creation_active')):
            # Leave the old marker intact: retry the transition when the owner
            # finishes the current wizard, without overwriting its context.
            continue
        watched[deal_id] = marker
        changed = changed or previous != marker
        if marker == "монтаж":
            existing = run_installation_workflow({"action":"get","deal_id":deal_id})
            if existing.get('ok') and (existing.get('result') or {}).get('status') == 'approved':
                complete_installation_handoff(token,deal_id,'status-reconciliation')
            if previous == 'монтаж':
                continue
            if not existing.get("ok"):
                if existing.get('error_code') != 'installation_not_prepared':
                    # A timeout or damaged storage is not an absent installation.
                    # Keep the transition pending for the next successful read.
                    if previous is None:watched.pop(deal_id,None)
                    else:watched[deal_id]=previous
                    continue
                claimed=ui_state_store().begin_idle(chat_id,live_ui.get('_revision',0),{'current_deal_id':deal_id})
                if claimed is None:
                    if previous is None:watched.pop(deal_id,None)
                    else:watched[deal_id]=previous
                    continue
                UI_CONTEXT=claimed
                send_message(token,chat_id,f"Сделка №{deal_id} переведена в «Монтаж» непосредственно в Мегаплане.")
                prepare_installation_after_transition(token,chat_id,deal_id)
            continue
        if marker != "закупка" or previous == "закупка":
            continue
        if migration_transition_guard.blocked(os.path.join(MEGAPLAN_DIR,'installations.sqlite3'),deal_id):
            continue
        run_procurement_workflow({"action": "snapshot", "deal_id": deal_id})
        stock = run_procurement_workflow({"action": "suggest_stock_for_deal", "deal_id": deal_id, "limit": 20})
        suggestions = stock.get("suggestions") or [] if stock.get("ok") else []
        if suggestions:
            claimed=ui_state_store().begin_idle(chat_id,live_ui.get('_revision',0),{
                'current_deal_id':deal_id,'pending':'procurement_stock_confirm',
                'procurement_stock_deal_id':deal_id,'procurement_stock_suggestions':suggestions})
            if claimed is None:
                if previous is None:watched.pop(deal_id,None)
                else:watched[deal_id]=previous
                continue
            UI_CONTEXT=claimed
            lines = [f"• {x.get('stock_name')} → {x.get('target_name')}: {float(x.get('qty') or 0):g}"
                     for x in suggestions]
            send_message(token, chat_id,
                f"Сделка №{deal_id} переведена в «Закупка». Перед заказом найдены внутренние остатки:\n" +
                "\n".join(lines), PROCUREMENT_STOCK_CONFIRM_KEYBOARD)
            continue
        procurement = run_hogart_procurement(deal_id, status)
        workbook = publish_procurement_register(token, chat_id, deal_id)
        if procurement.get("ok") and not procurement.get("skipped"):
            order = procurement.get("hogart_order_number") or procurement.get("hogart_order_id")
            message = f"✅ Сделка №{deal_id} переведена в «Закупка» в Мегаплане. Заказ Hogart №{order} создан."
        elif procurement.get("reason") == "already_recorded":
            message = f"📦 Сделка №{deal_id} переведена в «Закупка» в Мегаплане. Повторный заказ не создан."
        elif procurement.get("reason") == "no_hogart_items":
            message = f"📦 Сделка №{deal_id} переведена в «Закупка». Позиций для автоматического заказа Hogart нет."
        else:
            message = f"⚠️ Сделка №{deal_id} переведена в «Закупка», но заказ поставщику не создан: {procurement.get('error') or 'нужна проверка'}."
        if not workbook.get("ok"):
            message += f"\nНе удалось сохранить закупочную ведомость: {workbook.get('error')}"
        send_message(token, chat_id, message, DEAL_ACTIONS_KEYBOARD)
    if changed:
        durable_json.save(PROCUREMENT_WATCH_FILE,watched)


def format_deal_card(deal):
    executors = ", ".join(deal.get("executors") or []) or "не назначен — кнопка «👤 Назначить исполнителя»"
    address = deal.get("address") or "не указан"
    price = deal.get("price")
    price_text = f"{bank_money(price)} ₽" if isinstance(price, (int, float)) else "не указана"
    url = deal.get("url") or f"https://cclimat.megaplan.ru/deals/{deal['id']}/card/"
    subject = deal.get("description") or deal.get("name")
    return (
        f"Сделка №{deal['id']}\n"
        + (f"Суть: {deal_essence({'description': subject}, 120)}\n" if subject else "")
        + f"Клиент: {deal.get('client') or 'не указан'}\n"
        f"Адрес: {address}\n"
        f"Статус: {deal.get('status') or 'не указан'}\n"
        f"Исполнитель: {executors}\n"
        f"Сумма: {price_text}\n"
        f"Позиций: {deal.get('positions_count') or 0}\n"
        f"{url}"
    )


def deal_essence(deal, limit=90):
    raw = str(deal.get("description") or deal.get("address") or deal.get("client") or "Без описания")
    clean = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    clean = re.sub(r"\s+", " ", clean).strip() or "Без описания"
    sentence = re.match(r"^(.+?)(?:[.!?](?:\s|$)|$)", clean)
    if sentence:
        clean = sentence.group(1).strip()
    if limit and len(clean) > limit:
        return clean[:max(1, limit - 1)].rstrip(" ,.;:—-") + "…"
    return clean


def deal_selection_keyboard(deals):
    rows = [[{"text": f"№{d['id']} · {deal_essence(d, 38)}"}] for d in deals]
    rows.append([{"text": "⬅️ К списку сделок"}, {"text": "⬅️ Главное меню"}])
    return {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True}


def deal_list_price(value):
    """Format the CRM deal total compactly without inventing a missing amount."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "не указана"
    if not amount.is_finite():
        return "не указана"
    rendered = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    compact = rendered[:-3] if rendered.endswith(",00") else rendered
    return compact + " ₽"


def send_deal_list(token, chat_id, spec, result=None):
    result = result if result is not None else run_deal_browser(spec)
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось получить сделки: {result.get('error')}", DEALS_KEYBOARD)
        return
    deals = result.get("deals") or []
    if not deals:
        send_message(token, chat_id, "Подходящих сделок не найдено.", DEALS_KEYBOARD)
        return
    lines = [
        f"№{d['id']} — {d.get('client') or 'без клиента'}\n"
        f"Суть: {deal_essence(d)}\n"
        f"Статус: {d.get('status') or 'не указан'}\n"
        f"Сумма: {deal_list_price(d.get('price'))}"
        + (f"\nАдрес: {d['address']}" if d.get("address") else "")
        for d in deals
    ]
    total_count = int(result.get("total_count") or len(deals))
    shown = f" (показаны последние {len(deals)} из {total_count})" if total_count > len(deals) else ""
    send_message(token, chat_id, "Найденные сделки" + shown + ":\n\n" + "\n\n".join(lines), deal_selection_keyboard(deals))


def select_deal(token, chat_id, deal_id):
    # Opening a card is read-only navigation and must not wait for a slow CRM.
    # Mutating actions below still validate against live Megaplan data.
    result = run_deal_browser({"action": "get_cached", "deal_id": str(deal_id)}, timeout=8)
    if not result.get("ok"):
        error = str(result.get("error") or "неизвестная ошибка")
        if "не найден" in error:
            send_message(token, chat_id, f"Сделка №{deal_id} не найдена. Проверьте номер и введите его ещё раз.",
                         {"keyboard": [[{"text": "⬅️ К списку сделок"}]], "resize_keyboard": True})
        else:
            send_message(token, chat_id, f"Не удалось открыть сделку №{deal_id}: {error}", DEALS_KEYBOARD)
        return False
    deal = result["deal"]
    old_state = current_deal_ui_state(chat_id)
    previous = old_state.get("current_deal_id")
    values = {"current_deal_id": str(deal_id), "pending": None, "transitions": None, "pending_transition": None,
              "invoice_origin": None, "invoice_downloads": None, "deal_creation_active": False,
              "contract_deal_id": None}
    if previous != str(deal_id):
        cleanup_generated_contract(old_state)
        values["contract_signatory"] = None
        values["contract_signatory_payer_id"] = None
        values["generated_contract"] = None
        values["installation_pending_transition"] = None
        values["installation_deal_id"] = None
    update_deal_ui_state(chat_id, **values)
    send_message(token, chat_id, format_deal_card(deal), DEAL_ACTIONS_KEYBOARD)
    return True


def handle_explicit_deal_read(token, chat_id, text):
    match = DEAL_READ_RE.search(text or "")
    if not match:
        return False
    # A question word alone («что/какие/сколько … по сделке N») is a card read only
    # when the question asks for nothing the card cannot answer.
    if not DEAL_READ_VERB_RE.search(text or "") and DEAL_READ_OTHER_TASK_RE.search(text or ""):
        return False
    deal_id = next(group for group in match.groups() if group)
    result = run_deal_browser({"action": "get", "deal_id": deal_id})
    if not result.get("ok"):
        send_message(
            token, chat_id,
            f"Не удалось выполнить свежее чтение сделки №{deal_id} из Мегаплана: "
            f"{result.get('error') or 'неизвестная ошибка'}. Ранее сохранённые данные не показываю как актуальные.",
            DEALS_KEYBOARD,
        )
        return True
    deal = result["deal"]
    update_deal_ui_state(chat_id, current_deal_id=deal_id, pending=None, transitions=None,
                         pending_transition=None)
    answer = format_deal_card(deal) + "\n\nИсточник: свежее чтение из Мегаплана."
    lowered = (text or "").casefold().replace("ё", "е")
    economics_requested = any(word in lowered for word in ("себестоим", "умнож", "совпад", "разниц"))
    if economics_requested:
        ledger = fetch_deal_ledger(deal_id, force=True)
        if ledger is None:
            answer += "\n\nПроверка суммы и себестоимости: НЕ ПРОВЕРЕНО — не удалось свежо прочитать позиции сделки из CRM."
        else:
            unknown = []
            revenue = 0.0
            cost = 0.0
            details = []
            for index, item in enumerate(ledger, 1):
                try:
                    quantity = float(item.get("qty"))
                    sell_price = float(item.get("sell_price"))
                except (TypeError, ValueError):
                    unknown.append(f"строка {index}: нет количества или цены продажи")
                    continue
                raw_material = item.get("cost_material")
                raw_work = item.get("cost_work")
                if raw_material is None and raw_work is None:
                    unknown.append(f"строка {index}: нет себестоимости")
                    continue
                unit_cost = float(raw_material or 0) + float(raw_work or 0)
                line_revenue = quantity * sell_price
                revenue += line_revenue
                cost += quantity * unit_cost
                details.append(f"• {quantity:g} × {bank_money(sell_price)} ₽ = {bank_money(line_revenue)} ₽")
            if unknown or len(details) != len(ledger):
                answer += "\n\nПроверка суммы и себестоимости: НЕ ПРОВЕРЕНО — " + "; ".join(unknown)
            else:
                deal_total = float(deal.get("price") or 0)
                matches = abs(deal_total - revenue) <= 0.01
                answer += (
                    "\n\nПроверка суммы по позициям:\n" + "\n".join(details) +
                    f"\nИтого по позициям: {bank_money(revenue)} ₽."
                    f"\nСумма сделки: {bank_money(deal_total)} ₽."
                    f"\nСовпадает: {'да' if matches else 'нет'}."
                    f"\nОбщая себестоимость позиций: {bank_money(cost)} ₽."
                    f"\nРазница продажи и себестоимости: {bank_money(revenue - cost)} ₽."
                    "\nИсточник расчёта: свежие позиции CRM; внешние расходы вне позиций сюда не включены."
                )
    send_message(
        token, chat_id,
        answer,
        DEAL_ACTIONS_KEYBOARD,
    )
    return True


DEAL_SEARCH_PHRASE_RE = re.compile(
    r"(?i)^\s*(?:найди|найти|покажи|поищи|открой|какие|где)\s+(?:все\s+|мои\s+)?"
    r"(?:(?P<count>\d{1,2})\s+)?(?:последн\w*\s+)?сдел(?:к\w*|ок)\s+"
    r"(?:(?P<client>клиента|по\s+клиенту|у\s+клиента|с\s+клиентом|для)|(?P<address>по\s+адресу|на\s+адресе|адрес))\s+"
    r"(?P<query>[^?!.]{2,80})[?!.]*\s*$"
)


# «Найди сделку по складу в Химках»: no client/address marker — search everything.
DEAL_FREE_SEARCH_RE = re.compile(
    r"(?i)^\s*(?:найди|найти|покажи|поищи|где)\s+(?:все\s+|мои\s+)?(?:(?P<count>\d{1,2})\s+)?(?:последн\w*\s+)?"
    r"сдел(?:к\w*|ок)\s+(?P<query>[^?!.№]{3,80})[?!.]*\s*$"
)
# Lists by period/status/payment and deal numbers belong to other handlers.
DEAL_FREE_SEARCH_EXCLUDE_RE = re.compile(
    r"(?i)\b\d{3,}\b|статус|недел|месяц|сегодн|вчера|последн|открыт|оплат|долг|сч[её]т|работе"
)


BARE_DEAL_NUMBER_RE = re.compile(r"^\s*№?\s*(\d{3,7})\s*$")
ASSISTANT_CONTEXT_SECONDS = 600


def handle_bare_deal_number(token, chat_id, text):
    """A lone number opens that deal (QA idea И-2) — only when nobody asked a question.

    A number can be the answer to the bot's or the assistant's question (deal of a
    supplier invoice, quantity, report number), so any pending step, an active
    deal wizard, an open invoice or catalog task, or an assistant turn in the last
    ten minutes keeps the old behaviour.
    """
    match = BARE_DEAL_NUMBER_RE.match(text or "")
    if not match:
        return False
    state = current_deal_ui_state(chat_id)
    if state.get("pending") or state.get("deal_creation_active"):
        return False
    if time.time() - float(state.get("assistant_turn_at") or 0) < ASSISTANT_CONTEXT_SECONDS:
        return False
    try:
        tasks = invoice_tasks.read(chat_id)
    except Exception:
        return False
    if invoice_tasks.active(tasks) or (tasks.get("foreground") == "catalog"
                                       and time.time() - float(tasks.get("catalog_at") or 0) < 86400):
        return False
    return handle_deal_ui(token, chat_id, "№" + match.group(1))


def _phrase_limit(match):
    """«Покажи 10 сделок …» — the asked count, within the one-screen limit of 15."""
    return max(1, min(int(match.group("count") or 15), 15))


LISTED_DEAL_RE = re.compile(r"(?m)^\s*(?:\d{1,2}[.)]\s*)?№\s?(\d{3,7})\s*[—–-]\s*(.+?)\s*$")


def listed_deals_keyboard(text):
    """Buttons for deals an assistant answer lists one per line (owner request 25.10):
    a list of deals must be pressable, not «скажи "открой 858"»."""
    deals = list(dict.fromkeys(LISTED_DEAL_RE.findall(text or "")))
    ids = list(dict.fromkeys(deal_id for deal_id, _ in deals))
    if len(ids) < 2:
        return None
    titles = dict(reversed(deals))
    return deal_selection_keyboard([{"id": deal_id, "description": titles[deal_id]} for deal_id in ids[:15]])


def handle_deal_search_phrase(token, chat_id, text):
    """«Найди сделки клиента Иванов», «покажи сделки по адресу Химки» — a read, never the model."""
    match = DEAL_SEARCH_PHRASE_RE.match(text or "")
    if not match:
        free = DEAL_FREE_SEARCH_RE.match(text or "")
        if not free or DEAL_FREE_SEARCH_EXCLUDE_RE.search(free.group("query")):
            return False
        result = run_deal_browser({"action": "search_any", "query": free.group("query").strip(" «»\""),
                                   "limit": _phrase_limit(free)})
        if not result.get("ok") or not result.get("deals"):
            return False  # not a confident search: the usual route answers
        update_deal_ui_state(chat_id, pending=None)
        send_deal_list(token, chat_id, None, result)
        return True
    query = match.group("query").strip(" «»\"")
    action = "search_address" if match.group("address") else "search_client"
    update_deal_ui_state(chat_id, pending=None)
    send_deal_list(token, chat_id, {"action": action, "query": query, "limit": _phrase_limit(match)})
    return True


def handle_explicit_deal_comparison(token, chat_id, text):
    match = DEAL_COMPARE_RE.search(text or "")
    if not match:
        return False
    deal_ids = [match.group(1), match.group(2)]
    if deal_ids[0] == deal_ids[1]:
        send_message(token, chat_id, "Сравнение НЕ ПРОВЕРЕНО: укажите две разные сделки.", DEALS_KEYBOARD)
        return True
    deals = []
    failures = []
    for deal_id in deal_ids:
        result = run_deal_browser({"action": "get", "deal_id": deal_id})
        if not result.get("ok"):
            failures.append(f"сделка №{deal_id}: {result.get('error') or 'свежее чтение не удалось'}")
            continue
        deal = result.get("deal") or {}
        if deal.get("price") is None:
            failures.append(f"сделка №{deal_id}: в свежей карточке нет общей суммы")
        deals.append(deal)
    if failures or len(deals) != 2:
        send_message(
            token, chat_id,
            "Сравнение: НЕ ПРОВЕРЕНО.\nПричина: " + "; ".join(failures),
            DEALS_KEYBOARD,
        )
        return True
    lines = []
    for deal in deals:
        lines.append(
            f"Сделка №{deal.get('id')}\n"
            f"Клиент: {deal.get('client') or 'не указан'}\n"
            f"Текущий этап: {deal.get('status') or 'не указан'}\n"
            f"Сумма: {bank_money(deal['price'])} ₽\n"
            f"Позиций: {deal.get('positions_count') if deal.get('positions_count') is not None else 'не указано'}"
        )
    first_total = float(deals[0]["price"])
    second_total = float(deals[1]["price"])
    update_deal_ui_state(chat_id, comparison_deals=[
        {"deal_id": str(deal["id"]), "price": float(deal["price"])} for deal in deals
    ])
    if abs(first_total - second_total) <= 0.01:
        conclusion = "Суммы сделок равны."
    else:
        larger = deals[0] if first_total > second_total else deals[1]
        conclusion = f"Сумма сделки №{larger.get('id')} больше на {bank_money(abs(first_total - second_total))} ₽."
    answer = ("Сравнение по свежим карточкам Мегаплана:\n\n" +
              "\n\n".join(lines) + "\n\n" + conclusion +
              "\nНичего не изменено.")
    send_message(token, chat_id, answer, DEALS_KEYBOARD)
    return True


def handle_deal_comparison_followup(token, chat_id, text):
    if not DEAL_COMPARE_FOLLOWUP_RE.search(text or ""):
        return False
    comparison = current_deal_ui_state(chat_id).get("comparison_deals") or []
    valid = [item for item in comparison if item.get("deal_id") and item.get("price") is not None]
    if len(valid) != 2 or valid[0]["deal_id"] == valid[1]["deal_id"]:
        send_message(
            token, chat_id,
            "НЕ ПРОВЕРЕНО — в текущем диалоге нет подтверждённого сравнения двух разных сделок. Укажите оба номера.",
            DEALS_KEYBOARD,
        )
        return True
    if abs(float(valid[0]["price"]) - float(valid[1]["price"])) <= 0.01:
        send_message(
            token, chat_id,
            "НЕ ПРОВЕРЕНО — у сравниваемых сделок одинаковая сумма, меньшую выбрать нельзя.",
            DEALS_KEYBOARD,
        )
        return True
    selected = min(valid, key=lambda item: float(item["price"]))
    deal_id = str(selected["deal_id"])
    result = run_deal_browser({"action": "get", "deal_id": deal_id})
    if not result.get("ok"):
        send_message(
            token, chat_id,
            f"НЕ ПРОВЕРЕНО — не удалось свежо прочитать выбранную сделку №{deal_id}: "
            f"{result.get('error') or 'неизвестная ошибка'}.",
            DEALS_KEYBOARD,
        )
        return True
    deal = result["deal"]
    update_deal_ui_state(chat_id, current_deal_id=deal_id, pending=None)
    send_message(
        token, chat_id,
        "Из ранее подтверждённой пары меньшая сумма у этой сделки:\n\n" +
        format_deal_card(deal) + "\n\nИсточник: повторное свежее чтение из Мегаплана. Ничего не изменено.",
        DEAL_ACTIONS_KEYBOARD,
    )
    return True


def format_profitability(deal_id, result):
    margin = f"{float(result.get('margin_pct') or 0):.1f}".replace(".", ",")
    return (f"Экономика сделки №{deal_id}: выручка {bank_money(result.get('total_revenue', 0))} ₽, "
            f"себестоимость {bank_money(result.get('total_cost', 0))} ₽, "
            f"прибыль {bank_money(result.get('total_profit', 0))} ₽ ({margin}%).")


def send_current_profitability(token, chat_id, deal_id):
    send_message(token, chat_id, "📊 Читаю актуальные данные сделки из Мегаплана и считаю экономику...")
    result = build_and_store_profitability(deal_id)
    if not result.get("ok") and not (result.get("built") and result.get("path") and os.path.isfile(result["path"])):
        send_message(token, chat_id, f"Не удалось построить экономику: {result.get('error')}", DEAL_ACTIONS_KEYBOARD)
        return
    note = ("\n\nДанные не менялись — файл в сделке актуален, повторно не записывался." if result.get("unchanged") else
            f"\n\n⚠️ Расчёт готов, но {result.get('error')}. Файл ниже — актуальный." if not result.get("ok") else "")
    send_message(token, chat_id, format_profitability(deal_id, result) + note, DEAL_ACTIONS_KEYBOARD)
    send_document(token, chat_id, result["path"], "Расчёт рентабельности сделки")
    try:
        os.remove(result["path"])
    except OSError:
        pass


def run_contract_builder(spec):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "generate_contract.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=120,
        )
        parsed = json.loads((result.stdout or "").strip().splitlines()[-1])
        if parsed.get("ok"):
            return parsed
        return {"ok": False, "error": parsed.get("error") or "ошибка формирования договора", "missing": parsed.get("missing") or []}
    except Exception as e:
        print(f"{LOG_PREFIX} contract builder failed: {e}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка формирования договора"}


def run_contract_invoice(spec):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "contract_invoice.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=120,
        )
        lines = (result.stdout or "").strip().splitlines()
        parsed = json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ Мегаплана"}
        if not parsed.get("ok") and "Megaplan API error" in str(parsed.get("error")):
            print(f"{LOG_PREFIX} contract invoice API error: {parsed.get('error')}", file=sys.stderr)
            parsed["error"] = "Мегаплан отклонил данные счёта"
        return parsed
    except Exception as exc:
        print(f"{LOG_PREFIX} contract invoice failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка создания счёта"}


def format_contract_preview(preview):
    money = lambda value: f"{bank_money(value)} ₽"
    return (
        f"Договор №{preview.get('number')} от {preview.get('date')}\n"
        f"Поставщик: {preview.get('seller_name') or 'не указан'}\n"
        f"Клиент: {preview.get('client')}\n"
        f"Заказчик / плательщик: {preview.get('payer_name') or 'не указан'}\n"
        f"Объект: {preview.get('address')}\n"
        f"Предмет: {preview.get('subject')}\n\n"
        f"Оборудование: {money(preview.get('equipment', 0))}\n"
        f"Материалы: {money(preview.get('materials', 0))}\n"
        f"Авансовый платёж: {money(preview.get('advance', 0))}\n"
        f"Работы и услуги: {money(preview.get('works', 0))}\n"
        f"Окончательный платёж: {money(preview.get('works', 0))}\n"
        f"Итого: {money(preview.get('total', 0))}\n"
        f"Позиций в спецификации: {preview.get('positions_count', 0)}\n"
        f"{preview.get('tax_text')}"
    )


def record_operation_timing(operation, elapsed_seconds, chat_id="", outcome="ok", details=None):
    """Keep a bounded, local audit trail of slow user-facing operations."""
    if elapsed_seconds < 2:
        return
    event = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "operation": str(operation or "background"), "seconds": round(float(elapsed_seconds), 2),
             "chat_id": str(chat_id or ""), "outcome": str(outcome or "ok")}
    if details:
        event["details"] = str(details)[:300]
    try:
        with open(SLOW_OPERATIONS_LOG, "a+", encoding="utf-8") as log:
            fcntl.flock(log, fcntl.LOCK_EX)
            log.write(json.dumps(event, ensure_ascii=False) + "\n")
            # Keep the log useful but bounded; it is diagnostic data, not an
            # accounting register.
            log.seek(0)
            lines = log.readlines()
            if len(lines) > 1000:
                log.seek(0); log.truncate(); log.writelines(lines[-800:])
            fcntl.flock(log, fcntl.LOCK_UN)
    except OSError as error:
        print(f"{LOG_PREFIX} slow-operation log failed: {error}", file=sys.stderr)


def run_background_job(job, token, chat_id, operation="background", allow_stale=False):
    """Fork one bounded CRM/report job so Telegram polling never waits on network I/O."""
    pid = os.fork()
    if pid == 0:
        started = time.monotonic()
        outcome, details = "ok", ""
        try:
            if not allow_stale and not request_is_current():
                send_message(token, chat_id, 'Предыдущее действие отменено новым сообщением до начала выполнения. Повторите его в нужной сделке.')
                return
            job()
        except Exception as e:
            outcome, details = "error", str(e)
            print(f"{LOG_PREFIX} background job failed: {e}", file=sys.stderr)
            try:
                send_message(token, chat_id, "Операция завершилась технической ошибкой. Если подтверждалась запись, её результат нужно проверить перед повтором: внешний сервис мог успеть сохранить данные. Подтверждённые шаги автоматически повторяться не будут.")
            except Exception:
                pass
        finally:
            record_operation_timing(operation, time.monotonic() - started, chat_id, outcome, details)
            os._exit(0)
    try:
        while os.waitpid(-1, os.WNOHANG)[0]:
            pass
    except ChildProcessError:
        pass


UNSUPPORTED_MESSAGE_KINDS = (("voice", "Голосовые сообщения"), ("video_note", "Видеосообщения-кружки"),
                             ("audio", "Аудиофайлы"), ("sticker", "Стикеры"), ("location", "Геопозицию"),
                             ("contact", "Контакты"))


def transcribe_voice_message(token, chat_id, msg, env):
    """Download, recognise and echo a voice message; None when it cannot be used."""
    voice = msg.get("voice") or {}
    if int(voice.get("duration") or 0) > voice_intake.MAX_SECONDS:
        send_message(token, chat_id, "🎙 Голосовое длиннее 3 минут не распознаю. Разбейте поручение на части "
                     "или напишите его текстом.", home_keyboard(chat_id))
        return None
    send_typing(token, chat_id)
    path, error = download_telegram_media(token, voice, "voice.ogg")
    if error:
        send_message(token, chat_id, f"🎙 {error} Напишите поручение текстом.", home_keyboard(chat_id))
        return None
    try:
        text = voice_intake.transcribe(path, env)
    except voice_intake.VoiceError as exc:
        send_message(token, chat_id, f"🎙 Голосовое не распознано: {exc}. Поручение не принято — "
                     "напишите его текстом.", home_keyboard(chat_id))
        return None
    send_message(token, chat_id, f"🎙 Распознано: «{text}»\nЕсли неверно — повторите текстом. "
                 "Записи по-прежнему выполняются только после подтверждения кнопкой.")
    return text


def run_foreground(job):
    """Run a routed message in the polling process.

    Production simply calls the job (model turns fork inside it).  The human QA
    stand replaces this seam to execute forked branches in-process.
    """
    job()


def run_singleton_background_job(name, job, token, chat_id):
    """Run a periodic watcher without ever blocking Telegram polling.

    A non-blocking file lock prevents a slow previous run from being duplicated
    at the next interval.  The lock is released automatically when the child
    exits, including after an error.
    """
    os.makedirs(BACKGROUND_LOCK_DIR, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(name)).strip(".-") or "watcher"
    lock_path = os.path.join(BACKGROUND_LOCK_DIR, f"{safe_name}.lock")
    pid = os.fork()
    if pid == 0:
        lock = None
        try:
            lock = open(lock_path, "w")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os._exit(0)
            os.environ['MEGAPLAN_PRIORITY']='background'
            job()
        except Exception as exc:
            print(f"{LOG_PREFIX} background watcher {name} failed: {exc}", file=sys.stderr)
        finally:
            if lock is not None:
                try:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                    lock.close()
                except OSError:
                    pass
            os._exit(0)
    try:
        while os.waitpid(-1, os.WNOHANG)[0]:
            pass
    except ChildProcessError:
        pass


def continue_document_order(token, chat_id, order, details=None):
    order = {**order, 'details': {**order.get('details', {}), **(details or {})}}
    update_deal_ui_state(chat_id, document_order=order, pending='document_order_details')
    try:
        result = subprocess.run([REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, 'document_order.py')],
            input=json.dumps({**order, 'chat_id':str(chat_id), 'expected_revision':current_deal_ui_state(chat_id).get('_revision'), 'action':'fulfill'}, ensure_ascii=False),
            capture_output=True, text=True, timeout=240)
        outcome = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as exc:
        outcome = {'ok':False, 'error':'Обработка прервана; сохранённые этапы будут сверены при продолжении. '+type(exc).__name__}
    if not request_is_current():
        return
    if outcome.get('complete'):
        update_deal_ui_state(chat_id, document_order={**order, 'complete':True, 'result':outcome}, pending=None)
        send_message(token, chat_id, 'Готово: договор и счёт по сделке №'+str(order['deal_id'])+' сохранены в Мегаплане и отправлены вам файлами.', DEAL_ACTIONS_KEYBOARD)
    elif outcome.get('ok'):
        update_deal_ui_state(chat_id, document_order=order, pending='document_order_details')
        send_message(token, chat_id, order_continuation.question(outcome))
    else:
        update_deal_ui_state(chat_id, document_order={**order, 'last_error':outcome.get('error')}, pending='document_order_details')
        send_message(token, chat_id, 'Комплект №'+str(order['deal_id'])+' не завершён: '+str(outcome.get('error'))+
                     order_continuation.recovery_hint(outcome))


def prepare_contract_preview(token, chat_id, deal_id):
    state = current_deal_ui_state(chat_id)
    signer = state.get("contract_signatory") or {}
    signer_payer_id = str(state.get("contract_signatory_payer_id") or "")
    result = run_contract_builder({"action": "preview", "deal_id": deal_id,
                                   "customer_signatory": signer,
                                   "customer_signatory_payer_id": signer_payer_id})
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось проверить договор: {result.get('error')}", CONTRACT_KEYBOARD)
        return
    preview = result["preview"]
    payer_id = str(preview.get("payer_id") or "")
    if signer and signer_payer_id != payer_id:
        # The payer may be changed while the same deal stays selected. Drop every
        # signatory field from the former payer and resolve the new payer afresh.
        signer = {}
        result = run_contract_builder({"action": "preview", "deal_id": deal_id,
                                       "customer_signatory": {},
                                       "customer_signatory_payer_id": payer_id})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось проверить договор: {result.get('error')}", CONTRACT_KEYBOARD)
            return
        preview = result["preview"]
        update_deal_ui_state(chat_id, contract_signatory=None,
                             contract_signatory_payer_id=payer_id)
    resolved_signer = preview.get("signatory") or signer
    if resolved_signer != signer:
        update_deal_ui_state(chat_id, contract_signatory=resolved_signer,
                             contract_signatory_payer_id=payer_id)
        signer = resolved_signer
    missing = preview.get("missing") or []
    if "дата договора" in missing:
        update_deal_ui_state(chat_id, pending="contract_date", contract_deal_id=str(deal_id))
        send_message(token, chat_id, "Укажите дату договора в формате ДД.ММ.ГГГГ.")
        return
    if "адрес объекта" in missing:
        update_deal_ui_state(chat_id, pending="contract_address", contract_deal_id=str(deal_id))
        send_message(token, chat_id, "Укажите адрес объекта для договора.")
        return
    if "ФИО подписанта" in missing:
        update_deal_ui_state(chat_id, pending="contract_signatory_name", contract_deal_id=str(deal_id))
        send_message(token, chat_id, "Укажите ФИО подписанта со стороны заказчика полностью.")
        return
    if "должность подписанта" in missing:
        update_deal_ui_state(chat_id, pending="contract_signatory_position", contract_deal_id=str(deal_id))
        send_message(token, chat_id, "Укажите должность подписанта, например: Генеральный директор.")
        return
    if "основание полномочий подписанта" in missing:
        update_deal_ui_state(chat_id, pending="contract_signatory_authority", contract_deal_id=str(deal_id))
        keyboard = {"keyboard": [[{"text": "Устав"}, {"text": "Доверенность"}], [{"text": "❌ Отмена"}]], "resize_keyboard": True, "one_time_keyboard": True}
        send_message(token, chat_id, "На основании чего действует подписант?", keyboard)
        return
    if missing:
        send_message(token, chat_id, "Договор пока нельзя сформировать:\n- " + "\n- ".join(missing), CONTRACT_KEYBOARD)
        return
    keyboard = {"keyboard": [[{"text": "✅ Сформировать договор"}, {"text": "❌ Отмена"}]], "resize_keyboard": True, "one_time_keyboard": True}
    update_deal_ui_state(chat_id,pending='contract_generate_confirm',contract_deal_id=str(deal_id),contract_data_fingerprint=preview.get('fingerprint'))
    send_message(token, chat_id, format_contract_preview(preview) + "\n\nПроверьте данные перед формированием.", keyboard)


OPERATION_TITLES = {'run_create_megaplan_deal':'Создание сделки','run_payer_card_apply':'Привязка плательщика',
    'run_supplier_invoice_apply':'Учёт счёта поставщика','run_sync_deal_kp':'Обновление позиций сделки',
    'run_contract_invoice':'Клиентский счёт','run_installation_workflow':'Монтаж',
    'run_installer_settlements':'Взаиморасчёты с монтажником','run_megaplan_finance':'Финансовая операция',
    'run_procurement_workflow':'Закупка','run_bank_statement':'Разнесение выписки',
    'run_deal_browser':'Изменение сделки','run_apply_work_statement':'Монтажная ведомость'}
INVOICE_RECONCILE_LABEL = '🔍 Сверить с Мегапланом'
INVOICE_RECONCILE_KEYBOARD = {'keyboard': [[{'text': INVOICE_RECONCILE_LABEL}]],
                              'resize_keyboard': True, 'one_time_keyboard': True,
                              '_status_action': True}


def _readback_payer_link(store, operation):
    """An interrupted payer link is idempotent and readable: settle it by read-back."""
    spec = ((operation.get('payload') or {}).get('args') or [{}])[0] or {}
    if not spec.get('payer_id') or not spec.get('deal_id'):
        return None
    check = run_payer_card_apply({'action': 'list_deal_payers', 'deal_id': str(spec['deal_id'])})
    if not check.get('ok'):
        return None
    selected = next((p for p in check.get('payers') or [] if p.get('selected')), None)
    applied = str((selected or {}).get('id')) == str(spec['payer_id'])
    store.reconcile(operation['id'], operation['revision'], 'bridge-readback',
                    'succeeded' if applied else 'failed',
                    f"обратное чтение плательщиков сделки №{spec['deal_id']} после перезапуска",
                    {'ok': True, 'readback': selected} if applied else None)
    return applied, spec, selected


def _normalized_invoice_lines(values):
    return sorted(' '.join(str(value or '').casefold().replace('ё', 'е').split()) for value in values)


def _invoice_time(value):
    value = str(value or '').strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _readback_interrupted_invoice(store, operation):
    """Read invoices only; never replay an interrupted create request."""
    scenario = str(operation.get('scenario') or '')
    if scenario not in ('run_contract_invoice:create', 'run_contract_invoice:create_full'):
        return None
    spec = ((operation.get('payload') or {}).get('args') or [{}])[0] or {}
    deal_id = str(spec.get('deal_id') or '')
    expected_total = spec.get('reconcile_total')
    expected_lines = spec.get('reconcile_lines') or []
    confirmed_at = _invoice_time(spec.get('reconcile_confirmed_at') or operation.get('created_at'))
    if not deal_id or expected_total is None or not expected_lines or confirmed_at is None:
        return {'outcome': 'unavailable', 'deal_id': deal_id,
                'error': 'в сохранённой операции недостаточно данных для безопасной сверки'}
    check = run_contract_invoice({'action': 'list', 'deal_id': deal_id})
    if not check.get('ok'):
        return {'outcome': 'unavailable', 'deal_id': deal_id,
                'error': str(check.get('error') or 'Мегаплан не ответил')}
    try:
        wanted_total = Decimal(str(expected_total)).quantize(Decimal('0.01'))
    except InvalidOperation:
        return {'outcome': 'unavailable', 'deal_id': deal_id, 'error': 'сумма операции повреждена'}
    wanted_lines = _normalized_invoice_lines(expected_lines)
    candidates = []
    for invoice in check.get('invoices') or []:
        created_at = _invoice_time(invoice.get('created_at'))
        try:
            amount = Decimal(str(invoice.get('sum'))).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError):
            continue
        lines = invoice.get('lines') or ([invoice.get('line')] if invoice.get('line') else [])
        if created_at and created_at >= confirmed_at and amount == wanted_total and _normalized_invoice_lines(lines) == wanted_lines:
            candidates.append(invoice)
    evidence = (f"обратное чтение счетов сделки №{deal_id}: время не ранее {confirmed_at.isoformat()}, "
                f"сумма {wanted_total}, строки совпадают")
    if len(candidates) == 1:
        invoice = candidates[0]
        receipt = {'ok': True, 'deal_id': deal_id, 'invoice_id': str(invoice['id']),
                   'invoice_number': invoice.get('number'), 'readback': invoice}
        store.reconcile(operation['id'], operation['revision'], 'bridge-readback', 'succeeded', evidence, receipt)
        return {'outcome': 'found', 'deal_id': deal_id, 'invoice': invoice}
    if not candidates:
        store.reconcile(operation['id'], operation['revision'], 'bridge-readback', 'failed', evidence)
        return {'outcome': 'absent', 'deal_id': deal_id}
    return {'outcome': 'ambiguous', 'deal_id': deal_id, 'candidates': candidates}


def _send_invoice_reconciliation(token, actor, result):
    if result['outcome'] == 'found':
        invoice = result['invoice']
        send_message(token, actor,
                     f"♻️ Проверил Мегаплан: счёт №{invoice.get('number') or invoice['id']} по сделке "
                     f"№{result['deal_id']} найден в единственном экземпляре. Операция закрыта как выполненная; повторять её не нужно.")
        send_megaplan_invoice_by_id(token, actor, invoice['id'], DEAL_ACTIONS_KEYBOARD, result['deal_id'])
    elif result['outcome'] == 'absent':
        send_message(token, actor,
                     f"♻️ Проверил Мегаплан: подходящего счёта по сделке №{result['deal_id']} нет. "
                     "Прерванная операция закрыта как «записи нет». Чтобы выставить счёт, подготовьте новый предпросмотр и подтвердите его.",
                     DEAL_ACTIONS_KEYBOARD)
    elif result['outcome'] == 'ambiguous':
        rows = '\n'.join(f"• №{item.get('number') or item['id']} — {bank_money(item.get('sum'))} ₽"
                         for item in result['candidates'])
        send_message(token, actor,
                     f"⚠️ По сделке №{result['deal_id']} найдено несколько подходящих счетов:\n{rows}\n\n"
                     "Операция не закрыта: выберите правильный счёт после проверки в Мегаплане.",
                     INVOICE_RECONCILE_KEYBOARD)
    else:
        send_message(token, actor,
                     f"⚠️ Сверка счёта по сделке №{result.get('deal_id') or '?'} не завершена: {result.get('error')}. "
                     "Запись не повторялась; операция остаётся заблокированной.", INVOICE_RECONCILE_KEYBOARD)


def report_interrupted_operations(token, operation_ids):
    """After a restart every interrupted write is announced with its next step.

    Nothing is replayed.  A payer link is settled by read-back; any other write
    stays blocked until its result is checked, and the person is told so.
    """
    store = WorkflowStore(WORKFLOW_DB_FILE)
    for operation_id in operation_ids or []:
        try:
            operation = store.get(operation_id)
            scenario = str(operation.get('scenario') or '')
            target = operation.get('target') or {}
            deal = f" по сделке №{target['deal_id']}" if target.get('deal_id') else ''
            title = OPERATION_TITLES.get(scenario.split(':', 1)[0], 'Операция')
            invoice_readback = _readback_interrupted_invoice(store, operation)
            settled = _readback_payer_link(store, operation) if scenario.startswith('run_payer_card_apply') else None
            if invoice_readback is not None:
                _send_invoice_reconciliation(token, str(operation.get('actor') or MANAGER_CHAT_ID), invoice_readback)
                continue
            elif settled:
                applied, spec, selected = settled
                text = (f"♻️ Бот перезапускался во время смены плательщика{deal}. Проверил Мегаплан: "
                        + (f"плательщик «{(selected or {}).get('name')}» записан. Повторять не нужно."
                           if applied else "запись не прошла, данные не изменены. Повторите смену плательщика."))
            else:
                text = (f"⚠️ Бот перезапускался во время записи «{title}»{deal}. Результат неизвестен, "
                        f"поэтому повтор этой записи заблокирован — так её не сделать дважды. Проверьте в "
                        f"Мегаплане, появилась ли запись, и передайте разработчику код {operation_id} для сверки. "
                        "Остальная работа с ботом доступна.")
            send_message(token, str(operation.get('actor') or MANAGER_CHAT_ID), text)
        except Exception as exc:
            print(f"{LOG_PREFIX} interrupted operation report failed: {type(exc).__name__}: {exc}", file=sys.stderr)


def handle_status_query(token,chat_id,text):
    value=str(text or '').strip().casefold().rstrip('?! .')
    reconcile_requested = value == INVOICE_RECONCILE_LABEL.casefold()
    if value not in ('/status','статус обработки','что сейчас делает бот') and not reconcile_requested:
        return False
    try:
        operations=WorkflowStore(WORKFLOW_DB_FILE).unresolved(str(chat_id))
        if reconcile_requested:
            invoice_operations = [operation for operation in operations
                                  if str(operation.get('scenario') or '') in
                                  ('run_contract_invoice:create', 'run_contract_invoice:create_full')]
            if not invoice_operations:
                send_message(token, chat_id, 'Нет прерванных клиентских счетов, ожидающих сверки.', MAIN_KEYBOARD)
                return True
            store = WorkflowStore(WORKFLOW_DB_FILE)
            for operation in invoice_operations:
                _send_invoice_reconciliation(token, chat_id, _readback_interrupted_invoice(store, operation))
            return True
        job=latest_processing_document_job(chat_id)
        retry=latest_retryable_document_job(chat_id)
        interrupted=WorkflowStore(WORKFLOW_DB_FILE).interrupted_inputs(str(chat_id))
    except Exception as exc:
        print(f'{LOG_PREFIX} status read failed: {type(exc).__name__}',file=sys.stderr)
        send_message(token,chat_id,'Не удалось прочитать журнал задач. Не считайте это подтверждением, что обработка завершена; повторную финансовую запись пока не запускайте.')
        return True
    titles=OPERATION_TITLES
    lines=['Текущий статус зарегистрированных задач:']
    for operation in operations[-10:]:
        status='выполняется' if operation['status']=='running' else 'нужна сверка результата; повтор записи заблокирован'
        target=operation.get('target') or {}
        deal=(' · сделка №'+str(target['deal_id'])) if target.get('deal_id') else ''
        title=titles.get(str(operation['scenario']).split(':',1)[0],'Операция')
        lines.append(f"• {title}{deal}: {status}. Код проверки: {operation['id']}")
    if job:
        lines.append('• Разбор счёта поставщика: '+str(job.get('stage') or 'обработка')+'.')
    if retry:
        lines.append('• Есть прерванный разбор счёта. Откройте закупку нужной сделки и повторный разбор сохранённого файла; не применяйте счёт заново вслепую.')
    if interrupted:
        lines.append(f'Прерванных входящих запросов: {len(interrupted)}. Исходные сообщения сохранены, автоматически не повторялись. Откройте нужный раздел и сохранённый черновик; подтверждённую запись сначала сверьте по журналу выше.')
    if not operations and not job and not retry and not interrupted:
        lines.append('В журнале нет выполняющихся записей или незавершённого разбора счёта. Это проверка зарегистрированных задач, не внешних сервисов.')
    invoice_uncertain = any(str(operation.get('scenario') or '') in
                            ('run_contract_invoice:create', 'run_contract_invoice:create_full')
                            and operation.get('status') == 'uncertain' for operation in operations)
    send_message(token,chat_id,'\n'.join(lines), INVOICE_RECONCILE_KEYBOARD if invoice_uncertain else None)
    return True


def handle_global_navigation(token, chat_id, text):
    """Handle top-level navigation before any pending wizard or model queue.

    A stale payer/report/bank state must never reinterpret a menu button as business
    data. These actions are local and should make no CRM/model call.
    """
    value = (text or "").strip()
    if (re.match(r"^№\d+\b", value)
            or re.search(r"(?i)\b(?:перейти|открыть|показать)\w*\b.*\bкарточк\w*\b.*\bсделк\w*\b", value)):
        return handle_deal_ui(token, chat_id, value)
    if value == "🧪 Ошибки тестировщика":
        show_qa_findings(token, chat_id)
        return True
    qa_decision = re.fullmatch(r"(✅ Передать разработчику|🚫 Не передавать) (QA-[A-F0-9]+)", value)
    if qa_decision:
        task = qa_handoff.decide(qa_decision.group(2), qa_decision.group(1).startswith('✅'))
        if not task:
            send_message(token, chat_id, "Эта QA-карточка уже обработана или устарела.", MAIN_KEYBOARD)
        elif task['status'] == 'dismissed':
            send_message(token, chat_id, f"QA-задача {task['id']} отклонена. Разработчику она не передана.", MAIN_KEYBOARD)
        else:
            send_message(token, chat_id, f"QA-задача {task['id']} подтверждена. Передаю разработчику один раз; результат придёт сюда.", MAIN_KEYBOARD)
            run_background_job(lambda: process_qa_developer_task(token, chat_id, task['id']), token, chat_id,
                               operation='QA→разработчик:' + task['id'], allow_stale=True)
        return True
    idea_decision = (re.fullmatch(r"(✅) (\d{1,4})\. .+", value) or re.fullmatch(r"(✖) (\d{1,4})", value)
                     or re.fullmatch(r"(✅ Берём|🚫 Не надо) (IDEA-[0-9A-F]{8})", value))
    if idea_decision:
        mark, ref = idea_decision.groups()
        target = qa_ideas.by_number(ref) if ref.isdigit() else {'id': ref}
        record = qa_ideas.decide(target['id'], mark.startswith('✅')) if target else None
        if not record:
            send_message(token, chat_id, "По этой идее решение уже принято.", MAIN_KEYBOARD)
        elif record['status'] == 'declined':
            send_message(token, chat_id, f"✖ Не берём идею {record.get('num')}: «{record['title']}». Больше не предлагается.")
        else:
            send_message(token, chat_id, f"✅ Берём идею {record.get('num')}: «{record['title']}». Передаю разработчику; "
                         f"код — только в ветке handoff/{record['id']}, в рабочий бот попадёт после проверки "
                         "тестировщиком и вашего выпуска.")
            run_background_job(lambda: process_idea_task(token, chat_id, record['id']), token, chat_id,
                               operation='идея→разработчик:' + record['id'], allow_stale=True)
        # Owner design 26.10: the list shrinks after each decision instead of dying.
        waiting = qa_ideas.pending()
        if waiting:
            text, keyboard = qa_ideas.card(waiting)
            send_message(token, chat_id, text, keyboard)
        elif record:
            send_message(token, chat_id, "Все идеи разобраны.", MAIN_KEYBOARD)
        return True
    if value == "💡 Идеи тестировщика":
        waiting = qa_ideas.pending()
        if waiting:
            text, keyboard = qa_ideas.card(waiting)
            send_message(token, chat_id, text, keyboard)
        else:
            send_message(token, chat_id, "Нерешённых идей нет.\n\n" + qa_ideas.weekly_text(), MORE_KEYBOARD)
        return True
    handoff_decision = re.fullmatch(r"(✅ Выполнить|🚫 Отклонить) (TASK-\d{8}-\d{2})", value)
    if handoff_decision:
        record = handoff_watcher.decide(handoff_decision.group(2), handoff_decision.group(1).startswith('✅'))
        if not record:
            send_message(token, chat_id, "Это задание уже обработано или изменено.", MAIN_KEYBOARD)
        elif record['status'] == 'rejected':
            send_message(token, chat_id, f"{handoff_decision.group(2)} отклонено. Разработчику не передано.", MAIN_KEYBOARD)
        else:
            send_message(token, chat_id, f"{handoff_decision.group(2)} подтверждено. Передаю разработчику один раз.", MAIN_KEYBOARD)
            run_background_job(lambda: process_handoff_task(token, chat_id, handoff_decision.group(2)), token, chat_id,
                               operation='handoff:' + handoff_decision.group(2), allow_stale=True)
        return True
    if value in ("📊 Пульт сделок", "Пульт сделок", "/dashboard"):
        if str(chat_id) != str(MANAGER_CHAT_ID):
            return False
        send_message(token, chat_id, "Пульт сделок — объекты, оплаты, закупки и ближайшие действия. Кнопку можно использовать повторно.", DASHBOARD_INLINE)
        return True
    if value in ("🤝 Сделки", "🤝 Работа со сделками", "/deals"):
        update_deal_ui_state(
            chat_id, pending=None, transitions=None, pending_transition=None,
            bank_transaction_id=None, bank_pending_deal=None, deal_creation_active=False,
        )
        send_message(token, chat_id, "Работа со сделками — выберите действие.", DEALS_KEYBOARD)
        return True
    if value in ("🏦 Деньги", "🏦 Банк и платежи"):
        update_deal_ui_state(chat_id, pending=None, bank_transaction_id=None, bank_pending_deal=None)
        send_message(token, chat_id, "Деньги и платежи — выберите действие.", BANK_MENU_KEYBOARD)
        return True
    if value == "🧰 Монтаж":
        send_message(token, chat_id, "Монтаж — выберите действие.", MANAGER_INSTALLATION_KEYBOARD)
        return True
    if value == "☰ Ещё":
        send_message(token, chat_id, "Дополнительные функции.", MORE_KEYBOARD)
        return True
    if value in ('⬅️ Главное меню','/menu','/start','❌ Отмена'):
        update_deal_ui_state(
            chat_id, pending=None, transitions=None, pending_transition=None,
            bank_transaction_id=None, bank_pending_deal=None, deal_creation_active=False,
        )
        text = (
            "Действие отменено. Сохранённые документы и уже подтверждённые записи не удалены."
            if value == '❌ Отмена' else WELCOME_TEXT if value == '/start' else "Главное меню."
        )
        send_message(token, chat_id, text, MAIN_KEYBOARD)
        return True
    return False


def qa_task_keyboard(task_id):
    return {'keyboard': [[{'text': '✅ Передать разработчику ' + task_id}],
                         [{'text': '🚫 Не передавать ' + task_id}],
                         [{'text': '⬅️ Главное меню'}]],
            'resize_keyboard': True, 'one_time_keyboard': True}


def show_handoff_waiting(token, chat_id):
    """Re-show every tester task that still waits for the owner, one card each
    (26.10: only the oldest was shown, a newer release card stayed hidden behind it)."""
    try:
        waiting = sorted(task_id for task_id, record in handoff_watcher.read_state()['tasks'].items()
                         if record.get('status') == 'awaiting_owner')
        repo = handoff_watcher.repository() if waiting else None
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        print(f"{LOG_PREFIX} handoff card unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False
    shown = 0
    for task_id in waiting:
        try:
            task = handoff_watcher.load_task(task_id, repo)
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            print(f"{LOG_PREFIX} handoff card {task_id} unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if task:
            send_message(token, chat_id, handoff_watcher.owner_card(task), handoff_keyboard(task['id']))
            shown += 1
    return bool(shown)


def show_qa_findings(token, chat_id, only_unnotified=False):
    if not only_unnotified and show_handoff_waiting(token, chat_id):
        return True
    try:
        tasks = qa_handoff.ready(include_notified=not only_unnotified)
    except (ValueError, OSError) as exc:
        print(f"{LOG_PREFIX} QA registry read failed: {type(exc).__name__}: {exc}")
        if only_unnotified:
            return False
        send_message(token, chat_id, 'Не удалось прочитать QA-реестр: ' + type(exc).__name__, MAIN_KEYBOARD)
        return False
    if not tasks:
        if not only_unnotified:
            send_message(token, chat_id, 'Новых QA-проблем, ожидающих вашего решения, нет.', MAIN_KEYBOARD)
        return False
    task = tasks[0]
    delivered = send_message(token, chat_id, qa_handoff.summarize(task), qa_task_keyboard(task['id']))
    if delivered:
        qa_handoff.mark_notified(task['id'], True)
    return delivered


def handle_deal_ui(token, chat_id, text, _background=False):
    """Handle deterministic deal navigation without sending menu commands to the LLM."""
    value = text.strip()
    # A bound deal button is navigation, never free-form input for whichever
    # wizard happened to be left pending. This boundary must precede every
    # pending handler, including the developer-task prompt.
    selected_button = re.match(r"^№(\d+)\b", value)
    if selected_button:
        selected_id = selected_button.group(1)
        if _background:
            select_deal(token, chat_id, selected_id)
        else:
            run_background_job(lambda: handle_deal_ui(token, chat_id, text, _background=True), token, chat_id,
                               operation=f"сделка:открыть:{selected_id}")
        return True
    open_current = re.search(r"(?i)\b(?:перейти|открыть|показать)\w*\b.*\bкарточк\w*\b.*\bсделк\w*\b", value)
    if open_current:
        current_id = current_deal_ui_state(chat_id).get("current_deal_id")
        if not current_id:
            send_message(token, chat_id, "Сначала выберите сделку из списка.", DEALS_KEYBOARD)
        elif _background:
            select_deal(token, chat_id, current_id)
        else:
            run_background_job(lambda: handle_deal_ui(token, chat_id, text, _background=True), token, chat_id,
                               operation=f"сделка:открыть:{current_id}")
        return True
    local_menus = {
        "🔎 Найти сделку": ("Как найти сделку?", DEAL_SEARCH_KEYBOARD),
        "🕘 Последние сделки": ("Сколько последних сделок показать?", DEAL_RECENT_KEYBOARD),
        "📋 Основное": ("Основные действия со сделкой.", DEAL_BASIC_KEYBOARD),
        "📄 Документы сделки": ("Документы сделки.", DEAL_DOCUMENTS_KEYBOARD),
        "📦 Закупка сделки": ("Закупка по сделке.", DEAL_PROCUREMENT_KEYBOARD),
        "🧰 Монтаж сделки": ("Монтаж по сделке.", DEAL_INSTALLATION_KEYBOARD),
        "⬅️ Назад к сделке": ("Действия с текущей сделкой.", DEAL_ACTIONS_KEYBOARD),
    }
    if value in local_menus:
        title, menu = local_menus[value]
        send_message(token, chat_id, title, menu)
        return True
    if value == "⭐ Текущая сделка":
        deal_id = current_deal_ui_state(chat_id).get("current_deal_id")
        if not deal_id:
            send_message(token, chat_id, "Текущая сделка ещё не выбрана.", DEALS_KEYBOARD)
        elif _background:
            select_deal(token, chat_id, deal_id)
        else:
            run_background_job(lambda: handle_deal_ui(token, chat_id, text, _background=True), token, chat_id,
                               operation=f"сделка:открыть:{deal_id}")
        return True
    # Confirmation controls are a hard routing boundary.  Even if an older
    # parser lost/overwrote the draft state, a click must never fall through to
    # the general model (where it can be rate-limited and can corrupt the next
    # draft).  A valid current preview is handled by the transaction below; an
    # invalid/stale one gets an explicit recoverable response.
    if value == '✅ Создать подтверждённую сделку':
        confirmation_state = current_deal_ui_state(chat_id)
        if (confirmation_state.get('pending') != 'deal_create_confirm' or
                not confirmation_state.get('deal_create_spec')):
            send_message(
                token, chat_id,
                'Этот просмотр устарел или черновик не сохранён. '
                'Сделка не создана. Откройте создание сделки заново; '
                'нажатие не будет передано сервису ИИ.',
                MAIN_KEYBOARD,
            )
            return True
    if value == '✅ Заменить позиции подтверждённым КП':
        state = current_deal_ui_state(chat_id)
        if state.get('pending') != 'deal_sync_confirm' or not state.get('deal_sync_spec'):
            send_message(token, chat_id, 'Просмотр устарел. Подготовьте замену позиций заново.', DEAL_ACTIONS_KEYBOARD)
            return True
        if not _background:
            run_background_job(lambda: handle_deal_ui(token, chat_id, text, _background=True), token, chat_id)
            return True
        result = run_sync_deal_kp(state['deal_sync_spec'])
        if result.get('ok'):
            update_deal_ui_state(chat_id, pending=None, deal_sync_spec=None)
            send_message(token, chat_id, f"✅ Сделка №{result['deal_id']} обновлена: {result['positions_count']} позиций, {bank_money(result['total'])} ₽.", DEAL_ACTIONS_KEYBOARD)
        else:
            send_message(token, chat_id, 'Замена не подтверждена: ' + str(result.get('error')), DEAL_ACTIONS_KEYBOARD)
        return True
    if value == '✅ Записать стоимость монтажных работ':
        state=current_deal_ui_state(chat_id)
        prepared=state.get('work_price_preview') or {}
        if state.get('pending') != 'work_price_confirm' or not prepared:
            send_message(token,chat_id,'Подготовьте расчёт заново.',DEAL_ACTIONS_KEYBOARD); return True
        if not _background:
            run_background_job(lambda:handle_deal_ui(token,chat_id,text,_background=True),token,chat_id); return True
        result=run_apply_work_statement(prepared['deal_id'],prepared['markup_pct'],expected_fingerprint=prepared['fingerprint'])
        if result.get('ok'):
            update_deal_ui_state(chat_id,pending=None,work_price_preview=None)
            send_message(token,chat_id,f"Стоимость монтажных работ записана: {bank_money(result['montage_sell_price'])} ₽.",DEAL_ACTIONS_KEYBOARD)
            publish=build_and_store_profitability(prepared['deal_id'])
            if not publish.get('ok'): send_message(token,chat_id,'Стоимость записана, но файл экономики требует повторного формирования кнопкой «Экономика».',DEAL_ACTIONS_KEYBOARD)
        else: send_message(token,chat_id,'Запись не подтверждена: '+str(result.get('error')),DEAL_ACTIONS_KEYBOARD)
        return True
    if value == '✅ Обновить подтверждённый прайс':
        state=current_deal_ui_state(chat_id)
        if state.get('pending') != 'price_catalog_confirm' or not state.get('price_catalog_spec'):
            send_message(token,chat_id,'Подготовьте просмотр прайса заново.',MAIN_KEYBOARD); return True
        if not _background:
            run_background_job(lambda:handle_deal_ui(token,chat_id,text,_background=True),token,chat_id); return True
        result=run_update_kemix_prices(state['price_catalog_spec'])
        if result.get('ok'):
            update_deal_ui_state(chat_id,pending=None,price_catalog_spec=None)
            send_message(token,chat_id,format_price_update_summary(result),MAIN_KEYBOARD)
        else: send_message(token,chat_id,'Обновление не подтверждено: '+str(result.get('error')),MAIN_KEYBOARD)
        return True
    if value == '📥 Монтажные отчёты':
        if not _background:
            run_background_job(lambda:handle_deal_ui(token,chat_id,text,_background=True),token,chat_id); return True
        result=run_installation_workflow({'action':'pending_reports'})
        if not result.get('ok'):
            send_message(token,chat_id,'Не удалось прочитать очередь монтажных отчётов. Это не означает, что отчётов нет.',MAIN_KEYBOARD); return True
        notices=result.get('result') or []
        rows=[[{'text':f'🧰 Проверить монтажный отчёт ID {x["id"]}'}] for x in notices]
        rows.append([{'text':'⬅️ Главное меню'}])
        send_message(token,chat_id,'Отчёты, ожидающие проверки:' if notices else 'Новых монтажных отчётов нет.',{'keyboard':rows})
        return True
    report_match=re.fullmatch(r'🧰 Проверить монтажный отчёт ID (\d+)',value)
    if report_match:
        if not _background:
            run_background_job(lambda:handle_deal_ui(token,chat_id,text,_background=True),token,chat_id)
            return True
        report_id=report_match.group(1)
        available=run_installation_workflow({'action':'pending_reports'})
        if not available.get('ok') or not any(str(x['id'])==report_id for x in available.get('result') or []):
            send_message(token,chat_id,'Этот отчёт уже обработан или недоступен.',MAIN_KEYBOARD); return True
        result=run_installation_workflow({'action':'get_report','report_id':report_id})
        if not result.get('ok'):
            send_message(token,chat_id,'Не удалось прочитать отчёт. Он сохранён в очереди.',MAIN_KEYBOARD); return True
        parsed=result['result']; report=parsed['report']
        if report['status'] in ('approved','partially_approved','returned'):
            WorkflowStore(WORKFLOW_DB_FILE).dismiss_notification(chat_id,'installation_report',report_id)
            send_message(token,chat_id,'Отчёт уже обработан: '+report['status'],MAIN_KEYBOARD); return True
        update_deal_ui_state(chat_id,pending='installation_report_review',installation_report_id=report_id,installation_partial=None)
        lines=[f'• {x.get("name") or "не сопоставлено"}: {x.get("declared_qty")} {x.get("unit") or ""}' for x in parsed.get('items') or []]
        send_message(token,chat_id,f'Отчёт №{report["report_no"]}, сделка №{report["deal_id"]}.\n'+'\n'.join(lines),INSTALLATION_REPORT_REVIEW_KEYBOARD)
        return True
    # Deterministic route, before old draft states or the general model dialogue.
    proposal_request = re.search(r'(?i)(?:(?:сдела[йт]|сформир|подготов|собер|получ|скача).*(?:\bкп\b|коммерческое предложение).*\bсделк|^кп\s+(?:по|из)\s+сделк)', value)
    if value == '📄 КП по сделке' or re.fullmatch(r'📄 КП для сделки №\d+', value) or proposal_request:
        selected = current_deal_ui_state(chat_id).get('current_deal_id')
        explicit_id = re.search(r'(?i)сделк\w*\s*№?\s*(\d+)', value)
        target = explicit_id.group(1) if explicit_id else selected
        if not target:
            send_message(token, chat_id, 'Сначала выберите сделку или укажите её номер.', DEALS_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending='proposal_recipient', proposal_deal_id=str(target))
        send_message(token, chat_id, f'Кому адресовать КП по сделке №{target}?\nУкажите имя/ФИО или готовое обращение, например: «Уважаемая Татьяна,». Клиента самой сделки это не меняет.', PAYER_UPLOAD_KEYBOARD)
        return True
    proposal_state = current_deal_ui_state(chat_id)
    if proposal_state.get('pending') == 'proposal_recipient':
        navigation = {b['text'] for row in DEAL_ACTIONS_KEYBOARD['keyboard'] for b in row}
        navigation |= {'❌ Отмена', '⬅️ Главное меню', '🤝 Работа со сделками', '➕ Создать сделку'}
        if value not in navigation and not value.startswith('/'):
            recipient = ' '.join(value.split())
            target = proposal_state.get('proposal_deal_id')
            if not target or not recipient or len(recipient) > 200:
                send_message(token, chat_id, 'Введите имя/ФИО или обращение длиной до 200 символов.', PAYER_UPLOAD_KEYBOARD)
                return True
            update_deal_ui_state(chat_id, pending=None, proposal_deal_id=None)
            send_message(token, chat_id, f'📄 Формирую КП №{target}. Адресат: {recipient}.', DEAL_ACTIONS_KEYBOARD)
            if _background:
                send_deal_proposal(token, chat_id, target, recipient=recipient)
            else:
                run_background_job(lambda: send_deal_proposal(token, chat_id, target, recipient=recipient), token, chat_id,
                                   operation=f'КП по сделке:{target}')
            return True
        update_deal_ui_state(chat_id, pending=None, proposal_deal_id=None)
    if value == '➕ Создать сделку':
        update_deal_ui_state(chat_id, pending='deal_create_title', deal_creation_active=True,
                             deal_create_spec={}, deal_creation_items=None,
                             deal_creation_economics_path=None, current_deal_id=None,
                             deal_creation_request=None, deal_creation_source_path=None,
                             contract_deal_id=None)
        send_message(token, chat_id, 'Как назвать новую сделку?', PAYER_UPLOAD_KEYBOARD)
        return True
    creation = current_deal_ui_state(chat_id)
    creation_pending = creation.get('pending')
    if creation_pending in ('deal_create_title', 'deal_create_client') and value not in ('❌ Отмена', '⬅️ Главное меню'):
        draft = dict(creation.get('deal_create_spec') or {})
        if creation_pending == 'deal_create_title':
            draft['description'] = value
            update_deal_ui_state(chat_id, deal_create_spec=draft, pending='deal_create_client')
            organization = deal_title_organization(value)
            if organization:
                # Idea И-11: «Монтаж для ООО Альфа Климат» already names the client.
                send_message(token, chat_id, f'В названии указан клиент «{organization}» — ищу его карточку. '
                             'Если клиент другой, нажмите «🔍 Другой клиент».')
                return handle_deal_ui(token, chat_id, organization, _background=_background)
            send_message(token, chat_id, 'Укажите клиента: название организации или ФИО. Перед созданием бот проверит существующие карточки.', PAYER_UPLOAD_KEYBOARD)
        else:
            if not _background:
                send_message(token, chat_id, '🔎 Ищу существующие карточки клиента. Создание нового клиента пока не выполняется.')
                run_background_job(lambda: handle_deal_ui(token, chat_id, text, _background=True), token, chat_id)
                return True
            found = search_creation_clients(value)
            if not found.get('ok'):
                send_message(token, chat_id, 'Поиск клиента не выполнен. Новая карточка не создавалась. Повторите название позже.', PAYER_UPLOAD_KEYBOARD)
                return True
            draft['client_name'] = value
            clients = found.get('clients') or []
            update_deal_ui_state(chat_id, deal_create_spec=draft, pending='deal_create_client_select', deal_create_clients=clients)
            rows = [[{'text': f'Клиент ID {x["id"]} — {x["name"]}'}] for x in clients]
            if not clients:
                rows = [[{'text': 'Новый клиент — организация'}], [{'text': 'Новый клиент — физическое лицо'}]]
            rows.append([{'text': '🔍 Другой клиент'}, {'text': '❌ Отмена'}])
            send_message(token, chat_id, 'Выберите существующую карточку клиента:' if clients else
                         'Совпадений не найдено. Искать по другому названию или создать нового клиента?', {'keyboard': rows})
        return True
    if creation_pending == 'deal_create_client_select' and value not in ('❌ Отмена', '⬅️ Главное меню'):
        draft = dict(creation.get('deal_create_spec') or {})
        if value == '🔍 Другой клиент':
            update_deal_ui_state(chat_id, pending='deal_create_client')
            send_message(token, chat_id, 'Укажите другое название или ФИО.', PAYER_UPLOAD_KEYBOARD)
            return True
        selected = next((x for x in creation.get('deal_create_clients') or []
                         if value == f'Клиент ID {x["id"]} — {x["name"]}'), None)
        if selected:
            draft.update(client_id=selected['id'], client_name=selected['name'], client_kind=selected['kind'], allow_new_client=False)
        elif not creation.get('deal_create_clients') and value in ('Новый клиент — организация', 'Новый клиент — физическое лицо'):
            draft.update(client_id=None, client_kind='company' if value.endswith('организация') else 'human', allow_new_client=True)
        else:
            send_message(token, chat_id, 'Выберите карточку из показанного списка.'); return True
        update_deal_ui_state(chat_id, deal_create_spec=draft, pending='deal_create_items', deal_create_clients=None)
        if draft.get('items') and draft.get('tax_mode') in ('none', '22', '5'):
            prepare_deal_creation_review(token, chat_id, draft)
        elif draft.get('items'):
            update_deal_ui_state(chat_id, pending='deal_create_tax')
            send_message(token, chat_id, 'Клиент и позиции сохранены. Выберите режим НДС.', TAX_KEYBOARD)
        else:
            send_message(token, chat_id, 'Клиент сохранён. Пришлите спецификацию с количеством и ценами в Excel, Word, PDF или текстом.', PAYER_UPLOAD_KEYBOARD)
        return True
    if creation_pending == 'deal_create_confirm' and value == '✏️ Заменить спецификацию':
        draft = dict(creation.get('deal_create_spec') or {}); draft.pop('items', None)
        update_deal_ui_state(chat_id, pending='deal_create_items', deal_create_spec=draft, deal_creation_items=None)
        send_message(token, chat_id, 'Пришлите исправленную спецификацию. Сделка ещё не создана.', PAYER_UPLOAD_KEYBOARD)
        return True
    # Telegram replies/voice input occasionally arrive without the button emoji.
    # Keep procurement actions deterministic in either form; they must never be
    # interpreted as a new free-form question by the model.
    plain_supplier_actions = {
        "учти в прочую себестоимость сделки": "🧾 В прочую себестоимость сделки",
        "учесть в прочую себестоимость сделки": "🧾 В прочую себестоимость сделки",
        "сопоставить с позицией сделки": "🔗 Сопоставить с позицией сделки",
        "применить счёт поставщика": "✅ Применить счёт поставщика",
        "применить счет поставщика": "✅ Применить счёт поставщика",
    }
    value = plain_supplier_actions.get(value.casefold(), value)
    if value == "🔄 Повторить последний счёт":
        job = latest_retryable_document_job(chat_id)
        if not job:
            active = latest_processing_document_job(chat_id)
            if active:
                send_message(token, chat_id,
                             f"⏳ «{active.get('original_name') or 'Счёт'}» уже разбирается "
                             f"({active.get('stage') or 'обработка'}). Повторный запуск не нужен.",
                             PROCUREMENT_KEYBOARD)
            else:
                send_message(token, chat_id, "Нет счёта, ожидающего повторной обработки.", PROCUREMENT_KEYBOARD)
            return True
        send_message(token, chat_id, f"🔄 Повторно разбираю «{job.get('original_name') or 'счёт'}» для сделки №{job.get('deal_id')}…")
        run_background_job(lambda: retry_supplier_invoice_document(token, chat_id, job), token, chat_id)
        return True
    state = current_deal_ui_state(chat_id)
    deal_id = state.get("current_deal_id")
    installer = state.get("installer_report") or {}
    pending_now = state.get("pending") or ""
    supplier_control_values = {
        "🔗 Сопоставить с позицией сделки", "🧾 В прочую себестоимость сделки",
        "✅ Подтвердить всё распределение", "✅ Только в текущую сделку",
        "📦 Весь остаток в нераспределённые", "✏️ Изменить распределение",
        "🔍 Показать другие сделки", "🚫 Не учитывать остаток",
        "✅ Применить счёт поставщика", "✅ Подтвердить прочую себестоимость",
    }
    # Procurement buttons are a hard local protocol.  They must never fall through
    # to the conversational model even if another worker changed `pending` between
    # rendering the keyboard and receiving the click.
    if value in supplier_control_values and not pending_now.startswith("supplier_"):
        queue = state.get("supplier_invoice_queue") or []
        if queue:
            pending_now = "supplier_invoice_confirm"
            state["pending"] = pending_now
            update_deal_ui_state(chat_id, pending=pending_now,
                                 supplier_invoice_preview=queue[0])
        else:
            send_message(token, chat_id,
                         "Черновик счёта не найден. Откройте закупку нужной сделки и загрузите счёт заново.",
                         PROCUREMENT_KEYBOARD)
            return True
    if pending_now.startswith("contract_") and state.get("contract_deal_id"):
        deal_id = state.get("contract_deal_id")

    installation_values = {
        "✅ Утвердить монтажную ведомость", "📋 Скачать монтажную ведомость", "📤 Загрузить исправленную ведомость",
        "👤 Указать контакт объекта", "👤 Выбрать контакт по монтажу", "👤 Контакт по монтажу",
        "➕ Создать контакт по монтажу", "📐 Приложить проект", "📎 Привязать проект", "🚫 Работать БЕЗ ПРОЕКТА",
        "✅ Привязать выбранные файлы", "📤 Загрузить новый файл",
        "✅ Передать объект монтажнику", "✅ Принять монтажный отчёт", "↩️ Вернуть монтажнику",
        "✏️ Скорректировать объёмы", "💵 Выплата монтажнику", "✅ Записать выплату из кассы",
    }
    if (value in installation_values or pending_now.startswith(("installation_","installer_report","installer_excel_report"))) and not _background:
        run_background_job(lambda: handle_deal_ui(token, chat_id, text, _background=True), token, chat_id,
                           operation=f"монтаж:{value[:60]}")
        return True
    if pending_now==legacy_report_ui.PENDING_CONFIRM and value==legacy_report_ui.EDIT:
        rows=legacy_report_ui.edit_rows(state.get('installer_bundle_preview') or {})
        update_deal_ui_state(chat_id,pending=legacy_report_ui.PENDING_EDIT)
        send_message(token,chat_id,'Какую строку изменить? Отправьте её номер. Остальные решения сохраняются.\n'+'\n'.join(f"{i}. №{r['deal_id']} — {r['name']}: {r['amount']} ₽" for i,r in enumerate(rows,1)))
        return True
    if pending_now==legacy_report_ui.PENDING_EDIT:
        preview=copy.deepcopy(state.get('installer_bundle_preview') or {});rows=legacy_report_ui.edit_rows(preview)
        if not value.isdigit() or not 1<=int(value)<=len(rows):
            send_message(token,chat_id,'Введите номер строки из списка.');return True
        row=rows[int(value)-1];preview['review']=[row]
        update_deal_ui_state(chat_id,pending=legacy_report_ui.PENDING_MAP,installer_bundle_preview=preview)
        works=(preview.get('candidates_by_deal') or {}).get(row['deal_id']) or []
        send_message(token,chat_id,f"{row['name']} — {row['amount']} ₽, сделка №{row['deal_id']}.\nВыберите отдельную затрату либо введите ID работы; количество.\n"+'\n'.join(f"ID {w['id']} — {w['name']} ({w.get('unit')})" for w in works if w.get('active',True)),{'keyboard':[[{'text':legacy_report_ui.EXTRA}],[{'text':'❌ Отмена'}]],'resize_keyboard':True})
        return True
    if pending_now==legacy_report_ui.PENDING_COST:
        try:
            updated=legacy_report_ui.apply_material_decision(installer,state.get('installer_bundle_preview') or {},value)
        except (ValueError,KeyError,IndexError) as exc:
            send_message(token,chat_id,str(exc));return True
        legacy_report_ui.stage(sys.modules[__name__],token,chat_id,updated)
        return True
    if pending_now==legacy_report_ui.PENDING_MAP:
        try:
            updated=legacy_report_ui.apply_mapping(installer,state.get('installer_bundle_preview') or {},value)
        except (ValueError,KeyError,IndexError) as exc:
            send_message(token,chat_id,str(exc)); return True
        legacy_report_ui.stage(sys.modules[__name__],token,chat_id,updated)
        return True
    installation_deal_id = str(state.get("installation_deal_id") or deal_id or "")
    if value in ("👤 Выбрать контакт по монтажу","👤 Контакт по монтажу") and installation_deal_id:
        result=run_installation_workflow({"action":"contact_candidates","deal_id":installation_deal_id})
        if not result.get('ok'):
            send_message(token,chat_id,"Не удалось получить контакты клиента: "+str(result.get('error')),DEAL_ACTIONS_KEYBOARD); return True
        choices={}
        for item in result.get('result') or []:
            label=f"{item.get('name') or 'Без имени'} · {item.get('phone') or 'нет телефона'}"[:55]
            choices[label]=str(item['id'])
        back='draft' if value=="👤 Выбрать контакт по монтажу" else 'deal'
        update_deal_ui_state(chat_id,pending='installation_contact_select',installation_deal_id=installation_deal_id,
                             installation_contact_choices=choices,installation_contact_return=back)
        send_message(token,chat_id,"Выберите ответственного за монтаж. Даже единственный контакт нужно подтвердить.",installation_contact_keyboard(choices)); return True
    if pending_now=='installation_contact_select':
        choices=state.get('installation_contact_choices') or {}
        if value in choices:
            result=run_installation_workflow({"action":"select_contact","deal_id":installation_deal_id,
                                              "contact_ref":choices[value],"actor":str(chat_id)})
            if not result.get('ok'):
                send_message(token,chat_id,"Контакт не выбран: "+str(result.get('error')),installation_contact_keyboard(choices)); return True
            item=result['result']; back=state.get('installation_contact_return') or 'deal'
            update_deal_ui_state(chat_id,pending='installation_draft_review' if back=='draft' else None,
                                 installation_contact_choices=None,installation_contact_return=None)
            send_message(token,chat_id,f"✅ Контакт по монтажу: {item.get('contact_name')}, {item.get('contact_phone')}",INSTALLATION_DRAFT_KEYBOARD if back=='draft' else DEAL_ACTIONS_KEYBOARD)
            if item.get('status') in ('transferred','in_progress','review') and INSTALLER_NOTIFY_CHAT_ID:
                notify_installers(token,f"👤 По сделке №{installation_deal_id} изменён контакт на объекте:\n{item.get('contact_name')}, {item.get('contact_phone')}")
            return True
        if value=='➕ Создать контакт по монтажу':
            update_deal_ui_state(chat_id,pending='installation_contact_create_name')
            send_message(token,chat_id,"Укажите ФИО нового контактного лица."); return True
    if pending_now=='installation_contact_create_name':
        if len(value.split()) < 2:
            # Validate at the step where the value is entered.  Previously a
            # one-word name was accepted here and rejected only after the phone
            # had been entered; the wizard then stayed on the phone step and
            # interpreted every corrected full name as another phone number.
            update_deal_ui_state(chat_id,pending='installation_contact_create_name',
                                 installation_contact_new_name=None)
            send_message(token,chat_id,
                         "Укажите как минимум фамилию и имя, например: Иванов Иван.")
            return True
        update_deal_ui_state(chat_id,pending='installation_contact_create_phone',installation_contact_new_name=value)
        send_message(token,chat_id,"Укажите телефон нового контактного лица."); return True
    if pending_now=='installation_contact_create_phone':
        name=state.get('installation_contact_new_name') or ''
        if len(name.split()) < 2:
            # Recover old sessions that entered this broken state before the
            # validation above was added.
            update_deal_ui_state(chat_id,pending='installation_contact_create_name',
                                 installation_contact_new_name=None)
            send_message(token,chat_id,
                         "ФИО не было сохранено. Укажите фамилию и имя ещё раз.")
            return True
        if len(re.sub(r'\D','',value)) < 7:
            send_message(token,chat_id,
                         "Телефон не распознан. Пришлите номер минимум из 7 цифр, например: +7 999 123-45-67.")
            return True
        result=run_installation_workflow({"action":"create_contact","deal_id":installation_deal_id,
            "name":name,"phone":value,"actor":str(chat_id)})
        if not result.get('ok'):
            error=str(result.get('error') or 'неизвестная ошибка')
            if 'фамилию и имя' in error.casefold():
                update_deal_ui_state(chat_id,pending='installation_contact_create_name',
                                     installation_contact_new_name=None)
                send_message(token,chat_id,"Контакт не создан: "+error+". Введите ФИО заново.")
            else:
                send_message(token,chat_id,"Контакт не создан: "+error+". Исправьте телефон или нажмите «❌ Отмена».")
            return True
        item=result['result']; back=state.get('installation_contact_return') or 'deal'
        update_deal_ui_state(chat_id,pending='installation_draft_review' if back=='draft' else None,
                             installation_contact_new_name=None,installation_contact_choices=None,installation_contact_return=None)
        send_message(token,chat_id,f"✅ Новый контакт создан в Мегаплане и назначен для монтажа: {item.get('contact_name')}, {item.get('contact_phone')}",INSTALLATION_DRAFT_KEYBOARD if back=='draft' else DEAL_ACTIONS_KEYBOARD)
        if item.get('status') in ('transferred','in_progress','review') and INSTALLER_NOTIFY_CHAT_ID:
            notify_installers(token,f"👤 По сделке №{installation_deal_id} изменён контакт на объекте:\n{item.get('contact_name')}, {item.get('contact_phone')}")
        return True
    if value in ("📐 Приложить проект","📎 Привязать проект") and installation_deal_id:
        result=run_installation_workflow({"action":"project_candidates","deal_id":installation_deal_id})
        if not result.get("ok"):
            send_message(token,chat_id,"Не удалось получить файлы сделки: "+str(result.get("error")),DEAL_ACTIONS_KEYBOARD); return True
        choices={}
        for item in (result.get("result") or [])[:15]:
            label=(item.get("name") or "Файл")[:28]
            if label in choices: label=f"{label[:20]} · {item.get('id')}"
            choices[label]=str(item.get("id"))
        update_deal_ui_state(chat_id,pending="installation_project_select",installation_deal_id=installation_deal_id,
                             installation_project_choices=choices,installation_project_selected=[],
                             installation_project_return="draft" if value=="📎 Привязать проект" else "deal")
        message="Выберите один или несколько файлов проекта, уже загруженных в Мегаплан, либо загрузите новый файл."
        if not choices: message="В сделке пока нет файлов. Загрузите проект через бот."
        send_message(token,chat_id,message,project_selection_keyboard(choices)); return True
    if pending_now=="installation_project_select":
        choices=state.get("installation_project_choices") or {}; selected={str(x) for x in state.get("installation_project_selected") or []}
        raw=value[2:] if value.startswith(("☐ ","✅ ")) else value
        if raw in choices:
            fid=str(choices[raw]); selected.remove(fid) if fid in selected else selected.add(fid)
            update_deal_ui_state(chat_id,installation_project_selected=sorted(selected))
            send_message(token,chat_id,f"Выбрано файлов: {len(selected)}.",project_selection_keyboard(choices,selected)); return True
        if value=="📤 Загрузить новый файл":
            update_deal_ui_state(chat_id,pending="installation_project_upload")
            send_message(token,chat_id,"Пришлите файл проекта. Он будет сохранён как новая версия."); return True
        if value=="✅ Привязать выбранные файлы":
            if not selected:
                send_message(token,chat_id,"Сначала отметьте хотя бы один файл.",project_selection_keyboard(choices,selected)); return True
            result=run_installation_workflow({"action":"attach_project","deal_id":installation_deal_id,
                                              "file_ids":sorted(selected),"actor":str(chat_id)})
            if not result.get("ok"):
                send_message(token,chat_id,"Проект не привязан: "+str(result.get("error")),project_selection_keyboard(choices,selected)); return True
            project=result["result"]; back=state.get("installation_project_return") or "deal"
            update_deal_ui_state(chat_id,pending="installation_draft_review" if back=="draft" else None,
                                 installation_project_choices=None,installation_project_selected=None,installation_project_return=None)
            send_message(token,chat_id,f"✅ Проект версии №{project['version']} привязан. Файлов: {len(project['files'])}.",INSTALLATION_DRAFT_KEYBOARD if back=="draft" else DEAL_ACTIONS_KEYBOARD)
            if project.get("installation_status") in ("transferred","in_progress","review") and INSTALLER_NOTIFY_CHAT_ID:
                notify_installers(token,f"📐 По сделке №{installation_deal_id} опубликована новая версия проекта №{project['version']}.")
            return True
    if value=="🚫 Работать БЕЗ ПРОЕКТА" and installation_deal_id:
        result=run_installation_workflow({"action":"without_project","deal_id":installation_deal_id,"actor":str(chat_id)})
        if result.get("ok"):
            send_message(token,chat_id,"✅ Зафиксировано решение руководителя: работать без проекта.",INSTALLATION_DRAFT_KEYBOARD)
        else: send_message(token,chat_id,"Решение не сохранено: "+str(result.get("error")),INSTALLATION_DRAFT_KEYBOARD)
        return True
    if value == "📋 Скачать монтажную ведомость" and installation_deal_id:
        result = run_installation_workflow({"action": "get", "deal_id": installation_deal_id})
        item = result.get("result") or {}
        workbook_path = item.get("workbook_path")
        if not result.get("ok") or not workbook_path or not os.path.isfile(workbook_path):
            send_message(token, chat_id, "Не удалось получить монтажную ведомость. Попробуйте открыть сделку заново.", INSTALLATION_DRAFT_KEYBOARD)
            return True
        send_document(token, chat_id, workbook_path, "Актуальный черновик монтажной ведомости",
                      f"Монтажная ведомость - сделка {installation_deal_id}.xlsx")
        send_message(token, chat_id,
                     "Внесите изменения в этот Excel и верните его кнопкой «📤 Загрузить исправленную ведомость».",
                     INSTALLATION_DRAFT_KEYBOARD)
        return True
    if value == "📤 Загрузить исправленную ведомость" and installation_deal_id:
        update_deal_ui_state(chat_id, pending="installation_workbook_file", installation_deal_id=installation_deal_id)
        send_message(token, chat_id, "Пришлите исправленный Excel. Бот проверит структуру и покажет изменения перед утверждением.")
        return True
    if value in ("👤 Указать контакт объекта", "✍️ Ввести контакт вручную") and installation_deal_id:
        update_deal_ui_state(chat_id, pending="installation_contact_name",
                             installation_deal_id=installation_deal_id)
        send_message(token, chat_id, "Введите имя контактного лица на объекте.")
        return True
    if pending_now == "installation_contact_name":
        update_deal_ui_state(chat_id, pending="installation_contact_phone", installation_contact_name=value)
        send_message(token, chat_id, "Укажите телефон контактного лица.")
        return True
    if pending_now == "installation_contact_phone":
        name=state.get("installation_contact_name") or ""
        result=run_installation_workflow({"action":"update_details","deal_id":installation_deal_id,
                                          "contact_name":name,"contact_phone":value,"actor":str(chat_id)})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось сохранить контакт: {result.get('error')}", INSTALLATION_DRAFT_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="installation_draft_review", installation_contact_name=None)
        send_message(token, chat_id, "✅ Контакт объекта сохранён.\n\n"+installation_summary(result["result"]), INSTALLATION_DRAFT_KEYBOARD)
        return True
    if value == "✅ Утвердить монтажную ведомость" and installation_deal_id:
        # Validate locally before creating a durable write operation. A missing
        # contact is an ordinary incomplete form, not an uncertain external write.
        preview=run_installation_workflow({"action":"get","deal_id":installation_deal_id})
        current=preview.get("result") or {}
        missing=[]
        if current.get("project_required") is None: missing.append("решение по проекту")
        if missing:
            send_message(token, chat_id,
                         "Ведомость пока нельзя утвердить: не заполнено: "+", ".join(missing)+".\n\n"
                         "Контакт объекта для передачи в монтаж не обязателен.",
                         INSTALLATION_DRAFT_KEYBOARD)
            return True
        result=run_installation_workflow({"action":"approve","deal_id":installation_deal_id,"actor":str(chat_id)})
        if not result.get("ok"):
            send_message(token, chat_id, "Ведомость не утверждена: "+str(result.get("error")), INSTALLATION_DRAFT_KEYBOARD)
            return True
        transition = state.get("installation_pending_transition") or {
            "deal_id": installation_deal_id, "state_id": "136", "name": "Монтаж"
        }
        update_deal_ui_state(chat_id, pending="installation_status_ready",
                             installation_pending_transition=transition)
        send_message(token, chat_id,
                     "✅ Монтажная ведомость утверждена. Статус сделки пока не изменён, монтажник объект не получил.\n\n"+
                     installation_summary(result["result"])+
                     "\n\nТеперь можно перевести сделку в статус «Монтаж».",
                     INSTALLATION_STATUS_KEYBOARD)
        return True
    if value == "✅ Перевести сделку в Монтаж" and installation_deal_id:
        transition = state.get("installation_pending_transition") or {
            "deal_id": installation_deal_id, "state_id": "136", "name": "Монтаж"
        }
        installation = run_installation_workflow({"action":"get","deal_id":installation_deal_id})
        if not installation.get("ok") or (installation.get("result") or {}).get("status") != "approved":
            send_message(token, chat_id, "Сначала утвердите монтажную ведомость. Статус сделки не изменён.",
                         INSTALLATION_DRAFT_KEYBOARD)
            return True
        result = run_deal_browser({"action":"move_status","deal_id":installation_deal_id,
                                   "state_id":str(transition["state_id"])})
        if not result.get("ok"):
            error=str(result.get("error") or "неизвестная ошибка")
            if "Мегаплан сейчас недоступен" in error or "техническая ошибка поиска сделок" in error:
                queue_deal_transition(transition,chat_id)
                send_message(token,chat_id,
                    f"⏳ Ведомость утверждена. Перевод сделки №{installation_deal_id} в «Монтаж» сохранён в очереди.",
                    INSTALLATION_STATUS_KEYBOARD)
            else:
                send_message(token,chat_id,"Статус не изменён: "+error,INSTALLATION_STATUS_KEYBOARD)
            return True
        handoff=complete_installation_handoff(token,installation_deal_id,chat_id)
        if not handoff.get('ok'):
            send_message(token,chat_id,"⚠️ Статус «Монтаж» установлен. Передача в кабинет пока не подтверждена; бот повторит проверку.",INSTALLATION_TRANSFER_KEYBOARD)
            return True
        update_deal_ui_state(chat_id,pending=None,installation_pending_transition=None)
        send_message(token,chat_id,
                     f"✅ Сделка №{installation_deal_id} переведена в «Монтаж» и доступна монтажнику. Уведомление отправляется с контролем доставки.",
                     DEAL_ACTIONS_KEYBOARD)
        return True
    if value == "✅ Передать объект монтажнику" and installation_deal_id:
        result=complete_installation_handoff(token,installation_deal_id,chat_id)
        if not result.get("ok"):
            send_message(token, chat_id, f"Объект не передан: {result.get('error')}", INSTALLATION_TRANSFER_KEYBOARD)
            return True
        item=result["result"]; update_deal_ui_state(chat_id, pending=None, installation_deal_id=None)
        send_message(token, chat_id, "✅ Объект передан монтажнику. Он появился в разделе «Мои монтажи».\n\n"+installation_summary(item), DEAL_ACTIONS_KEYBOARD)
        return True
    if value == "✅ Принять монтажный отчёт" and state.get("installation_report_id"):
        result=run_installation_workflow({"action":"approve_report","report_id":state["installation_report_id"],"actor":str(chat_id),"partial":state.get('installation_partial')})
        if not result.get("ok"):
            send_message(token, chat_id, f"Отчёт не принят: {result.get('error')}", INSTALLATION_REPORT_REVIEW_KEYBOARD)
            return True
        item=result["result"]
        WorkflowStore(WORKFLOW_DB_FILE).dismiss_notification(chat_id,'installation_report',state['installation_report_id'])
        update_deal_ui_state(chat_id,pending=None,installation_report_id=None,installation_partial=None)
        warning=("\nОбновление экономики и копий файлов поставлено в фоновую очередь." if item.get('publication_pending') else
                 "" if item.get('economics_refreshed',True) else f"\n⚠️ Экономика не обновилась автоматически: {item.get('economics_error') or 'неизвестная ошибка'}")
        send_message(token,chat_id,f"✅ Отчёт принят. Начислено всего: {money(item.get('accepted_total'))}. {installation_balance_text(item)}{warning}",MAIN_KEYBOARD)
        if INSTALLER_NOTIFY_CHAT_ID:
            notify_installers(token,f"✅ Руководитель принял отчёт по сделке №{item.get('deal_id')}. Принято к оплате накопительно: {money(item.get('accepted_total'))}.")
        return True
    if value == "↩️ Вернуть монтажнику" and state.get("installation_report_id"):
        update_deal_ui_state(chat_id,pending="installation_report_return_comment")
        send_message(token,chat_id,"Напишите причину возврата отчёта монтажнику.")
        return True
    if pending_now=="installation_report_return_comment" and state.get("installation_report_id"):
        result=run_installation_workflow({"action":"return_report","report_id":state["installation_report_id"],"comment":value,"actor":str(chat_id)})
        if not result.get("ok"): send_message(token,chat_id,f"Отчёт не возвращён: {result.get('error')}",INSTALLATION_REPORT_REVIEW_KEYBOARD); return True
        update_deal_ui_state(chat_id,pending=None,installation_report_id=None)
        send_message(token,chat_id,"↩️ Отчёт возвращён монтажнику. В накопительное выполнение он не включён.",MAIN_KEYBOARD)
        if INSTALLER_NOTIFY_CHAT_ID: notify_installers(token,f"↩️ Отчёт по сделке №{result['result'].get('deal_id')} возвращён: {value}")
        return True
    if value=="✏️ Скорректировать объёмы" and state.get("installation_report_id"):
        parsed=run_installation_workflow({"action":"get_report","report_id":state["installation_report_id"]})
        rows=parsed.get("result",{}).get("items") or [] if parsed.get("ok") else []
        lines=[f"{x['id']}={float(x.get('declared_qty') or 0):g} — {x.get('name') or 'не сопоставлено'}" for x in rows if x.get('work_item_id')]
        update_deal_ui_state(chat_id,pending="installation_report_correction")
        send_message(token,chat_id,"Укажите принятые объёмы в формате ID=количество, каждый с новой строки. Ноль означает отклонить строку.\n\n"+"\n".join(lines))
        return True
    if pending_now=="installation_report_correction" and state.get("installation_report_id"):
        pairs=re.findall(r'(?m)^\s*(\d+)\s*=\s*(\d+(?:[.,]\d+)?)\s*$',value)
        if not pairs: send_message(token,chat_id,"Не распознано ни одной строки. Пример: 15=12,5"); return True
        partial={key:float(qty.replace(',','.')) for key,qty in pairs}
        if not all(math.isfinite(x) and x>=0 for x in partial.values()):
            send_message(token,chat_id,'Неверные количества. Начисления не изменены.'); return True
        update_deal_ui_state(chat_id,pending='installation_report_review',installation_partial=partial)
        send_message(token,chat_id,'Предлагаемая корректировка объёмов:\n'+ '\n'.join(f'ID {k}: {v:g}' for k,v in partial.items())+
                     '\nОстальные строки — по отчёту. Начисления ещё не изменены; подтвердите приёмку.',INSTALLATION_REPORT_REVIEW_KEYBOARD)
        return True
    if value == "💵 Выплата монтажнику" and deal_id:
        current=run_installation_workflow({"action":"get","deal_id":str(deal_id)})
        if not current.get("ok"):
            send_message(token,chat_id,"Для этой сделки монтажный контур ещё не создан.",DEAL_ACTIONS_KEYBOARD); return True
        update_deal_ui_state(chat_id,pending="installation_cash_amount",installation_deal_id=str(deal_id))
        send_message(token,chat_id,f"{installation_balance_text(current['result'])}\nВведите сумму фактически произведённой наличной выплаты.")
        return True
    if pending_now=="installation_cash_amount":
        try: amount=float(value.replace(' ','').replace(',','.'))
        except ValueError:
            send_message(token,chat_id,"Введите сумму числом, например 25000."); return True
        if not math.isfinite(amount) or amount<=0:
            send_message(token,chat_id,'Сумма должна быть конечной и больше нуля.'); return True
        update_deal_ui_state(chat_id,pending="installation_cash_confirm",installation_cash_amount=amount,
                             installation_cash_date=datetime.now().strftime('%d.%m.%Y'))
        send_message(token,chat_id,f"Записать наличную выплату {money(amount)} сегодняшней датой и создать расходную операцию по кассе Мегаплана?",INSTALLATION_CASH_CONFIRM_KEYBOARD)
        return True
    if value=="✅ Записать выплату из кассы" and pending_now=="installation_cash_confirm":
        payment_date=state.get('installation_cash_date') or datetime.now().strftime('%d.%m.%Y'); external=f"cash-{installation_deal_id}-{state.get('_confirmation_id') or UI_CONTEXT.update_id}"
        result=run_installation_workflow({"action":"record_payment","deal_id":installation_deal_id,"source":"cash",
            "amount":state.get("installation_cash_amount"),"payment_date":payment_date,"external_id":external,"comment":"Подтверждено руководителем в Telegram"})
        if not result.get("ok"):
            send_message(token,chat_id,f"Выплата не записана: {result.get('error')}",INSTALLATION_CASH_CONFIRM_KEYBOARD); return True
        item=result["result"]; update_deal_ui_state(chat_id,pending=None,installation_cash_amount=None)
        send_message(token,chat_id,f"✅ Выплата учтена. Операция Мегаплана №{item.get('operation_id')}. {installation_balance_text(item)}",DEAL_ACTIONS_KEYBOARD)
        return True

    # Deal creation is a deterministic two-step transaction.  The model prepares the
    # complete draft once; the short tax reply must not be reinterpreted in a later
    # model turn (that used to lose tax_mode and mix in an older deal/KP context).
    chosen_tax = tax_mode_from_text(value)
    if pending_now == "deal_create_tax" and chosen_tax:
        spec = dict(state.get('deal_create_spec') or {})
        spec['tax_mode'] = chosen_tax
        prepare_deal_creation_review(token, chat_id, spec)
        return True
    if pending_now == 'deal_create_confirm' and value == '✅ Создать подтверждённую сделку':
        if not _background:
            run_background_job(lambda: handle_deal_ui(token, chat_id, text, _background=True), token, chat_id)
            return True
        spec = dict(state.get("deal_create_spec") or {})
        if not spec:
            update_deal_ui_state(chat_id, pending=None, deal_create_spec=None)
            send_message(token, chat_id, "Черновик сделки не найден. Пришлите КП и экономику повторно.", MAIN_KEYBOARD)
            return True
        validated, error = normalize_create_deal_spec(spec)
        if error:
            spec.pop('__invalid__', None)
            next_step = 'deal_create_client' if not spec.get('client_name') else 'deal_create_items'
            update_deal_ui_state(chat_id, pending=next_step, deal_create_spec=spec)
            send_message(token, chat_id,
                         'Укажите клиента для новой сделки.' if next_step == 'deal_create_client' else
                         'НДС сохранён. Пришлите спецификацию: оборудование, материалы и работы с количеством и ценами.',
                         PAYER_UPLOAD_KEYBOARD)
            return True
        spec = validated
        send_message(token, chat_id, "🔧 Создаю новую сделку в Мегаплане по сохранённым КП и экономике...")
        result = run_create_megaplan_deal(spec)
        if result.get("ok"):
            update_deal_ui_state(chat_id, pending=None, deal_create_spec=None,
                                 deal_creation_active=False, deal_creation_items=None,
                                 deal_creation_economics_path=None,
                                 current_deal_id=str(result.get("id") or ""))
            send_message(token, chat_id, format_create_megaplan_deal_summary(spec, result), MAIN_KEYBOARD)
            if result.get("ledger"):
                review = build_spec_review_xlsx(spec.get("client_name", "?"), result["ledger"])
                if review:
                    send_document(token, chat_id, review, "Позиции и экономика созданной сделки")
            if spec.get('proposal_recipient'):
                send_deal_proposal(token, chat_id, str(result['id']), recipient=spec['proposal_recipient'])
            if order_continuation.requested(spec):
                continue_document_order(token, chat_id, {'deal_id':str(result['id']), 'user_request':spec['user_request'], 'details':{}})
        else:
            # Keep the exact draft so a transient API error can be retried without
            # reparsing files or borrowing data from another conversation branch.
            send_message(token, chat_id, f"Не удалось завершить создание: {result.get('error', 'неизвестная ошибка')}. Черновик сохранён.", DEAL_CREATE_CONFIRM_KEYBOARD)
        return True

    if value == "🛠 Задача разработчику":
        if pending_now == "developer_task_running":
            send_message(token, chat_id, "Предыдущая задача разработчику ещё выполняется. Результат придёт сюда автоматически.", MAIN_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="developer_task_input")
        send_message(
            token, chat_id,
            "Опишите задачу разработчику одним сообщением. Можно приложить файл или скриншот.\n\n"
            "Я подтвержу приём, выполню задачу в фоне и пришлю результат в этот чат.",
            DEVELOPER_TASK_KEYBOARD,
        )
        return True
    if pending_now == "developer_task_input" and value in ("❌ Отменить задачу", "⬅️ Главное меню"):
        update_deal_ui_state(chat_id, pending=None)
        send_message(token, chat_id, "Ввод задачи отменён.", MAIN_KEYBOARD)
        return True
    if pending_now == "developer_task_input":
        if not value or value.startswith(("🤝 ", "🧰 ", "📄 ", "❓ ")):
            send_message(token, chat_id, "Напишите задачу обычным текстом либо нажмите «❌ Отменить задачу».", DEVELOPER_TASK_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="developer_task_running", developer_task_text=value,
                             developer_task_started_at=datetime.now(timezone.utc).isoformat())
        send_message(token, chat_id, "🛠 Задача принята. Начинаю работу; результат пришлю сюда автоматически.", MAIN_KEYBOARD)
        run_background_job(lambda: process_developer_task(token, chat_id, value), token, chat_id)
        return True
    if pending_now == "developer_task_running" and value in ("/dev_status", "🛠 Задача разработчику"):
        send_message(token, chat_id, "Задача разработчику выполняется. Результат придёт в этот чат автоматически.", MAIN_KEYBOARD)
        return True

    stock_actions = {"📦 Нераспределённые закупки", "📋 Показать остатки",
                     "📥 Скачать реестр остатков", "🔎 Найти в остатках"}
    if value in stock_actions and not _background:
        run_background_job(lambda: handle_deal_ui(token, chat_id, text, _background=True), token, chat_id)
        return True
    if value == "📦 Нераспределённые закупки":
        update_deal_ui_state(chat_id, pending="unallocated_stock_menu")
        send_message(token, chat_id, "Нераспределённые закупки — внутренние остатки наших организаций.",
                     UNALLOCATED_STOCK_KEYBOARD)
        return True
    if value == "📋 Показать остатки":
        result = run_procurement_workflow({"action": "list_unallocated_stock"})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось прочитать остатки: {result.get('error')}", UNALLOCATED_STOCK_KEYBOARD)
            return True
        rows = result.get("items") or []
        if not rows:
            send_message(token, chat_id, "Нераспределённых закупок сейчас нет.", UNALLOCATED_STOCK_KEYBOARD)
            return True
        lines = ["Нераспределённые закупки:"]
        for item in rows[:30]:
            company = (item.get("purchasing_company") or {}).get("name") or "организация не указана"
            lines.append(f"• {item.get('name')} — {float(item.get('available_qty') or 0):g} "
                         f"{item.get('unit') or ''}, {bank_money(item.get('available_amount'))} ₽; {company}; "
                         f"счёт №{item.get('invoice_number') or 'б/н'}")
        send_message(token, chat_id, "\n".join(lines), UNALLOCATED_STOCK_KEYBOARD)
        return True
    if value == "📥 Скачать реестр остатков":
        result = run_procurement_workflow({"action": "export_unallocated_stock"})
        if result.get("ok"):
            send_document(token, chat_id, result["path"], "Нераспределённые закупки")
            try:
                os.remove(result["path"])
            except OSError:
                pass
        else:
            send_message(token, chat_id, f"Не удалось сформировать реестр: {result.get('error')}", UNALLOCATED_STOCK_KEYBOARD)
        return True
    if value == "🔎 Найти в остатках":
        update_deal_ui_state(chat_id, pending="unallocated_stock_search")
        send_message(token, chat_id, "Введите артикул, модель или часть названия.", UNALLOCATED_STOCK_KEYBOARD)
        return True
    if pending_now == "unallocated_stock_search" and value not in stock_actions:
        result = run_procurement_workflow({"action": "list_unallocated_stock", "query": value})
        update_deal_ui_state(chat_id, pending="unallocated_stock_menu")
        rows = result.get("items") or [] if result.get("ok") else []
        if not rows:
            send_message(token, chat_id, "Подходящих остатков не найдено.", UNALLOCATED_STOCK_KEYBOARD)
        else:
            send_message(token, chat_id, "Найдено:\n" + "\n".join(
                f"• {x.get('name')} — {float(x.get('available_qty') or 0):g} {x.get('unit') or ''}, "
                f"{bank_money(x.get('available_amount'))} ₽" for x in rows[:20]), UNALLOCATED_STOCK_KEYBOARD)
        return True

    contract_actions = {
        "📑 Работа с договором", "📝 Подготовить договор", "👁 Проверить данные договора",
        "✅ Сформировать договор", "📑 Получить договор", "📎 Получить договор из Мегаплана",
        "✅ Загрузить договоры в сделку", "🧾 Выставить счёт по договору", "🏢 Добавить плательщика",
    }
    if value in contract_actions and not deal_id:
        send_message(token, chat_id, "Сначала выберите существующую сделку, затем откройте «Работа с договором».", DEALS_KEYBOARD)
        return True

    # Every operation that may touch Megaplan, build a report, convert a document or
    # upload a file runs outside the polling process. Previously a slow API response
    # froze even unrelated menu clicks for up to the subprocess/network timeout.
    slow_values = {
        "🔄 Изменить статус", "✅ Подтвердить", "💰 Экономика",
        "📝 Подготовить договор", "👁 Проверить данные договора",
        "✅ Сформировать договор", "📑 Получить договор",
        "🧾 Выставить счёт по договору", "✅ Выставить счёт",
        "🧾 Работа со счетами", "📋 Общий счёт по спецификации", "✅ Выставить общий счёт", "📚 Скачать счёт",
        "🧾 Выставить счёт", "🏢 Сменить плательщика", "📤 Отправить по ЭДО",
        "1. Полностью согласно спецификации", "2. Упрощённый согласно п.6.4", "3. Оба варианта",
        "📎 Получить договор из Мегаплана", "🛠 Ведомость работ", "📋 Монтажная ведомость",
        "📄 Позиции сделки", "📥 Получить счёт", "✅ Загрузить договоры в сделку",
        "✅ Утвердить монтажную ведомость", "✅ Перевести сделку в Монтаж",
    }
    is_slow = (
        bool(re.fullmatch(r"🕘 (?:Последние )?(5|10|15)", value))
        or bool(re.match(r"^№\d+\b", value))
        or value in (state.get("transitions") or {})
        or pending_now in ("search_client", "search_address", "get_number", "contract_date", "contract_address",
                           "contract_signatory_authority", "contract_invoice_clause", "invoice_menu", "invoice_download",
                           "supplier_invoice_confirm", "supplier_distribution_edit",
                           "supplier_distribution_exclusion_reason")
        or value in slow_values
    )
    if is_slow and not _background:
        run_background_job(lambda: handle_deal_ui(token, chat_id, text, _background=True), token, chat_id,
                           operation=f"сделка:{value[:60]}")
        return True

    if value in ("🤝 Сделки", "🤝 Работа со сделками", "/deals"):
        update_deal_ui_state(chat_id, pending=None, transitions=None, pending_transition=None)
        send_message(token, chat_id, "Работа со сделками — выберите действие.", DEALS_KEYBOARD)
        return True
    if value == "⬅️ Главное меню":
        update_deal_ui_state(chat_id, pending=None, transitions=None, pending_transition=None)
        send_message(token, chat_id, "Главное меню.", MAIN_KEYBOARD)
        return True
    if value == "⬅️ К списку сделок":
        update_deal_ui_state(chat_id, pending=None, transitions=None, pending_transition=None)
        send_message(token, chat_id, "Выберите способ поиска сделки.", DEALS_KEYBOARD)
        return True

    recent = re.fullmatch(r"🕘 (?:Последние )?(5|10|15)", value)
    if recent:
        send_deal_list(token, chat_id, {"action": "list", "limit": int(recent.group(1))})
        return True

    search_prompts = {
        "🔎 Найти по клиенту": ("search_client", "Введите название или часть названия клиента."),
        "📍 Найти по адресу": ("search_address", "Введите адрес или его часть."),
        "🔢 Найти по номеру": ("get_number", "Введите внутренний номер сделки."),
    }
    if value in search_prompts:
        pending, prompt = search_prompts[value]
        update_deal_ui_state(chat_id, pending=pending)
        send_message(token, chat_id, prompt, {"keyboard": [[{"text": "⬅️ К списку сделок"}]], "resize_keyboard": True})
        return True

    pending = state.get("pending")
    if pending == "installer_excel_report_date":
        try:
            parsed_date = datetime.strptime(value, "%d.%m.%Y")
        except ValueError:
            send_message(token, chat_id, "Введите дату в формате ДД.ММ.ГГГГ, например 24.09.2026.")
            return True
        installer["report_date"] = parsed_date.strftime("%d.%m.%Y")
        installer["report"] = parsed_date.strftime("%d.%m")
        if str(chat_id) in INSTALLER_CHAT_IDS and MANAGER_CHAT_ID:
            send_message(token, MANAGER_CHAT_ID, f"🔔 Сергей Деревянко загрузил новый Excel-отчёт от {installer['report_date']}. Бот начал разбор.", MAIN_KEYBOARD)
        update_deal_ui_state(chat_id, pending="installer_excel_report_deal", installer_report=installer)
        send_message(token, chat_id, "Укажите внутренний номер сделки, к которой относится выполнение, либо выберите «Всякая всячина».", {
            "keyboard": [[{"text": "📦 Всякая всячина"}], [{"text": "❌ Отменить отчёт"}]], "resize_keyboard": True,
        })
        return True
    if pending == "installer_excel_report_deal":
        if installer.get("source_deal_id") and value != installer["source_deal_id"]:
            send_message(token, chat_id, "Ведомость относится к сделке №"+installer["source_deal_id"]+". Подтвердите этот номер; для другой сделки загрузите её ведомость.")
            return True
        if value != "📦 Всякая всячина" and not re.fullmatch(r"\d+", value):
            send_message(token, chat_id, "Введите внутренний номер сделки только цифрами либо выберите «📦 Всякая всячина».")
            return True
        if value == "📦 Всякая всячина":
            for obj in installer.get("objects") or []:
                obj.update({"name": "Всякая всячина", "deal_id": None, "essence": "без привязки к сделке", "confidence": 1.0})
            for item in installer.get("exceptions") or []:
                item.update({"object": "Всякая всячина", "deal_id": None, "bucket": "Всякая всячина", "resolution": "всякая всячина — начислить без сделки"})
            for line in installer.get("report_lines") or []:
                line["object"] = "Всякая всячина"
        else:
            for obj in installer.get("objects") or []:
                obj.update({"deal_id": value, "essence": "выбрано монтажником", "confidence": 1.0})
            for item in installer.get("exceptions") or []:
                item["deal_id"] = value
            for line in installer.get("report_lines") or []:
                line.update({"deal_id": value, "deal_essence": "выбрано монтажником", "mapping_confidence": 1.0})
        installer["stage"] = "exceptions"
        update_deal_ui_state(chat_id, pending="installer_report_review", installer_report=installer)
        send_message(token, chat_id, installer_review_text(installer), installer_review_keyboard(chat_id))
        return True
    if value == "🧰 Открыть отчёт монтажника" and state.get("incoming_installer_report"):
        incoming = state.get("incoming_installer_report")
        incoming["stage"] = "manager_review"
        incoming["exception_index"] = 0
        for item in incoming.get("exceptions") or []:
            if item.get("resolution") == "оставлено вопросом":
                item["resolution"] = None
        update_deal_ui_state(
            chat_id,
            pending="installer_report_review",
            installer_report=incoming,
            incoming_installer_report=None,
        )
        send_message(token, chat_id, installer_review_text(incoming), INSTALLER_REPORT_REVIEW_KEYBOARD)
        return True
    if value == "📤 Передать руководителю" and str(chat_id) in INSTALLER_CHAT_IDS and (pending or "").startswith("installer_report"):
        if not MANAGER_CHAT_ID:
            send_message(token, chat_id, "Не настроен аккаунт руководителя. Черновик сохранён.", installer_review_keyboard(chat_id))
            return True
        submitted = copy.deepcopy(installer)
        submitted["stage"] = "awaiting_manager"
        submitted["submitted_at"] = datetime.now(timezone.utc).isoformat()
        submitted["submitted_by_chat_id"] = str(chat_id)
        unresolved = [
            item for item in submitted.get("exceptions") or []
            if not item.get("resolution") or item.get("resolution") == "оставлено вопросом"
        ]
        update_deal_ui_state(MANAGER_CHAT_ID, incoming_installer_report=submitted)
        update_deal_ui_state(chat_id, pending="installer_report_submitted", installer_report=installer)
        send_message(
            token, chat_id,
            f"Отчёт от {submitted.get('report_date') or submitted.get('report')} передан руководителю. "
            f"Нерешённых вопросов: {len(unresolved)}. После проверки руководителем отчёт будет утверждён.",
            INSTALLER_USER_KEYBOARD,
        )
        send_message(token, MANAGER_CHAT_ID, (
            f"📥 Получен отчёт Сергея Деревянко от {submitted.get('report_date') or submitted.get('report')}.\n"
            f"Распознано строк без уточнений: {submitted.get('automatic_count', 0)} на {money(submitted.get('automatic_sum', 0))}.\n"
            f"Итог к проверке: {money(submitted.get('payable_amount') or submitted.get('net_total') or submitted.get('declared_total'))}.\n"
            f"Нерешённых вопросов: {len(unresolved)}."
        ), INSTALLER_MANAGER_OPEN_KEYBOARD)
        return True
    if value == "🧰 Отчёт монтажника":
        update_deal_ui_state(chat_id, pending=None)
        send_message(token, chat_id, "Работа с отчётами и взаиморасчётами монтажника.", INSTALLER_MENU_KEYBOARD)
        return True
    if value == "📄 Загрузить отчёт":
        update_deal_ui_state(chat_id, pending="installer_report_file", installer_report=None)
        keyboard = {"keyboard": [[{"text": "❌ Отменить отчёт"}], [{"text": "⬅️ Главное меню"}]], "resize_keyboard": True}
        send_message(token, chat_id, "Пришлите PDF-отчёт монтажника. Сначала я покажу только найденные объекты и сделки, а затем — только спорные строки.", keyboard)
        return True
    if value == "💳 Учесть выплату":
        update_deal_ui_state(chat_id, pending="installer_payment_file", installer_payment=None)
        send_message(token, chat_id, "Пришлите платёжное поручение/квитанцию в PDF либо напишите выплату текстом, например: «20 000 ₽ выплачено наличными за Вестгарден».", {"keyboard": [[{"text": "❌ Отменить выплату"}]], "resize_keyboard": True})
        return True
    if value == "📊 Взаиморасчёты":
        result = run_installer_settlements({"action": "export"})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось сформировать реестр: {result.get('error')}", INSTALLER_MENU_KEYBOARD)
            return True
        send_document(token, chat_id, result["path"], "Накопительный реестр взаиморасчётов с монтажником", os.path.basename(result["path"]))
        send_message(token, chat_id, "Реестр сформирован по всем утверждённым отчётам и учтённым выплатам.", INSTALLER_MENU_KEYBOARD)
        return True
    if value == "❌ Отменить выплату" and (pending or "").startswith("installer_payment"):
        update_deal_ui_state(chat_id, pending=None, installer_payment=None)
        send_message(token, chat_id, "Учёт выплаты отменён.", INSTALLER_MENU_KEYBOARD)
        return True
    if pending == "installer_payment_file":
        payment = parse_text_installer_payment(value, chat_id)
        if not payment:
            send_message(token, chat_id, "Не удалось определить сумму выплаты. Напишите, например: «20 000 ₽ выплачено наличными за Вестгарден», либо пришлите PDF.")
            return True
        update_deal_ui_state(chat_id, pending="installer_payment_confirm", installer_payment=payment)
        suggested = "\nРаспознано как наличная выплата — подтвердите кнопкой ниже." if payment.get("suggested_method") == "cash" else ""
        send_message(token, chat_id, (
            f"Выплата монтажнику от {payment['date']}\n"
            f"Сумма: {money(payment['amount'])}\n"
            f"Комментарий: {payment['purpose']}\n\n"
            "Эта выплата относится к общим взаиморасчётам с монтажником и не требует сделки. "
            "Название объекта или «Всякая всячина» сохраняется только как комментарий."
            f"{suggested}"
        ), INSTALLER_PAYMENT_KEYBOARD)
        return True
    if pending == "installer_payment_confirm" and value in ("🏦 Безналичная — зачесть 94%", "💵 Наличная — зачесть 100%"):
        payment = state.get("installer_payment") or {}
        payment["payment_method"] = "cashless" if value.startswith("🏦") else "cash"
        coefficient = 0.94 if payment["payment_method"] == "cashless" else 1.0
        result = run_installer_settlements({"action": "record_payment", "payment": payment})
        if not result.get("ok"):
            send_message(token, chat_id, f"Выплата не учтена: {result.get('error')}", INSTALLER_PAYMENT_KEYBOARD)
            return True
        op = result["operation"]
        update_deal_ui_state(chat_id, pending=None, installer_payment=None)
        send_message(token, chat_id, f"Выплата {money(op.get('gross_amount') or op.get('amount'))} учтена. Взаиморасчёты: коэффициент {op.get('coefficient'):.2f}, зачтено {money(op.get('settlement_amount'))}. Нераспределённый аванс: {money(op.get('unallocated_advance') or 0)}.", INSTALLER_MENU_KEYBOARD)
        send_document(token, chat_id, result["path"], "Обновлённый накопительный реестр взаиморасчётов", os.path.basename(result["path"]))
        if INSTALLER_NOTIFY_CHAT_ID:
            method = "безналичным расчётом" if op.get("payment_method") == "cashless" else "наличными"
            detail = ""
            if op.get("payment_method") == "cashless":
                detail = f"\nВо взаиморасчётах зачтено: {money(op.get('settlement_amount'))} (94%)."
            notify_installers(
                token,
                f"💳 Выплата произведена {op.get('date')} {method}.\n"
                f"Перечислено: {money(op.get('gross_amount') or op.get('amount'))}.{detail}",
            )
        return True
    if value == "❌ Отменить отчёт" and (pending or "").startswith(("installer_report", "installer_excel_report")):
        update_deal_ui_state(chat_id, pending=None, installer_report=None)
        send_message(token, chat_id, "Разбор отчёта отменён. Никакие данные не записывались.", home_keyboard(chat_id))
        return True
    if pending == "installer_report_tables" and value == "✅ Все файлы загружены":
        finish_installer_report_files(token, chat_id, installer)
        return True
    if pending == "installer_report_objects" and value == "✅ Объекты верны":
        installer["stage"] = "exceptions"
        update_deal_ui_state(chat_id, pending="installer_report_review", installer_report=installer)
        send_message(token, chat_id, installer_review_text(installer), installer_review_keyboard(chat_id))
        return True
    if pending == "installer_report_objects" and value == "✏️ Исправить объект":
        rows = [[{"text": f"Объект: {obj['name']}"}] for obj in installer.get("objects") or []]
        rows.append([{"text": "❌ Отменить отчёт"}])
        update_deal_ui_state(chat_id, pending="installer_report_fix_object", installer_report=installer)
        send_message(token, chat_id, "Какой объект нужно перепривязать?", {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})
        return True
    if pending == "installer_report_fix_object" and value.startswith("Объект: "):
        name = value.split(": ", 1)[1]
        installer["fix_object"] = name
        update_deal_ui_state(chat_id, pending="installer_report_fix_deal", installer_report=installer)
        send_message(token, chat_id, f"Введите внутренний номер сделки для объекта «{name}».")
        return True
    if pending == "installer_report_fix_deal":
        match = re.fullmatch(r"\d+", value)
        if not match:
            send_message(token, chat_id, "Введите только внутренний номер сделки цифрами.")
            return True
        for obj in installer.get("objects") or []:
            if obj.get("name") == installer.get("fix_object"):
                obj.update({"deal_id": match.group(0), "essence": "выбрано вручную", "confidence": 1.0, "inherited": False})
        for item in installer.get("exceptions") or []:
            if item.get("object") == installer.get("fix_object"):
                item["deal_id"] = match.group(0)
                if item.get("type") == "deal":
                    if item.get("amount") is not None:
                        item["resolution"] = f"сделка №{match.group(0)}"
                    else:
                        item["type"] = "amount"
                        item["reason"] = "не указана сумма"
        for line in installer.get("report_lines") or []:
            if line.get("object") == installer.get("fix_object"):
                line.update({"deal_id": match.group(0), "deal_essence": "выбрано вручную", "mapping_confidence": 1.0})
        installer.pop("fix_object", None)
        update_deal_ui_state(chat_id, pending="installer_report_objects", installer_report=installer)
        send_message(token, chat_id, installer_objects_text(installer), INSTALLER_REPORT_OBJECTS_KEYBOARD)
        return True
    if pending == "installer_report_review" and value == "▶️ Разобрать исключения":
        installer["exception_index"] = 0
        send_installer_exception(token, chat_id, installer)
        return True
    if pending == "installer_report_exception":
        exceptions = installer.get("exceptions") or []
        index = int(installer.get("exception_index") or 0)
        if index < len(exceptions):
            item = exceptions[index]
            resolutions = {
                "💰 Учесть одной суммой": "учесть одной суммой",
                "✅ Принять выполнение таблицы": "выполнение принято по таблице",
                "🔢 Выбрать позиции позже": "выбрать позиции позже",
                "✅ Подтвердить операцию": "операция подтверждена",
                "✅ Строки и суммы сверены": "строки и суммы сверены",
                "⏭ Оставить вопросом": "оставлено вопросом",
                "➕ Внеплановый расход": "внеплановый расход",
                "🚫 Не учитывать": "не учитывать",
            }
            if value == "📦 Всякая всячина" and item.get("type") == "deal":
                if item.get("amount") is None:
                    request_exception_amount(token, chat_id, installer, index, "всякая всячина — начислить без сделки", "Всякая всячина")
                    return True
                item["resolution"] = "всякая всячина — начислить без сделки"
                item["bucket"] = "Всякая всячина"
                item["deal_id"] = None
                installer["exception_index"] = index + 1
                send_installer_exception(token, chat_id, installer)
                return True
            if value == "✅ Принять построчный итог" and item.get("type") == "discrepancy":
                item["resolution"] = "принят построчный итог"
                installer["payable_amount"] = item.get("calculated_total")
                installer["adjustment"] = 0
                installer["exception_index"] = index + 1
                send_installer_exception(token, chat_id, installer)
                return True
            if value == "➕ Добавить корректировку" and item.get("type") == "discrepancy":
                item["resolution"] = f"добавлена корректировка {item.get('amount'):.2f} ₽"
                installer["adjustment"] = item.get("amount")
                installer["payable_amount"] = item.get("declared_total")
                installer["exception_index"] = index + 1
                send_installer_exception(token, chat_id, installer)
                return True
            if value == "✏️ Исправить строки" and item.get("type") == "discrepancy":
                item["resolution"] = "оставлено вопросом"
                update_deal_ui_state(chat_id, pending="installer_report_review", installer_report=installer)
                send_message(token, chat_id, "Исправьте исходные строки или загрузите исправленный отчёт. До устранения расхождения утверждение заблокировано.", installer_review_keyboard(chat_id))
                return True
            if value == "🔢 Указать номер сделки":
                installer["deal_exception_index"] = index
                update_deal_ui_state(chat_id, pending="installer_report_exception_deal", installer_report=installer)
                send_message(token, chat_id, "Введите внутренний номер сделки цифрами.")
                return True
            if value in resolutions:
                if item.get("amount") is None and value != "⏭ Оставить вопросом":
                    request_exception_amount(token, chat_id, installer, index, resolutions[value])
                    return True
                item["resolution"] = resolutions[value]
                installer["exception_index"] = index + 1
                send_installer_exception(token, chat_id, installer)
                return True
    if pending == "installer_report_exception_amount":
        index = int(installer.get("amount_exception_index") or 0)
        exceptions = installer.get("exceptions") or []
        if index >= len(exceptions):
            update_deal_ui_state(chat_id, pending="installer_report_review", installer_report=installer)
            send_message(token, chat_id, "Строка для ввода стоимости не найдена.", installer_review_keyboard(chat_id))
            return True
        amount = parse_nonnegative_money(value)
        if amount is None:
            send_message(token, chat_id, "Введите неотрицательную сумму цифрами, например 5000 или 0.")
            return True
        item = exceptions[index]
        item["amount"] = amount
        item["resolution"] = installer.pop("amount_resolution", None) or "стоимость подтверждена"
        bucket = installer.pop("amount_bucket", None)
        if bucket:
            item["bucket"] = bucket
            item["deal_id"] = None
        installer.pop("amount_exception_index", None)
        for line in installer.get("report_lines") or []:
            if line.get("source") == item.get("source") and line.get("object") == item.get("object"):
                line["amount"] = amount
        installer["net_total"] = sum(
            float(line.get("amount") or 0) * float(line.get("sign") or 0)
            for line in installer.get("report_lines") or []
        )
        installer["payable_amount"] = installer["net_total"] + float(installer.get("adjustment") or 0)
        installer["exception_index"] = index + 1
        send_message(token, chat_id, f"Стоимость {money(amount)} сохранена.")
        send_installer_exception(token, chat_id, installer)
        return True
    if pending == "installer_report_exception_deal":
        match = re.fullmatch(r"\d+", value)
        if not match:
            send_message(token, chat_id, "Введите только внутренний номер сделки цифрами.")
            return True
        index = int(installer.get("deal_exception_index") or 0)
        exceptions = installer.get("exceptions") or []
        if index < len(exceptions):
            exceptions[index]["deal_id"] = match.group(0)
            exceptions[index]["resolution"] = f"сделка №{match.group(0)}"
            target = exceptions[index]
            for line in installer.get("report_lines") or []:
                if (
                    not line.get("deal_id")
                    and line.get("source") == target.get("source")
                    and line.get("object") == target.get("object")
                ):
                    line["deal_id"] = match.group(0)
                    line["deal_essence"] = "выбрано руководителем"
                    line["mapping_confidence"] = 1.0
            if target.get("amount") is None:
                request_exception_amount(token, chat_id, installer, index, target["resolution"])
                return True
        installer["exception_index"] = index + 1
        installer.pop("deal_exception_index", None)
        send_installer_exception(token, chat_id, installer)
        return True
    if (value == "✅ Утвердить черновик" and pending in ("installer_report_review", "installer_report_exception")) or (value==legacy_report_ui.CONFIRM and pending==legacy_report_ui.PENDING_CONFIRM):
        if str(chat_id) in INSTALLER_CHAT_IDS:
            send_message(token, chat_id, "Окончательное утверждение выполняет руководитель. Передайте черновик руководителю.", INSTALLER_REPORT_SUBMIT_KEYBOARD)
            return True
        unresolved = [item for item in installer.get("exceptions") or [] if not item.get("resolution") or item.get("resolution") == "оставлено вопросом"]
        missing_amounts = [item for item in installer.get("exceptions") or [] if item.get("type") in ("amount", "deal") and item.get("amount") is None]
        if missing_amounts:
            send_message(token, chat_id, f"Черновик пока не утверждён: у {len(missing_amounts)} строк не указана стоимость. Введите сумму для каждой строки, включая 0 для неоплачиваемой работы.", INSTALLER_REPORT_REVIEW_KEYBOARD)
            return True
        if unresolved:
            send_message(token, chat_id, f"Черновик пока не утверждён: осталось вопросов — {len(unresolved)}.", INSTALLER_REPORT_REVIEW_KEYBOARD)
            return True
        if value!=legacy_report_ui.CONFIRM:
            legacy_report_ui.stage(sys.modules[__name__],token,chat_id,installer)
            return True
        installer["approved"] = True
        installer["stage"] = "approved_draft"
        result = build_installer_report_result(installer)
        if not result.get("ok"):
            installer['approved']=False
            installer['stage']='review'
            update_deal_ui_state(chat_id,pending='installer_report_review',installer_report=installer)
            send_message(token, chat_id, f"Приёмка не записана: Excel сформировать не удалось: {result.get('error')}. Можно повторить проверку черновика.", INSTALLER_REPORT_REVIEW_KEYBOARD)
            return True
        payable=installer.get('payable_amount') if installer.get('payable_amount') is not None else installer.get('net_total')
        try:payable=float(payable)
        except (TypeError,ValueError):payable=float('nan')
        if not math.isfinite(payable) or payable<0:
            send_message(token,chat_id,'В сборном отчёте не подтверждена итоговая сумма взаиморасчётов. Приёмка не записана; сначала нужно проверить итог.'); return True
        committed=run_installation_workflow({'action':'accept_legacy_report','session':installer,
            'source_digest':state.get('installer_bundle_digest'),
            'expected_fingerprint':(state.get('installer_bundle_preview') or {}).get('fingerprint'), 'actor':str(chat_id)})
        if not committed.get('ok'):
            send_message(token,chat_id,'Сборный отчёт не принят: '+str(committed.get('error')))
            return True
        accrual = run_installation_workflow({'action':'sync_legacy_ledger','source_digest':state.get('installer_bundle_digest')})
        if not accrual.get("ok") or (accrual.get('result') or {}).get('pending_errors'):
            send_message(token, chat_id, "Работы приняты в едином монтажном кабинете. Обновление сводного реестра отложено и будет повторено автоматически. Не загружайте отчёт заново: начисления уже сохранены.")
        save_approved_installer_report(installer, result.get("path"))
        save_installer_fact_registry(installer)
        installer["generated_deal_files"] = result.get("deal_files") or []
        update_deal_ui_state(chat_id, pending="installer_report_upload", installer_report=installer)
        submitter_chat_id = str(installer.get("submitted_by_chat_id") or "")
        if submitter_chat_id and submitter_chat_id != str(chat_id):
            notify_installers(
                token,
                f"✅ Руководитель утвердил отчёт от {installer.get('report_date') or installer.get('report')}. "
                f"К оплате по отчёту: {money(installer.get('payable_amount') or installer.get('net_total') or installer.get('declared_total'))}.",
            )
        if (committed.get('result') or {}).get('reports'):
            summary='Работы по сделкам приняты; актуальные ведомости и экономика поставлены в очередь обновления.'
        else:
            summary='Подтверждённые отдельные расчёты сохранены для сводного реестра. Монтажные объёмы сделок не изменялись.'
        send_message(token, chat_id, 'Сборный отчёт принят. '+summary+' Прикрепление исходного разбора — отдельный шаг.')
        send_document(token, chat_id, result["path"], f"Итоговый разбор отчёта монтажника от {installer.get('report')}", os.path.basename(result["path"]))
        files_text = "\n".join(f"• сделка №{item['deal_id']}: {item['filename']}" for item in installer["generated_deal_files"])
        send_message(token, chat_id, f"Подготовлены отдельные файлы:\n{files_text}\n\nЗагрузить их в соответствующие сделки?", INSTALLER_REPORT_UPLOAD_KEYBOARD)
        return True
    if pending == "installer_report_upload" and value == "📤 Загрузить выполнение в сделки":
        results = []
        for item in installer.get("generated_deal_files") or []:
            result = run_deal_browser({"action": "upload_execution_file", "deal_id": item["deal_id"], "path": item["path"]})
            results.append((item, result))
        failed = [(item, result) for item, result in results if not result.get("ok")]
        if failed:
            details = "\n".join(f"• сделка №{item['deal_id']}: {result.get('error')}" for item, result in failed)
            send_message(token, chat_id, f"Не все файлы загружены:\n{details}", INSTALLER_REPORT_UPLOAD_KEYBOARD)
            return True
        installer["stage"] = "uploaded"
        installer["uploaded_to_deals"] = True
        update_deal_ui_state(chat_id, pending=None, installer_report=installer)
        details = "\n".join(f"• сделка №{item['deal_id']} — файл загружен" for item, _result in results)
        send_message(token, chat_id, f"Выполнение загружено в Мегаплан:\n{details}\nНакопительный факт обновлён.", home_keyboard(chat_id))
        return True
    if pending == "installer_report_upload" and value == "❌ Не загружать выполнение":
        update_deal_ui_state(chat_id, pending=None, installer_report=installer)
        send_message(token, chat_id, "Исходный разбор дополнительно не прикреплён к сделкам. Уже принятые начисления и обновление монтажных ведомостей остаются в силе.", home_keyboard(chat_id))
        return True
    if value == "❌ Отмена" and pending and pending.startswith("contract_"):
        from_invoice_menu = state.get("invoice_origin") == "menu"
        update_deal_ui_state(chat_id, pending="invoice_menu" if from_invoice_menu else None,
                             contract_invoice_preview=None, invoice_origin=None)
        send_message(token, chat_id, "Действие отменено.", INVOICE_MENU_KEYBOARD if from_invoice_menu else CONTRACT_KEYBOARD)
        return True
    if value == "❌ Отмена" and pending and pending.startswith("invoice_"):
        update_deal_ui_state(chat_id, pending=None, invoice_downloads=None)
        send_message(token, chat_id, "Действие со счётом отменено.", INVOICE_MENU_KEYBOARD)
        return True
    if pending == "invoice_menu" and re.fullmatch(r"6\.4\.\d+", value):
        result = run_contract_invoice({"action": "preview", "deal_id": str(deal_id), "clause": value})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось подготовить счёт: {invoice_error_text(result.get('error'))}", INVOICE_MENU_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="contract_invoice_confirm", contract_invoice_preview=result, invoice_origin="menu")
        send_message(token, chat_id, f"В счёте будет одна строка:\n\n{result['line']}\n\nВыставить счёт?", CONTRACT_INVOICE_CONFIRM_KEYBOARD)
        return True
    if pending == "invoice_full_confirm" and value == "✅ Выставить общий счёт":
        update_deal_ui_state(chat_id, pending="invoice_menu")
        invoice_id = create_and_send_full_invoice(token, chat_id, deal_id)
        if invoice_id:
            offer_edo(token, chat_id, deal_id, invoice_id)
        return True
    if pending == "invoice_download":
        invoice = (state.get("invoice_downloads") or {}).get(value)
        if not invoice:
            send_message(token, chat_id, "Выберите счёт кнопкой из списка.")
            return True
        send_megaplan_invoice_by_id(token, chat_id, invoice["id"])
        update_deal_ui_state(chat_id, pending="invoice_menu", invoice_downloads=None)
        send_message(token, chat_id, "Работа со счетами — выберите действие.", INVOICE_MENU_KEYBOARD)
        return True
    if pending == "contract_invoice_clause":
        clause_match = re.fullmatch(r"6\.4\.\d+", value)
        if not clause_match:
            send_message(token, chat_id, "Укажите пункт оплаты в формате 6.4.1.", CONTRACT_INVOICE_CLAUSE_KEYBOARD)
            return True
        result = run_contract_invoice({"action": "preview", "deal_id": str(deal_id), "clause": value})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось подготовить счёт: {invoice_error_text(result.get('error'))}", CONTRACT_INVOICE_CLAUSE_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="contract_invoice_confirm", contract_invoice_preview=result, invoice_origin=None)
        send_message(
            token, chat_id,
            f"Будет выставлен счёт по сделке №{deal_id}. В счёте будет ровно одна строка:\n\n{result['line']}\n\nСумма: {_ru_money(result['amount'])} руб.\nПлательщик: {result.get('payer_name') or result['payer_id']}\nИсточник: {result['contract_filename']}",
            CONTRACT_INVOICE_CONFIRM_KEYBOARD,
        )
        return True
    if pending == "contract_invoice_confirm" and value == "✅ Выставить счёт":
        prepared = state.get("contract_invoice_preview") or {}
        return_keyboard = INVOICE_MENU_KEYBOARD if state.get("invoice_origin") == "menu" else CONTRACT_KEYBOARD
        result = run_contract_invoice({"action": "create", "deal_id": str(deal_id), "clause": prepared.get("clause"),
            'expected_fingerprint':prepared.get('fingerprint'), 'reconcile_total':prepared.get('amount'),
            'reconcile_lines':[prepared.get('line')], 'reconcile_confirmed_at':datetime.now(timezone.utc).isoformat()})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось выставить счёт: {result.get('error')}", CONTRACT_INVOICE_CONFIRM_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="invoice_menu" if state.get("invoice_origin") == "menu" else None, contract_invoice_preview=None, invoice_origin=None)
        send_message(token, chat_id, f"Счёт №{result.get('invoice_number') or result['invoice_id']} выставлен и привязан к сделке №{deal_id}.", return_keyboard)
        pdf = fetch_megaplan_invoice_pdf({"invoiceId": result["invoice_id"]})
        if pdf.get("ok"):
            try:
                send_document(token, chat_id, pdf["path"], pdf.get("caption") or "Счёт из Мегаплана", pdf.get("filename"))
            finally:
                try:
                    os.remove(pdf["path"])
                except OSError:
                    pass
        else:
            send_message(token, chat_id, "Счёт создан, но PDF пока не удалось получить. Его можно скачать через меню счетов.", return_keyboard)
        offer_edo(token, chat_id, deal_id, result["invoice_id"])
        return True
    if pending == "contract_signatory_name":
        if value.startswith(("📝 ", "📑 ", "👁 ", "✅ ", "⬅️ ", "🤝 ")):
            send_message(token, chat_id, "Введите ФИО подписанта текстом, не нажимая кнопку меню.")
            return True
        signer = state.get("contract_signatory") or {}
        signer["name"] = value
        update_deal_ui_state(chat_id, pending="contract_signatory_position", contract_signatory=signer,
                             contract_signatory_payer_id=state.get("contract_signatory_payer_id"))
        send_message(token, chat_id, "Укажите должность подписанта, например: Генеральный директор.")
        return True
    if pending == "contract_signatory_position":
        if value.startswith(("📝 ", "📑 ", "👁 ", "✅ ", "⬅️ ", "🤝 ")):
            send_message(token, chat_id, "Введите должность подписанта текстом.")
            return True
        signer = state.get("contract_signatory") or {}
        signer["position"] = value
        update_deal_ui_state(chat_id, pending="contract_signatory_authority", contract_signatory=signer)
        keyboard = {"keyboard": [[{"text": "Устав"}, {"text": "Доверенность"}], [{"text": "❌ Отмена"}]], "resize_keyboard": True, "one_time_keyboard": True}
        send_message(token, chat_id, "На основании чего действует подписант?", keyboard)
        return True
    if pending == "contract_signatory_authority":
        signer = state.get("contract_signatory") or {}
        signer["authority"] = value
        update_deal_ui_state(chat_id, pending=None, contract_signatory=signer)
        saved = run_payer_card_apply({
            "action": "save_signatory", "deal_id": str(deal_id),
            "director": signer.get("name"), "position": signer.get("position"),
            "authority": signer.get("authority"),
        })
        if not saved.get("ok"):
            send_message(token, chat_id, f"⚠️ Договор можно продолжить, но ФИО руководителя не сохранилось в плательщике: {saved.get('error')}")
        prepare_contract_preview(token, chat_id, deal_id)
        return True
    if pending == "contract_date":
        if not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
            send_message(token, chat_id, "Введите дату договора строго в формате ДД.ММ.ГГГГ.")
            return True
        try:
            datetime.strptime(value, "%d.%m.%Y")
        except ValueError:
            send_message(token, chat_id, "Такой даты не существует. Введите дату в формате ДД.ММ.ГГГГ.")
            return True
        result = run_deal_browser({"action": "update_contract_fields", "deal_id": str(deal_id), "contract_date": value})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось сохранить дату договора: {result.get('error')}")
            return True
        update_deal_ui_state(chat_id, pending=None)
        prepare_contract_preview(token, chat_id, deal_id)
        return True
    if pending == "contract_address":
        if len(value) < 5:
            send_message(token, chat_id, "Адрес слишком короткий. Укажите полный адрес объекта.")
            return True
        result = run_deal_browser({"action": "update_contract_fields", "deal_id": str(deal_id), "address": value})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось сохранить адрес объекта: {result.get('error')}")
            return True
        update_deal_ui_state(chat_id, pending=None)
        prepare_contract_preview(token, chat_id, deal_id)
        return True
    if pending in ("search_client", "search_address", "get_number"):
        update_deal_ui_state(chat_id, pending=None)
        if pending == "get_number":
            match = re.search(r"\d+", value)
            if not match:
                update_deal_ui_state(chat_id, pending="get_number")
                send_message(token, chat_id, "Не вижу номера сделки. Введите только цифры.",
                             {"keyboard": [[{"text": "⬅️ К списку сделок"}]], "resize_keyboard": True})
            elif not select_deal(token, chat_id, match.group(0)):
                update_deal_ui_state(chat_id, pending="get_number")
        else:
            send_deal_list(token, chat_id, {"action": pending, "query": value, "limit": 15})
        return True

    if pending == "procurement_stock_select":
        suggestions = state.get("procurement_stock_suggestions") or []
        if value == "❌ Отмена":
            update_deal_ui_state(chat_id, pending="procurement_menu", procurement_stock_deal_id=None,
                                 procurement_stock_suggestions=None)
            send_message(token, chat_id, "Подбор из остатков отменён.", PROCUREMENT_KEYBOARD)
            return True
        numbers = [int(x) for x in re.findall(r"\d+", value or "")]
        chosen = sorted(set(x for x in numbers if 1 <= x <= len(suggestions)))
        if not chosen:
            send_message(token, chat_id, "Выберите номер варианта, например: 1 или 1,3.")
            return True
        selected_suggestions = [suggestions[x - 1] for x in chosen]
        update_deal_ui_state(chat_id, pending="procurement_stock_confirm",
                             procurement_stock_suggestions=selected_suggestions)
        lines = [f"• {x.get('stock_name')} → {x.get('target_name')}: {float(x.get('qty') or 0):g}"
                 for x in selected_suggestions]
        send_message(token, chat_id, "Учесть в фактической себестоимости:\n" + "\n".join(lines) + "?",
                     PROCUREMENT_STOCK_CONFIRM_KEYBOARD)
        return True

    if pending == "procurement_stock_confirm" and value in (
            "✅ Использовать найденные остатки", "⏭ Не использовать остатки"):
        stock_deal_id = str(state.get("procurement_stock_deal_id") or deal_id or "")
        suggestions = state.get("procurement_stock_suggestions") or []
        if value == "✅ Использовать найденные остатки":
            updates = [{"offer_id": x.get("offer_id"), "offer_row_id": x.get("offer_row_id"),
                        "qty_used": x.get("qty"), "material_cost_used": x.get("amount"),
                        "work_cost_used": 0, "source_line_key": f"stock:{x.get('stock_id')}",
                        "source_name": x.get("stock_name"), "source_qty": x.get("qty"),
                        "source_total": x.get("amount")} for x in suggestions]
            applied = run_supplier_invoice_apply({"deal_id": stock_deal_id, "updates": updates,
                                                   "additions": [], "invoice": {}})
            if not applied.get("ok"):
                send_message(token, chat_id, f"Не удалось использовать остатки: {applied.get('error')}",
                             PROCUREMENT_STOCK_CONFIRM_KEYBOARD)
                return True
            for item in suggestions:
                consumed = run_procurement_workflow({"action": "consume_unallocated_stock",
                    "stock_id": item.get("stock_id"), "deal_id": stock_deal_id, "qty": item.get("qty"),
                    "offer_id": item.get("offer_id"), "offer_row_id": item.get("offer_row_id"),
                    "actor": str(chat_id)})
                if not consumed.get("ok"):
                    send_message(token, chat_id,
                        f"⚠️ Себестоимость записана, но движение остатка требует проверки: {consumed.get('error')}",
                        DEAL_ACTIONS_KEYBOARD)
            economics = build_and_store_profitability(stock_deal_id)
            if economics.get("path"):
                try: os.remove(economics["path"])
                except OSError: pass
            send_message(token, chat_id, "✅ Нераспределённые остатки учтены в себестоимости сделки.")
        update_deal_ui_state(chat_id, pending=None, procurement_stock_deal_id=None,
                             procurement_stock_suggestions=None)
        continue_procurement_after_stock(token, chat_id, stock_deal_id, "Закупка")
        return True

    if value == "🔄 Изменить статус":
        if not deal_id:
            send_message(token, chat_id, "Сначала выберите сделку.", DEALS_KEYBOARD)
            return True
        # Choosing a target is read-only navigation.  The actual confirmation
        # below still writes to and verifies live Megaplan, but opening this
        # menu must keep working during a CRM outage.
        result = run_deal_browser({"action": "get_cached", "deal_id": deal_id}, timeout=8)
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось прочитать статусы: {result.get('error')}", DEAL_ACTIONS_KEYBOARD)
            return True
        transitions = {f"➡️ {t['name']}": t for t in result["deal"].get("transitions", []) if t.get("enabled")}
        if not transitions:
            send_message(token, chat_id, "Для этой сделки сейчас нет доступных переходов.", DEAL_ACTIONS_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, transitions=transitions)
        keyboard = [[{"text": label}] for label in transitions]
        keyboard.append([{"text": "❌ Отмена"}])
        send_message(token, chat_id, f"Текущий статус: {result['deal'].get('status')}. Куда перевести сделку?", {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True})
        return True

    transitions = state.get("transitions") or {}
    if value in transitions:
        transition = transitions[value]
        pending_transition = {"deal_id": deal_id, "state_id": transition["state_id"], "name": transition["name"]}
        normalized_target = (transition.get("name") or "").casefold().replace("ё", "е")
        if normalized_target.strip() == "монтаж":
            update_deal_ui_state(chat_id, transitions=None, pending_transition=None,
                                 installation_pending_transition=pending_transition,
                                 installation_deal_id=str(deal_id))
            prepare_installation_after_transition(token, chat_id, deal_id)
            return True
        if "выставление счет" in normalized_target:
            existing = run_contract_invoice({"action": "list", "deal_id": str(deal_id)})
            pending_transition["invoice_ids_before"] = [item["id"] for item in existing.get("invoices") or []] if existing.get("ok") else []
            update_deal_ui_state(chat_id, pending="transition_invoice_type", pending_transition=pending_transition)
            send_message(token, chat_id, "Какой счёт сформировать после перевода сделки в статус «Выставление счета»?", TRANSITION_INVOICE_TYPE_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending_transition=pending_transition)
        keyboard = {"keyboard": [[{"text": "✅ Подтвердить"}, {"text": "❌ Отмена"}]], "resize_keyboard": True, "one_time_keyboard": True}
        send_message(token, chat_id, f"Подтвердите перевод сделки №{deal_id} в статус «{transition['name']}».", keyboard)
        return True

    if pending == "transition_invoice_type" and value in (
            "1. Полностью согласно спецификации", "2. Упрощённый согласно п.6.4", "3. Оба варианта"):
        transition = state.get("pending_transition") or {}
        transition["invoice_choice"] = {"1. Полностью согласно спецификации": "full",
                                         "2. Упрощённый согласно п.6.4": "simple",
                                         "3. Оба варианта": "both"}[value]
        if transition["invoice_choice"] in ("simple", "both"):
            update_deal_ui_state(chat_id, pending="transition_invoice_clause", pending_transition=transition)
            send_message(token, chat_id, "По какому пункту договора выставить упрощённый счёт?", CONTRACT_INVOICE_CLAUSE_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending=None, pending_transition=transition)
        keyboard = {"keyboard": [[{"text": "✅ Подтвердить"}, {"text": "❌ Отмена"}]], "resize_keyboard": True, "one_time_keyboard": True}
        send_message(token, chat_id, f"Подтвердите перевод сделки №{deal_id} и создание полного счёта по спецификации.", keyboard)
        return True
    if pending == "transition_invoice_clause":
        if not re.fullmatch(r"6\.4\.\d+", value):
            send_message(token, chat_id, "Выберите пункт 6.4.1, 6.4.2 или 6.4.3.", CONTRACT_INVOICE_CLAUSE_KEYBOARD)
            return True
        transition = state.get("pending_transition") or {}
        transition["clause"] = value
        update_deal_ui_state(chat_id, pending=None, pending_transition=transition)
        label = "упрощённого и полного счетов" if transition.get("invoice_choice") == "both" else "упрощённого счёта"
        keyboard = {"keyboard": [[{"text": "✅ Подтвердить"}, {"text": "❌ Отмена"}]], "resize_keyboard": True, "one_time_keyboard": True}
        send_message(token, chat_id, f"Подтвердите перевод сделки №{deal_id} и создание {label} по п.{value}.", keyboard)
        return True

    if value == "✅ Подтвердить" and state.get("pending_transition"):
        transition = state["pending_transition"]
        result = run_deal_browser({"action": "move_status", "deal_id": transition["deal_id"], "state_id": transition["state_id"]})
        update_deal_ui_state(chat_id, pending_transition=None, transitions=None)
        if result.get("ok"):
            send_message(token, chat_id, f"Статус действительно изменён на «{result['deal'].get('status')}».\n\n" + format_deal_card(result["deal"]), DEAL_ACTIONS_KEYBOARD)
            normalized_status = (result["deal"].get("status") or "").casefold().replace("ё", "е")
            if normalized_status.strip() == 'коммерческое предложение':
                run_deal_proposal({'action': 'enqueue', 'deal_id': str(transition['deal_id'])})
                run_singleton_background_job('proposal-status',
                    lambda: check_external_proposal_transitions(token, chat_id), token, chat_id)
            if normalized_status.strip() == "закупка":
                run_procurement_workflow({"action": "snapshot", "deal_id": str(transition["deal_id"])})
                stock = run_procurement_workflow({"action": "suggest_stock_for_deal",
                                                  "deal_id": str(transition["deal_id"]), "limit": 20})
                suggestions = stock.get("suggestions") or [] if stock.get("ok") else []
                if suggestions:
                    update_deal_ui_state(chat_id, pending="procurement_stock_confirm",
                        procurement_stock_deal_id=str(transition["deal_id"]),
                        procurement_stock_suggestions=suggestions)
                    lines = [f"• {x.get('stock_name')} → {x.get('target_name')}: "
                             f"{float(x.get('qty') or 0):g} на {bank_money(x.get('amount'))} ₽"
                             + ("; закупка другой нашей организацией" if x.get("cross_company") else "")
                             for x in suggestions]
                    send_message(token, chat_id,
                        "Перед заказом поставщику найдены подходящие нераспределённые остатки:\n\n" +
                        "\n".join(lines) + "\n\nИспользовать их? После этого Hogart получит заказ только на недостающее количество.",
                        PROCUREMENT_STOCK_CONFIRM_KEYBOARD)
                else:
                    continue_procurement_after_stock(token, chat_id, transition["deal_id"], result["deal"].get("status"))
            if normalized_status.strip() == "монтаж":
                prepare_installation_after_transition(token, chat_id, transition["deal_id"])
            if "выставление счет" in normalized_status:
                choice = transition.get("invoice_choice") or "full"
                generated = wait_for_new_deal_invoice(transition["deal_id"], transition.get("invoice_ids_before"))
                if choice == "simple" and generated and "п.6.4." not in (generated.get("line") or ""):
                    run_contract_invoice({"action": "delete", "deal_id": str(transition["deal_id"]), "invoice_id": generated["id"]})
                    generated = None
                if choice in ("full", "both"):
                    if generated:
                        send_megaplan_invoice_by_id(token, chat_id, generated["id"], DEAL_ACTIONS_KEYBOARD)
                    else:
                        create_and_send_full_invoice(token, chat_id, transition["deal_id"], DEAL_ACTIONS_KEYBOARD)
                if choice in ("simple", "both"):
                    create_and_send_contract_invoice(token, chat_id, transition["deal_id"], transition.get("clause"), DEAL_ACTIONS_KEYBOARD)
                after = run_contract_invoice({"action": "list", "deal_id": str(transition["deal_id"])})
                before_ids = {str(item) for item in transition.get("invoice_ids_before") or []}
                new_ids = [item["id"] for item in after.get("invoices") or []
                           if str(item.get("id")) not in before_ids]
                if new_ids:
                    try:
                        dispatched = dispatch_edo_documents(token, transition["deal_id"], new_ids)
                    except Exception as exc:
                        print(f"{LOG_PREFIX} EDO dispatch failed: {exc}", file=sys.stderr)
                        dispatched = {"ok": False, "error": "техническая ошибка отправки"}
                    if dispatched.get("ok"):
                        send_message(token, chat_id, "✅ Договор и новый счёт отправлены Татьяне по email и в Telegram для передачи по ЭДО.", DEAL_ACTIONS_KEYBOARD)
                    else:
                        send_message(token, chat_id, f"⚠️ Счёт создан, но комплект для ЭДО не отправлен: {dispatched.get('error')}", DEAL_ACTIONS_KEYBOARD)
        else:
            error = str(result.get("error") or "неизвестная ошибка")
            if "Мегаплан сейчас недоступен" in error or "техническая ошибка поиска сделок" in error:
                queue_deal_transition(transition, chat_id)
                send_message(token, chat_id,
                    f"⏳ Мегаплан сейчас недоступен. Подтверждённый перевод сделки №{transition['deal_id']} "
                    f"в статус «{transition['name']}» сохранён в очереди и будет выполнен один раз после восстановления связи.",
                    DEAL_ACTIONS_KEYBOARD)
            else:
                send_message(token, chat_id, f"Статус не изменён: {error}", DEAL_ACTIONS_KEYBOARD)
        return True
    if value == "❌ Отмена":
        update_deal_ui_state(chat_id, pending=None, pending_transition=None, transitions=None)
        send_message(token, chat_id, "Действие отменено.", DEAL_ACTIONS_KEYBOARD if deal_id else DEALS_KEYBOARD)
        return True

    if value == "💰 Экономика" and deal_id:
        send_current_profitability(token, chat_id, deal_id)
        return True
    if value == "👷 Монтаж по сделке" and deal_id:
        result=run_installation_workflow({"action":"get","deal_id":str(deal_id)})
        if not result.get("ok"):
            deal_result=run_deal_browser({"action":"get_cached","deal_id":str(deal_id)}, timeout=8)
            status=((deal_result.get("deal") or {}).get("status") or "").casefold().replace("ё","е")
            if status.strip()!="монтаж":
                send_message(token,chat_id,"Монтажный контур создаётся после перевода сделки в статус «Монтаж».",DEAL_ACTIONS_KEYBOARD); return True
            prepare_installation_after_transition(token,chat_id,deal_id); return True
        item=result["result"]; update_deal_ui_state(chat_id,installation_deal_id=str(deal_id))
        if item.get("status") in ("draft", "migration_draft"):
            update_deal_ui_state(chat_id,pending="installation_draft_review")
            send_message(token,chat_id,installation_summary(item),INSTALLATION_DRAFT_KEYBOARD)
        elif item.get("status")=="approved":
            update_deal_ui_state(chat_id,pending="installation_ready_to_transfer")
            send_message(token,chat_id,installation_summary(item),INSTALLATION_TRANSFER_KEYBOARD)
        else:
            send_message(token,chat_id,installation_summary(item)+f"\nПринято работ: {money(item.get('accepted_total'))}\nВыплаты, записанные в кабинете: {money(item.get('paid_gross_total',item.get('paid_total')))}\nЗачтено из этих выплат: {money(item.get('paid_total'))}\n{installation_balance_text(item)}",DEAL_ACTIONS_KEYBOARD)
        return True
    if value == "🏢 Сменить плательщика" and deal_id:
        return _start_human_payer(token, chat_id, deal_id)
    if value == "👤 Назначить исполнителя" and deal_id:
        return _start_human_executor(token, chat_id, deal_id)
    if value == "📤 Отправить по ЭДО":
        return send_offered_edo(token, chat_id, state)
    if value in ("🧾 Работа со счетами", "🧾 Выставить счёт") and deal_id:
        update_deal_ui_state(chat_id, pending="invoice_menu", invoice_downloads=None)
        send_message(token, chat_id, "Работа со счетами — можно выставить общий счёт, счёт по отдельному этапу оплаты или скачать любой ранее созданный счёт.", INVOICE_MENU_KEYBOARD)
        return True
    if value == "📋 Общий счёт по спецификации" and deal_id and pending == "invoice_menu":
        preview=run_contract_invoice({'action':'preview_full','deal_id':str(deal_id)})
        if not preview.get('ok'):
            send_message(token,chat_id,'Счёт не подготовлен: '+invoice_error_text(preview.get('error')),INVOICE_MENU_KEYBOARD); return True
        update_deal_ui_state(chat_id, pending="invoice_full_confirm",invoice_full_preview=preview)
        send_message(token, chat_id, f"Выставить общий счёт по сделке №{deal_id}?\nПлательщик: {preview['payer_name']}\nПозиций: {len(preview['rows'])}\nСумма: {bank_money(preview['total'])} ₽\nОснование: {preview['basis']}", INVOICE_FULL_CONFIRM_KEYBOARD)
        return True
    if value == "📚 Скачать счёт" and deal_id and pending == "invoice_menu":
        result = run_contract_invoice({"action": "list", "deal_id": str(deal_id)})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось получить список счетов: {result.get('error')}", INVOICE_MENU_KEYBOARD)
            return True
        invoices = result.get("invoices") or []
        if not invoices:
            send_message(token, chat_id, "У сделки пока нет счетов.", INVOICE_MENU_KEYBOARD)
            return True
        downloads, rows = {}, []
        for invoice in invoices:
            kind = "п.6.4" if invoice.get("rows_count") == 1 and "п.6.4." in (invoice.get("line") or "") else "общий"
            label = f"📥 №{invoice.get('number')} · {invoice.get('sum') or 0:g} ₽ · {kind}"
            downloads[label] = invoice
            rows.append([{"text": label}])
        rows.append([{"text": "❌ Отмена"}])
        update_deal_ui_state(chat_id, pending="invoice_download", invoice_downloads=downloads)
        send_message(token, chat_id, "Выберите счёт для скачивания:", {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})
        return True
    if value == "📦 Закупка по сделке" and deal_id:
        run_procurement_workflow({"action": "snapshot", "deal_id": str(deal_id)})
        update_deal_ui_state(chat_id, pending="procurement_menu")
        send_message(token, chat_id, "Закупка по сделке — выберите действие.", PROCUREMENT_KEYBOARD)
        return True
    if value in ("🔎 Подобрать из остатков", "найди в нераспределенных закупках товары похожие на неприобретенные в данной сделке") and deal_id:
        # Broader review search than the automatic procurement path: the owner
        # explicitly selects every variant before internal stock is consumed.
        run_procurement_workflow({"action": "snapshot", "deal_id": str(deal_id)})
        stock = run_procurement_workflow({"action": "suggest_stock_for_deal", "deal_id": str(deal_id),
                                          "limit": 12, "min_score": 0.40})
        suggestions = stock.get("suggestions") or [] if stock.get("ok") else []
        if not suggestions:
            send_message(token, chat_id, "Похожих внутренних остатков для незакрытых позиций сделки не найдено.", PROCUREMENT_KEYBOARD)
            return True
        lines = ["Возможные соответствия — выберите номера для учёта:"]
        for index, item in enumerate(suggestions, 1):
            company = "; закуплено другой нашей компанией" if item.get("cross_company") else ""
            lines.append(
                f"{index}. {item.get('stock_name')} → {item.get('target_name')}\n"
                f"   {float(item.get('qty') or 0):g} ед. на {bank_money(item.get('amount'))} ₽"
                f"; совпадение {round(float(item.get('confidence') or 0) * 100):.0f}%{company}"
            )
        rows = [[{"text": str(i)} for i in range(start, min(start + 4, len(suggestions) + 1))]
                for start in range(1, len(suggestions) + 1, 4)]
        rows.append([{"text": "❌ Отмена"}])
        update_deal_ui_state(chat_id, pending="procurement_stock_select",
                             procurement_stock_deal_id=str(deal_id),
                             procurement_stock_suggestions=suggestions)
        send_message(token, chat_id, "\n\n".join(lines) + "\n\nМожно выбрать несколько: например, 1,3.",
                     {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})
        return True
    if value in ("📋 Скачать перечень закупки", "📚 Реестр для бухгалтерии") and deal_id:
        result = publish_procurement_register(token, chat_id, deal_id)
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось сформировать закупочный реестр: {result.get('error')}", PROCUREMENT_KEYBOARD)
        return True
    if value == "📊 Статус закупок" and deal_id:
        result = run_procurement_workflow({"action": "procurement_status", "deal_id": str(deal_id)})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось получить статус закупок: {result.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        invoices = result.get("invoices") or []
        lines = [f"Статус закупок по сделке №{deal_id}:"]
        if invoices:
            lines.append("Счета поставщиков:")
            for invoice in invoices:
                lines.append(f"• №{invoice['number']} от {invoice['date']} — {invoice['supplier']}: "
                             f"{bank_money(invoice['total'])} ₽; {invoice['payment_status']} "
                             f"({bank_money(invoice['paid'])} ₽); закрывающих: {invoice.get('closing_count', 0)}")
        else:
            lines.append("Счета поставщиков пока не привязаны.")
        lines.append(f"\nПозиции: учтено по счетам {float(result.get('invoiced_qty') or 0):g} "
                     f"из {float(result.get('ordered_qty') or 0):g}; получено {float(result.get('received_qty') or 0):g}.")
        lines.append("Закрывающие документы поставщиков: " + str(result.get('closing_documents') or "не загружены"))
        send_message(token, chat_id, "\n".join(lines), PROCUREMENT_KEYBOARD)
        return True
    if value == "📎 Загрузить УПД/акт поставщика" and deal_id:
        result = run_procurement_workflow({"action": "supplier_invoices", "deal_id": str(deal_id)})
        invoices = result.get("invoices") or [] if result.get("ok") else []
        if not invoices:
            send_message(token, chat_id, "Сначала привяжите к сделке счёт поставщика.", PROCUREMENT_KEYBOARD)
            return True
        choices, rows = {}, []
        for invoice in invoices:
            label = f"№{invoice.get('number') or 'б/н'} · {str(invoice.get('supplier') or '')[:28]}"
            while label in choices: label += " ·"
            choices[label] = {"id": str(invoice.get("id") or ""), "number": invoice.get("number") or "б/н",
                              "supplier": invoice.get("supplier") or ""}
            rows.append([{"text": label}])
        rows.append([{"text": "❌ Отмена"}])
        update_deal_ui_state(chat_id, pending="supplier_closing_invoice", supplier_closing_choices=choices)
        send_message(token, chat_id, "К какому счёту поставщика относится УПД или акт?", {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})
        return True
    if pending == "supplier_closing_invoice" and value in (state.get("supplier_closing_choices") or {}):
        invoice = state["supplier_closing_choices"][value]
        update_deal_ui_state(chat_id, pending="supplier_closing_upload", supplier_closing_invoice=invoice)
        send_message(token, chat_id, f"Пришлите УПД или акт по счёту №{invoice['number']}. Поддерживаются PDF, Word и Excel.",
                     {"keyboard": [[{"text": "❌ Отмена"}]], "resize_keyboard": True, "one_time_keyboard": True})
        return True
    if value == "🏢 Организация продажи" and deal_id:
        update_deal_ui_state(chat_id, pending="procurement_selling_company")
        send_message(token, chat_id, "От какой нашей организации ведётся продажа по этой сделке?", PROCUREMENT_COMPANY_KEYBOARD)
        return True
    if pending == "procurement_selling_company" and deal_id:
        company_ids = {"ООО «КЛИВЭЛ»": "cliwell", "ООО «Инсис»": "insis",
                       "ИП Кочержинский А.В.": "kocherzhinsky_ip"}
        if value not in company_ids:
            send_message(token, chat_id, "Выберите организацию кнопкой.", PROCUREMENT_COMPANY_KEYBOARD)
            return True
        result = run_procurement_workflow({"action": "set_deal_company", "deal_id": str(deal_id),
                                           "company_id": company_ids[value]})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось сохранить организацию: {result.get('error')}", PROCUREMENT_COMPANY_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="procurement_menu")
        publish_procurement_register(token, chat_id, deal_id)
        send_message(token, chat_id, f"✅ Организация продажи по сделке №{deal_id}: {value}.", PROCUREMENT_KEYBOARD)
        return True
    if value == "🏢 Межфирменные взаиморасчёты" and deal_id:
        result = run_procurement_workflow({"action": "accounting_hints", "deal_id": str(deal_id)})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось рассчитать взаиморасчёты: {result.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        balances = result.get("balances") or []
        candidates = result.get("settlement_candidates") or []
        lines = ["Межфирменные взаиморасчёты:"]
        if balances:
            for row in balances:
                lines.append(f"• {row['debtor'].get('name')} → {row['creditor'].get('name')}: "
                             f"{bank_money(row.get('balance'))} ₽ к компенсации "
                             f"по {row.get('invoices', 0)} счёт(ам).")
        else:
            lines.append("По этой сделке межфирменной задолженности нет.")
        if not candidates:
            send_message(token, chat_id, "\n".join(lines) + "\n\nПодходящих переводов между своими организациями в выписке не найдено.", PROCUREMENT_KEYBOARD)
            return True
        choices, rows = {}, []
        lines.append("\nНайдены переводы для подтверждения:")
        for index, candidate in enumerate(candidates[:12], 1):
            label = f"{index}. {candidate['date']} · {bank_money(candidate['amount'])} ₽"
            choices[label] = candidate
            rows.append([{"text": label}])
            lines.append(f"{index}. {candidate['from']['name']} → {candidate['to']['name']}: "
                         f"{bank_money(candidate['amount'])} ₽")
        rows.append([{"text": "❌ Отмена"}])
        update_deal_ui_state(chat_id, pending="procurement_settlement_select",
                             procurement_settlement_choices=choices)
        send_message(token, chat_id, "\n".join(lines) + "\n\nВыберите перевод, который является компенсацией.",
                     {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})
        return True
    if pending == "procurement_settlement_select" and value in (state.get("procurement_settlement_choices") or {}):
        candidate = state["procurement_settlement_choices"][value]
        update_deal_ui_state(chat_id, pending="procurement_settlement_confirm", procurement_settlement_candidate=candidate)
        send_message(token, chat_id,
                     f"Подтвердить компенсацию {bank_money(candidate['amount'])} ₽:\n"
                     f"{candidate['from']['name']} → {candidate['to']['name']}\n"
                     f"Дата: {candidate['date']}?",
                     {"keyboard": [[{"text": "✅ Подтвердить компенсацию"}, {"text": "❌ Отмена"}]],
                      "resize_keyboard": True, "one_time_keyboard": True})
        return True
    if pending == "procurement_settlement_confirm" and value == "✅ Подтвердить компенсацию":
        candidate = state.get("procurement_settlement_candidate") or {}
        result = run_procurement_workflow({
            "action": "record_intercompany_settlement", "transaction_id": candidate.get("transaction_id"),
            "debtor_id": (candidate.get("from") or {}).get("id"),
            "creditor_id": (candidate.get("to") or {}).get("id"),
            "amount": candidate.get("amount"), "date": candidate.get("date") or "",
        })
        if not result.get("ok"):
            send_message(token, chat_id, "Компенсация не записана: " + str(result.get("error") or "ошибка"), PROCUREMENT_KEYBOARD)
            return True
        settlement = result.get("settlement") or {}
        update_deal_ui_state(chat_id, pending="procurement_menu", procurement_settlement_choices=None,
                             procurement_settlement_candidate=None)
        publish_procurement_register(token, chat_id, deal_id)
        allocations = settlement.get("allocations") or []
        details = "\n".join(f"• сделка №{x.get('deal_id')}: {bank_money(x.get('amount'))} ₽" for x in allocations)
        send_message(token, chat_id, "✅ Компенсация учтена во взаиморасчётах." +
                     ("\nРаспределение:\n" + details if details else ""), PROCUREMENT_KEYBOARD)
        return True
    if value == "🏦 Сверить оплаты поставщикам" and deal_id:
        result = run_procurement_workflow({"action": "reconcile_bank"})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось сверить оплаты: {result.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        own = [item for item in result.get("matched") or [] if str(item.get("deal_id")) == str(deal_id)]
        review = result.get("review") or []
        message = f"Сверка завершена. Новых оплат по сделке №{deal_id}: {len(own)}. Требуют ручной проверки: {len(review)}."
        if own:
            message += "\n\n" + "\n".join(f"• {bank_money(item['amount'])} ₽ — {item['status']}" for item in own)
        send_message(token, chat_id, message, PROCUREMENT_KEYBOARD)
        return True
    if value == "📥 Отметить поступление" and deal_id:
        result = run_procurement_workflow({"action": "snapshot", "deal_id": str(deal_id)})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось прочитать закупку: {result.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        choices, rows = {}, []
        for item in (result.get("snapshot") or {}).get("items") or []:
            remaining = float(item.get("remaining_qty") or 0)
            if remaining <= 1e-9:
                continue
            label = f"📥 {(item.get('sku') or item.get('name') or '')[:34]} · осталось {remaining:g}"
            while label in choices: label += " ·"
            choices[label] = item
            rows.append([{"text": label}])
        if not rows:
            send_message(token, chat_id, "Все позиции закупки уже отмечены как полученные.", PROCUREMENT_KEYBOARD)
            return True
        rows.append([{"text": "❌ Отмена"}])
        update_deal_ui_state(chat_id, pending="procurement_receipt_item", procurement_receipt_choices=choices)
        send_message(token, chat_id, "Выберите поступившую позицию:", {"keyboard": rows, "resize_keyboard": True, "one_time_keyboard": True})
        return True
    if pending == "procurement_receipt_item" and value in (state.get("procurement_receipt_choices") or {}):
        item = state["procurement_receipt_choices"][value]
        update_deal_ui_state(chat_id, pending="procurement_receipt_qty", procurement_receipt_item=item)
        send_message(token, chat_id,
                     f"Позиция: {item.get('name')}\nОсталось получить: {float(item.get('remaining_qty') or 0):g} {item.get('unit') or ''}.\n\nНажмите «Получено полностью» или введите фактически полученное количество.",
                     PROCUREMENT_RECEIPT_QTY_KEYBOARD)
        return True
    if pending == "procurement_receipt_qty":
        item = state.get("procurement_receipt_item") or {}
        if value == "✅ Получено полностью":
            qty = float(item.get("remaining_qty") or 0)
        else:
            try: qty = float(value.replace(" ", "").replace(",", "."))
            except ValueError:
                send_message(token, chat_id, "Введите количество числом либо нажмите «✅ Получено полностью».", PROCUREMENT_RECEIPT_QTY_KEYBOARD)
                return True
        result = run_procurement_workflow({"action": "record_receipt", "deal_id": str(deal_id),
                                           "offer_row_id": item.get("offer_row_id"), "qty": qty})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось записать поступление: {result.get('error')}", PROCUREMENT_RECEIPT_QTY_KEYBOARD)
            return True
        saved = result["item"]
        run_deal_browser({"action": "record_procurement_receipt", "deal_id": str(deal_id),
                          "name": saved.get("name"), "qty": qty, "unit": saved.get("unit")})
        update_deal_ui_state(chat_id, pending="procurement_menu", procurement_receipt_item=None,
                             procurement_receipt_choices=None)
        publish_procurement_register(token, chat_id, deal_id)
        send_message(token, chat_id,
                     f"✅ Поступление записано: {saved.get('name')} — {qty:g} {saved.get('unit') or ''}. Осталось: {float(saved.get('remaining_qty') or 0):g}.",
                     PROCUREMENT_KEYBOARD)
        return True
    if value == "✅ Проверить готовность закупки" and deal_id:
        run_procurement_workflow({"action": "snapshot", "deal_id": str(deal_id)})
        result = run_procurement_workflow({"action": "closure_check", "deal_id": str(deal_id)})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось проверить закупку: {result.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        if result.get("closed"):
            send_message(token, chat_id, "✅ Закупка уже закрыта.", PROCUREMENT_KEYBOARD)
            return True
        if not result.get("ready"):
            labels = {"invoice": "нет счёта/фактической себестоимости", "receipt": "не получено", "payment": "не оплачено", "closing": "не загружен УПД/акт"}
            lines = []
            for problem in (result.get("problems") or [])[:20]:
                suffix = " ₽" if problem.get("type") == "payment" else ""
                lines.append(f"• {problem.get('name')} — {labels.get(problem.get('type'), 'нужна проверка')}: {float(problem.get('missing') or 0):g}{suffix}")
            extra = f"\n…и ещё {len(result.get('problems') or []) - 20}" if len(result.get("problems") or []) > 20 else ""
            send_message(token, chat_id, "Закупку пока нельзя закрыть:\n\n" + "\n".join(lines) + extra, PROCUREMENT_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="procurement_close_confirm")
        send_message(token, chat_id,
                     f"Все {result.get('items_count')} позиций обеспечены счетами, оплачены и получены. Закрыть закупку по сделке №{deal_id}?",
                     PROCUREMENT_CLOSE_KEYBOARD)
        return True
    if pending == "procurement_close_confirm" and value == "✅ Закрыть закупку":
        result = run_procurement_workflow({"action": "close", "deal_id": str(deal_id)})
        if not result.get("ok"):
            send_message(token, chat_id, f"Закупка не закрыта: {result.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        recorded = run_deal_browser({"action": "close_procurement", "deal_id": str(deal_id)})
        if not recorded.get("ok"):
            send_message(token, chat_id, f"Закупка проверена, но запись в Мегаплан не выполнена: {recorded.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="procurement_menu")
        publish_procurement_register(token, chat_id, deal_id)
        send_message(token, chat_id, "✅ Закупка закрыта и зафиксирована в истории сделки. Сделку можно передавать на следующий этап.", PROCUREMENT_KEYBOARD)
        return True
    if value in ("🧾 Учесть счёт", "📎 Загрузить счёт поставщика") and deal_id:
        update_deal_ui_state(chat_id, pending="invoice_file",
                             supplier_invoice_deal_id=str(deal_id),
                             supplier_invoice_queue=None,
                             supplier_invoice_preview=None)
        send_message(token, chat_id, f"Пришлите счёт поставщика для сделки №{deal_id} и при необходимости подпишите, какую позицию обновить.", DEAL_ACTIONS_KEYBOARD)
        return True
    if pending == "supplier_invoice_confirm" and value == "🔗 Сопоставить с позицией сделки":
        queue = state.get("supplier_invoice_queue") or []
        base_spec = (queue[0] if queue else state.get("supplier_invoice_preview")) or {}
        sources = base_spec.get("unallocated") or []
        ledger = fetch_deal_ledger(base_spec.get("deal_id")) or []
        targets = []
        for row in ledger:
            available = max(0.0, float(row.get("qty") or 0) - float(row.get("consumed_qty") or 0))
            if available <= 1e-9 or (float(row.get("cost_work") or 0) > 0 and
                                    float(row.get("cost_material") or 0) <= 0):
                continue
            targets.append({**row, "available": available})
        if not sources:
            send_message(token, chat_id, "Нераспределённых строк в счёте нет.", SUPPLIER_DISTRIBUTION_KEYBOARD)
            return True
        if not targets:
            send_message(token, chat_id, "В сделке нет незакупленных материальных позиций для сопоставления. Можно отнести остаток на прочую себестоимость.", SUPPLIER_DISTRIBUTION_KEYBOARD)
            return True
        source_lines = [f"{i}. {x.get('name') or x.get('source_name')} — {float(x.get('qty') or 0):g}, {bank_money(x.get('amount'))} ₽"
                        for i, x in enumerate(sources, 1)]
        target_lines = [f"{i}. {x.get('name')} — требуется {float(x.get('available') or 0):g} {x.get('unit') or ''}"
                        for i, x in enumerate(targets, 1)]
        update_deal_ui_state(chat_id, pending="supplier_manual_mapping",
                             supplier_mapping_sources=sources, supplier_mapping_targets=targets)
        send_message(token, chat_id,
            "Строки счёта:\n" + "\n".join(source_lines) +
            "\n\nНезакупленные позиции сделки:\n" + "\n".join(target_lines) +
            "\n\nВведите соответствия в формате `строка счёта=позиция сделки`, например:\n1=4; 2=7\n\n"
            "Одну строку счёта можно разделить между позициями: `1=4; 1=7`. "
            "Сумма распределится пропорционально количеству; остаток сохранится нераспределённым.",
            {"keyboard": [[{"text": "❌ Отмена"}]], "resize_keyboard": True})
        return True
    if pending == "supplier_manual_mapping":
        queue = state.get("supplier_invoice_queue") or []
        base_spec = (queue[0] if queue else state.get("supplier_invoice_preview")) or {}
        sources = state.get("supplier_mapping_sources") or []
        targets = state.get("supplier_mapping_targets") or []
        pairs = re.findall(r"(\d+)\s*=\s*(\d+)", value)
        if not pairs:
            send_message(token, chat_id, "Не удалось прочитать соответствия. Пример: 1=4; 2=7")
            return True
        try:
            base_spec, mapped_lines = apply_manual_supplier_mapping(base_spec, sources, targets, pairs)
        except ValueError as exc:
            send_message(token, chat_id, str(exc))
            return True
        status = run_procurement_workflow({"action": "invoice_allocation_status", "invoice_spec": base_spec})
        preview, error = prepare_supplier_invoice_preview(base_spec, status)
        if error:
            send_message(token, chat_id, f"Сопоставление не принято: {error}", SUPPLIER_DISTRIBUTION_KEYBOARD)
            return True
        base_spec["_allocation_preview"] = preview
        plan = run_procurement_workflow({"action": "suggest_distribution", "invoice_spec": base_spec, "limit": 10})
        if plan.get("ok"): base_spec["_distribution_plan"] = plan
        new_queue = list(queue); new_queue[0] = base_spec
        update_deal_ui_state(chat_id, pending="supplier_invoice_confirm", supplier_invoice_queue=new_queue,
                             supplier_invoice_preview=base_spec, supplier_mapping_sources=None,
                             supplier_mapping_targets=None)
        send_message(token, chat_id, "Сопоставление подготовлено:\n" + "\n".join(mapped_lines) +
                     f"\n\nОсталось нераспределённых строк: {len(base_spec['unallocated'])}. Данные ещё не записаны.",
                     SUPPLIER_DISTRIBUTION_KEYBOARD)
        return True
    if pending == "supplier_invoice_confirm" and value == "🧾 В прочую себестоимость сделки":
        queue = state.get("supplier_invoice_queue") or []
        base_spec = (queue[0] if queue else state.get("supplier_invoice_preview")) or {}
        rows = base_spec.get("unallocated") or []
        if not rows:
            send_message(token, chat_id, "Нераспределённых строк в счёте нет.", SUPPLIER_DISTRIBUTION_KEYBOARD)
            return True
        expenses = list(base_spec.get("additional_expenses") or [])
        expenses.extend({"source_line_key": x.get("source_line_key"),
                         "source_sku": x.get("source_sku") or x.get("sku"),
                         "source_name": x.get("name") or x.get("source_name"),
                         "source_qty": float(x.get("qty") or 0),
                         "source_total": float(x.get("amount") or 0),
                         "qty": float(x.get("qty") or 0), "amount": float(x.get("amount") or 0),
                         "category": "прочая себестоимость",
                         "reason": "позиция счёта поставщика вне спецификации сделки"} for x in rows)
        base_spec["additional_expenses"] = expenses; base_spec["unallocated"] = []
        base_spec.pop("_distribution_plan", None)
        status = run_procurement_workflow({"action": "invoice_allocation_status", "invoice_spec": base_spec})
        preview, error = prepare_supplier_invoice_preview(base_spec, status)
        if error:
            send_message(token, chat_id, f"Не удалось подготовить прочую себестоимость: {error}", SUPPLIER_DISTRIBUTION_KEYBOARD)
            return True
        base_spec["_allocation_preview"] = preview
        new_queue = list(queue); new_queue[0] = base_spec
        update_deal_ui_state(chat_id, pending="supplier_misc_confirm", supplier_invoice_queue=new_queue,
                             supplier_invoice_preview=base_spec)
        amount = sum(float(x.get("amount") or 0) for x in expenses)
        send_message(token, chat_id,
                     f"На прочую фактическую себестоимость сделки №{base_spec.get('deal_id')} будет отнесено "
                     f"{len(rows)} позиции на {bank_money(amount)} ₽. Коммерческие позиции сделки не изменятся.",
                     SUPPLIER_MISC_CONFIRM_KEYBOARD)
        return True
    if pending == "supplier_misc_confirm" and value == "✅ Подтвердить прочую себестоимость":
        queue = state.get("supplier_invoice_queue") or []
        base_spec = (queue[0] if queue else state.get("supplier_invoice_preview")) or {}
        result = apply_distributed_invoice_spec(base_spec)
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось записать прочую себестоимость: {result.get('error')}",
                         SUPPLIER_MISC_CONFIRM_KEYBOARD)
            return True
        remove_supplier_invoice_preview(chat_id, base_spec)
        amount = sum(float(x.get("amount") or 0) for x in base_spec.get("additional_expenses") or [])
        send_message(token, chat_id,
                     f"✅ Прочая фактическая себестоимость сделки №{base_spec.get('deal_id')} увеличена на "
                     f"{bank_money(amount)} ₽. " + supplier_completion.summary([result]), PROCUREMENT_KEYBOARD)
        return True
    if pending == "supplier_distribution_edit":
        queue = state.get("supplier_invoice_queue") or []
        base_spec = (queue[0] if queue else state.get("supplier_invoice_preview")) or {}
        plan = base_spec.get("_distribution_plan") or {}
        sources = base_spec.get("unallocated") or []
        if not sources:
            send_message(token, chat_id, "В этом счёте нет остатка для изменения.", SUPPLIER_DISTRIBUTION_KEYBOARD)
            return True
        requests = []
        if len(sources) == 1:
            requests = [(sources[0], value)]
        else:
            for line in value.splitlines():
                if ":" not in line:
                    continue
                label, allocation_text = line.split(":", 1)
                needle = normalized_search_text(label)
                matched_sources = [x for x in sources if needle and needle in normalized_search_text(
                    x.get("name") or x.get("source_name") or x.get("source_line_key"))]
                if len(matched_sources) == 1:
                    requests.append((matched_sources[0], allocation_text))
        if len(requests) != len(sources):
            examples = "\n".join(f"{(x.get('name') or x.get('source_name') or '')[:35]}: №901=10"
                                 for x in sources)
            send_message(token, chat_id,
                "Для нескольких товаров укажите отдельную строку для каждого остатка:\n" + examples,
                {"keyboard": [[{"text": "❌ Отмена"}]], "resize_keyboard": True})
            return True
        original_suggestions = plan.get("suggestions") or []
        changed, stock_remainders = [], []
        for source, allocation_text in requests:
            pairs = re.findall(r"№?\s*(\d+)\s*=\s*([0-9]+(?:[.,][0-9]+)?)", allocation_text)
            source_key = str(source.get("source_line_key") or "")
            by_deal = {str(x.get("deal_id")): x for x in original_suggestions
                       if str(x.get("source_line_key") or "") == source_key}
            remaining_qty = float(source.get("qty") or 0); remaining_amount = float(source.get("amount") or 0)
            for target_id, qty_text in pairs:
                candidate = by_deal.get(target_id); qty = float(qty_text.replace(",", "."))
                if not candidate or qty <= 0 or qty > float(candidate.get("needed") or 0) + 1e-9 or qty > remaining_qty + 1e-9:
                    send_message(token, chat_id,
                        f"Количество для сделки №{target_id} по позиции «{source.get('name')}» недопустимо.",
                        SUPPLIER_DISTRIBUTION_KEYBOARD)
                    return True
                amount = (remaining_amount if abs(qty - remaining_qty) <= 1e-9 else
                          round(float(source.get("amount") or 0) * qty / float(source.get("qty") or 1), 2))
                changed.append({**candidate, "qty": qty, "amount": amount})
                remaining_qty -= qty; remaining_amount = round(remaining_amount - amount, 2)
            if remaining_qty > 1e-9 or remaining_amount > 0.01:
                stock_remainders.append({**source, "qty": remaining_qty, "amount": remaining_amount})
        plan["suggestions"] = changed
        plan["inventory_remainder"] = stock_remainders
        base_spec["_distribution_plan"] = plan
        new_queue = list(queue); new_queue[0] = base_spec
        update_deal_ui_state(chat_id, pending="supplier_invoice_confirm", supplier_invoice_queue=new_queue,
                             supplier_invoice_preview=base_spec)
        lines = [f"• №{x['deal_id']} — {float(x['qty']):g}" for x in changed]
        stock_qty = sum(float(x.get("qty") or 0) for x in stock_remainders)
        send_message(token, chat_id, "Распределение изменено:\n" + ("\n".join(lines) or "• другие сделки не выбраны") +
                     f"\n• в нераспределённые — {stock_qty:g}", SUPPLIER_DISTRIBUTION_KEYBOARD)
        return True
    if pending == "supplier_distribution_exclusion_reason":
        queue = state.get("supplier_invoice_queue") or []
        base_spec = (queue[0] if queue else state.get("supplier_invoice_preview")) or {}
        if len(value.strip()) < 3:
            send_message(token, chat_id, "Причина слишком короткая. Опишите, почему остаток исключается.")
            return True
        results = [apply_distributed_invoice_spec(x) for x in distribution_specs(base_spec, include_nearby=False)]
        if not all(x.get("ok") for x in results):
            failed = next(x for x in results if not x.get("ok"))
            send_message(token, chat_id, f"Не удалось применить текущую часть счёта: {failed.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        excluded_rows = base_spec.get("unallocated") or []
        recorded = run_procurement_workflow({"action": "record_excluded_remainder", "invoice_spec": base_spec,
            "rows": excluded_rows, "reason": value.strip(), "actor": str(chat_id)})
        if not recorded.get("ok"):
            send_message(token, chat_id, f"Текущая часть применена, но исключение остатка не записано: {recorded.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        remove_supplier_invoice_preview(chat_id, base_spec)
        send_message(token, chat_id, "✅ Текущая сделка обновлена. Остаток исключён из учёта с указанной причиной.\n" + supplier_completion.summary(results), PROCUREMENT_KEYBOARD)
        return True
    distribution_actions = {
        "✅ Подтвердить всё распределение", "✅ Только в текущую сделку",
        "📦 Весь остаток в нераспределённые", "✏️ Изменить распределение",
        "🔍 Показать другие сделки", "🚫 Не учитывать остаток",
    }
    if pending == "supplier_invoice_confirm" and value in distribution_actions:
        queue = state.get("supplier_invoice_queue") or []
        base_spec = (queue[0] if queue else state.get("supplier_invoice_preview")) or {}
        if not base_spec:
            send_message(token, chat_id, "Черновик распределения не найден. Загрузите счёт повторно.", PROCUREMENT_KEYBOARD)
            return True
        if value == "🔍 Показать другие сделки":
            nearby_ids = refresh_nearby_procurement_snapshots(base_spec.get("deal_id"), 30)
            expanded = run_procurement_workflow({"action": "suggest_distribution", "invoice_spec": base_spec,
                                                 "limit": 30, "candidate_deal_ids": nearby_ids})
            if expanded.get("ok"):
                base_spec["_distribution_plan"] = expanded
                # Replace the queued head atomically enough for this single-chat worker.
                remaining_queue = list(queue); remaining_queue[0] = base_spec
                update_deal_ui_state(chat_id, supplier_invoice_queue=remaining_queue,
                                     supplier_invoice_preview=base_spec)
                lines = [f"• №{x.get('deal_id')} — {float(x.get('qty') or 0):g}: {x.get('target_name')}"
                         for x in expanded.get("suggestions") or []]
                send_message(token, chat_id, "Дополнительные подходящие сделки:\n" +
                             ("\n".join(lines) if lines else "не найдены"), SUPPLIER_DISTRIBUTION_KEYBOARD)
            else:
                send_message(token, chat_id, f"Не удалось расширить поиск: {expanded.get('error')}", SUPPLIER_DISTRIBUTION_KEYBOARD)
            return True
        if value == "✏️ Изменить распределение":
            update_deal_ui_state(chat_id, pending="supplier_distribution_edit")
            send_message(token, chat_id,
                "Введите желаемые количества по сделкам одной строкой, например:\n"
                "№901=40; №905=20\n\n"
                "Неуказанное количество останется в нераспределённых закупках. "
                "Для счёта с несколькими остаточными строками укажите также название перед двоеточием.",
                {"keyboard": [[{"text": "❌ Отмена"}]], "resize_keyboard": True})
            return True
        if value == "🚫 Не учитывать остаток":
            update_deal_ui_state(chat_id, pending="supplier_distribution_exclusion_reason")
            send_message(token, chat_id,
                "Укажите причину, по которой остаток счёта не должен учитываться в закупочном реестре.",
                {"keyboard": [[{"text": "❌ Отмена"}]], "resize_keyboard": True})
            return True

        include_nearby = value == "✅ Подтвердить всё распределение"
        specs = distribution_specs(base_spec, include_nearby=include_nearby)
        # Validate every part before the first CRM write. Without this gate a
        # repeated invoice can partially update one deal and fail on the next.
        for allocation_spec in specs:
            preflight = run_procurement_workflow({"action": "prepare_invoice_allocation",
                                                  "invoice_spec": allocation_spec})
            if not preflight.get("ok"):
                send_message(token, chat_id,
                    "Распределение не применено: " + str(preflight.get("error") or "не пройдена проверка") +
                    ". Черновик устарел; загрузите счёт заново — уже учтённые строки будут исключены автоматически.",
                    PROCUREMENT_KEYBOARD)
                return True
        send_message(token, chat_id, "💾 Применяю подтверждённое распределение и пересчитываю экономику сделок...")
        results = []
        for allocation_spec in specs:
            result = apply_distributed_invoice_spec(allocation_spec)
            results.append(result)
            if not result.get("ok"):
                break
        if not all(x.get("ok") for x in results):
            failed = next(x for x in results if not x.get("ok"))
            send_message(token, chat_id,
                f"Распределение остановлено на сделке №{failed.get('deal_id')}: {failed.get('error')}. "
                "Уже подтверждённые предыдущие части повторно применять не нужно.", PROCUREMENT_KEYBOARD)
            return True
        plan = base_spec.get("_distribution_plan") or {}
        stock_rows = (plan.get("inventory_remainder") or []) if include_nearby else (base_spec.get("unallocated") or [])
        if stock_rows:
            stored = run_procurement_workflow({"action": "put_unallocated_stock", "invoice_spec": base_spec,
                                               "rows": stock_rows, "actor": str(chat_id)})
            if not stored.get("ok"):
                send_message(token, chat_id, f"Сделки обновлены, но остаток не сохранён: {stored.get('error')}", PROCUREMENT_KEYBOARD)
                return True
        remove_supplier_invoice_preview(chat_id, base_spec)
        deal_labels = ", ".join(f"№{x['deal_id']}" for x in results)
        stock_qty = sum(float(x.get("qty") or 0) for x in stock_rows)
        send_message(token, chat_id,
            ((f"✅ Счёт распределён по сделкам: {deal_labels}.\n" if deal_labels else
              "✅ Новых распределений по сделкам не записано.\n"))
            + (f"📦 В нераспределённые закупки помещено: {stock_qty:g}.\n" if stock_qty else "")
            + supplier_completion.summary(results), PROCUREMENT_KEYBOARD)
        return True
    if pending == "supplier_invoice_confirm" and value == "✅ Применить счёт поставщика":
        queue = state.get("supplier_invoice_queue") or []
        invoice_apply_spec = (queue[0] if queue else state.get("supplier_invoice_preview")) or {}
        has_current_allocation = bool(invoice_apply_spec.get("updates") or invoice_apply_spec.get("additions") or
                                      invoice_apply_spec.get("additional_expenses"))
        if not has_current_allocation and invoice_apply_spec.get("unallocated"):
            stored = run_procurement_workflow({"action": "put_unallocated_stock",
                                               "invoice_spec": invoice_apply_spec,
                                               "rows": invoice_apply_spec.get("unallocated") or [],
                                               "actor": str(chat_id)})
            if not stored.get("ok"):
                send_message(token, chat_id,
                             f"Не удалось сохранить остаток счёта: {stored.get('error')}",
                             SUPPLIER_DISTRIBUTION_KEYBOARD)
                return True
            remove_supplier_invoice_preview(chat_id, invoice_apply_spec)
            qty = sum(float(x.get("qty") or 0) for x in invoice_apply_spec.get("unallocated") or [])
            amount = sum(float(x.get("amount") or x.get("source_total") or 0)
                         for x in invoice_apply_spec.get("unallocated") or [])
            send_message(token, chat_id,
                         "✅ Уже учтённые строки повторно не записаны.\n"
                         f"📦 В нераспределённые закупки сохранено: {qty:g} ед. на {bank_money(amount)} ₽.",
                         PROCUREMENT_KEYBOARD)
            return True
        # Recheck immediately before writing to Megaplan: another queued worker may
        # have registered the same external document since the preview was shown.
        preflight = run_procurement_workflow({"action": "prepare_invoice_allocation",
                                              "invoice_spec": invoice_apply_spec})
        if not preflight.get("ok"):
            send_message(token, chat_id, f"Счёт не применён: {preflight.get('error')}", PROCUREMENT_KEYBOARD)
            return True
        send_message(token, chat_id, "💾 Привязываю счёт и записываю фактическую себестоимость...")
        result = (run_supplier_invoice_apply(invoice_apply_spec)
                  if invoice_apply_spec.get("updates") or invoice_apply_spec.get("additions")
                  else {"ok": True, "url": f"https://cclimat.megaplan.ru/deals/{deal_id}/card/",
                        "updated_count": 0, "added_count": 0})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось применить счёт поставщика: {result.get('error')}", SUPPLIER_INVOICE_CONFIRM_KEYBOARD)
            return True
        run_procurement_workflow({"action": "record_invoice", "deal_id": str(deal_id),
                                  "invoice_spec": invoice_apply_spec, "result": result})
        invoice_doc = invoice_apply_spec.get("invoice") or {}
        source_path = invoice_doc.get("source_path")
        upload_notice = ""
        if source_path:
            uploaded = run_deal_browser({"action": "upload_supplier_invoice", "deal_id": str(deal_id),
                                         "path": source_path, "number": invoice_doc.get("number"),
                                         "supplier": invoice_doc.get("supplier")})
            if not uploaded.get("ok"):
                print(f"{LOG_PREFIX} supplier invoice upload failed: {uploaded}", file=sys.stderr)
                upload_notice = ("\n\n⚠️ Себестоимость записана, но исходный файл счёта не прикреплён: "
                                 f"{uploaded.get('error') or 'ошибка загрузки'}. Повторно применять счёт не нужно.")
            else:
                upload_notice = "\n\n📎 Исходный файл счёта сохранён в карточке сделки."
                archived = run_financial_archive({
                    "deal_id": str(deal_id), "path": source_path, "category": "supplier_invoice",
                    "document_number": invoice_doc.get("number") or "",
                    "display_name": (f"Счёт поставщика №{invoice_doc.get('number') or 'б н'} "
                                     f"от {invoice_doc.get('date') or 'без даты'} — "
                                     f"{invoice_doc.get('supplier') or 'Поставщик'}"),
                })
                if archived.get("ok"):
                    upload_notice += " Копия также сохранена в финансовом архиве OneDrive."
                else:
                    upload_notice += " ⚠️ Копию в OneDrive сохранить не удалось; повторно применять счёт не нужно."
        else:
            upload_notice = "\n\n⚠️ Исходный файл счёта не прикреплён: путь к файлу отсутствует."
        economics = build_and_store_profitability(deal_id)
        if economics.get("ok"):
            upload_notice += "\n📊 Экономика пересчитана, актуальный файл заменён в карточке сделки."
            try:
                os.remove(economics["path"])
            except OSError:
                pass
        else:
            upload_notice += ("\n⚠️ Счёт применён, но файл экономики не обновлён: "
                              f"{economics.get('error') or 'техническая ошибка'}.")
        procurement_register = build_and_store_procurement_register(deal_id)
        if procurement_register.get("ok"):
            upload_notice += "\n📦 Перечень закупки обновлён и заменён в карточке сделки."
            try:
                os.remove(procurement_register["path"])
                os.rmdir(os.path.dirname(procurement_register["path"]))
            except OSError:
                pass
        else:
            upload_notice += ("\n⚠️ Счёт применён, но перечень закупки не обновлён: "
                              f"{procurement_register.get('error') or 'техническая ошибка'}.")
        remaining = remove_supplier_invoice_preview(chat_id, invoice_apply_spec)
        suffix = (f"\n\nВ очереди остался ещё {len(remaining)} счёт. Проверьте и примените следующий."
                  if remaining else "")
        hints = run_procurement_workflow({"action": "accounting_hints", "deal_id": str(deal_id)})
        if hints.get("ok"):
            invoice_number = str((invoice_apply_spec.get("invoice") or {}).get("number") or "")
            relevant = [x.get("text") for x in hints.get("hints") or []
                        if not invoice_number or f"№{invoice_number}" in (x.get("text") or "")]
            if relevant:
                suffix += "\n\n📒 Для бухгалтерии:\n" + "\n".join(f"• {x}" for x in relevant)
        send_message(token, chat_id, format_supplier_invoice_apply_summary(result) + suffix + upload_notice,
                     SUPPLIER_INVOICE_CONFIRM_KEYBOARD if remaining else PROCUREMENT_KEYBOARD)
        return True
    if value == "📑 Работа с договором" and deal_id:
        send_message(token, chat_id, "Работа с договором — выберите действие.", CONTRACT_KEYBOARD)
        return True
    if value == "🏢 Добавить плательщика" and deal_id:
        update_deal_ui_state(
            chat_id, pending="payer_card_file", payer_card=None, payer_result=None,
            payer_target_deal_id=str(deal_id), deal_creation_active=False,
        )
        send_message(
            token, chat_id,
            f"Пришлите карточку реквизитов плательщика для сделки №{deal_id} в PDF, Word или Excel. "
            "После проверки бот создаст плательщика у клиента этой сделки и сразу его привяжет.",
            PAYER_UPLOAD_KEYBOARD,
        )
        return True
    if value == "⬅️ Назад к сделке" and deal_id:
        select_deal(token, chat_id, deal_id)
        return True
    if value == "🏢 Смена нашей фирмы" and deal_id:
        update_deal_ui_state(chat_id, pending='contract_selling_company')
        send_message(token, chat_id, 'Выберите организацию для новых договоров и счетов этой сделки.',
                     {'keyboard': [[{'text': 'ООО «КЛИВЭЛ»'}], [{'text': 'ИП Кочержинский А.В.'}],
                                   [{'text': '❌ Отмена'}]], 'resize_keyboard': True})
        return True
    if pending == 'contract_selling_company' and deal_id:
        choices = {'ООО «КЛИВЭЛ»': 'cliwell', 'ИП Кочержинский А.В.': 'kocherzhinsky_ip'}
        if value not in choices:
            send_message(token, chat_id, 'Выберите организацию кнопкой.')
            return True
        result = run_procurement_workflow({'action': 'set_deal_company', 'deal_id': str(deal_id),
                                           'company_id': choices[value]})
        if not result.get('ok'):
            send_message(token, chat_id, f"Не удалось сохранить организацию: {result.get('error')}")
            return True
        cleanup_generated_contract(state)
        update_deal_ui_state(chat_id, pending=None, generated_contract=None, contract_invoice_preview=None)
        send_message(token, chat_id, f'Организация для новых документов сделки №{deal_id}: {value}. '
                     'Можно сформировать договор и затем выставить новый счёт. Ранее выпущенные документы сохраняются.',
                     CONTRACT_KEYBOARD)
        return True
    if value in ("📝 Подготовить договор", "👁 Проверить данные договора") and deal_id:
        update_deal_ui_state(chat_id, contract_deal_id=str(deal_id), deal_creation_active=False)
        prepare_contract_preview(token, chat_id, deal_id)
        return True
    if value == "🧾 Выставить счёт по договору" and deal_id:
        update_deal_ui_state(chat_id, pending="contract_invoice_clause", contract_invoice_preview=None)
        send_message(token, chat_id, "По какому пункту последнего загруженного договора выставить счёт?", CONTRACT_INVOICE_CLAUSE_KEYBOARD)
        return True
    if value == "✅ Сформировать договор" and deal_id:
        cleanup_generated_contract(current_deal_ui_state(chat_id))
        update_deal_ui_state(chat_id, generated_contract=None)
        signer = current_deal_ui_state(chat_id).get("contract_signatory") or {}
        signer_payer_id = current_deal_ui_state(chat_id).get("contract_signatory_payer_id")
        send_message(token, chat_id, "📑 Формирую Word без подписи и подписанный PDF...")
        result = run_contract_builder({"action": "generate", "deal_id": deal_id,
                                       "customer_signatory": signer,
                                       "customer_signatory_payer_id": signer_payer_id,
                                       "expected_fingerprint":current_deal_ui_state(chat_id).get('contract_data_fingerprint')})
        if not result.get("ok"):
            details = "\n- " + "\n- ".join(result.get("missing") or []) if result.get("missing") else ""
            send_message(token, chat_id, f"Не удалось сформировать договор: {result.get('error')}{details}", CONTRACT_KEYBOARD)
            return True
        send_document(token, chat_id, result["docx_path"], "Договор — Word без подписи и печати", os.path.basename(result["docx_path"]))
        send_document(token, chat_id, result["pdf_path"], "Договор — подписанный PDF", os.path.basename(result["pdf_path"]))
        update_deal_ui_state(chat_id, pending="contract_upload", generated_contract={
            "deal_id": str(deal_id),
            "docx_path": result["docx_path"],
            "pdf_path": result["pdf_path"],
        })
        send_message(
            token, chat_id,
            f"Оба файла сформированы. Загрузить Word и подписанный PDF в сделку №{deal_id}?",
            CONTRACT_UPLOAD_KEYBOARD,
        )
        return True
    if value == "✅ Загрузить договоры в сделку" and deal_id:
        generated = current_deal_ui_state(chat_id).get("generated_contract") or {}
        if generated.get("deal_id") != str(deal_id):
            send_message(token, chat_id, "Нет подготовленного комплекта договоров для этой сделки.", CONTRACT_KEYBOARD)
            return True
        send_message(token, chat_id, f"📤 Загружаю Word и подписанный PDF в сделку №{deal_id}...")
        result = run_deal_browser({
            "action": "upload_contracts", "deal_id": str(deal_id),
            "paths": [generated.get("docx_path"), generated.get("pdf_path")],
        })
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось загрузить договоры: {result.get('error')}", CONTRACT_UPLOAD_KEYBOARD)
            return True
        filenames = "\n".join(f"- {item.get('name')}" for item in result.get("files") or [])
        archive_errors = []
        for contract_path in (generated.get("docx_path"), generated.get("pdf_path")):
            if not contract_path:
                continue
            archived = run_financial_archive({"deal_id": str(deal_id), "path": contract_path,
                                               "category": "contract_client"})
            if not archived.get("ok"):
                archive_errors.append(archived.get("error") or "ошибка OneDrive")
        cleanup_generated_contract(current_deal_ui_state(chat_id))
        update_deal_ui_state(chat_id, pending=None, generated_contract=None)
        archive_notice = ("\n📁 Копии договоров сохранены в финансовом архиве OneDrive."
                          if not archive_errors else
                          "\n📁 Договоры загружены в Мегаплан. Передача в OneDrive ещё не подтверждена; исходники сохранены в очереди архива.")
        send_message(token, chat_id, f"Договоры загружены и подтверждены в сделке №{deal_id}.\n{filenames}{archive_notice}", DEAL_ACTIONS_KEYBOARD)
        return True
    if value == "❌ Не загружать" and deal_id:
        cleanup_generated_contract(current_deal_ui_state(chat_id))
        update_deal_ui_state(chat_id, pending=None, generated_contract=None)
        send_message(token, chat_id, "Файлы оставлены только в Telegram и в сделку не загружались.", DEAL_ACTIONS_KEYBOARD)
        return True
    if value in ("📑 Получить договор", "📎 Получить договор из Мегаплана") and deal_id:
        result = run_deal_browser({"action": "get_contract", "deal_id": deal_id})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось получить договор: {result.get('error')}", DEAL_ACTIONS_KEYBOARD)
            return True
        send_document(token, chat_id, result["path"], f"Договор из сделки №{deal_id}", result.get("filename"))
        try:
            os.remove(result["path"])
        except OSError:
            pass
        return True
    if value == "📥 Получить счёт":
        if not deal_id:
            send_message(token, chat_id, "Сначала откройте сделку, затем нажмите «📥 Получить счёт».", DEALS_KEYBOARD)
        else:
            send_latest_megaplan_invoice(token, chat_id, deal_id)
        return True
    if value in ("🛠 Ведомость работ", "📋 Монтажная ведомость", "📄 Позиции сделки") and deal_id:
        ledger = fetch_deal_ledger(deal_id)
        if ledger is None:
            send_message(token, chat_id, "Не удалось получить актуальные позиции сделки.", DEAL_ACTIONS_KEYBOARD)
            return True
        if value in ("🛠 Ведомость работ", "📋 Монтажная ведомость"):
            installation=run_installation_workflow({"action":"get","deal_id":str(deal_id)})
            installation_path=(installation.get("result") or {}).get("workbook_path") if installation.get("ok") else None
            if installation_path and os.path.isfile(installation_path):
                send_document(token,chat_id,installation_path,"Актуальная монтажная ведомость",
                              f"Монтажная ведомость - сделка {deal_id}.xlsx")
                return True
            deal_result = run_deal_browser({"action": "get_cached", "deal_id": str(deal_id)}, timeout=8)
            if not deal_result.get("ok"):
                send_message(token, chat_id, "Не удалось определить текущий статус сделки.", DEAL_ACTIONS_KEYBOARD)
                return True
            deal = deal_result.get("deal") or {}
            path = build_deal_work_statement_xlsx(
                deal_id, deal.get("client") or deal_client_name(deal_id),
                deal.get("status"), ledger,
            )
        else:
            send_message(token, chat_id, format_deal_positions(deal_id, ledger), DEAL_BASIC_KEYBOARD)
            path = build_spec_review_xlsx(deal_client_name(deal_id), ledger)
        if path:
            caption = "Актуальные позиции сделки" if value == "📄 Позиции сделки" else "Монтажная ведомость по текущим позициям сделки"
            filename = (f"Позиции сделки {deal_id}.xlsx" if value == "📄 Позиции сделки"
                        else f"Монтажная ведомость — сделка {deal_id}.xlsx")
            send_document(token, chat_id, path, caption, filename)
            try:
                os.remove(path)
            except OSError:
                pass
        else:
            send_message(token, chat_id, "Не удалось сформировать Excel.", DEAL_ACTIONS_KEYBOARD)
        return True
    return False


def format_deal_positions(deal_id, ledger, limit=40):
    """Positions as a person reads them in chat; the Excel file carries the economics."""
    if not ledger:
        return f"В сделке №{deal_id} нет позиций."
    lines, total = [f"Позиции сделки №{deal_id}:"], Decimal("0")
    for index, item in enumerate(ledger, 1):
        try:
            qty = Decimal(str(item.get("qty") or 0))
            price = Decimal(str(item.get("sell_price") if item.get("sell_price") is not None else item.get("unit_price") or 0))
        except (InvalidOperation, ValueError):
            qty, price = Decimal("0"), Decimal("0")
        amount = qty * price
        total += amount
        if index <= limit:
            lines.append(f"{index}. {item.get('name') or 'без названия'} — {qty.normalize():f} {item.get('unit') or 'шт'} × "
                         f"{bank_money(price)} ₽ = {bank_money(amount)} ₽")
    if len(ledger) > limit:
        lines.append(f"… и ещё {len(ledger) - limit} поз. — полный список в Excel.")
    lines.append(f"Итого: {bank_money(total)} ₽")
    return "\n".join(lines)


def send_document(token, chat_id, path, caption=None, filename=None):
    # Use curl for reliable multipart upload instead of hand-rolling it.
    # filename overrides what Telegram shows as the attachment's name (defaults to path's
    # own basename, e.g. an ugly tempfile name - pass it explicitly when path is a temp file).
    document_field = f"document=@{path};filename={filename}" if filename else f"document=@{path}"
    cmd = [
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{token}/sendDocument",
        "-F", f"chat_id={chat_id}",
        "-F", document_field,
    ]
    if caption:
        cmd += ["-F", f"caption={caption[:1024]}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        resp = json.loads(result.stdout or "{}")
        if not resp.get("ok"):
            print(f"{LOG_PREFIX} sendDocument failed for {path}: {resp}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"{LOG_PREFIX} sendDocument error for {path}: {e}", file=sys.stderr)
        return False


# Brands with no contractPrice (cost) data on this Hogart account, per real product
# checks (2026-08-26): Casarte (Haier's own premium sub-line) always came back with
# contractPrice: None across every SKU spot-checked, unlike plain Haier which reliably
# has one (~0.6x defaultPrice). Owner's call: since we can't compute real margin for
# these, don't offer them on equal footing - push them to the bottom of search results
# (and thus more likely to fall past MAX_HOGART_ITEMS_IN_PROMPT's truncation) rather
# than trusting the model to notice/deprioritize a null field on its own every time -
# that's exactly the kind of "should have noticed" behavior that's failed to hold up
# reliably today (see the search-stall incidents above).
LOW_PRIORITY_HOGART_BRANDS = {"casarte"}


def hogart_live_search(keyword):
    """Run the fixed, non-shell hogart API client on Claude's behalf (official REST API,
    no browser). Returns {"keyword": ..., "items": [...]} or None."""
    script = os.path.join(HOGART_DIR, "hogart_api.py")
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, script, "search", keyword],
            cwd=HOGART_DIR,
            capture_output=True,
            text=True,
            timeout=HOGART_SEARCH_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(f"{LOG_PREFIX} hogart_live_search timed out for {keyword!r}", file=sys.stderr)
        return None
    if result.returncode != 0:
        print(f"{LOG_PREFIX} hogart_live_search failed for {keyword!r}: {result.stderr[-800:]}", file=sys.stderr)
        return None
    try:
        items = json.loads(result.stdout)
        items.sort(key=lambda it: (it.get("brand") or {}).get("name", "").strip().lower() in LOW_PRIORITY_HOGART_BRANDS)
        return {"keyword": keyword, "count": len(items), "items": items}
    except Exception as e:
        print(f"{LOG_PREFIX} hogart_live_search bad JSON for {keyword!r}: {e}", file=sys.stderr)
        return None


def handle_invoice_cancellation(token, chat_id, msg):
    result = invoice_tasks.cancel(chat_id, msg.get("text", ""), msg.get("message_id", 0))
    if result is None:
        return False
    state, result = result
    if result.get("ambiguous"):
        send_message(token, chat_id, "У нескольких счетов совпадает короткий номер. Укажите полный номер отменяемого счёта.")
        return True
    statement_document_context.exclude_documents(chat_id, result.get("cancelled", []))
    current = invoice_tasks.active(state)
    ui = current_deal_ui_state(chat_id)
    queue = [p for p in ui.get("supplier_invoice_queue", [])
             if not invoice_tasks.same_number((p.get("invoice") or {}).get("number", ""), result["number"])]
    updates = {"conversation_invoice": current}
    preview = ui.get("supplier_invoice_preview") or {}
    if invoice_tasks.same_number((preview.get("invoice") or {}).get("number", ""), result["number"]):
        updates.update(supplier_invoice_queue=queue, supplier_invoice_preview=queue[0] if queue else None,
                       pending="supplier_invoice_confirm" if queue else None)
    update_deal_ui_state(chat_id, **updates)
    reply = f"Счёт №{result['number']} исключён из дальнейшей обработки. Файл сохранён."
    if current:
        reply += "\n\nПродолжаем счёт №" + current['number'] + ". " + invoice_tasks.question(current)
    send_message(token, chat_id, reply)
    return True


def needs_fresh_hogart_search(user_text):
    """Whether this new user message must not reuse an earlier Hogart response."""
    value = str(user_text or "")
    return bool(HOGART_BRAND_RE.search(value) and HOGART_LIVE_INTENT_RE.search(value))


def explicit_catalog_request(user_text):
    return catalog_conversation.explicit(user_text)


def extract_hogart_searches(reply_text):
    keywords = [m.strip() for m in HOGART_SEARCH_RE.findall(reply_text)][:MAX_HOGART_SEARCHES_PER_TURN]
    clean_text = HOGART_SEARCH_RE.sub("", reply_text).strip()
    return clean_text, keywords


def daichi_live_search(filters):
    """Run daichi_search.py against the cached catalog (see DAICHI_SEARCH_RE above).
    `filters` is the parsed JSON dict Claude sent - keys: keyword, goodtype,
    inverter_only, capacity_kw, tolerance, in_stock_only, max_price, limit. Returns
    {"filters": ..., "count": N, "items": [...]} or None on failure."""
    script = os.path.join(DAICHI_DIR, "daichi_search.py")
    args = [REPORT_VENV_PY, script]
    if filters.get("keyword"):
        args.append(str(filters["keyword"]))
    if filters.get("goodtype"):
        args += ["--goodtype", str(filters["goodtype"])]
    if filters.get("inverter_only"):
        args.append("--inverter-only")
    if filters.get("capacity_kw") is not None:
        args += ["--capacity-kw", str(filters["capacity_kw"])]
    if filters.get("tolerance") is not None:
        args += ["--tolerance", str(filters["tolerance"])]
    if filters.get("in_stock_only"):
        args.append("--in-stock-only")
    if filters.get("max_price") is not None:
        args += ["--max-price", str(filters["max_price"])]
    if filters.get("limit"):
        args += ["--limit", str(filters["limit"])]
    try:
        result = subprocess.run(
            args, cwd=DAICHI_DIR, capture_output=True, text=True, timeout=DAICHI_SEARCH_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(f"{LOG_PREFIX} daichi_live_search timed out for {filters!r}", file=sys.stderr)
        return None
    if result.returncode != 0:
        print(f"{LOG_PREFIX} daichi_live_search failed for {filters!r}: {result.stderr[-800:]}", file=sys.stderr)
        return None
    try:
        items = json.loads(result.stdout)
        return {"filters": filters, "count": len(items), "items": items}
    except Exception as e:
        print(f"{LOG_PREFIX} daichi_live_search bad JSON for {filters!r}: {e}", file=sys.stderr)
        return None


def extract_daichi_searches(reply_text):
    filters_list = []
    for m in DAICHI_SEARCH_RE.findall(reply_text)[:MAX_DAICHI_SEARCHES_PER_TURN]:
        try:
            filters_list.append(json.loads(m))
        except Exception as e:
            print(f"{LOG_PREFIX} DAICHI_SEARCH block was not valid JSON: {e}", file=sys.stderr)
    clean_text = DAICHI_SEARCH_RE.sub("", reply_text).strip()
    return clean_text, filters_list


def download_image_url(url):
    """Download an https image URL to a temp file. Only hogart's own image host is allowed."""
    if not re.match(r"^https://[a-zA-Z0-9.-]*\.hogart\.ru/", url):
        print(f"{LOG_PREFIX} refusing to download image from untrusted host: {url}", file=sys.stderr)
        return None
    try:
        ext = os.path.splitext(url)[1][:5] or ".jpg"
        fd, path = __import__("tempfile").mkstemp(suffix=ext, prefix="hogart-img-")
        os.close(fd)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp, open(path, "wb") as f:
            f.write(resp.read())
        return path
    except Exception as e:
        print(f"{LOG_PREFIX} failed to download image {url}: {e}", file=sys.stderr)
        return None


INCOMING_DIR = os.path.join(os.path.expanduser("~/hogart-scraper"), "incoming")
MAX_INCOMING_DOC_BYTES = 20 * 1024 * 1024
# 2026-08-24: supplier invoices/КП arrive in whatever format the supplier used, not
# just PDF - owner explicitly asked for Word/Excel/image-as-file support too. Claude's
# Read tool natively handles PDF/images/notebooks but NOT binary Office XML formats
# (.doc/.docx/.xls/.xls) - those get converted to Markdown text first (convert_document.py,
# markitdown under ~/.report-venv) and the resulting .md is what Claude actually reads.
DOCUMENT_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".bmp")
CONVERT_EXTENSIONS = (".doc", ".docx", ".xls", ".xlsx")
TEXT_EXTENSIONS = (".txt",)
DOCUMENT_CONVERT_TIMEOUT_SEC = 60


def convert_document_to_text(path):
    """Shell out to convert_document.py (markitdown, ~/.report-venv) for a Word/Excel
    file Claude's Read tool can't parse directly. Returns the sibling ".md" path, or
    None on failure (caller falls back to the original path with a warning - better to
    let Claude try and fail visibly than silently drop the file)."""
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(BASE_DIR, "convert_document.py")],
            input=json.dumps({"path": path}, ensure_ascii=False),
            capture_output=True, text=True, timeout=DOCUMENT_CONVERT_TIMEOUT_SEC,
        )
        parsed = json.loads(result.stdout.strip().splitlines()[-1])
        if parsed.get("ok"):
            return parsed["text_path"]
        print(f"{LOG_PREFIX} convert_document_to_text failed for {path}: {parsed.get('error')}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"{LOG_PREFIX} convert_document_to_text error for {path}: {e}", file=sys.stderr)
        return None


def download_telegram_document(token, document):
    """Download a Telegram-uploaded document (supplier invoice/КП/price list - PDF,
    Word, Excel, or an image sent "as file") to a local staging dir, so Claude can read
    it. Size-capped. Office documents (.doc/.docx/.xls/.xlsx) are converted to Markdown
    text before being handed to Claude - see convert_document_to_text()."""
    file_name = document.get("file_name") or "document"
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in DOCUMENT_EXTENSIONS and ext not in CONVERT_EXTENSIONS and ext not in TEXT_EXTENSIONS:
        return None, "Принимаю PDF, Word, Excel, TXT, JPEG, PNG, BMP - этот формат не поддерживается."
    if (document.get("file_size") or 0) > MAX_INCOMING_DOC_BYTES:
        return None, "Файл слишком большой (лимит 20MB)."

    try:
        info = tg_api(token, "getFile", {"file_id": document["file_id"]})
        if not info.get("ok"):
            return None, "Не удалось получить файл от Telegram."
        tg_path = info["result"]["file_path"]
    except Exception as e:
        print(f"{LOG_PREFIX} getFile failed: {e}", file=sys.stderr)
        return None, "Не удалось получить файл от Telegram."

    os.makedirs(INCOMING_DIR, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Zа-яА-Я0-9._-]+", "_", file_name)
    local_path = os.path.join(INCOMING_DIR, f"{int(time.time())}-{uuid.uuid4().hex}-{safe_name}")
    try:
        url = f"https://api.telegram.org/file/bot{token}/{tg_path}"
        with urllib.request.urlopen(url, timeout=60) as resp, open(local_path, "wb") as f:
            f.write(resp.read(MAX_INCOMING_DOC_BYTES + 1))
        if os.path.getsize(local_path) > MAX_INCOMING_DOC_BYTES:
            os.remove(local_path)
            return None, "Файл слишком большой (лимит 20MB)."
    except Exception as e:
        print(f"{LOG_PREFIX} document download failed: {e}", file=sys.stderr)
        return None, "Не удалось скачать файл."

    if ext in CONVERT_EXTENSIONS:
        text_path = convert_document_to_text(local_path)
        if text_path:
            return text_path, None
        return None, "Не удалось прочитать содержимое файла (Word/Excel) - попробуйте прислать как PDF."
    return local_path, None


def download_telegram_photo(token, photo_sizes):
    """Download a Telegram photo message (e.g. a screenshot of a spec table pasted
    directly, not sent "as file") to a local staging dir, so Claude can Read it -
    Claude Code's Read tool reads images natively (vision), same as it reads PDFs
    natively, no OCR step needed. `photo_sizes` is Telegram's array of PhotoSize
    objects (same photo at different resolutions, ascending) - take the largest.
    Added 2026-08-23: the message-type filter previously only accepted "text"/
    "document", so a pasted screenshot (Telegram sends compressed photos as "photo",
    never "document", unless the user explicitly sends "as file") was silently
    dropped - no log line at all, which is why the first real attempt looked like it
    just vanished."""
    largest = max(photo_sizes, key=lambda p: p.get("width", 0) * p.get("height", 0))
    if (largest.get("file_size") or 0) > MAX_INCOMING_DOC_BYTES:
        return None, "Файл слишком большой (лимит 20MB)."
    try:
        info = tg_api(token, "getFile", {"file_id": largest["file_id"]})
        if not info.get("ok"):
            return None, "Не удалось получить файл от Telegram."
        tg_path = info["result"]["file_path"]
    except Exception as e:
        print(f"{LOG_PREFIX} getFile failed: {e}", file=sys.stderr)
        return None, "Не удалось получить файл от Telegram."

    os.makedirs(INCOMING_DIR, exist_ok=True)
    ext = os.path.splitext(tg_path)[1] or ".jpg"
    local_path = os.path.join(INCOMING_DIR, f"{int(time.time())}-{uuid.uuid4().hex}-photo{ext}")
    try:
        url = f"https://api.telegram.org/file/bot{token}/{tg_path}"
        with urllib.request.urlopen(url, timeout=60) as resp, open(local_path, "wb") as f:
            f.write(resp.read(MAX_INCOMING_DOC_BYTES + 1))
        if os.path.getsize(local_path) > MAX_INCOMING_DOC_BYTES:
            os.remove(local_path)
            return None, "Файл слишком большой (лимит 20MB)."
        return local_path, None
    except Exception as e:
        print(f"{LOG_PREFIX} document download failed: {e}", file=sys.stderr)
        return None, "Не удалось скачать файл."


def download_telegram_media(token, media, default_name="video.mp4"):
    if (media.get("file_size") or 0) > MAX_INCOMING_DOC_BYTES:
        return None, "Файл слишком большой. Максимальный размер одного фото или видео — 20 МБ."
    try:
        info=tg_api(token,"getFile",{"file_id":media["file_id"]})
        if not info.get("ok"): return None,"Не удалось получить файл от Telegram."
        tg_path=info["result"]["file_path"]
        os.makedirs(INCOMING_DIR,exist_ok=True)
        ext=os.path.splitext(tg_path)[1] or os.path.splitext(default_name)[1] or ".bin"
        path=os.path.join(INCOMING_DIR,f"{int(time.time())}-{uuid.uuid4().hex}-media{ext}")
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{tg_path}",timeout=120) as resp, open(path,"wb") as out:
            out.write(resp.read(MAX_INCOMING_DOC_BYTES+1))
        if os.path.getsize(path)>MAX_INCOMING_DOC_BYTES:
            os.remove(path); return None,"Файл слишком большой. Максимальный размер — 20 МБ."
        return path,None
    except Exception as exc:
        print(f"{LOG_PREFIX} media download failed: {exc}",file=sys.stderr)
        return None,"Не удалось скачать медиафайл."


def extract_image_urls(reply_text):
    urls = [m.strip() for m in ATTACH_URL_RE.findall(reply_text)][:MAX_IMAGE_DOWNLOADS_PER_TURN]
    clean_text = ATTACH_URL_RE.sub("", reply_text).strip()
    return clean_text, urls


def send_photo(token, chat_id, path, caption=None):
    cmd = [
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{token}/sendPhoto",
        "-F", f"chat_id={chat_id}",
        "-F", f"photo=@{path}",
    ]
    if caption:
        cmd += ["-F", f"caption={caption[:1024]}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        resp = json.loads(result.stdout or "{}")
        if not resp.get("ok"):
            print(f"{LOG_PREFIX} sendPhoto failed for {path}: {resp}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"{LOG_PREFIX} sendPhoto error for {path}: {e}", file=sys.stderr)
        return False


def extract_build_kp(reply_text):
    """Pull a KP JSON block out without ever exposing the bridge protocol to Telegram.

    The documented protocol is BEGIN/END.  Older/resumed model sessions can still emit
    ``BUILD_KP: {...}``; accept that form defensively and remove the exact JSON span.
    """
    m = BUILD_KP_RE.search(reply_text)
    if m:
        clean_text = (reply_text[:m.start()] + reply_text[m.end():]).strip()
        try:
            return clean_text, json.loads(m.group(1))
        except Exception as e:
            print(f"{LOG_PREFIX} BUILD_KP block was not valid JSON: {e}", file=sys.stderr)
            return clean_text, {"__invalid__": True}
    legacy = BUILD_KP_LEGACY_RE.search(reply_text)
    if not legacy:
        return reply_text, None
    try:
        spec, consumed = json.JSONDecoder().raw_decode(reply_text[legacy.end():].lstrip())
        json_start = legacy.end() + (len(reply_text[legacy.end():]) - len(reply_text[legacy.end():].lstrip()))
        clean_text = (reply_text[:legacy.start()] + reply_text[json_start + consumed:]).strip()
        return clean_text, spec
    except Exception as e:
        # The payload is service data even when malformed.  Drop it rather than leak
        # internal JSON/SKUs to the customer-facing chat.
        print(f"{LOG_PREFIX} legacy BUILD_KP block was not valid JSON: {e}", file=sys.stderr)
        return reply_text[:legacy.start()].strip(), {"__invalid__": True}


def sanitize_service_protocol(reply_text):
    """Last-resort output firewall for unconsumed model-to-bridge commands."""
    marker = re.search(
        r"(?m)^\s*(?:BUILD_KP(?:_BEGIN)?\s*:|BUILD_KP_BEGIN\b|"
        r"CREATE_MEGAPLAN_DEAL_BEGIN\b|SUPPLIER_INVOICE_APPLY_BEGIN\b|"
        r"PAYER_CARD_APPLY_BEGIN\b|APPLY_WORK_STATEMENT_BEGIN\b|"
        r"UPDATE_KEMIX_PRICES_BEGIN\b|SYNC_DEAL_KP_BEGIN\b|"
        r"UPDATE_MEGAPLAN_DEAL\b|ADD_DEAL_ITEM_BEGIN\b|[A-Z][A-Z0-9_]*_BEGIN\b)", reply_text,
    )
    if marker:
        print(f"{LOG_PREFIX} stripped unconsumed service protocol from user reply", file=sys.stderr)
        prefix=reply_text[:marker.start()].strip()
        if 'REGISTER_CONTRACTOR_PAYMENT' in marker.group(0) or not prefix:
            reply_text = 'Автоматическое действие не выполнено: получена неподдерживаемая служебная команда. Для выплаты монтажнику откройте «🧰 Отчёт монтажника» → «💳 Учесть выплату». Финансовую запись нужно подтвердить в этом разделе.'
        else:
            reply_text=prefix
    reply_text = re.sub(
        r"(?m)^\s*(?:HOGART_SEARCH|DAICHI_SEARCH|RECENT_DEALS_REQUEST|"
        r"DEAL_LEDGER_REQUEST|RESEND_DEAL_REVIEW|WORK_STATEMENT_REQUEST|"
        r"PROFITABILITY_REQUEST|TAX_CHOICE_REQUEST|CREATE_KP_DEAL_CONFIRM)\s*:?.*$",
        "", reply_text,
    )
    return reply_text.strip()


def extract_sync_deal_kp(reply_text):
    match = SYNC_DEAL_KP_RE.search(reply_text)
    if not match:
        return reply_text, None
    clean = SYNC_DEAL_KP_RE.sub("", reply_text).strip()
    try:
        return clean, json.loads(match.group(1))
    except Exception as exc:
        print(f"{LOG_PREFIX} SYNC_DEAL_KP block was not valid JSON: {exc}", file=sys.stderr)
        return clean, {"__invalid__": True}


def run_sync_deal_kp(spec):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "replace_deal_from_kp.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=240,
        )
        lines = (result.stdout or "").strip().splitlines()
        return json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ Мегаплана"}
    except Exception as exc:
        print(f"{LOG_PREFIX} sync deal with KP failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка обновления сделки"}


def run_deal_proposal(spec):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, 'deal_proposal.py')],
            input=json.dumps(spec), capture_output=True, text=True, timeout=180,
        )
        return json.loads(result.stdout)
    except Exception:
        return {'ok': False, 'error': 'Не удалось завершить формирование КП. Повторная попытка не создаст новую сделку.'}


def send_deal_proposal(token, chat_id, deal_id, automatic=False, recipient=None):
    result = run_deal_proposal({'action': 'publish', 'deal_id': str(deal_id), 'recipient': recipient})
    if not result.get('ok'):
        send_message(token, chat_id, 'КП не сформировано: ' + result.get('error', 'ошибка проверки'), DEAL_ACTIONS_KEYBOARD)
        return False
    caption = f"КП КЛИВЭЛ по сделке №{deal_id}: {result['count']} позиций, {bank_money(result['total'])} ₽. Копия сохранена в сделке."
    sent = send_document(token, chat_id, result['path'], caption)
    if sent and automatic:
        run_deal_proposal({'action': 'ack', 'deal_id': str(deal_id)})
    if not sent:
        send_message(token, chat_id, 'КП сохранено в сделке, но Telegram не принял файл. Нажмите «📄 КП по сделке» для повторного получения.')
    return sent


def try_begin_proposal_recipient(chat_id, deal_id, expected_revision=None):
    """An unsolicited stage event must not overwrite another active workflow."""
    global UI_CONTEXT
    store=ui_state_store()
    if expected_revision is None:expected_revision=store.current(chat_id).get('_revision',0)
    claimed=store.begin_idle(chat_id,expected_revision,
        {'pending':'proposal_recipient','proposal_deal_id':str(deal_id)})
    if claimed is None:return False
    UI_CONTEXT=claimed
    return True


def check_external_proposal_transitions(token, chat_id):
    revision=ui_state_store().current(chat_id).get('_revision',0)
    result = run_deal_proposal({'action': 'scan'})
    for item in result.get('results') or []:
        if item.get('ok'):
            button = f"📄 КП для сделки №{item['deal_id']}"
            if try_begin_proposal_recipient(chat_id, item['deal_id'],revision):
                sent = send_message(token, chat_id,
                    f"📄 Сделка №{item['deal_id']} переведена на стадию «Коммерческое предложение». Кому адресовать КП?\nУкажите имя/ФИО или готовое обращение, например: «Уважаемая Татьяна,».", PAYER_UPLOAD_KEYBOARD)
            else:
                sent = send_message(token, chat_id,
                    f"📄 Для сделки №{item['deal_id']} на стадии «Коммерческое предложение» нужно указать адресата КП. Текущее действие и его кнопки сохранены. Когда закончите, откройте эту сделку и нажмите «📄 КП по сделке».")
            if sent:
                run_deal_proposal({'action': 'ack', 'deal_id': item['deal_id'], 'event': item.get('event')})
        else:
            print(f"{LOG_PREFIX} auto proposal pending for deal {item.get('deal_id')}", file=sys.stderr)
            if item.get('notify'):
                send_message(token, chat_id, f"⚠️ Сделка №{item.get('deal_id')} на стадии «Коммерческое предложение», но КП пока не сформировано. Повторю автоматически. Причину проверки можно получить кнопкой «📄 КП по сделке».")


KP_JOBS_DIR = os.path.join(BASE_DIR, "kp_jobs")

def run_generate_kp(spec, chat_id=None):
    spec = copy.deepcopy(spec)
    for index, variant in enumerate(spec.get("variants") or [], 1):
        if not variant.get("label"):
            variant["label"] = variant.get("title") or f"Вариант {index}"
    def execute(path):
        return subprocess.run([REPORT_VENV_PY, os.path.join(HOGART_DIR, "generate_kp.py"), path],
            cwd=HOGART_DIR, capture_output=True, text=True, timeout=GENERATE_KP_TIMEOUT_SEC)
    return kp_jobs.run(spec, chat_id or _model_chat_id(), KP_JOBS_DIR, execute)

def retry_failed_kp(token, chat_id, text):
    if not re.fullmatch(r"(?i)\s*(?:повтори|повторить|пересобери)\s+кп[.!]?\s*", text or ""):
        return False
    job = kp_jobs.latest_failed(chat_id, KP_JOBS_DIR)
    if not job:
        return False
    send_message(token, chat_id, "Повторяю сохранённое КП с прежними моделями, количеством и метражом.")
    result = run_generate_kp(job["spec"], chat_id)
    if result.get("ok"):
        send_document(token, chat_id, result["path"], "Коммерческое предложение")
        send_document(token, chat_id, result["economics_xlsx_path"], "Экономика — внутренний файл")
    else:
        send_message(token, chat_id, result.get("error", "КП пока не готово; задание сохранено."))
    return True


def should_auto_create_kp_deal(user_text):
    """A revision is a document edit, not authorization for a duplicate CRM deal."""
    value = user_text or ""
    revision = bool(re.search(
        r"(?i)\b(?:пересобер\w*|передела\w*|обнови\w*)\b.*\bкп\b|"
        r"\bкп\b.*\b(?:пересобер\w*|передела\w*|обнови\w*)\b", value,
    ))
    explicit = bool(re.search(
        r"(?i)\b(?:созда(?:й|ть)|завед(?:и|ите|ти))\b.{0,30}\bсделк", value,
    ))
    # A proposal is a document, never implicit authority to create a CRM deal.
    return explicit


def build_megaplan_description(kp_spec, kp_result):
    """Plain-text summary of the KP request, for the Megaplan deal's description field
    (the only free-text field that reliably sticks on create - see megaplan_api.py).
    generate_kp.py's result is a list of independent "variants" (2026-08-26) - a single
    unlabeled variant (the common case) prints exactly like before; multiple prints each
    as its own labeled block, own total, never summed together (these are alternatives
    the client picks ONE of, not one combined order)."""
    lines = [f"КП сформирован ботом. Клиент: {kp_spec.get('client', '?')}", ""]
    for v in kp_result.get("variants", []):
        if v.get("label"):
            lines.append(f"=== {v['label']} ===")
        for it in v.get("items", []):
            kind = it.get("type", "equipment")
            if kind == "equipment":
                lines.append(f"{it['sku']} x{it['qty']} — {it['unit_price']:.2f} руб/шт ({it.get('availability', '?')})")
            elif kind == "install":
                lines.append(f"  + монтаж ({it.get('capacity_kw')} кВт) x{it['qty']} — {it['unit_price']:.2f} руб/шт")
            elif kind == "freon_line":
                lines.append(f"  + доп. фреоновая магистраль, {it.get('length_m')} м — {it['unit_price_per_m']:.2f} руб/м")
        lines.append(f"Итого по варианту: {v.get('total', 0):.2f} руб.")
        lines.append("")
    return "\n".join(lines).strip()


def create_megaplan_deal(kp_spec, kp_result):
    """Shell out to the fixed megaplan_api.py CLI (stdin, never argv - see project
    memory on ARG_MAX). Best-effort: a Megaplan outage shouldn't block sending the KP
    itself, so failures here are logged, not raised."""
    if RUNTIME_ACTIVE:
        # The old path creates a description-only deal with no confirmed client
        # or specification. All new deals now go through the reviewed wizard.
        return None
    description = build_megaplan_description(kp_spec, kp_result)
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "megaplan_api.py"), "create-kp-deal"],
            cwd=MEGAPLAN_DIR, input=json.dumps({"description": description}, ensure_ascii=False),
            capture_output=True, text=True, timeout=MEGAPLAN_TIMEOUT_SEC,
        )
        parsed = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as e:
        print(f"{LOG_PREFIX} megaplan deal creation failed: {e}", file=sys.stderr)
        return None
    if not parsed.get("ok"):
        print(f"{LOG_PREFIX} megaplan deal creation error: {parsed}", file=sys.stderr)
        return None
    return parsed


def extract_create_megaplan_deal(reply_text):
    """Pull a CREATE_MEGAPLAN_DEAL_BEGIN/END JSON block out of the reply, if present."""
    m = CREATE_MEGAPLAN_DEAL_RE.search(reply_text)
    if not m:
        return reply_text, None
    clean_text = CREATE_MEGAPLAN_DEAL_RE.sub("", reply_text).strip()
    try:
        payload = m.group(1).strip()
        payload = re.sub(r'^```(?:json)?\s*|\s*```$', '', payload, flags=re.I).strip()
        spec = json.loads(payload)
        if not isinstance(spec, dict):
            raise ValueError('ожидался объект сделки')
    except Exception as e:
        print(f"{LOG_PREFIX} CREATE_MEGAPLAN_DEAL block was not valid JSON: {e}", file=sys.stderr)
        return clean_text, {"__invalid__": True}
    return clean_text, spec


def normalize_create_deal_spec(raw_spec):
    """Normalize model aliases at the trust boundary before any CRM write.

    The marker protocol documents canonical names, but a model can still emit common
    business synonyms.  Accept those deterministically and reject incomplete data
    here instead of letting a child process fail with a KeyError and empty stdout.
    """
    raw = dict(raw_spec or {})
    client_name = str(raw.get("client_name") or raw.get("client") or "").strip()
    from document_tax_policy import creation_rate
    tax_value = creation_rate(raw)
    normalized_tax = tax_mode_from_text(str(tax_value)) or str(tax_value or "").strip().casefold()
    if normalized_tax not in ("none", "22", "5", "pending"):
        normalized_tax = "pending"
    items = []
    errors = []
    for index, source in enumerate(raw.get("items") or [], start=1):
        item = dict(source or {})
        name = str(item.get("name") or "").strip()
        qty = item.get("qty", item.get("quantity"))
        unit_price = item.get("unit_price", item.get("sale_price", item.get("sell_price")))
        if not name:
            errors.append(f"позиция {index}: отсутствует наименование")
        try:
            qty = float(qty)
            if not math.isfinite(qty) or qty <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"позиция {index}: количество должно быть больше нуля")
            qty = None
        if unit_price is not None:
            try:
                unit_price = float(unit_price)
                if not math.isfinite(unit_price) or unit_price < 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"позиция {index}: цена должна быть неотрицательным числом")
                unit_price = None
        normalized = {**item, "name": name, "qty": qty}
        normalized.pop("quantity", None)
        normalized.pop("sale_price", None)
        normalized.pop("sell_price", None)
        if unit_price is not None:
            normalized["unit_price"] = unit_price
        items.append(normalized)
    if not client_name:
        errors.append("не указан клиент")
    if not items:
        errors.append("не указаны позиции сделки")
    if errors:
        return None, "; ".join(errors)
    description = raw.get("description") or raw.get("name")
    spec = {
        **raw,
        "client_name": client_name,
        "client_kind": raw.get("client_kind") or "company",
        "tax_mode": normalized_tax,
        "items": items,
    }
    spec.pop("client", None)
    spec.pop("name", None)
    if description:
        spec["description"] = description
    return spec, None


def extract_payer_card_apply(reply_text):
    """Pull a confirmed payer-card write block out of the model reply."""
    m = PAYER_CARD_APPLY_RE.search(reply_text)
    if not m:
        return reply_text, None
    clean_text = PAYER_CARD_APPLY_RE.sub("", reply_text).strip()
    try:
        spec = json.loads(m.group(1))
    except Exception as e:
        print(f"{LOG_PREFIX} PAYER_CARD_APPLY block was not valid JSON: {e}", file=sys.stderr)
        return clean_text, {"__invalid__": True}
    return clean_text, spec


def run_payer_card_apply(spec):
    """Validate, create/reuse and link a payer through the fixed Megaplan CLI."""
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "payer_manager.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=PAYER_CARD_APPLY_TIMEOUT_SEC,
        )
        lines = (result.stdout or "").strip().splitlines()
        return json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ Мегаплана"}
    except Exception as e:
        print(f"{LOG_PREFIX} run_payer_card_apply failed: {e}", file=sys.stderr)
        return {"ok": False, "error": "внутренняя ошибка при сохранении плательщика"}


def payer_card_summary(card):
    labels = (
        ("name", "Наименование"), ("inn", "ИНН"), ("kpp", "КПП"),
        ("ogrn", "ОГРН"), ("legalAddress", "Юридический адрес"),
        ("currentAccount", "Расчётный счёт"), ("bank", "Банк"),
        ("bik", "БИК"), ("correspondentAccount", "Корреспондентский счёт"),
        ("director", "Руководитель"),
    )
    return "\n".join(f"{label}: {card[key]}" for key, label in labels if card.get(key))


def begin_payer_card_flow(token, chat_id, path):
    """Intercept a requisites card before the general LLM document flow."""
    try:
        card = requisites_card.parse_document(path)
    except Exception as exc:
        print(f"{LOG_PREFIX} requisites-card parse failed: {exc}", file=sys.stderr)
        return False
    if not card:
        return False
    state = current_deal_ui_state(chat_id)
    target_deal_id = str(state.get("payer_target_deal_id") or "")
    if target_deal_id:
        # This file was uploaded from an already selected deal. Its client is
        # the only allowed parent, so never ask the user to type it again.
        deal_result = run_deal_browser({"action": "get", "deal_id": target_deal_id})
        if not deal_result.get("ok"):
            send_message(token, chat_id,
                         f"Карточка распознана, но не удалось проверить сделку №{target_deal_id}: "
                         f"{deal_result.get('error')}. Повторите попытку из карточки сделки.",
                         CONTRACT_KEYBOARD)
            return True
        client_name = str((deal_result.get("deal") or {}).get("client") or "").strip()
        if not client_name or client_name == "не указан":
            send_message(token, chat_id,
                         f"В сделке №{target_deal_id} не указан клиент. Сначала укажите клиента в Мегаплане.",
                         CONTRACT_KEYBOARD)
            return True
        update_deal_ui_state(
            chat_id, pending="payer_target_confirm", payer_card=card,
            payer_target_deal_id=target_deal_id, payer_target_client_name=client_name,
        )
        send_message(token, chat_id, (
            "🏦 Карточка реквизитов распознана. Проверьте данные:\n\n"
            f"{payer_card_summary(card)}\n\n"
            f"Создать (или найти) этого плательщика у клиента «{client_name}» "
            f"и привязать к сделке №{target_deal_id}?"
        ), PAYER_TARGET_CONFIRM_KEYBOARD)
        return True
    update_deal_ui_state(
        chat_id, pending="payer_client", payer_card=card,
        payer_target_deal_id=None,
    )
    send_message(token, chat_id, (
        "🏦 Карточка реквизитов распознана. Проверьте данные:\n\n"
        f"{payer_card_summary(card)}\n\n"
        "В какого клиента Мегаплана добавить этого плательщика? Напишите точное имя клиента."
    ))
    return True


def handle_payer_flow_text(token, chat_id, text):
    state = current_deal_ui_state(chat_id)
    pending = state.get("pending")
    if pending not in ("payer_card_file", "payer_target_confirm", "payer_client", "payer_deal"):
        return False
    value = text.strip()
    if value.casefold() in ("❌ отменить", "отмена", "отменить"):
        update_deal_ui_state(chat_id, pending=None, payer_card=None, payer_result=None,
                             payer_target_deal_id=None, payer_target_client_name=None)
        send_message(token, chat_id, "Операция с плательщиком отменена.", CONTRACT_KEYBOARD)
        return True

    if pending == "payer_card_file":
        send_message(token, chat_id, "Сейчас ожидается файл карточки реквизитов в PDF, Word или Excel.", PAYER_UPLOAD_KEYBOARD)
        return True

    if pending == "payer_target_confirm":
        if value != "✅ Создать и привязать плательщика":
            send_message(token, chat_id, "Подтвердите создание плательщика или отмените операцию.",
                         PAYER_TARGET_CONFIRM_KEYBOARD)
            return True
        target_deal_id = str(state.get("payer_target_deal_id") or "")
        client_name = str(state.get("payer_target_client_name") or "")
        send_typing(token, chat_id)
        result = run_payer_card_apply({"deal_id": target_deal_id, "payer": state.get("payer_card") or {}})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось создать плательщика: {result.get('error')}. "
                         "Данные не привязаны к сделке.", PAYER_TARGET_CONFIRM_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending=None, payer_card=None, payer_result=None,
                             payer_target_deal_id=None, payer_target_client_name=None)
        action = "Создан" if result.get("created") else "Найден существующий"
        send_message(token, chat_id,
                     f"✅ {action} плательщик «{result.get('payer_name')}» и привязан к сделке №{target_deal_id}.",
                     CONTRACT_KEYBOARD)
        return True

    if pending == "payer_client":
        match = re.search(r"(?i)\bклиент(?:е|у|а)?\s+(.+?)(?:\s+с\s+этими\s+реквизитами)?\s*$", value)
        client_name = (match.group(1) if match else value).strip(" .«»\"")
        if not client_name:
            send_message(token, chat_id, "Напишите точное имя клиента в Мегаплане.")
            return True
        send_typing(token, chat_id)
        result = run_payer_card_apply({"client_name": client_name, "payer": state.get("payer_card") or {}})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось создать плательщика: {result.get('error')}. Уточните имя клиента или отмените операцию.")
            return True
        target_deal_id = str(state.get("payer_target_deal_id") or "")
        if target_deal_id:
            linked = run_payer_card_apply({"deal_id": target_deal_id, "payer_id": result.get("payer_id")})
            if not linked.get("ok"):
                send_message(token, chat_id, f"Плательщик создан, но не привязан к сделке №{target_deal_id}: {linked.get('error')}. Попробуйте ещё раз из договора.", CONTRACT_KEYBOARD)
                return True
            update_deal_ui_state(chat_id, pending=None, payer_card=None, payer_result=None, payer_target_deal_id=None)
            action = "Создан" if result.get("created") else "Найден существующий"
            send_message(token, chat_id, f"✅ {action} плательщик «{result.get('payer_name')}» и привязан к сделке №{target_deal_id}.", CONTRACT_KEYBOARD)
            return True
        update_deal_ui_state(chat_id, pending="payer_deal", payer_result=result, payer_card=state.get("payer_card"))
        action = "Создан" if result.get("created") else "Найден существующий"
        send_message(token, chat_id, (
            f"✅ {action} плательщик «{result.get('payer_name')}» в клиенте «{result.get('client_name')}».\n\n"
            "Теперь укажите внутренний ID сделки, к которой его привязать, либо выберите «Без привязки к сделке»."
        ), PAYER_DEAL_KEYBOARD)
        return True

    if value.casefold() in ("без привязки к сделке", "без привязки", "не привязывать"):
        update_deal_ui_state(chat_id, pending=None, payer_card=None, payer_result=None, payer_target_deal_id=None)
        send_message(token, chat_id, "Готово. Плательщик сохранён в клиенте без привязки к сделке.", MAIN_KEYBOARD)
        return True
    ids = re.findall(r"\b\d+\b", value)
    if not ids:
        send_message(token, chat_id, "Укажите внутренний ID сделки числом, например 888, либо выберите «Без привязки к сделке».", PAYER_DEAL_KEYBOARD)
        return True
    deal_id = ids[-1]
    payer_result = state.get("payer_result") or {}
    result = run_payer_card_apply({"deal_id": deal_id, "payer_id": payer_result.get("payer_id")})
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось привязать плательщика: {result.get('error')}. Проверьте ID сделки.", PAYER_DEAL_KEYBOARD)
        return True
    update_deal_ui_state(chat_id, pending=None, payer_card=None, payer_result=None, payer_target_deal_id=None)
    send_message(token, chat_id, (
        f"✅ Плательщик «{result.get('payer_name')}» привязан к сделке №{deal_id}.\n"
        f"{result.get('deal_url')}"
    ), MAIN_KEYBOARD)
    return True


def extract_tax_choice_request(reply_text):
    found = bool(TAX_CHOICE_REQUEST_RE.search(reply_text))
    return TAX_CHOICE_REQUEST_RE.sub("", reply_text).strip(), found


def tax_mode_from_text(text):
    """Map only an explicit tax answer; never infer taxation from unrelated text."""
    value = re.sub(r"\s+", " ", (text or "").strip().casefold())
    # Telegram users often tap/copy the numbered option shown in the preceding
    # question ("1. Без НДС").  Treat the prefix as UI decoration, not as part of
    # the tax value, so the deterministic wizard does not ask the same question twice.
    value = re.sub(r"^\d+\s*[.)]\s*", "", value)
    if value in ("1", "без ндс", "ндс не облагается", "none"):
        return "none"
    if value in ("ндс 22%", "22%", "22") or value.startswith("ндс 22% "):
        return "22"
    if value in ("ндс 5%", "5%", "5") or value.startswith("ндс 5% "):
        return "5"
    return None


def parse_deal_economics_xlsx(path):
    """Parse a known economics workbook through a fixed script, never through LLM.

    The model remains responsible for the conversational fields (client, address,
    subject), but the exact rows/prices/costs from Excel are authoritative and must
    survive unchanged into the CRM draft.
    """
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(HOGART_DIR, "parse_economics_xlsx.py")],
            input=json.dumps({"path": path}, ensure_ascii=False),
            capture_output=True, text=True, timeout=30,
        )
        lines = (result.stdout or "").strip().splitlines()
        parsed = json.loads(lines[-1]) if lines else {"ok": False, "error": "пустой ответ парсера"}
        return parsed
    except Exception as exc:
        print(f"{LOG_PREFIX} economics workbook parse failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка разбора экономики"}


def is_explicit_new_deal_request(text):
    value = " ".join(str(text or "").casefold().replace("ё", "е").split())
    return bool(re.search(r"(?:созда(?:й|ть)|завед(?:и|ите|ести)|нов\w*)\s+(?:нов\w*\s+)?сделк", value))


def is_explicit_contract_request(text):
    value = " ".join(str(text or "").casefold().replace("ё", "е").split())
    return "договор" in value and bool(re.search(r"созда|сформир|подготов|сделай|получ", value))


def extract_profitability_request(reply_text):
    m = PROFITABILITY_REQUEST_RE.search(reply_text)
    clean = PROFITABILITY_REQUEST_RE.sub("", reply_text).strip()
    return clean, (m.group(1) if m else None)


def price_install_addons(items):
    """Shell out to hogart-scraper/price_install_addons.py (stdin JSON, never argv) to
    price install/freon-line addons for hogart-sourced items by the same fixed tariff
    generate_kp.py uses - Claude never invents these numbers itself (see SYSTEM_PROMPT).
    Also looks up each hogart-sourced item's own purchase cost (Hogart's contractPrice),
    not just the addons' cost - added 2026-08-23 so equipment lines get a real
    "Цена закупки" too, not just install/freon lines (see project_megaplan_crm.md).
    Returns (addons, equipment_costs, errors); on any failure returns ([], {}, [error])."""
    lookups = [it for it in items if it.get("hogart_sku")]
    if not lookups:
        return [], {}, []
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(HOGART_DIR, "price_install_addons.py")],
            cwd=HOGART_DIR,
            input=json.dumps({"items": [
                {"sku": it["hogart_sku"], "qty": it["qty"], "include_install": it.get("include_install"),
                 "line_length_m": it.get("line_length_m")} for it in lookups
            ]}, ensure_ascii=False),
            capture_output=True, text=True, timeout=HOGART_SEARCH_TIMEOUT_SEC,
        )
        parsed = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as e:
        print(f"{LOG_PREFIX} price_install_addons failed: {e}", file=sys.stderr)
        return [], {}, ["не удалось посчитать монтаж/трассу (внутренняя ошибка)"]
    if not parsed.get("ok"):
        return [], {}, [parsed.get("error", "не удалось посчитать монтаж/трассу")]
    return parsed.get("addons") or [], parsed.get("equipment_costs") or {}, parsed.get("errors") or []


DEAL_TITLE_ORGANIZATION_RE = re.compile(
    r"(?<![\w-])(ООО|ОАО|ЗАО|ПАО|АО|ИП)\s+([«\"“][^»\"”\n]{2,60}[»\"”]|[А-ЯЁA-Z][\w-]*(?:\s+[А-ЯЁA-Z][\w-]*){0,3})"
)


def deal_title_organization(title):
    """A client named with its legal form inside a new deal title, else None."""
    match = DEAL_TITLE_ORGANIZATION_RE.search(title or "")
    return f"{match.group(1)} {match.group(2).strip()}" if match else None


def search_creation_clients(name):
    try:
        result = subprocess.run([REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, 'megaplan_api.py'), 'search-contractors'],
            cwd=MEGAPLAN_DIR, input=json.dumps({'name': name}, ensure_ascii=False),
            capture_output=True, text=True, timeout=45)
        return json.loads(result.stdout)
    except Exception as exc:
        print(f'{LOG_PREFIX} client lookup failed: {type(exc).__name__}', file=sys.stderr)
        return {'ok': False}


def prepare_economics_deal_request(token, chat_id, caption, path, notify=True):
    """Route an explicit Excel deal request through client lookup, not model memory.

    Saves a draft only; CRM creation still requires the normal tax/review steps.
    """
    if not is_explicit_new_deal_request(caption):
        return False
    economics = parse_deal_economics_xlsx(path)
    if not economics.get('ok'):
        return False
    match = re.search(r'(?i)\b(?:с\s+)?клиент(?:ом|а)?\s+(.+?)(?=\s+и\s+(?:пришли|отправь|подготовь|сформируй)|[,;\n]|$)', caption)
    name = match.group(1).strip(' «»"') if match else ''
    recipient = re.search(r'(?i)(?:коммерческ\w*\s+предложени\w*|\bкп\b)\s+для\s+([^\n,;]+)', caption)
    spec = {'items': economics['items'], 'tax_mode': 'pending', 'allow_new_client': False}
    if recipient:
        spec['proposal_recipient'] = recipient.group(1).strip()
    if name:
        spec['client_name'] = name
    spec['description'] = f'Поставка и работы — {name}' if name else 'Поставка и работы по спецификации'
    update_deal_ui_state(chat_id, deal_creation_active=True, deal_create_spec=spec,
                         deal_creation_items=economics['items'], deal_creation_economics_path=path,
                         current_deal_id=None, contract_deal_id=None,
                         deal_create_clients=None, pending='deal_create_client')
    if not name:
        if notify:
            send_message(token, chat_id, 'Позиции и цены из Excel сохранены. Укажите клиента для поиска в Мегаплане.', PAYER_UPLOAD_KEYBOARD)
        return True
    found = search_creation_clients(name)
    if not found.get('ok'):
        if notify:
            send_message(token, chat_id, 'Позиции и цены сохранены. Поиск клиента не выполнен; новая карточка не создавалась.', PAYER_UPLOAD_KEYBOARD)
        return True
    clients = found.get('clients') or []
    if len(clients) == 1:
        client = clients[0]
        spec.update(client_id=client['id'], client_name=client['name'], client_kind=client['kind'])
        update_deal_ui_state(chat_id, deal_create_spec=spec, pending='deal_create_tax')
        if notify:
            send_message(token, chat_id, f'Найден существующий клиент «{client["name"]}», ID {client["id"]}. '
                         f'Сохранены все {len(economics["items"])} позиций из Excel. Выберите режим НДС для сделки.', TAX_KEYBOARD)
        return True
    update_deal_ui_state(chat_id, pending='deal_create_client_select', deal_create_clients=clients)
    rows = [[{'text': f'Клиент ID {x["id"]} — {x["name"]}'}] for x in clients]
    if not clients:
        rows = [[{'text': 'Новый клиент — организация'}], [{'text': 'Новый клиент — физическое лицо'}]]
    rows.append([{'text': '🔍 Другой клиент'}, {'text': '❌ Отмена'}])
    if notify:
        send_message(token, chat_id, 'Выберите существующую карточку клиента:' if clients else
                     'Совпадений не найдено. Искать по другому названию или создать нового клиента?', {'keyboard': rows})
    return True


def prepare_deal_creation_review(token, chat_id, spec):
    if not spec.get('client_id') and not spec.get('allow_new_client') and spec.get('user_request') and spec.get('client_name'):
        found = search_creation_clients(spec['client_name'])
        if found.get('ok'):
            clients = found.get('clients') or []
            if len(clients) == 1:
                client = clients[0]
                spec = {**spec, 'client_id': client['id'], 'client_name': client['name'], 'client_kind': client['kind']}
            else:
                update_deal_ui_state(chat_id, deal_create_spec=spec, pending='deal_create_client_select', deal_create_clients=clients)
                rows = [[{'text': f'Клиент ID {x["id"]} — {x["name"]}'}] for x in clients]
                rows.append([{'text': '🔍 Другой клиент'}, {'text': '❌ Отмена'}])
                send_message(token, chat_id, 'Выберите найденную карточку клиента:' if clients else
                             'Клиент по указанному названию не найден. Нажмите «Другой клиент» для поиска по другому названию.', {'keyboard': rows})
                return
    if not spec.get('client_id') and not spec.get('allow_new_client'):
        update_deal_ui_state(chat_id, deal_create_spec=spec, pending='deal_create_client')
        send_message(token, chat_id, 'Нужно подтвердить карточку клиента. Введите его название для поиска; спецификация сохранена.', PAYER_UPLOAD_KEYBOARD)
        return
    try:
        summary = deal_creation.review(spec)
    except ValueError as exc:
        update_deal_ui_state(chat_id, deal_create_spec=spec, pending='deal_create_items')
        send_message(token, chat_id, f'Черновик сохранён, но пока не готов к созданию: {exc}\nПришлите уточнённую спецификацию.', PAYER_UPLOAD_KEYBOARD)
        return
    update_deal_ui_state(chat_id, deal_create_spec=spec, pending='deal_create_confirm', deal_creation_active=True)
    send_message(token, chat_id, summary, DEAL_CREATE_CONFIRM_KEYBOARD)


def run_create_megaplan_deal(spec):
    """Shell out to megaplan_api.py's create-full-deal CLI (stdin JSON, never argv - see
    project memory on ARG_MAX). First prices any install/freon-line addons and each
    hogart-sourced item's own purchase cost (see price_install_addons above), folding
    the addons into the item list as their own positions and the cost onto each
    equipment item, then finds/creates the contractor and each item's catalog Offer
    (with cost_material/cost_work carried onto Мегаплан's "Цена закупки"/"Себестоимость
    работ" fields - see megaplan_api.py's find_or_create_offer), and creates the deal
    with real positions filled in."""
    spec, validation_error = normalize_create_deal_spec(spec)
    if validation_error:
        return {"ok": False, "error": f"некорректный черновик сделки: {validation_error}"}
    if str(spec.get("tax_mode")) not in ("none", "22", "5"):
        return {"ok": False, "error": "не выбран режим НДС (без НДС / 22% / 5%)"}
    if RUNTIME_ACTIVE:
        try:
            deal_creation.review(spec)
        except ValueError as exc:
            return {'ok': False, 'no_effect': True, 'error': str(exc)}
        # Commit precisely the reviewed specification. A price refresh belongs
        # to draft preparation, never to a confirmed write.
        addons, equipment_costs, addon_errors = [], {}, []
    else:
        addons, equipment_costs, addon_errors = price_install_addons(spec.get("items") or [])
    if addon_errors:
        return {"ok": False, "error": "; ".join(addon_errors)}
    items = [
        {**it, "cost_material": equipment_costs[it["hogart_sku"]]}
        if it.get("hogart_sku") and equipment_costs.get(it["hogart_sku"]) is not None
        else it
        for it in (spec.get("items") or [])
    ]
    if addons:
        items = [*items, *[
            {"name": a["name"], "qty": a["qty"], "unit_price": a["unit_price"],
             "cost_material": a.get("cost_material"), "cost_work": a.get("cost_work")}
            for a in addons
        ]]
    spec = dict(spec, items=items)

    # Phase 1b (2026-08-23): if any item has no unit_price at all, this is a raw
    # "spec without prices" request - route through create-deal-from-spec (tiered
    # Мегаплан-catalog / Hogart / Kemiks resolution) instead of create-full-deal
    # (which requires every item pre-priced). A spec can be mixed - some items already
    # priced, some not - create-deal-from-spec handles that per-item.
    cli_cmd = "create-full-deal" if all(it.get("unit_price") is not None for it in items) else "create-deal-from-spec"
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "megaplan_api.py"), cli_cmd],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=CREATE_MEGAPLAN_DEAL_TIMEOUT_SEC,
        )
        output_lines = (result.stdout or "").strip().splitlines()
        if not output_lines:
            detail = (result.stderr or "").strip().splitlines()
            detail = detail[-1] if detail else f"процесс завершился с кодом {result.returncode}"
            raise RuntimeError(detail)
        # The CRM CLI can return a pretty-printed JSON error. Parsing its last
        # line alone hides the actual rejection behind JSONDecodeError.
        try:
            parsed = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            parsed = json.loads(output_lines[-1])
        if not parsed.get("ok") and not parsed.get("error"):
            errors = ((parsed.get("body") or {}).get("meta") or {}).get("errors") or []
            parsed["error"] = "; ".join(str(e.get("message") or e.get("type")) for e in errors) or f"Мегаплан отклонил запрос (HTTP {parsed.get('status', '?')})"
    except Exception as e:
        print(f"{LOG_PREFIX} run_create_megaplan_deal failed: {e}", file=sys.stderr)
        return {"ok": False, "error": f"внутренняя ошибка при создании сделки: {e}"}
    if parsed.get("ok"):
        parsed["_expanded_items"] = parsed.get("ledger") or spec["items"]
    return parsed


def build_spec_review_xlsx(client_name, ledger_entries):
    """Shell out to hogart-scraper/spec_review_xlsx.py (under ~/.report-venv, which has
    openpyxl - the system python3 running bridge.py is Debian's externally-managed one,
    same reason generate_kp.py's own xlsx report already goes through that venv) to
    build the "please confirm these matches" review file for a spec-based deal.
    Returns the file path, or None on failure (logged, not raised - a review-file
    hiccup shouldn't un-create the deal that already exists)."""
    fd, path = __import__("tempfile").mkstemp(suffix=".xlsx", prefix="spec-review-")
    os.close(fd)
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(HOGART_DIR, "spec_review_xlsx.py")],
            input=json.dumps({"path": path, "client": client_name, "entries": ledger_entries}, ensure_ascii=False),
            capture_output=True, text=True, timeout=30,
        )
        parsed = json.loads((result.stdout or "").strip().splitlines()[-1])
    except Exception as e:
        print(f"{LOG_PREFIX} build_spec_review_xlsx failed: {e}", file=sys.stderr)
        return None
    if not parsed.get("ok"):
        print(f"{LOG_PREFIX} spec_review_xlsx.py error: {parsed.get('error')}", file=sys.stderr)
        return None
    return path


def build_deal_work_statement_xlsx(deal_id, client_name, status, ledger_entries):
    """Build the installer-facing statement without sales or material economics."""
    fd, path = __import__("tempfile").mkstemp(suffix=".xlsx", prefix=f"work-statement-{deal_id}-")
    os.close(fd)
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "build_deal_work_statement.py")],
            input=json.dumps({
                "path": path, "deal_id": str(deal_id), "client": client_name,
                "status": status, "entries": ledger_entries,
            }, ensure_ascii=False),
            capture_output=True, text=True, timeout=30,
        )
        parsed = json.loads((result.stdout or "").strip().splitlines()[-1])
    except Exception as e:
        print(f"{LOG_PREFIX} build_deal_work_statement_xlsx failed: {e}", file=sys.stderr)
        parsed = {"ok": False}
        result = None
    if result is None or result.returncode != 0 or not parsed.get("ok"):
        if result is not None:
            print(f"{LOG_PREFIX} build_deal_work_statement.py error: {parsed.get('error')}", file=sys.stderr)
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    return path


def extract_recent_deals_request(reply_text):
    """Pull a bare RECENT_DEALS_REQUEST marker out of the reply (Phase 1b's
    supplier-invoice flow, step 1 - see SYSTEM_PROMPT)."""
    found = bool(RECENT_DEALS_REQUEST_RE.search(reply_text))
    clean_text = RECENT_DEALS_REQUEST_RE.sub("", reply_text).strip()
    return clean_text, found


def extract_deal_ledger_request(reply_text):
    """Pull a DEAL_LEDGER_REQUEST: <deal_id> marker out of the reply (step 2)."""
    m = DEAL_LEDGER_REQUEST_RE.search(reply_text)
    clean_text = DEAL_LEDGER_REQUEST_RE.sub("", reply_text).strip()
    return clean_text, (m.group(1) if m else None)


def extract_resend_deal_review(reply_text):
    """Pull a RESEND_DEAL_REVIEW: <deal_id> marker out of the reply - owner asking for
    the review .xlsx again for a deal that already exists (2026-08-24: there used to be
    no way to do this at all, Claude had to explain it couldn't - see SYSTEM_PROMPT)."""
    m = RESEND_DEAL_REVIEW_RE.search(reply_text)
    clean_text = RESEND_DEAL_REVIEW_RE.sub("", reply_text).strip()
    return clean_text, (m.group(1) if m else None)


def extract_create_kp_deal_confirm(reply_text):
    """Pull a CREATE_KP_DEAL_CONFIRM: да/нет marker - the answer to the "завести сделку
    в Мегаплане?" question the bridge appends after a multi-variant KP (see
    _pending_kp_deal above). Normalizes да/yes -> True, нет/no -> False."""
    m = CREATE_KP_DEAL_CONFIRM_RE.search(reply_text)
    clean_text = CREATE_KP_DEAL_CONFIRM_RE.sub("", reply_text).strip()
    if not m:
        return clean_text, None
    return clean_text, m.group(1).strip().lower() in ("да", "yes")


def extract_work_statement_request(reply_text):
    """Pull a WORK_STATEMENT_REQUEST: <deal_id> marker out of the reply - owner asking
    for the "ведомость работ" (labour-cost breakdown) on an existing deal."""
    m = WORK_STATEMENT_REQUEST_RE.search(reply_text)
    clean_text = WORK_STATEMENT_REQUEST_RE.sub("", reply_text).strip()
    return clean_text, (m.group(1) if m else None)


def run_build_work_statement(deal_id):
    """Shell out to megaplan-crm/build_work_statement.py. Returns the parsed JSON, or
    {"ok": False, "error": ...} on failure - same result shape as the other run_* helpers."""
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "build_work_statement.py"), str(deal_id)],
            cwd=MEGAPLAN_DIR, capture_output=True, text=True, timeout=WORK_STATEMENT_TIMEOUT_SEC,
        )
        if result.returncode == 0 and (result.stdout or "").strip():
            return json.loads(result.stdout.strip().splitlines()[-1])
        print(
            f"{LOG_PREFIX} build_work_statement.py {deal_id} failed: "
            f"returncode={result.returncode} stdout={(result.stdout or '')[:500]!r} "
            f"stderr={(result.stderr or '')[:500]!r}",
            file=sys.stderr,
        )
        return {"ok": False, "error": "техническая ошибка при расчёте ведомости"}
    except Exception as e:
        print(f"{LOG_PREFIX} build_work_statement.py {deal_id} error: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}


def extract_apply_work_statement(reply_text):
    """Pull an APPLY_WORK_STATEMENT_BEGIN/END JSON block out of the reply, if present."""
    m = APPLY_WORK_STATEMENT_RE.search(reply_text)
    if not m:
        return reply_text, None
    clean_text = APPLY_WORK_STATEMENT_RE.sub("", reply_text).strip()
    try:
        spec = json.loads(m.group(1))
    except Exception as e:
        print(f"{LOG_PREFIX} APPLY_WORK_STATEMENT block was not valid JSON: {e}", file=sys.stderr)
        return clean_text, {"__invalid__": True}
    return clean_text, spec


def run_apply_work_statement(deal_id, markup_pct, preview=False, expected_fingerprint=None):
    try:
        command = [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, 'apply_work_statement.py'), str(deal_id), str(markup_pct)]
        if preview: command.append('--preview')
        if expected_fingerprint: command.extend(['--expected-fingerprint', expected_fingerprint])
        result = subprocess.run(
            command,
            cwd=MEGAPLAN_DIR, capture_output=True, text=True, timeout=APPLY_WORK_STATEMENT_TIMEOUT_SEC,
        )
        if result.returncode == 0 and (result.stdout or "").strip():
            return json.loads(result.stdout.strip().splitlines()[-1])
        print(
            f"{LOG_PREFIX} apply_work_statement.py {deal_id} {markup_pct} failed: "
            f"returncode={result.returncode} stdout={(result.stdout or '')[:500]!r} "
            f"stderr={(result.stderr or '')[:500]!r}",
            file=sys.stderr,
        )
        return {"ok": False, "error": "техническая ошибка при записи себестоимости монтажных работ"}
    except Exception as e:
        print(f"{LOG_PREFIX} apply_work_statement.py {deal_id} {markup_pct} error: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}


def run_build_profitability_report(deal_id):
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "build_profitability_report.py"), str(deal_id)],
            cwd=MEGAPLAN_DIR, capture_output=True, text=True, timeout=WORK_STATEMENT_TIMEOUT_SEC,
        )
        if result.returncode == 0 and (result.stdout or "").strip():
            return json.loads(result.stdout.strip().splitlines()[-1])
        print(
            f"{LOG_PREFIX} build_profitability_report.py {deal_id} failed: "
            f"returncode={result.returncode} stdout={(result.stdout or '')[:500]!r} "
            f"stderr={(result.stderr or '')[:500]!r}",
            file=sys.stderr,
        )
        return {"ok": False, "error": "техническая ошибка при расчёте рентабельности"}
    except Exception as e:
        print(f"{LOG_PREFIX} build_profitability_report.py {deal_id} error: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}


def build_and_store_profitability(deal_id):
    """Build the current workbook and keep exactly one bot-managed copy in the deal."""
    result = run_build_profitability_report(deal_id)
    if not result.get("ok"):
        return result
    stored = run_deal_browser({
        "action": "upsert_profitability_file",
        "deal_id": str(deal_id),
        "path": result["path"],
        # Unchanged numbers keep the published file: no CRM write (QA, 23.10).
        "data_fingerprint": result.get("data_fingerprint"),
    })
    if not stored.get("ok"):
        return {**result, "ok": False, "built": True,
                "error": f"файл построен, но не сохранён в сделке: {stored.get('error') or 'ошибка Мегаплана'}"}
    result["stored"] = stored
    if stored.get("unchanged"):
        # The same version is already in the deal and in the archive.
        result["unchanged"] = True
        return result
    archived = run_financial_archive({
        "deal_id": str(deal_id), "path": result["path"], "category": "economics",
    })
    if not archived.get("ok"):
        # Megaplan remains the working copy: an archive outage must not discard a
        # correctly built report or make a financial operation fail.
        result["archive_warning"] = archived.get("error") or "не удалось сохранить версию в OneDrive"
    else:
        result["archive"] = archived
    return result


def run_financial_archive(spec):
    """Store an immutable financial-document copy in the deal's OneDrive folder."""
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "archive_outbox.py")],
            cwd=MEGAPLAN_DIR, input=json.dumps({"action": "archive", **spec}, ensure_ascii=False),
            capture_output=True, text=True, timeout=180,
        )
        lines = (result.stdout or "").strip().splitlines()
        parsed = json.loads(lines[-1]) if lines else {}
        if parsed.get('queued'): return parsed
        if result.returncode or not parsed.get("ok"):
            return {"ok": False, "error": parsed.get("error") or (result.stderr or "ошибка архива OneDrive")[-500:]}
        return parsed
    except Exception as error:
        print(f"{LOG_PREFIX} financial archive error: {error}", file=sys.stderr)
        return {"ok": False, "error": str(error)}


def _run_deal_ledger_cli(args, attempt=1):
    """Shell out to megaplan-crm/deal_ledger.py's CLI (same directory as megaplan_api.py,
    imported there directly - but bridge.py stays consistent with this project's
    established cross-directory subprocess pattern rather than importing across
    project dirs). Returns the parsed JSON, or None on failure - callers MUST treat
    None as "fetch failed, unknown state", never as "empty" (see 2026-08-24 incident
    below: `fetch_deal_ledger` used to return `[]` on ANY failure, indistinguishable
    from a deal that genuinely has zero positions - a transient failure here made
    Claude believe deal 883 had no positions at all, so it re-added two positions
    that already existed instead of updating them, with mismatched pricing on top).
    Logs full stdout/stderr on failure so a repeat is actually diagnosable (the
    original bug's only trace was a useless "Expecting value: line 1 column 1" from
    json.loads on an empty string - the real error was never captured). Retries once
    on any failure before giving up, in case it's transient (subprocess spawn hiccup,
    disk contention - this box is known to run tight on RAM, see project memory)."""
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "deal_ledger.py"), *args],
            cwd=MEGAPLAN_DIR, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and (result.stdout or "").strip():
            return json.loads(result.stdout.strip().splitlines()[-1])
        print(
            f"{LOG_PREFIX} deal_ledger.py {args} failed (attempt {attempt}): "
            f"returncode={result.returncode} stdout={(result.stdout or '')[:500]!r} "
            f"stderr={(result.stderr or '')[:500]!r}",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"{LOG_PREFIX} deal_ledger.py {args} error (attempt {attempt}): {e}", file=sys.stderr)
    if attempt == 1:
        return _run_deal_ledger_cli(args, attempt=2)
    return None


def fetch_recent_deals():
    result = _run_deal_ledger_cli(["list-recent"])
    return result if result is not None else []


def fetch_deal_ledger(deal_id, force=False):
    """Refresh and return the ledger from the live Megaplan deal.

    Manual edits in Megaplan (especially material/work costs) must be reflected in
    every review/economics report; the local JSON is only a cache plus accumulation
    metadata, never the authority for current row values.
    """
    deal_id = str(deal_id)
    cache_key = (os.getpid(), deal_id)
    cached_live = DEAL_LEDGER_CACHE.get(cache_key)
    if (not force and cached_live and
            time.monotonic() - cached_live["at"] < DEAL_LEDGER_CACHE_TTL_SEC):
        return copy.deepcopy(cached_live["ledger"])

    started = time.monotonic()
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "megaplan_api.py"), "sync-deal-ledger"],
            cwd=MEGAPLAN_DIR,
            input=json.dumps({"deal_id": deal_id}, ensure_ascii=False),
            # Runs in a worker: allow the CRM request to finish. A timeout is
            # unknown state, never evidence that a deal has no positions.
            capture_output=True, text=True, timeout=45,
        )
        parsed = json.loads((result.stdout or "").strip().splitlines()[-1])
        if result.returncode == 0 and parsed.get("ok"):
            ledger = parsed.get("ledger")
            if not isinstance(ledger, list):
                raise ValueError("CRM response has no verified ledger")
            DEAL_LEDGER_CACHE[cache_key] = {"at": time.monotonic(), "ledger": copy.deepcopy(ledger)}
            record_operation_timing("Мегаплан: позиции сделки", time.monotonic() - started,
                                    details=f"сделка №{deal_id}")
            return ledger
        print(f"{LOG_PREFIX} sync-deal-ledger {deal_id} failed: {parsed}", file=sys.stderr)
    except Exception as e:
        print(f"{LOG_PREFIX} sync-deal-ledger {deal_id} error: {e}", file=sys.stderr)
    record_operation_timing("Мегаплан: позиции сделки", time.monotonic() - started,
                            outcome="error", details=f"сделка №{deal_id}")
    return None


def deal_client_name(deal_id):
    """Best-effort client name lookup for a deal, for the review file's header - falls
    back to a generic label if the deal isn't in the local recent-deals index (e.g. it
    predates that index, or the lookup failed) rather than blocking on it."""
    for d in fetch_recent_deals():
        if str(d.get("deal_id")) == str(deal_id):
            return d.get("client_name") or f"сделка {deal_id}"
    return f"сделка {deal_id}"


def normalized_search_text(value):
    return re.sub(r"[^0-9a-zа-я]+", " ", str(value or "").casefold().replace("ё", "е")).strip()


def extract_supplier_invoice_apply(reply_text):
    """Pull a SUPPLIER_INVOICE_APPLY_BEGIN/END JSON block out of the reply, if present."""
    m = SUPPLIER_INVOICE_APPLY_RE.search(reply_text)
    if not m:
        return reply_text, None
    clean_text = SUPPLIER_INVOICE_APPLY_RE.sub("", reply_text).strip()
    try:
        spec = json.loads(m.group(1))
    except Exception as e:
        print(f"{LOG_PREFIX} SUPPLIER_INVOICE_APPLY block was not valid JSON: {e}", file=sys.stderr)
        return clean_text, {"__invalid__": True}
    return clean_text, spec


def accept_supplier_invoice_protocol(spec, supplier_invoice_mode):
    """Only a document uploaded from the selected procurement flow may create a draft."""
    return spec if supplier_invoice_mode else None


def apply_manual_supplier_mapping(spec, sources, targets, pairs):
    """Turn explicit `invoice line=deal position` pairs into safe proportional updates.

    Repeating an invoice-line number deliberately splits that source line over
    several positions.  Each fragment carries its own quantity and proportional
    subtotal, so neither a partial match nor a repeated upload can overstate cost.
    """
    available = {index: max(0.0, float(item.get("available") or 0))
                 for index, item in enumerate(targets)}
    # A preview may already contain automatic matches.  They are not in the
    # persisted ledger yet, but they must reserve their target quantity while
    # the owner makes manual matches; otherwise a second mapping can silently
    # create a "ДОП" row for the very same deal position.
    for update in spec.get("updates") or []:
        for index, target in enumerate(targets):
            if (str(update.get("offer_row_id") or "") == str(target.get("offer_row_id") or "")
                    and str(target.get("offer_row_id") or "")):
                available[index] = max(0.0, available[index] - float(update.get("qty_used") or 0))
    remaining = {}
    for index, item in enumerate(sources):
        quantity = float(item.get("qty") or item.get("source_qty") or 0)
        amount = float(item.get("amount") or item.get("source_total") or 0)
        if quantity <= 0 and amount > 0:
            quantity = 1.0
        remaining[index] = {"qty": quantity, "amount": amount}

    updates = list(spec.get("updates") or [])
    mapped_lines = []
    for source_text, target_text in pairs:
        source_index, target_index = int(source_text) - 1, int(target_text) - 1
        if source_index < 0 or source_index >= len(sources) or target_index < 0 or target_index >= len(targets):
            raise ValueError(f"Нет строки {source_text} или позиции {target_text}. Проверьте номера.")
        source, target = sources[source_index], targets[target_index]
        source_left, target_left = remaining[source_index], available[target_index]
        if source_left["qty"] <= 1e-9:
            raise ValueError(f"Строка счёта {source_text} уже полностью распределена.")
        if target_left <= 1e-9:
            raise ValueError(f"Позиция сделки {target_text} уже полностью закрыта другими строками.")
        original_qty = float(source.get("qty") or source.get("source_qty") or 0) or source_left["qty"]
        original_amount = float(source.get("amount") or source.get("source_total") or 0)
        quantity = min(source_left["qty"], target_left)
        # Keep the unit cost of the supplier line intact even after a split.
        amount = round(original_amount * quantity / original_qty, 2) if original_qty else source_left["amount"]
        amount = min(amount, source_left["amount"])
        duplicate = next((u for u in updates if u.get("manual_mapping")
                          and str(u.get("source_line_key") or "") == str(source.get("source_line_key") or "")
                          and str(u.get("offer_row_id") or "") == str(target.get("offer_row_id") or "")
                          and abs(float(u.get("qty_used") or 0) - quantity) <= 1e-9
                          and abs(float(u.get("material_cost_used") or 0) - amount) <= 0.01), None)
        if duplicate:
            # Telegram may deliver a retry after a slow response.  Replaying
            # an identical manual command must be a no-op, not a duplicate cost.
            continue
        updates.append({
            "offer_id": target.get("offer_id"), "offer_row_id": target.get("offer_row_id"),
            "qty_used": quantity, "material_cost_used": amount, "work_cost_used": 0,
            "source_line_key": source.get("source_line_key"),
            "source_sku": source.get("source_sku") or source.get("sku"),
            "source_name": source.get("name") or source.get("source_name"),
            "source_qty": quantity, "source_total": amount,
            "manual_mapping": True,
        })
        source_left["qty"] = round(source_left["qty"] - quantity, 9)
        source_left["amount"] = round(source_left["amount"] - amount, 2)
        available[target_index] = round(target_left - quantity, 9)
        mapped_lines.append(f"• {source.get('name') or source.get('source_name')} → {target.get('name')} "
                            f"({quantity:g} ед., {bank_money(amount)} ₽)")

    unallocated = []
    for index, source in enumerate(sources):
        leftover = remaining[index]
        if leftover["qty"] > 1e-9 or leftover["amount"] > 0.01:
            unallocated.append({
                "source_line_key": source.get("source_line_key"),
                "source_sku": source.get("source_sku") or source.get("sku"),
                "name": source.get("name") or source.get("source_name"),
                "qty": max(0.0, leftover["qty"]), "amount": max(0.0, leftover["amount"]),
            })
    return {**spec, "updates": updates, "unallocated": unallocated}, mapped_lines


def cap_invoice_allocation_to_deal(spec):
    """Never turn another deal's quantity into a ДОП row of the selected deal.

    The invoice parser reports the supplier line's full quantity.  For a shared
    invoice we allocate at most the selected deal's still-uncovered quantity and
    retain the proportional balance as unallocated for another deal.
    """
    deal_id = str(spec.get("deal_id") or "")
    ledger = fetch_deal_ledger(deal_id) if deal_id else None
    if ledger is None:
        return spec
    by_offer = {str(x.get("offer_id")): x for x in ledger}
    unallocated = list(spec.get("unallocated") or [])
    normalized = []
    for update in spec.get("updates") or []:
        row = by_offer.get(str(update.get("offer_id")))
        requested = float(update.get("qty_used") or update.get("qty") or update.get("source_qty") or 0)
        source_qty = float(update.get("source_qty") or requested or 0)
        source_total = float(update.get("source_total") or 0)
        if source_total <= 0:
            explicit_total = float(update.get("material_cost_used") or 0) + float(update.get("work_cost_used") or 0)
            source_total = explicit_total or (
                (float(update.get("cost_material") or 0) + float(update.get("cost_work") or 0)) * source_qty
            )
        requested_amount = (round(source_total * requested / source_qty, 2) if source_qty else source_total)
        update = {**update, "qty_used": requested, "source_qty": source_qty,
                  "source_total": source_total, "material_cost_used": requested_amount,
                  "work_cost_used": 0}
        if not row:
            normalized.append(update); continue
        available = max(0.0, float(row.get("qty") or 0) - float(row.get("consumed_qty") or 0))
        if requested <= available + 1e-9:
            normalized.append(update); continue
        if available <= 1e-9:
            unallocated.append({"source_line_key": update.get("source_line_key"),
                                "name": update.get("source_name"), "qty": requested,
                                "amount": round(source_total * requested / source_qty, 2) if source_qty else source_total})
            continue
        allocated_amount = round(source_total * available / source_qty, 2) if source_qty else round(
            float(update.get("material_cost_used") or 0) * available / requested, 2)
        remainder_qty = requested - available
        remainder_amount = round(requested_amount - allocated_amount, 2)
        update = {**update, "qty_used": available, "material_cost_used": allocated_amount}
        normalized.append(update)
        unallocated.append({"source_line_key": update.get("source_line_key"),
                            "name": update.get("source_name"), "qty": remainder_qty,
                            "amount": remainder_amount})
    # Unknown supplier lines are operating costs by default, not new commercial
    # positions. Only an explicit add_to_commercial flag may change the client scope.
    commercial_additions, additional_expenses = [], list(spec.get("additional_expenses") or [])
    for row in spec.get("additions") or []:
        if row.get("add_to_commercial") is True:
            commercial_additions.append(row)
            continue
        qty = float(row.get("qty") or 0)
        amount = (float(row.get("cost_material") or 0) + float(row.get("cost_work") or 0)) * qty
        additional_expenses.append({"source_line_key": row.get("source_line_key") or row.get("name"),
            "source_name": row.get("name") or "Дополнительный расход", "source_sku": row.get("source_sku") or "",
            "source_qty": qty, "source_total": amount, "qty": qty, "amount": amount,
            "category": row.get("category") or "материалы", "reason": row.get("reason") or "внеплановый расход"})
    return {**spec, "updates": normalized, "unallocated": unallocated,
            "additions": commercial_additions, "additional_expenses": additional_expenses}


def trim_previously_allocated_invoice_lines(spec, status):
    """Remove the already-recorded part when the same invoice is uploaded again."""
    usage = status.get("source_usage") or {}
    fresh, skipped_qty, skipped_amount = [], 0.0, 0.0
    for original in spec.get("updates") or []:
        row = dict(original)
        key = str(row.get("source_line_key") or row.get("source_sku") or row.get("source_name") or "").strip().casefold()
        used = usage.get(key) or {}
        used_qty = float(used.get("qty") or 0)
        used_amount = float(used.get("amount") or 0)
        source_qty = float(row.get("source_qty") or row.get("qty_used") or row.get("qty") or 0)
        source_total = float(row.get("source_total") or 0)
        if source_total <= 0:
            source_total = ((float(row.get("cost_material") or 0) + float(row.get("cost_work") or 0)) * source_qty
                            or float(row.get("material_cost_used") or 0) + float(row.get("work_cost_used") or 0))
        if used_qty <= 1e-9 and used_amount <= 0.01:
            fresh.append(row); continue
        remaining_qty = max(0.0, source_qty - used_qty) if source_qty else 0.0
        remaining_amount = max(0.0, source_total - used_amount)
        skipped_qty += min(source_qty, used_qty) if source_qty else 0
        skipped_amount += min(source_total, used_amount) if source_total else used_amount
        if remaining_qty <= 1e-9 or remaining_amount <= 0.01:
            continue
        row.update({"source_qty": remaining_qty, "source_total": remaining_amount,
                    "qty_used": remaining_qty, "material_cost_used": remaining_amount,
                    "work_cost_used": 0})
        fresh.append(row)
    # A repeated upload can contain a line which was previously placed into
    # internal stock. It is no longer fresh invoice material and must be used
    # through the stock workflow, not allocated a second time here.
    stock_keys = set(status.get("stocked_line_keys") or [])
    unallocated = []
    for row in spec.get("unallocated") or []:
        key = str(row.get("source_line_key") or row.get("source_sku") or row.get("source_name") or "").strip().casefold()
        if key and key in stock_keys:
            skipped_qty += float(row.get("qty") or row.get("source_qty") or 0)
            skipped_amount += float(row.get("amount") or row.get("source_total") or 0)
            continue
        unallocated.append(row)
    return {**spec, "updates": fresh, "unallocated": unallocated,
            "_repeat_invoice": {"existing": bool(status.get("existing")),
                                "skipped_qty": skipped_qty, "skipped_amount": round(skipped_amount, 2),
                                "allocated_total": float(status.get("allocated_total") or 0)}}


def supplier_invoice_spec_coverage(spec):
    """Amount represented by parser rows before duplicate trimming.

    Every supplier line must appear either as an update, an unallocated row, an
    additional expense, or an explicit addition.  This catches the common model
    failure where prose says 'the rest is unallocated' but JSON omits those rows.
    """
    amount = 0.0
    for row in spec.get("updates") or []:
        source_total = float(row.get("source_total") or 0)
        if source_total <= 0:
            qty = float(row.get("source_qty") or row.get("qty_used") or row.get("qty") or 0)
            source_total = ((float(row.get("cost_material") or 0) + float(row.get("cost_work") or 0)) * qty
                            or float(row.get("material_cost_used") or 0) + float(row.get("work_cost_used") or 0))
        amount += source_total
    amount += sum(float(x.get("amount") or x.get("source_total") or x.get("total") or 0)
                  for x in spec.get("unallocated") or [])
    amount += sum(float(x.get("amount") or x.get("source_total") or x.get("total") or 0)
                  for x in spec.get("additional_expenses") or [])
    amount += sum((float(x.get("cost_material") or 0) + float(x.get("cost_work") or 0)) *
                  float(x.get("qty") or 0) for x in spec.get("additions") or [])
    return round(amount, 2)


def prepare_supplier_invoice_preview(spec, repeat_status=None):
    """Build a preview for both deal allocations and remainder-only invoices."""
    repeat_status = repeat_status or {}
    preview = run_procurement_workflow({"action": "prepare_invoice_allocation",
                                        "invoice_spec": spec})
    if preview.get("ok"):
        return preview, None
    remainder_only = (bool(spec.get("unallocated")) and not spec.get("updates") and
                      not spec.get("additions") and not spec.get("additional_expenses"))
    if not remainder_only:
        return None, str(preview.get("error") or "неизвестная ошибка")
    invoice_total = float(repeat_status.get("invoice_total") or
                          (spec.get("invoice") or {}).get("total") or 0)
    allocated = float(repeat_status.get("allocated_total") or 0)
    remaining = max(0, round(invoice_total - allocated, 2))
    return {"ok": True, "existing": bool(repeat_status.get("existing")),
            "allocation_amount": 0, "allocated_before": allocated,
            "remaining_before": remaining, "remaining_after": remaining}, None


def run_supplier_invoice_apply(spec):
    """Shell out to megaplan_api.py's apply-supplier-invoice CLI (stdin JSON, never
    argv - see project memory on ARG_MAX)."""
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "megaplan_api.py"), "apply-supplier-invoice"],
            cwd=MEGAPLAN_DIR, input=json.dumps(spec, ensure_ascii=False),
            capture_output=True, text=True, timeout=SUPPLIER_INVOICE_APPLY_TIMEOUT_SEC,
        )
        raw = (result.stdout or "").strip()
        # The CLI deliberately prints structured JSON even on a controlled API
        # error.  Preserve it for the user and logs instead of replacing it with
        # an unrelated JSON decoder error.
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                for line in reversed(raw.splitlines()):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        pass
        print(f"{LOG_PREFIX} supplier invoice apply failed: returncode={result.returncode} "
              f"stdout={raw[:800]!r} stderr={(result.stderr or '')[:800]!r}", file=sys.stderr)
        return {"ok": False, "error": "техническая ошибка при применении счёта поставщика"}
    except Exception as e:
        print(f"{LOG_PREFIX} run_supplier_invoice_apply failed: {e}", file=sys.stderr)
        return {"ok": False, "error": "внутренняя ошибка при применении счёта поставщика"}


def format_supplier_invoice_apply_summary(result):
    lines = [
        f"Сделка обновлена: {result['url']}",
        f"Обновлено позиций: {result.get('updated_count', 0)}, добавлено новых: {result.get('added_count', 0)}",
    ]
    for notice in result.get("overage_notices") or []:
        lines.append(f"⚠️ {notice}")
    return "\n".join(lines)


def distribution_specs(base_spec, include_nearby=True):
    """Convert the confirmed proposal into normal per-deal supplier-invoice specs."""
    has_current_allocation = bool(base_spec.get("updates") or base_spec.get("additions") or
                                  base_spec.get("additional_expenses"))
    specs = [dict(base_spec)] if has_current_allocation else []
    if specs:
        specs[0].pop("_distribution_plan", None); specs[0].pop("_allocation_preview", None)
    if not include_nearby:
        return specs
    grouped = {}
    for row in (base_spec.get("_distribution_plan") or {}).get("suggestions") or []:
        grouped.setdefault(str(row["deal_id"]), []).append(row)
    for target_deal, rows in grouped.items():
        updates = []
        for row in rows:
            updates.append({"offer_id": row.get("offer_id"), "offer_row_id": row.get("offer_row_id"),
                "qty_used": row.get("qty"), "material_cost_used": row.get("amount"), "work_cost_used": 0,
                "source_line_key": row.get("source_line_key"), "source_name": row.get("source_name"),
                "source_sku": row.get("source_sku"), "source_qty": row.get("source_qty"),
                "source_total": row.get("source_total")})
        specs.append({"deal_id": target_deal, "invoice": base_spec.get("invoice") or {},
                      "updates": updates, "additions": [], "unallocated": []})
    return specs


def apply_distributed_invoice_spec(spec):
    """Apply and register one deal allocation; safe to call sequentially for one invoice."""
    preflight = run_procurement_workflow({"action": "prepare_invoice_allocation", "invoice_spec": spec})
    if not preflight.get("ok"):
        return {"ok": False, "deal_id": str(spec.get("deal_id")), "error": preflight.get("error")}
    has_commercial_write = bool(spec.get("updates") or spec.get("additions"))
    applied = (run_supplier_invoice_apply(spec) if has_commercial_write else
               {"ok": True, "url": f"https://cclimat.megaplan.ru/deals/{spec.get('deal_id')}/card/",
                "updated_count": 0, "added_count": 0})
    if not applied.get("ok"):
        return {"ok": False, "deal_id": str(spec.get("deal_id")), "error": applied.get("error")}
    recorded = run_procurement_workflow({"action": "record_invoice", "deal_id": str(spec.get("deal_id")),
                                         "invoice_spec": spec, "result": applied})
    if not recorded.get("ok"):
        return {"ok": False, "deal_id": str(spec.get("deal_id")), "error": recorded.get("error")}
    doc = spec.get("invoice") or {}
    upload = None
    if doc.get("source_path"):
        upload = run_deal_browser({"action": "upload_supplier_invoice", "deal_id": str(spec.get("deal_id")),
            "path": doc["source_path"], "number": doc.get("number"), "supplier": doc.get("supplier")})
    economics = build_and_store_profitability(str(spec.get("deal_id")))
    if economics.get("ok") and economics.get("path"):
        try:
            os.remove(economics["path"])
        except OSError:
            pass
    procurement_register = build_and_store_procurement_register(str(spec.get("deal_id")))
    if procurement_register.get("ok") and procurement_register.get("path"):
        try:
            os.remove(procurement_register["path"])
            os.rmdir(os.path.dirname(procurement_register["path"]))
        except OSError:
            pass
    result = {"ok": True, "deal_id": str(spec.get("deal_id")), "applied": applied,
              "upload": upload, "economics": economics, "procurement_register": procurement_register}
    pending = supplier_completion.pending_steps(result)
    try:
        supplier_completion.record(spec, result)
    except Exception as exc:
        pending.append("сохранить результат проверки в общей очереди: " + type(exc).__name__)
    result.update(complete=not pending, pending_steps=pending)
    return result


def format_create_megaplan_deal_summary(spec, result):
    lines = [f"Сделка создана: {result['url']}", "", f"Клиент: {spec.get('client_name', '?')}"]
    for it in result.get("_expanded_items") or spec.get("items", []):
        # ledger entries (Phase 1b, spec mode) use "sell_price"; plain spec items
        # (Phase 1, already-priced) use "unit_price" - either shape can show up here.
        price = it.get("unit_price", it.get("sell_price"))
        lines.append(f"- {it['name']} × {it['qty']} — {_ru_money(price)} руб/шт")
    return "\n".join(lines)


def fetch_megaplan_invoice_pdf(params):
    """Shell out to megaplan_webhook.py's CLI mode (stdin JSON, never argv - see project
    memory on ARG_MAX) to fetch an invoice PDF by invoiceId or dealId. Returns the parsed
    {"ok": ..., "path"/"error", ...} dict, or {"ok": False, "error": ...} on any failure."""
    try:
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(MEGAPLAN_DIR, "megaplan_webhook.py"), "fetch-invoice-pdf"],
            cwd=MEGAPLAN_DIR, input=json.dumps(params, ensure_ascii=False),
            capture_output=True, text=True, timeout=MEGAPLAN_INVOICE_FETCH_TIMEOUT_SEC,
        )
        return json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as e:
        print(f"{LOG_PREFIX} fetch_megaplan_invoice_pdf failed: {e}", file=sys.stderr)
        return {"ok": False, "error": "внутренняя ошибка при обращении к Мегаплану"}


def send_latest_megaplan_invoice(token, chat_id, deal_id, wait_for_creation=False):
    """Fetch and send the latest customer invoice linked to a deal.

    A Megaplan automation may create/render the invoice a few seconds after the deal
    transition completes, so the status-driven path polls briefly. Manual requests
    remain single-shot and return immediately.
    """
    attempts = 3 if wait_for_creation else 1
    if wait_for_creation:
        send_message(token, chat_id, "🧾 Проверяю, сформировался ли счёт в Мегаплане...")
    last_error = "счёт пока не найден"
    for attempt in range(attempts):
        result = fetch_megaplan_invoice_pdf({"dealId": str(deal_id)})
        if result.get("ok"):
            try:
                sent = send_document(
                    token, chat_id, result["path"],
                    result.get("caption") or f"Счёт по сделке №{deal_id}",
                    result.get("filename"),
                )
            finally:
                try:
                    os.remove(result["path"])
                except OSError:
                    pass
            if sent is False:
                send_message(token, chat_id, "Счёт найден, но Telegram не принял файл. Попробуйте кнопку ещё раз.", DEAL_ACTIONS_KEYBOARD)
                return False
            send_message(token, chat_id, "Счёт получен из Мегаплана.", DEAL_ACTIONS_KEYBOARD)
            return True
        last_error = result.get("error") or last_error
        if attempt + 1 < attempts:
            time.sleep(2)
    if wait_for_creation:
        send_message(
            token, chat_id,
            "Статус изменён, но счёт в Мегаплане пока не сформирован. После его появления нажмите «📥 Получить счёт».",
            DEAL_ACTIONS_KEYBOARD,
        )
    else:
        send_message(token, chat_id, f"Не удалось получить счёт: {last_error}", DEAL_ACTIONS_KEYBOARD)
    return False


def send_megaplan_invoice_by_id(token, chat_id, invoice_id, keyboard=INVOICE_MENU_KEYBOARD, deal_id=None):
    result = fetch_megaplan_invoice_pdf({"invoiceId": str(invoice_id)})
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось получить счёт: {result.get('error')}", keyboard)
        return False
    try:
        sent = send_document(token, chat_id, result["path"], result.get("caption") or "Счёт из Мегаплана", result.get("filename"))
        if deal_id:
            archived = run_financial_archive({"deal_id": str(deal_id), "path": result["path"],
                                               "category": "invoice_client", "document_number": str(invoice_id)})
            if not archived.get("ok"):
                print(f"{LOG_PREFIX} customer invoice archive failed: {archived}", file=sys.stderr)
    finally:
        try:
            os.remove(result["path"])
        except OSError:
            pass
    if sent is False:
        send_message(token, chat_id, "Telegram не принял PDF счёта. Повторите попытку.", keyboard)
        return False
    return True


def invoice_error_text(error):
    """CRM refusals with the next step a person can take right here."""
    error = str(error or "неизвестная ошибка")
    folded = error.casefold()
    if "плательщик" in folded:
        return error + ("\n\nДобавьте плательщика: напишите «Смени плательщика на …» или откройте "
                        "«📑 Работа с договором» → «🏢 Добавить плательщика» и пришлите карточку реквизитов.")
    if "договор" in folded:
        return error + ("\n\nСчёт по пункту 6.4 выставляется по подписанному договору в сделке. "
                        "Подготовьте договор в «📑 Работа с договором» или выставите «📋 Общий счёт по спецификации».")
    if "позици" in folded:
        return error + "\n\nДобавьте позиции в сделку в Мегаплане и повторите."
    return error


EDO_OFFER_KEYBOARD = {"keyboard": [[{"text": "📤 Отправить по ЭДО"}], [{"text": "⬅️ Назад к сделке"}]],
                      "resize_keyboard": True, "one_time_keyboard": True}


def offer_edo(token, chat_id, deal_id, invoice_id):
    """Next step after an invoice (QA idea И-4): offered, never sent on its own."""
    update_deal_ui_state(chat_id, edo_offer={"deal_id": str(deal_id), "invoice_ids": [str(invoice_id)]})
    send_message(token, chat_id, f"Дальше: отправить договор и этот счёт Татьяне для передачи клиенту по ЭДО? "
                 f"Сделка №{deal_id}. Без нажатия ничего не отправляется.", EDO_OFFER_KEYBOARD)


def send_offered_edo(token, chat_id, state):
    offer = state.get("edo_offer") or {}
    if not offer.get("deal_id") or str(offer["deal_id"]) != str(state.get("current_deal_id") or offer["deal_id"]):
        send_message(token, chat_id, "Это предложение отправки устарело. Откройте сделку и выставьте или выберите счёт заново.",
                     DEAL_ACTIONS_KEYBOARD)
        return True
    update_deal_ui_state(chat_id, edo_offer=None)
    try:
        result = dispatch_edo_documents(token, offer["deal_id"], offer["invoice_ids"])
    except Exception as exc:
        print(f"{LOG_PREFIX} EDO dispatch failed: {exc}", file=sys.stderr)
        result = {"ok": False, "error": "техническая ошибка отправки; повторять до проверки не нужно"}
    if result.get("skipped"):
        text = "Этот договор и счёт уже отправлялись по ЭДО. Повторно не отправляю."
    elif result.get("ok"):
        text = "✅ Договор и счёт отправлены Татьяне по email и в Telegram для передачи по ЭДО."
    else:
        text = f"⚠️ Комплект для ЭДО не отправлен: {result.get('error')}"
    send_message(token, chat_id, text, DEAL_ACTIONS_KEYBOARD)
    return True


def create_and_send_contract_invoice(token, chat_id, deal_id, clause, keyboard=INVOICE_MENU_KEYBOARD):
    preview = run_contract_invoice({"action": "preview", "deal_id": str(deal_id), "clause": clause})
    if not preview.get('ok'):
        send_message(token, chat_id, f"Не удалось подготовить счёт: {preview.get('error')}", keyboard)
        return False
    result = run_contract_invoice({"action": "create", "deal_id": str(deal_id), "clause": clause,
        'expected_fingerprint': preview.get('fingerprint'), 'reconcile_total': preview.get('amount'),
        'reconcile_lines': [preview.get('line')], 'reconcile_confirmed_at': datetime.now(timezone.utc).isoformat()})
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось выставить счёт: {result.get('error')}", keyboard)
        return False
    send_message(token, chat_id, f"Счёт №{result.get('invoice_number') or result['invoice_id']} выставлен и привязан к сделке №{deal_id}.", keyboard)
    send_megaplan_invoice_by_id(token, chat_id, result["invoice_id"], keyboard, deal_id)
    return str(result["invoice_id"])


def create_and_send_full_invoice(token, chat_id, deal_id, keyboard=INVOICE_MENU_KEYBOARD):
    preview=current_deal_ui_state(chat_id).get('invoice_full_preview') or {}
    if str(preview.get('deal_id'))!=str(deal_id):
        preview=run_contract_invoice({'action':'preview_full','deal_id':str(deal_id)})
    if not preview.get('ok'):
        send_message(token,chat_id,'Счёт не подготовлен: '+invoice_error_text(preview.get('error')),keyboard); return False
    result = run_contract_invoice({"action": "create_full", "deal_id": str(deal_id),'expected_fingerprint':preview.get('fingerprint'),
        'reconcile_total': preview.get('total'), 'reconcile_lines': [row.get('name') for row in preview.get('rows') or []],
        'reconcile_confirmed_at': datetime.now(timezone.utc).isoformat()})
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось выставить общий счёт: {result.get('error')}", keyboard)
        return False
    send_message(token, chat_id, f"Общий счёт №{result.get('invoice_number') or result['invoice_id']} выставлен: позиций — {result.get('rows_count')}.", keyboard)
    update_deal_ui_state(chat_id,invoice_full_preview=None)
    send_megaplan_invoice_by_id(token, chat_id, result["invoice_id"], keyboard, deal_id)
    return str(result["invoice_id"])
    return True


def wait_for_new_deal_invoice(deal_id, before_ids, attempts=4):
    before_ids = {str(item) for item in (before_ids or [])}
    for attempt in range(attempts):
        result = run_contract_invoice({"action": "list", "deal_id": str(deal_id)})
        if result.get("ok"):
            fresh = [item for item in result.get("invoices") or [] if str(item.get("id")) not in before_ids]
            if fresh:
                return fresh[0]
        if attempt + 1 < attempts:
            time.sleep(2)
    return None


def ensure_contract_pdf_for_edo(deal_id):
    """Return the latest signed contract PDF, generating and attaching it when absent."""
    existing = run_deal_browser({"action": "get_contract", "deal_id": str(deal_id), "format": "pdf"})
    if existing.get("ok"):
        return existing

    generated = run_contract_builder({"action": "generate", "deal_id": str(deal_id)})
    if not generated.get("ok"):
        missing = generated.get("missing") or []
        details = ", ".join(str(value) for value in missing if value)
        error = generated.get("error") or "не удалось сформировать договор"
        if details:
            error = f"{error}: {details}"
        return {"ok": False, "error": f"PDF договора отсутствует; {error}"}

    paths = [generated.get("docx_path"), generated.get("pdf_path")]
    try:
        uploaded = run_deal_browser({
            "action": "upload_contracts",
            "deal_id": str(deal_id),
            "paths": paths,
        })
        if not uploaded.get("ok"):
            return {
                "ok": False,
                "error": "PDF договора отсутствует; новый договор сформирован, но не прикреплён: "
                         + str(uploaded.get("error") or "ошибка Мегаплана"),
            }
    finally:
        cleanup_generated_contract({"generated_contract": generated})

    attached = run_deal_browser({"action": "get_contract", "deal_id": str(deal_id), "format": "pdf"})
    if not attached.get("ok"):
        return {
            "ok": False,
            "error": "договор сформирован и загружен, но Мегаплан не вернул его PDF: "
                     + str(attached.get("error") or "неизвестная ошибка"),
        }
    return attached


def dispatch_edo_documents(token, deal_id, invoice_ids, force=False):
    """Send one contract plus newly issued invoices to the EDI employee once."""
    invoice_ids = sorted({str(value) for value in invoice_ids if value}, key=int)
    if not invoice_ids:
        return {"ok": False, "error": "нет новых счетов для отправки"}
    key = f"{deal_id}:" + ",".join(invoice_ids)
    registry=durable_json.read(EDO_DISPATCH_FILE,dict)
    if registry.get(key, {}).get("complete") and not force:
        return {"ok": True, "skipped": True}
    env = load_env()
    try:
        chat_id = open(EDO_RECIPIENT_CHAT_FILE, encoding="utf-8").read().strip()
    except OSError:
        chat_id = str(env.get("EDO_NOTIFY_TELEGRAM_CHAT_ID") or "").strip()
    if not chat_id:
        return {"ok": False, "error": "Татьяна не зарегистрирована в Telegram-боте"}
    contract = ensure_contract_pdf_for_edo(deal_id)
    preview = run_contract_builder({"action": "preview", "deal_id": str(deal_id)})
    invoices = run_contract_invoice({"action": "list", "deal_id": str(deal_id)})
    if not contract.get("ok"):
        return {"ok": False, "error": str(contract.get("error") or "не удалось получить PDF договора")}
    if not preview.get("ok"):
        try:
            os.remove(contract.get("path") or "")
        except OSError:
            pass
        return {"ok": False, "error": "не удалось прочитать данные договора: "
                                         + str(preview.get("error") or "неизвестная ошибка")}
    if not invoices.get("ok"):
        try:
            os.remove(contract.get("path") or "")
        except OSError:
            pass
        return {"ok": False, "error": "не удалось получить сведения о счёте: "
                                         + str(invoices.get("error") or "неизвестная ошибка")}
    metadata = {str(item["id"]): item for item in invoices.get("invoices") or []}
    selected = [metadata[item] for item in invoice_ids if item in metadata]
    if len(selected) != len(invoice_ids):
        return {"ok": False, "error": "не найдены сведения о новом счёте"}
    p = preview["preview"]
    checked=run_contract_invoice({'action':'validate_bundle','deal_id':str(deal_id),
        'contract_file_id':contract.get('file_id'),'contract_path':contract['path'],'invoice_ids':invoice_ids})
    if not checked.get('ok'):
        try:os.remove(contract['path'])
        except OSError:pass
        return {'ok':False,'error':'Комплект ЭДО не прошёл сверку: '+str(checked.get('error') or 'не подтверждены версии документов')}
    if (checked.get('contract_number')!=p.get('number') or checked.get('contract_date')!=p.get('date')):
        try:os.remove(contract['path'])
        except OSError:pass
        return {'ok':False,'error':'Данные договора изменились во время подготовки комплекта; отправка остановлена.'}
    invoice_labels = [f"Счет № {item.get('number')} от {item.get('date')}" for item in selected]
    documents = [f"Договор № {p.get('number')} от {p.get('date')}", *invoice_labels]
    lines = "\n".join(f"  - {item}" + ("," if index + 1 < len(documents) else "")
                      for index, item in enumerate(documents))
    text_message = (
        "Татьяна Григорьевна, добрый день!\n\n"
        f"Отправьте, пожалуйста, для клиента {p.get('payer_name')} по ЭДО следующие документы:\n\n"
        f"{lines}\n\n"
        "С уважением, SmartBild AI Assistant\n"
        "@SmartBildAI_bot"
    )
    paths = [(contract["path"], contract.get("filename") or "Договор.pdf")]
    try:
        for item in selected:
            fetched = fetch_megaplan_invoice_pdf({"invoiceId": item["id"]})
            if not fetched.get("ok"):
                raise RuntimeError(fetched.get("error") or "не получен PDF счёта")
            paths.append((fetched["path"], fetched.get("filename") or f"Счёт {item.get('number')}.pdf"))
        message = EmailMessage()
        message["From"] = env["SMTP_FROM"]
        message["To"] = env["EDO_NOTIFY_EMAIL"]
        message["Subject"] = (f"Документы по ЭДО — {p.get('client')} — "
                              f"{p.get('payer_name')}")
        message.set_content(text_message)
        for path, filename in paths:
            with open(path, "rb") as source:
                message.add_attachment(source.read(), maintype="application", subtype="pdf", filename=filename)
        def deliver_email():
            port = int(env['SMTP_PORT'])
            connection = (smtplib.SMTP(env['SMTP_HOST'], port, timeout=30) if port == 587 else
                          smtplib.SMTP_SSL(env['SMTP_HOST'], port, context=ssl.create_default_context(), timeout=30))
            with connection as smtp:
                if port == 587:
                    smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
                smtp.login(env['SMTP_USERNAME'], env['SMTP_PASSWORD'])
                refused = smtp.send_message(message)
                if refused: raise RuntimeError('Адресат не принял письмо')
            return True
        content_hash = hashlib.sha256(text_message.encode())
        # Use the business document identity, not generated PDF metadata: a
        # regeneration timestamp must not turn a delivery retry into a resend.
        content_hash.update(key.encode())
        content_hash.update(str(chat_id).encode())
        content_hash.update(env['EDO_NOTIFY_EMAIL'].encode())
        content_hash.update(checked['fingerprint'].encode())
        steps = [('edo-email', deliver_email), ('edo-telegram-message', lambda: send_message(token, chat_id, text_message))]
        steps.extend((f'edo-telegram-file-{index}', lambda p=path, n=filename: send_document(token, chat_id, p, filename=n))
                     for index, (path, filename) in enumerate(paths))
        # force is an explicit resend command, not a retry after an outage.
        delivery_key = key + (':' + uuid.uuid4().hex if force else '')
        delivery = delivery_steps.deliver(WorkflowStore(WORKFLOW_DB_FILE), delivery_key, content_hash.hexdigest(), steps)
        if not delivery.get('ok'):
            return delivery
        with durable_json.locked(EDO_DISPATCH_FILE):
            registry=durable_json.read(EDO_DISPATCH_FILE,dict)
            registry[key] = {"complete": True, "fingerprint":checked['fingerprint'],"time": datetime.now(timezone.utc).isoformat()}
            durable_json.save(EDO_DISPATCH_FILE,registry)
        return {"ok": True}
    finally:
        for path, _filename in paths:
            try:
                os.remove(path)
            except OSError:
                pass


def extract_update_kemix_prices(reply_text):
    """Pull an UPDATE_KEMIX_PRICES_BEGIN/END JSON block out of the reply, if present."""
    m = UPDATE_KEMIX_PRICES_RE.search(reply_text)
    if not m:
        return reply_text, None
    clean_text = UPDATE_KEMIX_PRICES_RE.sub("", reply_text).strip()
    try:
        spec = json.loads(m.group(1))
    except Exception as e:
        print(f"{LOG_PREFIX} UPDATE_KEMIX_PRICES block was not valid JSON: {e}", file=sys.stderr)
        return clean_text, {"__invalid__": True}
    return clean_text, spec


def run_update_kemix_prices(spec):
    """Run the fixed, non-shell price-update script on Claude's behalf - it only ever
    writes kemix_prices.json (a data file), never lets Claude touch code directly."""
    fd, spec_path = __import__("tempfile").mkstemp(suffix=".json", prefix="kemix-price-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False)
        result = subprocess.run(
            [REPORT_VENV_PY, os.path.join(HOGART_DIR, "update_kemix_prices.py"), spec_path],
            cwd=HOGART_DIR, capture_output=True, text=True, timeout=UPDATE_KEMIX_PRICES_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "обновление цен не уложилось в отведённое время"}
    finally:
        try:
            os.remove(spec_path)
        except OSError:
            pass

    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        print(f"{LOG_PREFIX} update_kemix_prices.py bad output: stdout={result.stdout[-500:]!r} stderr={result.stderr[-500:]!r}", file=sys.stderr)
        return {"ok": False, "error": "скрипт обновления цен вернул некорректный ответ"}


def format_price_update_summary(result):
    lines = ["Цены КЕМИКС обновлены:"]
    for c in result.get("changes") or []:
        arrow = "↗" if c["new"] > c["old"] else "↘"
        pct = f" ({c['pct']:+}%)" if c.get("pct") is not None else ""
        lines.append(f"{arrow} {c['item']}: {c['old']} → {c['new']} ₽{pct}")
    if not result.get("changes"):
        lines.append("(цены не изменились)")
    not_found = result.get("not_found") or []
    if not_found:
        lines.append("")
        lines.append("⚠️ Не найдено в присланном файле (оставил прежние значения):")
        for item in not_found:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _ru_money(n):
    return f"{n:,.2f}".replace(",", " ").replace(".", ",")


def format_kp_summary(kp_result):
    """generate_kp.py now always returns a list of independent "variants" (2026-08-26,
    see that script's docstring) - a single unlabeled variant (the common one-option
    case) reads exactly like the old flat-summary format; multiple variants each get
    their own heading/total/warning, with NO combined grand total across them (they're
    alternatives the client picks ONE of, never a single combined order)."""
    variants = kp_result["variants"]
    lines = [f"КП для {kp_result['client']} готово" + (":" if len(variants) == 1 else f" — {len(variants)} вариант(а/ов):")]
    any_cost_unknown = False
    for v in variants:
        if v.get("label"):
            lines.append("")
            lines.append(f"**{v['label']}**")
        for it in v["items"]:
            kind = it.get("type", "equipment")
            if kind == "equipment":
                lines.append(
                    f"- {it['sku']} × {it['qty']} — {_ru_money(it['unit_price'])} руб/шт "
                    f"({it['availability']})"
                )
            elif kind == "install":
                lines.append(
                    f"  + монтаж ({it['capacity_kw']} кВт) × {it['qty']} — "
                    f"{_ru_money(it['unit_price'])} руб/шт"
                )
            elif kind == "freon_line":
                lines.append(
                    f"  + доп. фреоновая магистраль, {it['length_m']} м — "
                    f"{_ru_money(it['unit_price_per_m'])} руб/м"
                )
        lines.append(f"Итого: {_ru_money(v['total'])} руб.")
        if not v["economics"].get("cost_fully_known"):
            any_cost_unknown = True

    lines.append("")
    lines.append("Экономика и профит по каждому варианту — в приложенном Excel-файле (отдельные таблицы).")
    if any_cost_unknown:
        lines.append(
            "⚠️ По части позиций (см. файл) нет закупочной цены у поставщика — "
            "себестоимость и прибыль там занижены."
        )
    return "\n".join(lines)


def extract_attachments(reply_text):
    """Pull ATTACH_FILE: <path> lines out of the reply, return (clean_text, [paths])."""
    paths = [m.strip() for m in ATTACH_RE.findall(reply_text)]
    clean_text = ATTACH_RE.sub("", reply_text).strip()
    valid_paths = []
    home = os.path.realpath(os.path.expanduser("~"))
    for p in paths:
        rp = os.path.realpath(os.path.expanduser(p))
        if not rp.startswith(home + os.sep):
            print(f"{LOG_PREFIX} refusing to attach path outside home: {rp}", file=sys.stderr)
            continue
        if not os.path.isfile(rp):
            print(f"{LOG_PREFIX} ATTACH_FILE path does not exist: {rp}", file=sys.stderr)
            continue
        if os.path.getsize(rp) > MAX_ATTACH_BYTES:
            print(f"{LOG_PREFIX} ATTACH_FILE too large, skipping: {rp}", file=sys.stderr)
            continue
        valid_paths.append(rp)
    return clean_text, valid_paths


def _parse_codex_output(result):
    """Return (final_text, thread_id) from `codex exec --json` JSONL output."""
    messages = []
    thread_id = None
    for raw_line in (result.stdout or "").splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            messages.append(item.get("text") or "")
    return (messages[-1].strip() if messages else ""), thread_id


def _run_codex(session_id, prompt, timeout=MODEL_TIMEOUT_SEC):
    """Run one Codex turn. An empty session_id starts a new persistent thread."""
    common = ["--json", "--ignore-rules", "--skip-git-repo-check"]
    if session_id:
        cmd = [
            CODEX_BIN, "exec", "resume", *common, "--all",
            "-c", 'sandbox_mode="read-only"', session_id, "-",
        ]
        model_prompt = prompt
    else:
        cmd = [
            CODEX_BIN, "exec", *common, "--sandbox", "read-only",
            "--cd", os.path.expanduser("~"), "-",
        ]
        # Codex CLI has no append-system-prompt flag. Seed the persistent thread with
        # the bridge protocol once; later turns resume the same thread.
        model_prompt = SYSTEM_PROMPT + "\n\nСООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ:\n" + prompt
    return subprocess.run(
        cmd,
        cwd=os.path.expanduser("~"),
        input=model_prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _model_chat_id():
    return str(getattr(UI_CONTEXT, "actor", getattr(UI_CONTEXT, "chat_id", "owner")))


def _model_failure(prompt, kind, mode):
    ident = model_recovery.save_failure(MODEL_FAILURES_FILE, _model_chat_id(), prompt, mode, kind)
    print(f"{LOG_PREFIX} model unavailable kind={kind} request={ident}", file=sys.stderr)
    return model_recovery.ModelUnavailable(model_recovery.failure_message(kind, mode), kind, ident)


def ask_claude(session_id, prompt):
    """Resume valid chat threads; preserve failures rather than blaming user input."""
    session_id = open(SESSION_FILE).read().strip() if os.path.exists(SESSION_FILE) else ""
    model_recovery.begin_request(MODEL_FAILURES_FILE, _model_chat_id(), prompt, "chat")
    try:
        result = _run_codex(session_id, prompt)
        kind = model_recovery.failure_kind(result)
        # A new conversation fixes a missing rollout, not expired credentials.
        if kind == "missing_thread" and session_id:
            result = _run_codex("", prompt)
            kind = model_recovery.failure_kind(result)
    except subprocess.TimeoutExpired:
        return _model_failure(prompt, "timeout", "chat")
    except OSError:
        return _model_failure(prompt, "provider", "chat")
    if kind:
        return _model_failure(prompt, kind, "chat")
    out, new_thread_id = _parse_codex_output(result)
    if not out:
        return _model_failure(prompt, "provider", "chat")
    if new_thread_id and new_thread_id != session_id:
        with open(SESSION_FILE, "w") as f:
            f.write(new_thread_id)
    model_recovery.mark_answered(MODEL_FAILURES_FILE, _model_chat_id(), prompt, "chat")
    return out


def ask_fresh_document_model(prompt):
    """Transactional documents stay isolated from the general conversation."""
    model_recovery.begin_request(MODEL_FAILURES_FILE, _model_chat_id(), prompt, "document")
    try:
        result = _run_codex("", prompt, timeout=120)
    except subprocess.TimeoutExpired:
        return _model_failure(prompt, "timeout", "document")
    except OSError:
        return _model_failure(prompt, "provider", "document")
    kind = model_recovery.failure_kind(result)
    if kind:
        return _model_failure(prompt, kind, "document")
    out, _thread_id = _parse_codex_output(result)
    if not out:
        return _model_failure(prompt, "provider", "document")
    model_recovery.mark_answered(MODEL_FAILURES_FILE, _model_chat_id(), prompt, "document")
    return out


def extract_document_text_for_model(path, max_chars=50000):
    """Provide machine-readable document text directly to the document parser.

    For normal supplier PDFs this removes an expensive model tool-call/read step.
    Scanned or protected documents simply fall back to the existing model path.
    """
    ext = os.path.splitext(str(path or ""))[1].casefold()
    if ext not in (".pdf", ".xlsx", ".xls", ".docx"):
        return ""
    try:
        if ext == ".pdf":
            result = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=15)
        else:
            result = subprocess.run([REPORT_VENV_PY, os.path.join(BASE_DIR, "extract_document_text.py")],
                input=json.dumps({"path": str(path)}), capture_output=True, text=True, timeout=20)
        if result.returncode:
            return ""
        value = (result.stdout or "").strip()
        return value[:max_chars] if len(value) >= 100 else ""
    except Exception as exc:
        print(f"{LOG_PREFIX} document extraction failed: {type(exc).__name__}", file=sys.stderr)
        return ""


DEVELOPER_SYSTEM_PROMPT = """Разрешены только проекты telegram-bridge, megaplan-crm, hogart-scraper, daichi-scraper. Системные изменения, sudo, SSH, настройки VPN и управление службами выполняет владелец через SSH. Не пытайся обходить ограничения. Для локальных тестовых HTTP-серверов используй порты 48000–48999. После изменения кода моста используй существующий механизм безопасной перезагрузки.
Ты Codex-разработчик SmartBild. Пользователь явно передал задачу через режим
«Задача разработчику». Работай непосредственно с проектами в /home/kocher.av: исследуй причину,
внеси необходимые изменения, проверь их тестами и сообщи владельцу, если для применения нужен перезапуск службы через SSH. Не ограничивайся советами, если задача просит изменение. Береги существующие пользовательские
данные и не выполняй разрушительные действия без явного основания в задаче. В конце дай короткий отчёт
на русском: что сделано, как проверено и что пользователь может проверить в боте.
ВАЖНО: не перезапускай telegram-bridge.service самостоятельно. Мост отправит пользователю твой итоговый
отчёт и только после этого сам выполнит необходимый перезапуск."""


def _run_developer_codex(session_id, prompt, workdir=None, sandbox_root=None):
    workdir = str(workdir or BASE_DIR)
    writable = ["/home/kocher.av/telegram-bridge", "/home/kocher.av/megaplan-crm",
                "/home/kocher.av/hogart-scraper", "/home/kocher.av/daichi-scraper"]
    # A task clone is opened through its parent: Codex keeps <root>/.git read-only.
    root = str(sandbox_root or workdir)
    if root not in writable:
        writable.append(root)
    # Newer Codex sandboxes keep <root>/.git read-only inside a writable root
    # (26.10: «.git/index.lock: Read-only file system»). Handoff work must commit
    # in its service clone, so its metadata is named explicitly.
    git_dir = os.path.join(workdir, ".git")
    if os.path.isdir(git_dir) and git_dir not in writable:
        writable.append(git_dir)
    common = ["--json", "--ignore-rules", "--skip-git-repo-check", "-c", 'approval_policy="never"',
              "-c", 'sandbox_workspace_write.network_access=true', "-c",
              'sandbox_workspace_write.writable_roots=' + json.dumps(writable)]
    if session_id:
        cmd = [CODEX_BIN, "exec", "resume", *common, "--all",
               "-c", 'sandbox_mode="workspace-write"', session_id, "-"]
        model_prompt = "НОВАЯ ЗАДАЧА РАЗРАБОТЧИКУ:\n" + prompt
    else:
        cmd = [CODEX_BIN, "exec", *common, "--sandbox", "workspace-write",
               "--cd", workdir, "-"]
        model_prompt = DEVELOPER_SYSTEM_PROMPT + "\n\nЗАДАЧА ПОЛЬЗОВАТЕЛЯ:\n" + prompt
    return subprocess.run(cmd, cwd=workdir, input=model_prompt,
                          capture_output=True, text=True, timeout=DEVELOPER_TIMEOUT_SEC)


def ask_task_developer(task):
    """Fresh developer session in a task clone (see handoff_watcher.workspace)."""
    try:
        root, clone = handoff_watcher.workspace(task['id'])
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"{LOG_PREFIX} task workspace failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return f"Не удалось выполнить задачу: рабочая копия репозитория не подготовлена ({type(exc).__name__})."
    return ask_developer(handoff_watcher.developer_prompt(task), workdir=str(clone), fresh=True, sandbox_root=str(root))


def ask_developer(prompt, workdir=None, fresh=False, sandbox_root=None):
    session_id = (open(DEVELOPER_SESSION_FILE).read().strip()
                  if not fresh and os.path.exists(DEVELOPER_SESSION_FILE) else "")
    try:
        result = _run_developer_codex(session_id, prompt, workdir, sandbox_root)
    except subprocess.TimeoutExpired:
        return "Задача не завершилась за 30 минут. Напишите её повторно или разбейте на несколько этапов."
    if result.returncode != 0:
        print(f"{LOG_PREFIX} developer Codex failed, retrying fresh: {(result.stderr or '')[-1500:]}", file=sys.stderr)
        try:
            result = _run_developer_codex("", prompt, workdir, sandbox_root)
        except subprocess.TimeoutExpired:
            return "Задача не завершилась за 30 минут. Напишите её повторно или разбейте на несколько этапов."
    if result.returncode != 0:
        print(f"{LOG_PREFIX} developer Codex fresh run failed: {(result.stderr or '')[-2000:]}", file=sys.stderr)
        return "Не удалось выполнить задачу разработчику. Технические подробности записаны в журнале бота."
    answer, new_thread_id = _parse_codex_output(result)
    if new_thread_id:
        with open(DEVELOPER_SESSION_FILE, "w") as target:
            target.write(new_thread_id)
    return answer or "Задача завершена, но Codex не вернул текстовый отчёт."


CHANGELOG_FILE = os.path.join(BASE_DIR, "docs", "architecture", "CHANGELOG.md")


def changelog_headings(path=None):
    try:
        with open(path or CHANGELOG_FILE, encoding="utf-8") as source:
            return [line[3:].strip() for line in source if line.startswith("## ")]
    except OSError:
        return []


def announce_reload(token, chat_id):
    """Owner request 25.10: say when the bot came back on a new version and what it brings.
    A restart on the same code stays silent."""
    try:
        with open(__file__, "rb") as source:
            version = hashlib.sha256(source.read()).hexdigest()[:12]
    except OSError:
        return False
    state = durable_json.read(RELOAD_NOTICE_FILE, dict)
    if state.get("version") == version:
        return False
    headings = changelog_headings()
    known = state.get("last_heading")
    fresh = headings[:headings.index(known)] if known in headings else headings[:3]
    lines = [f"🔄 Бот перезапущен на новой версии ({version[:8]}) и работает."]
    if fresh:
        lines.append("Что нового:")
        lines += ["• " + heading.split(" — ", 1)[-1] for heading in fresh[:5]]
        if len(fresh) > 5:
            lines.append(f"…и ещё {len(fresh) - 5} — в журнале изменений.")
    send_message(token, chat_id, "\n".join(lines))
    durable_json.save(RELOAD_NOTICE_FILE, {"version": version, "last_heading": headings[0] if headings else known,
                                           "announced_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return True


STALE_RELOAD_NOTICE = {"key": None}


def report_stale_reload(token, chat_id):
    """A released version that cannot load must not stay silent."""
    changed = safe_reload.stale_request(RELOAD_REQUEST_FILE, __file__)
    key = "|".join(changed)
    if not changed or STALE_RELOAD_NOTICE["key"] == key:
        return False
    STALE_RELOAD_NOTICE["key"] = key
    names = ", ".join(os.path.basename(path) for path in changed[:5]) + (f" и ещё {len(changed) - 5}" if len(changed) > 5 else "")
    send_message(token, chat_id, "⚠️ Выпущенная версия бота НЕ загружена: после выпуска на сервере изменились файлы "
                 f"({names}). Бот продолжает работать на прежней версии. Нужен повторный выпуск, чтобы код "
                 "на сервере совпал с проверенным.")
    return True


def reload_snapshot():
    try:
        return safe_reload.bundle_manifest(__file__)
    except (OSError, SyntaxError) as exc:
        print(f"{LOG_PREFIX} bundle snapshot failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def bundle_changed(before):
    """Any changed module needs a reload, not only bridge.py (QA 25.10: a stand fix
    after a release silently voided the release's reload request)."""
    after = reload_snapshot()
    return after is not None and after != before


def process_developer_task(token, chat_id, task_text):
    bundle_before = reload_snapshot()
    with open(DEVELOPER_LOCK_FILE, "w") as model_lock:
        fcntl.flock(model_lock, fcntl.LOCK_EX)
        result = ask_developer(task_text)
    current = current_deal_ui_state(chat_id)
    if current.get("pending") == "developer_task_running":
        update_deal_ui_state(chat_id, pending=None, developer_task_text=None, developer_task_started_at=None)
    if bundle_changed(bundle_before):
        safe_reload.request(RELOAD_REQUEST_FILE,__file__)
        result+='\n\nОбновление процесса ожидает завершения активных задач; они не будут прерваны перезапуском.'
    send_message(token, chat_id, "✅ Результат задачи разработчику:\n\n" + result, MAIN_KEYBOARD)


def process_qa_developer_task(token, chat_id, task_id):
    """Owner rule 25.10: a QA repair takes the same route as every task — branch
    handoff/QA-…, report in GitHub, tester review, owner release.  Nothing is
    edited or reloaded in the deployed bot."""
    task = qa_handoff.claim(task_id)
    if not task:
        send_message(token, chat_id, f"QA-задача {task_id} уже выполняется или была обработана.", MAIN_KEYBOARD)
        return False
    handoff = qa_handoff.handoff_task(task)
    send_message(token, chat_id, handoff_watcher.started_text(handoff))
    bundle_before = reload_snapshot()
    with open(DEVELOPER_LOCK_FILE, 'w') as model_lock:
        fcntl.flock(model_lock, fcntl.LOCK_EX)
        result = ask_task_developer(handoff)
    failed = result.startswith(('Не удалось выполнить', 'Задача не завершилась'))
    try:
        verification = handoff_watcher.verify_report(task_id, handoff_watcher.repository())
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        verification = {'ok': False, 'status': None, 'commits': {}, 'report': None,
                        'problems': [f'GitHub не прочитан ({type(exc).__name__})']}
    outcome = ('awaiting_release' if not failed and verification['ok'] and verification.get('status') == 'done'
               else 'waiting_input' if verification['ok'] and verification.get('status') in ('blocked', 'needs_owner')
               else 'approved')
    qa_handoff.finish(task_id, result, outcome == 'awaiting_release', status=outcome)
    text = handoff_watcher.result_text(handoff, verification, result)
    if outcome == 'awaiting_release':
        text += (f"\n\nДальше: тестировщик проверит ветку handoff/{task_id}, затем выпуск вашей кнопкой. "
                 "В работающем боте пока ничего не изменилось.")
    if bundle_changed(bundle_before):
        # The rules forbid it; never load such an edit silently.
        text += ("\n\n⚠️ Разработчик изменил файлы работающего бота в обход ветки. Перезагрузка НЕ запрошена; "
                 "следующий выпуск вернёт версию из GitHub.")
    send_message(token, chat_id, text, MAIN_KEYBOARD)
    return outcome == 'awaiting_release'


def handoff_keyboard(task_id):
    return {'keyboard': [[{'text': f'✅ Выполнить {task_id}'}], [{'text': f'🚫 Отклонить {task_id}'}]],
            'resize_keyboard': True, 'one_time_keyboard': True}


def poll_handoff(token, chat_id):
    """Pick up tester tasks from Git (read-only) and hand them to the developer once."""
    config = qa_schedule.handoff_config()
    try:
        repo = handoff_watcher.repository()
        tasks, problems = handoff_watcher.discover(repo, config)
        state = handoff_watcher.read_state()
        dispatch, ask, new_problems = handoff_watcher.plan(tasks, problems, state, config)
        handoff_watcher.save_state(state)
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"{LOG_PREFIX} handoff poll failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False
    for problem in new_problems:
        send_message(token, chat_id, f"📨 Задание тестировщика оформлено с ошибкой и не передано: {problem['path']} "
                     f"({problem['ref']}) — {problem['error']}. Разработчику ничего не передано.")
    for task in ask:
        send_message(token, chat_id, handoff_watcher.owner_card(task), handoff_keyboard(task['id']))
    for task in dispatch:
        process_handoff_task(token, chat_id, task['id'])
    return True


def process_handoff_task(token, chat_id, task_id):
    if not handoff_watcher.start(task_id):
        return False
    try:
        task = handoff_watcher.load_task(task_id, handoff_watcher.repository())
    except (RuntimeError, ValueError, OSError) as exc:
        handoff_watcher.finish(task_id, f'Задание не прочитано: {exc}', False)
        send_message(token, chat_id, f"⚠️ {task_id}: файл задания не прочитан ({exc}). Разработчику не передано.")
        return False
    if task is None:
        handoff_watcher.finish(task_id, 'Файл изменён после решения; будет рассмотрен заново.', False)
        return False
    send_message(token, chat_id, handoff_watcher.started_text(task))
    bundle_before = reload_snapshot()
    with open(DEVELOPER_LOCK_FILE, 'w') as model_lock:
        fcntl.flock(model_lock, fcntl.LOCK_EX)
        result = ask_task_developer(task)
    ok = not result.startswith(('Не удалось выполнить', 'Задача не завершилась'))
    handoff_watcher.finish(task_id, result, ok)
    # The developer's own words are a claim; GitHub is the receipt.
    try:
        verification = handoff_watcher.verify_report(task_id, handoff_watcher.repository(),
                                                     release=task['kind'] == 'release')
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        verification = {'ok': False, 'status': None, 'commits': {}, 'report': None,
                        'problems': [f'GitHub не прочитан ({type(exc).__name__})']}
    handoff_watcher.record_verification(task_id, verification)
    if bundle_changed(bundle_before):
        safe_reload.request(RELOAD_REQUEST_FILE, __file__)
        result += '\n\nОбновление ожидает безопасной перезагрузки после завершения активных задач.'
    send_message(token, chat_id, handoff_watcher.result_text(task, verification, result), MAIN_KEYBOARD)
    return ok and verification['ok']


def run_qa_autopilot(token, chat_id, profile='human'):
    """Run QA, repair a technical failure, and immediately verify the repair.

    Two repair attempts bound one scheduled cycle.  An unresolved task remains
    approved and is resumed by the next cycle without owner intervention.
    """
    repairs = 0
    while True:
        result = qa_autopilot.run(profile)
        if not result.get('ok'):
            send_message(token, chat_id, '⚠️ AI-тестировщик не завершил прогон: ' + str(result.get('error')))
            return False
        tasks = result.get('tasks') or ([result['task']] if result.get('task') else [])
        if not tasks:
            return True
        # External prerequisites (missing CRM snapshot, owner decision) leave the
        # developer queue; a code defect found in the same run is still repaired.
        for item in tasks:
            qa_autopilot.defer_external(item)
        task = next((item for item in tasks if qa_autopilot.technical(item)), None)
        if not task:
            return False
        approved = qa_autopilot.approve_technical(task)
        if not approved:
            return False
        if repairs >= 2:
            return False
        repairs += 1
        send_message(token, chat_id, f"🧪 {approved['id']} передана разработчику автоматически.")
        # The repair lands in a branch; it is verified by the run after its release.
        process_qa_developer_task(token, chat_id, approved['id'])
        return False


def nightly_qa_window(moment=None):
    """Night window of the approved schedule (default 00:00–07:00 Moscow)."""
    moment = moment or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError('Night QA requires a timezone-aware moment')
    return qa_schedule.in_night_window(moment)


def qa_night_plan(schedule=None):
    """Owner-readable plan for the coming night (the night after today's digest)."""
    try:
        import human_qa_explorer
        missions = human_qa_explorer.load_missions()
    except Exception as exc:
        print(f"{LOG_PREFIX} explorer missions unavailable: {type(exc).__name__}", file=sys.stderr)
        missions = ()
    tonight = qa_schedule.moscow().date() + timedelta(days=1)
    return qa_schedule.plan_text(tonight, schedule, missions)


def send_owner_digest(token, chat_id, schedule=None, now=None):
    """Evening digest; then new ideas with decision buttons; on Fridays the week's ideas."""
    send_message(token, chat_id, qa_autopilot.digest(now=now) + "\n\n" + qa_night_plan(schedule), MAIN_KEYBOARD)
    try:
        waiting = qa_ideas.register(qa_ideas.recent(qa_handoff._read(qa_handoff.PRODUCTION_STATE), now), now=now)
        if waiting:
            text, keyboard = qa_ideas.card(waiting)
            send_message(token, chat_id, text, keyboard)
        if qa_schedule.moscow(now).weekday() == 4:
            send_message(token, chat_id, qa_ideas.weekly_text(now=now), MAIN_KEYBOARD)
    except (OSError, ValueError) as exc:
        print(f"{LOG_PREFIX} tester ideas unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        send_message(token, chat_id, "⚠️ Идеи тестировщика не показаны: реестр идей не прочитан.", MAIN_KEYBOARD)


def process_idea_task(token, chat_id, idea_id):
    """A taken idea goes to the developer under the handoff rules and GitHub verification."""
    record = qa_ideas.start(idea_id)
    if not record:
        return False
    task = qa_ideas.developer_task(record)
    send_message(token, chat_id, handoff_watcher.started_text(task))
    bundle_before = reload_snapshot()
    with open(DEVELOPER_LOCK_FILE, 'w') as model_lock:
        fcntl.flock(model_lock, fcntl.LOCK_EX)
        result = ask_task_developer(task)
    ok = not result.startswith(('Не удалось выполнить', 'Задача не завершилась'))
    try:
        verification = handoff_watcher.verify_report(idea_id, handoff_watcher.repository())
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        verification = {'ok': False, 'status': None, 'commits': {}, 'report': None,
                        'problems': [f'GitHub не прочитан ({type(exc).__name__})']}
    qa_ideas.finish(idea_id, ok and verification['ok'] and verification.get('status') == 'done', verification)
    if bundle_changed(bundle_before):
        safe_reload.request(RELOAD_REQUEST_FILE, __file__)
        result += '\n\nОбновление ожидает безопасной перезагрузки после завершения активных задач.'
    send_message(token, chat_id, handoff_watcher.result_text(task, verification, result), MAIN_KEYBOARD)
    return ok and verification['ok']


def run_nightly_qa(token, chat_id):
    """Run broad profiles serially so repairs never race each other."""
    completed = []
    # Order comes from QA_SCHEDULE.json; «explore» is the AI tester playing a
    # manager, and its findings wait for the owner.
    for profile in qa_schedule.night_sequence():
        completed.append(profile)
        run_qa_autopilot(token, chat_id, profile)
        if safe_reload.pending_reviewed(RELOAD_REQUEST_FILE, __file__):
            break
    return completed


def installer_media_allowed(msg, pending):
    if pending == 'installation_report_collect':
        return True
    return ('document' in msg and pending in (None, '', 'installer_report_file', 'installer_report_tables'))


def handle_installer_ui(token, chat_id, text):
    value = text.strip()
    if value in ('⬅️ Главное меню','/menu','/start','❌ Отмена'):
        update_deal_ui_state(chat_id,pending=None,installation_report_id=None)
        send_message(token,chat_id,'Меню монтажника. Черновики отчётов сохранены.',INSTALLER_USER_KEYBOARD)
        return True
    state = current_deal_ui_state(chat_id)
    pending = str(state.get("pending") or "")
    if value in ('📤 Сборный отчёт','📄 Отправить отчёт'):
        if pending.startswith(('installer_report','installer_excel')) and state.get('installer_report') and pending != 'installer_report_submitted':
            send_message(token,chat_id,'У вас уже открыт сборный отчёт. Продолжите проверку или нажмите «❌ Отменить отчёт», прежде чем загружать новый.',installer_review_keyboard(chat_id))
            return True
        update_deal_ui_state(chat_id,pending='installer_report_file',installer_report=None,installer_report_failure=None,installation_report_id=None)
        send_message(token,chat_id,'Пришлите сборный отчёт в PDF, Word (.docx), Excel (.xlsx) или текстом одним сообщением. Если в нём есть «По таблице», затем запрошу Excel .xlsx. После проверки передайте черновик руководителю; начисления без его утверждения не записываются.',{'keyboard':[[{'text':'❌ Отменить отчёт'}]],'resize_keyboard':True})
        return True
    if pending == 'installer_report_file' and value == '🔄 Повторить разбор':
        path = (state.get('installer_report_failure') or {}).get('source_path')
        if path and os.path.isfile(path):
            process_installer_report(token, chat_id, path)
        else:
            send_message(token, chat_id, 'Сохранённый файл не найден. Пришлите отчёт файлом или текстом.')
        return True
    if pending == 'installer_report_file' and '\n' in value and re.search(r'\d', value):
        os.makedirs(INCOMING_DIR, exist_ok=True)
        import tempfile
        stamp = datetime.now(timezone.utc).strftime('%d.%m.%Y')
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.txt', prefix=f'Отчет_{stamp}_', dir=INCOMING_DIR, delete=False) as source:
            source.write(value)
            path = source.name
        process_installer_report(token, chat_id, path)
        return True
    if pending.startswith(('installer_report','installer_excel')) and value not in ('🛠 Мои монтажи','⬅️ Мои монтажи','📜 История монтажей','📚 Утверждённые отчёты','📊 Мои взаиморасчёты','❓ Помощь'):
        allowed={'✅ Объекты верны','✏️ Исправить объект','▶️ Разобрать исключения','📤 Передать руководителю','❌ Отменить отчёт','✅ Все файлы загружены'}
        if pending=='installer_report_exception':
            allowed.update({'✅ Строки и суммы сверены','💰 Учесть одной суммой','✅ Принять выполнение таблицы','🔢 Выбрать позиции позже','✅ Подтвердить операцию','⏭ Оставить вопросом','➕ Внеплановый расход','🚫 Не учитывать','📦 Всякая всячина','✅ Принять построчный итог','➕ Добавить корректировку','✏️ Исправить строки','🔢 Указать номер сделки'})
        if pending=='installer_excel_report_deal':allowed.add('📦 Всякая всячина')
        free_input=(pending=='installer_report_fix_object' and value.startswith('Объект: ')) or (pending in ('installer_report_fix_deal','installer_report_exception_amount','installer_report_exception_deal','installer_excel_report_date','installer_excel_report_deal') and bool(re.fullmatch(r'[\d\s.,₽рРубУБ]+',value)))
        if value in allowed or free_input:
            return handle_deal_ui(token,chat_id,text,_background=True)
        send_message(token,chat_id,'Сборный отчёт ещё не утверждён. Используйте кнопки проверки и «📤 Передать руководителю». Начисления утверждает только руководитель.',installer_review_keyboard(chat_id))
        return True
    if value in ("/start", "/help", "/помощь", "/menu", "❓ Помощь"):
        from installer_onboarding import GUIDE
        send_message(token, chat_id, GUIDE, INSTALLER_USER_KEYBOARD)
        return True
    if value in ("🛠 Мои монтажи","⬅️ Мои монтажи"):
        result=run_installation_workflow({"action":"list_mine","installer_name":"Деревянко"})
        items=result.get("result") or [] if result.get("ok") else []
        if not items:
            send_message(token,chat_id,"Переданных вам объектов в статусе «Монтаж» пока нет.",INSTALLER_USER_KEYBOARD); return True
        choices={f"№{x['deal_id']} · {x['client'][:24]} · {x['essence'][:28]}":x['deal_id'] for x in items}
        rows=[[{"text":label}] for label in choices]; rows.append([{"text":"⬅️ Главное меню"}])
        update_deal_ui_state(chat_id,pending="installation_mine_select",installation_choices=choices)
        send_message(token,chat_id,"Ваши монтажи — выберите объект.",{"keyboard":rows,"resize_keyboard":True}); return True
    if value in ("📜 История монтажей", "⬅️ История монтажей"):
        result=run_installation_workflow({"action":"list_history","installer_name":"Деревянко"})
        items=result.get("result") or [] if result.get("ok") else []
        if not items:
            send_message(token,chat_id,"Исторических монтажей пока нет.",INSTALLER_USER_KEYBOARD); return True
        choices={f"№{x['deal_id']} · {x['client'][:24]} · {x['essence'][:28]}":x['deal_id'] for x in items}
        rows=[[{"text":label}] for label in choices]; rows.append([{"text":"⬅️ Главное меню"}])
        update_deal_ui_state(chat_id,pending="installation_history_select",installation_history_choices=choices)
        send_message(token,chat_id,"История монтажей — выберите объект.",{"keyboard":rows,"resize_keyboard":True}); return True
    if pending=="installation_mine_select" and value in (state.get("installation_choices") or {}):
        did=str(state["installation_choices"][value]); result=run_installation_workflow({"action":"get","deal_id":did})
        if not result.get("ok"): send_message(token,chat_id,f"Не удалось открыть объект: {result.get('error')}",INSTALLER_USER_KEYBOARD); return True
        update_deal_ui_state(chat_id,pending="installation_object",installation_deal_id=did,installation_choices=None)
        send_message(token,chat_id,installation_summary(result["result"]),INSTALLER_INSTALLATION_KEYBOARD); return True
    if pending=="installation_history_select" and value in (state.get("installation_history_choices") or {}):
        did=str(state["installation_history_choices"][value]); result=run_installation_workflow({"action":"get","deal_id":did})
        if not result.get("ok"): send_message(token,chat_id,f"Не удалось открыть историю: {result.get('error')}",INSTALLER_USER_KEYBOARD); return True
        update_deal_ui_state(chat_id,pending="installation_history_object",installation_deal_id=did,installation_history_choices=None)
        history_keyboard={"keyboard":[[{"text":"📋 Монтажная ведомость"}],[{"text":"⬅️ История монтажей"}]],"resize_keyboard":True}
        send_message(token,chat_id,"📜 Исторический объект — новые отчёты по нему отключены.\n\n"+installation_summary(result["result"]),history_keyboard); return True
    if pending in ("installation_object", "installation_history_object") and value=="📋 Монтажная ведомость":
        result=run_installation_workflow({"action":"get","deal_id":state.get("installation_deal_id")})
        item=result.get("result") or {}
        if item.get("workbook_path") and os.path.isfile(item["workbook_path"]):
            send_document(token,chat_id,item["workbook_path"],"Актуальная монтажная ведомость",os.path.basename(item["workbook_path"]))
        else: send_message(token,chat_id,"Актуальная ведомость пока недоступна.",INSTALLER_INSTALLATION_KEYBOARD)
        return True
    if pending=="installation_object" and value=="📦 Материалы по счетам":
        send_message(token,chat_id,'📦 Формирую материалы: PDF для телефона и Excel для компьютера.')
        paths=[]
        try:
            process=subprocess.run([REPORT_VENV_PY,os.path.join(BASE_DIR,'installer_material_delivery.py')],
                input=json.dumps({'chat':str(chat_id),'deal_id':state.get('installation_deal_id'),
                                 'test_chat':str(INSTALLER_NOTIFY_CHAT_ID or '')}),
                capture_output=True,text=True,timeout=90)
            result=json.loads(process.stdout.strip().splitlines()[-1])
            if not result.get('ok'):
                send_message(token,chat_id,result.get('error') or 'Материалы пока недоступны.',INSTALLER_INSTALLATION_KEYBOARD)
                return True
            paths=[result['pdf'],result['xlsx']]
            from installer_material_delivery import authorize
            authorize(os.path.join(MEGAPLAN_DIR,'installations.sqlite3'),os.path.join(BASE_DIR,'installer_accounts.sqlite3'),
                      chat_id,state.get('installation_deal_id'),str(INSTALLER_NOTIFY_CHAT_ID or ''))
            delivered=[]
            for path,caption in zip(paths,('Материалы по счетам — для телефона. Не подтверждает доставку.',
                                           'Материалы по счетам — Excel с подробностями. Без цен.')):
                delivered.append(send_document(token,chat_id,path,caption,os.path.basename(path)))
            note='Файлы отправлены.' if all(delivered) else 'Не все файлы доставлены. Нажмите кнопку ещё раз для повторного получения.'
            if not result.get('confirmed_positions'):
                note+=' Подтверждённых привязок к позициям пока нет.'
            send_message(token,chat_id,note,INSTALLER_INSTALLATION_KEYBOARD)
        except Exception:
            send_message(token,chat_id,'Не удалось получить материалы. Попробуйте позже; данные учёта не изменены.',INSTALLER_INSTALLATION_KEYBOARD)
        finally:
            for path in paths:
                try: os.remove(path)
                except OSError: pass
            if paths:
                try: os.rmdir(os.path.dirname(paths[0]))
                except OSError: pass
        return True
    if pending=="installation_object" and value=="📐 Проектная документация":
        result=run_installation_workflow({"action":"project_files","deal_id":state.get("installation_deal_id")})
        files=result.get("result") or [] if result.get("ok") else []
        if not files: send_message(token,chat_id,"Для этого объекта руководитель подтвердил отсутствие проектной документации либо файлы не найдены.",INSTALLER_INSTALLATION_KEYBOARD); return True
        for item in files:
            send_document(token,chat_id,item["path"],"Проектная документация",item.get("name"))
            try: os.remove(item["path"])
            except OSError: pass
        send_message(token,chat_id,f"Отправлено файлов: {len(files)}.",INSTALLER_INSTALLATION_KEYBOARD); return True
    if pending=="installation_object" and value=="🧰 Новый отчёт":
        result=run_installation_workflow({"action":"create_report","deal_id":state.get("installation_deal_id"),"chat_id":str(chat_id)})
        if not result.get("ok"): send_message(token,chat_id,f"Не удалось открыть отчёт: {result.get('error')}",INSTALLER_INSTALLATION_KEYBOARD); return True
        report=result["result"]; update_deal_ui_state(chat_id,pending="installation_report_collect",installation_report_id=report["id"])
        send_message(token,chat_id,f"Открыт отчёт №{report['report_no']}. Присылайте текст, фото, видео и документы. Максимальный размер одного файла — 20 МБ. Когда закончите, нажмите «Все материалы отправлены».",INSTALLATION_REPORT_COLLECT_KEYBOARD); return True
    if pending=="installation_report_collect" and value=="✅ Все материалы отправлены":
        result=run_installation_workflow({"action":"submit_report","report_id":state.get("installation_report_id")})
        if not result.get("ok"): send_message(token,chat_id,f"Отчёт пока не отправлен: {result.get('error')}",INSTALLATION_REPORT_COLLECT_KEYBOARD); return True
        parsed=result["result"]; lines=[f"• [{x.get('id')}] {x.get('name') or 'не сопоставлено'} — {float(x.get('declared_qty') or 0):g} {x.get('unit') or ''}" for x in parsed.get("items") or []]
        update_deal_ui_state(chat_id,pending=None,installation_report_id=None)
        send_message(token,chat_id,"✅ Отчёт передан руководителю.\n\n"+("\n".join(lines) if lines else "Структурированных строк не найдено; руководитель увидит исходный текст."),INSTALLER_USER_KEYBOARD)
        if MANAGER_CHAT_ID:
            WorkflowStore(WORKFLOW_DB_FILE).notify(MANAGER_CHAT_ID,'installation_report',parsed['report']['id'],{'deal_id':parsed['report']['deal_id']})
            send_message(token,MANAGER_CHAT_ID,f"🧰 Получен монтажный отчёт №{parsed['report']['report_no']} по сделке №{parsed['report']['deal_id']}.\nОткройте «📥 Монтажные отчёты» для проверки. Текущая операция не изменена.")
        return True
    if pending=="installation_report_collect" and value=="❌ Отменить отчёт":
        update_deal_ui_state(chat_id,pending=None,installation_report_id=None)
        send_message(token,chat_id,"Черновик закрыт. Записанные материалы остаются в истории и не приняты к оплате.",INSTALLER_USER_KEYBOARD); return True
    if pending=="installation_report_collect":
        result=run_installation_workflow({"action":"append_report_text","report_id":state.get("installation_report_id"),"text":value})
        send_message(token,chat_id,"📝 Текст добавлен в текущий отчёт." if result.get("ok") else f"Текст не сохранён: {result.get('error')}",INSTALLATION_REPORT_COLLECT_KEYBOARD); return True
    if value == "📊 Мои взаиморасчёты":
        result = run_installer_settlements({"action": "export"})
        if not result.get("ok"):
            send_message(token, chat_id, f"Не удалось сформировать реестр: {result.get('error')}", INSTALLER_USER_KEYBOARD)
        else:
            send_document(token, chat_id, result["path"], "Ваш накопительный реестр взаиморасчётов", os.path.basename(result["path"]))
            send_message(token, chat_id, "Реестр сформирован.", INSTALLER_USER_KEYBOARD)
        return True
    if value == "📚 Утверждённые отчёты":
        reports = load_approved_installer_reports().get("reports") or []
        if not reports:
            send_message(token, chat_id, "Утверждённых отчётов пока нет.", INSTALLER_USER_KEYBOARD)
            return True
        rows = [[{"text": f"📄 Отчёт {item.get('date')}"}] for item in reports[:20]]
        rows.append([{"text": "⬅️ Главное меню"}])
        update_deal_ui_state(chat_id, pending="installer_approved_report_list")
        summary = "\n".join(f"• {item.get('date')} — {money(item.get('amount'))}" for item in reports[:20])
        send_message(token, chat_id, "Утверждённые руководителем отчёты:\n" + summary + "\n\nВыберите отчёт для расшифровки.", {"keyboard": rows, "resize_keyboard": True})
        return True
    if pending == "installer_approved_report_list" and value.startswith("📄 Отчёт "):
        report_date = value.removeprefix("📄 Отчёт ")
        report = next((item for item in load_approved_installer_reports().get("reports") or [] if item.get("date") == report_date), None)
        if report:
            send_message(token, chat_id, approved_report_text(report), INSTALLER_USER_KEYBOARD)
            excel_path = report.get("excel_path")
            if excel_path and os.path.isfile(excel_path):
                send_document(
                    token, chat_id, excel_path,
                    f"Утверждённый разобранный отчёт от {report_date}",
                    os.path.basename(excel_path),
                )
            else:
                send_message(token, chat_id, "Excel этого старого отчёта не найден в архиве.", INSTALLER_USER_KEYBOARD)
        else:
            send_message(token, chat_id, "Отчёт не найден в архиве.", INSTALLER_USER_KEYBOARD)
        update_deal_ui_state(chat_id, pending=None)
        return True
    if value == "⬅️ Главное меню":
        update_deal_ui_state(chat_id, pending=None)
        send_message(token, chat_id, "Меню монтажника.", INSTALLER_USER_KEYBOARD)
        return True
    send_message(token, chat_id, "В режиме монтажника доступны отправка отчёта и просмотр своих взаиморасчётов.", INSTALLER_USER_KEYBOARD)
    return True


def _human_choice_keyboard(labels, extra=None):
    rows=[[{'text':label}] for label in labels]
    if extra:rows.append([{'text':extra}])
    rows.append([{'text':'❌ Отмена'}])
    return {'keyboard':rows,'resize_keyboard':True,'one_time_keyboard':True}


def payer_choices(payers):
    """Button label -> payer (QA idea И-5): name, INN and the current mark tell payers apart."""
    choices = {}
    for item in payers:
        label = item.get('name') or 'Без названия'
        if item.get('inn'):
            label += f" · ИНН {item['inn']}"
        if item.get('selected'):
            label += ' · ✓ текущий'
        if label in choices:
            label += f" · ID {item['id']}"
        choices[label] = item
    return choices


def _start_human_payer(token,chat_id,deal_id,target=None):
    result=run_payer_card_apply({'action':'list_deal_payers','deal_id':str(deal_id)})
    if not result.get('ok'):
        send_message(token,chat_id,'Не удалось прочитать плательщиков сделки: '+str(result.get('error')))
        return True
    payers=result.get('payers') or []
    choices=payer_choices(payers)
    if target:
        needle=' '.join(str(target).casefold().replace('ё','е').split())
        digits=re.sub(r'\D','',str(target))
        matches=([item for item in payers if digits and str(item.get('inn') or '')==digits] if len(digits)>=10 else
                 [item for item in payers if needle in ' '.join(str(item.get('name') or '').casefold().replace('ё','е').split())])
        if len(matches)==1 and matches[0].get('selected'):
            update_deal_ui_state(chat_id,pending=None,human_intent=None,human_choices=None)
            send_message(token,chat_id,f"В сделке №{deal_id} плательщик уже «{matches[0]['name']}». Менять нечего, ничего не записано.",DEAL_ACTIONS_KEYBOARD)
            return True
        if len(matches)==1:
            item=matches[0]
            update_deal_ui_state(chat_id,pending='human_payer_confirm',human_intent={'name':human_intents.CHANGE_PAYER,'deal_id':str(deal_id),'payer':item})
            current=next((x for x in payers if x.get('selected')),None)
            send_message(token,chat_id,
                f"Сделка №{deal_id}.\nТекущий плательщик: {(current or {}).get('name') or 'не выбран'}.\nНовый плательщик: {item['name']}" + (f", ИНН {item['inn']}" if item.get('inn') else '') + f" (ID {item['id']}).\n\nДанные ещё не записаны.",HUMAN_PAYER_CONFIRM_KEYBOARD)
            return True
    update_deal_ui_state(chat_id,pending='human_payer_select',human_intent={'name':human_intents.CHANGE_PAYER,'deal_id':str(deal_id)},human_choices=choices)
    if choices:
        current=next((x for x in payers if x.get('selected')),None)
        not_found=f"Плательщик «{target}» у клиента сделки не найден однозначно.\n" if target else ''
        send_message(token,chat_id,f"{not_found}Сделка №{deal_id}, клиент {result.get('client_name') or 'не указан'}.\nТекущий плательщик: {(current or {}).get('name') or 'не выбран'}.\nВыберите нового плательщика или пришлите новую карточку.",_human_choice_keyboard(choices,'📎 Новая карточка плательщика'))
    else:
        update_deal_ui_state(chat_id,pending='payer_card_file',payer_target_deal_id=str(deal_id),human_intent=None,human_choices=None)
        send_message(token,chat_id,f"У клиента сделки №{deal_id} нет доступных карточек. Пришлите карточку нового плательщика.")
    return True


def _start_human_executor(token,chat_id,deal_id,query=None,kind=human_intents.ASSIGN_EXECUTOR):
    if not query:
        update_deal_ui_state(chat_id,pending='human_executor_query',human_intent={'name':kind,'deal_id':str(deal_id)})
        send_message(token,chat_id,f"Кого назначить {'монтажником' if kind==human_intents.CHANGE_INSTALLER else 'исполнителем'} сделки №{deal_id}? Укажите имя или фамилию.")
        return True
    result=run_deal_browser({'action':'search_employees','query':query})
    employees=result.get('employees') or [] if result.get('ok') else []
    if result.get('ok') and not employees:
        # «назначь Смирнова», «поставь Деревянко Сергея»: retry with word stems.
        for stem in human_intents.name_stems(query):
            retry=run_deal_browser({'action':'search_employees','query':stem})
            employees=retry.get('employees') or [] if retry.get('ok') else []
            if employees:break
    if not result.get('ok'):
        send_message(token,chat_id,'Поиск сотрудника не выполнен: '+str(result.get('error')));return True
    if not employees:
        update_deal_ui_state(chat_id,pending='human_executor_query',human_intent={'name':kind,'deal_id':str(deal_id)})
        send_message(token,chat_id,f"Сотрудник «{query}» не найден. Уточните имя или фамилию.");return True
    choices={f"Сотрудник ID {item['id']} — {item['name']}":item for item in employees}
    update_deal_ui_state(chat_id,pending='human_executor_select',human_intent={'name':kind,'deal_id':str(deal_id)},human_choices=choices)
    send_message(token,chat_id,'Выберите сотрудника. Ничего ещё не записано.',_human_choice_keyboard(choices))
    return True


def _start_human_invoice(token,chat_id,deal_id,kind):
    """«Выстави счёт…» opens the invoice menu of that deal; «пришли счёт…» sends the latest one."""
    if kind==human_intents.GET_INVOICE:
        update_deal_ui_state(chat_id,current_deal_id=str(deal_id))
        send_latest_megaplan_invoice(token,chat_id,deal_id)
        return True
    select_deal(token,chat_id,deal_id)
    if str(current_deal_ui_state(chat_id).get('current_deal_id'))!=str(deal_id):
        return True
    update_deal_ui_state(chat_id,pending='invoice_menu',invoice_downloads=None)
    send_message(token,chat_id,f"Какой счёт выставить по сделке №{deal_id}?\n«📋 Общий счёт по спецификации» — на все позиции сделки; 6.4.1–6.4.3 — счёт на этап оплаты по договору. До подтверждения ничего не записывается.",INVOICE_MENU_KEYBOARD)
    return True


def _status_stem(value):
    words = re.findall(r"[а-яёa-z0-9]+", str(value or "").casefold().replace("ё", "е"))
    return " ".join(word[:5] for word in words)


def _start_human_status(token, chat_id, deal_id, target=None):
    """«Переведи сделку N в закупку»: the same confirmation screen as the status buttons."""
    result = run_deal_browser({"action": "get_cached", "deal_id": str(deal_id)}, timeout=8)
    if not result.get("ok"):
        send_message(token, chat_id, f"Не удалось открыть сделку №{deal_id}: {result.get('error')}", DEALS_KEYBOARD)
        return True
    deal = result["deal"]
    transitions = {f"➡️ {t['name']}": t for t in deal.get("transitions", []) if t.get("enabled")}
    update_deal_ui_state(chat_id, current_deal_id=str(deal_id), pending=None, transitions=transitions,
                         pending_transition=None)
    if not transitions:
        send_message(token, chat_id, f"Для сделки №{deal_id} сейчас нет доступных переходов. Текущий статус: {deal.get('status')}.",
                     DEAL_ACTIONS_KEYBOARD)
        return True
    wanted = _status_stem(target)
    matches = [label for label, t in transitions.items() if wanted and (
        _status_stem(t.get("name")) == wanted or _status_stem(t.get("name")).startswith(wanted))]
    if len(matches) == 1:
        return handle_deal_ui(token, chat_id, matches[0], _background=True)
    if wanted and _status_stem(deal.get("status")) == wanted:
        send_message(token, chat_id, f"Сделка №{deal_id} уже в статусе «{deal.get('status')}».", DEAL_ACTIONS_KEYBOARD)
        return True
    note = f"Статус «{target}» для сделки №{deal_id} недоступен. " if target else ""
    keyboard = [[{"text": label}] for label in transitions] + [[{"text": "❌ Отмена"}]]
    send_message(token, chat_id, f"{note}Сделка №{deal_id}, текущий статус: {deal.get('status')}. Куда перевести сделку?",
                 {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True})
    return True


def _human_payment_summary(deal_id):
    deal_result=run_deal_browser({'action':'get','deal_id':str(deal_id)})
    if not deal_result.get('ok'):return {'ok':False,'error':'не удалось прочитать сделку: '+str(deal_result.get('error'))}
    invoices=run_contract_invoice({'action':'list','deal_id':str(deal_id)})
    bank=run_bank_statement({'action':'list','limit':10000})
    if not invoices.get('ok') or not bank.get('ok'):
        return {'ok':False,'error':'не удалось прочитать счета или банковский реестр'}
    invoice_rows=[item for item in (invoices.get('invoices') or []) if item.get('status') in ('drawn','paid','partially_paid')]
    invoice_total=sum((Decimal(str(item.get('sum') or 0)) for item in invoice_rows),Decimal('0'))
    operations=[item for item in (bank.get('transactions') or []) if str(item.get('deal_id') or '')==str(deal_id) and item.get('status')=='assigned' and item.get('direction')=='income']
    paid=sum((Decimal(str(item.get('amount') or 0)) for item in operations),Decimal('0'))
    return {'ok':True,'deal':deal_result['deal'],'invoice_total':invoice_total,'paid':paid,
            'remainder':invoice_total-paid,'invoices':invoice_rows,'operations':operations}


def has_explicit_deal_economics(text):
    """Return true when a typed spec carries user-owned sale and cost data."""
    value = str(text or '')
    amounts = re.findall(r'(?<!\w)\d[\d\s]*(?:[.,]\d+)?\s*(?:₽|руб(?:\.|л(?:ей|я)?)?)', value, re.I)
    return len(amounts) >= 2 and bool(re.search(r'(?i)\b(?:закуп\w*|себестоим\w*)\b', value))


# Top-level menu entries: a person pressing one has left whatever they were doing.
TOP_LEVEL_NAVIGATION = {"🤝 Сделки", "🤝 Работа со сделками", "/deals", "🏦 Деньги", "🏦 Банк и платежи",
                        "🧰 Монтаж", "☰ Ещё", "⬅️ Главное меню", "/menu", "/start", "📊 Пульт сделок",
                        "/dashboard", "🧪 Ошибки тестировщика"}


def handle_human_workflow(token,chat_id,text):
    value=str(text or '').strip();state=current_deal_ui_state(chat_id);pending=state.get('pending') or ''
    if value in TOP_LEVEL_NAVIGATION:
        if pending.startswith('human_'):
            update_deal_ui_state(chat_id,pending=None,human_intent=None,human_choices=None)
        return False
    if pending.startswith('human_') and value=='❌ Отмена':
        update_deal_ui_state(chat_id,pending=None,human_intent=None,human_choices=None)
        send_message(token,chat_id,'Действие отменено.',DEALS_KEYBOARD);return True
    if pending=='human_payer_deal':
        match=re.search(r'\d{2,}',value)
        if not match:send_message(token,chat_id,'Укажите номер сделки.');return True
        return _start_human_payer(token,chat_id,match.group())
    if pending=='human_payer_select':
        if value=='📎 Новая карточка плательщика':
            deal_id=(state.get('human_intent') or {}).get('deal_id');update_deal_ui_state(chat_id,pending='payer_card_file',payer_target_deal_id=deal_id,human_intent=None,human_choices=None)
            send_message(token,chat_id,f"Пришлите PDF, Word или Excel-карточку нового плательщика для сделки №{deal_id}.");return True
        item=(state.get('human_choices') or {}).get(value)
        if not item:send_message(token,chat_id,'Выберите плательщика из списка.');return True
        deal_id=(state.get('human_intent') or {}).get('deal_id');update_deal_ui_state(chat_id,pending='human_payer_confirm',human_intent={'name':human_intents.CHANGE_PAYER,'deal_id':deal_id,'payer':item},human_choices=None)
        send_message(token,chat_id,f"Сделка №{deal_id}. Новый плательщик: {item['name']} (ID {item['id']}).\nДанные ещё не записаны.",HUMAN_PAYER_CONFIRM_KEYBOARD);return True
    if pending in ('human_payer_confirm','human_executor_confirm') and not value.startswith('✅') and human_intents.classify(value):
        # A new request in words replaces an unconfirmed preview (also one left
        # behind by a restart); nothing was written for the old one.
        update_deal_ui_state(chat_id,pending=None,human_intent=None,human_choices=None)
        state=current_deal_ui_state(chat_id);pending=''
    if pending=='human_payer_confirm':
        if value!='✅ Сменить плательщика':send_message(token,chat_id,'Нажмите кнопку под предпросмотром или отмените.');return True
        intent=state.get('human_intent') or {};payer=intent.get('payer') or {};result=run_payer_card_apply({'deal_id':intent.get('deal_id'),'payer_id':payer.get('id')})
        if not result.get('ok'):send_message(token,chat_id,'Плательщик не изменён: '+str(result.get('error')),HUMAN_PAYER_CONFIRM_KEYBOARD);return True
        check=run_payer_card_apply({'action':'list_deal_payers','deal_id':intent.get('deal_id')});selected=next((x for x in check.get('payers') or [] if x.get('selected')),None)
        if str((selected or {}).get('id'))!=str(payer.get('id')):send_message(token,chat_id,'Запись не подтверждена обратным чтением. Не повторяйте без сверки.');return True
        update_deal_ui_state(chat_id,pending=None,human_intent=None);send_message(token,chat_id,f"✅ В сделке №{intent.get('deal_id')} плательщик изменён на «{selected.get('name')}». Источник: обратное чтение Мегаплана.\n\nДальше: «🧾 Выставить счёт» — счёт будет выставлен уже на нового плательщика.",DEAL_ACTIONS_KEYBOARD);return True
    if pending=='human_executor_deal':
        match=re.search(r'\d{2,}',value)
        if not match:send_message(token,chat_id,'Укажите номер сделки.');return True
        saved=state.get('human_intent') or {};return _start_human_executor(token,chat_id,match.group(),saved.get('target'),saved.get('name') or human_intents.ASSIGN_EXECUTOR)
    if pending=='human_executor_query':
        saved=state.get('human_intent') or {};return _start_human_executor(token,chat_id,saved.get('deal_id'),value,saved.get('name'))
    if pending=='human_executor_select':
        employee=(state.get('human_choices') or {}).get(value)
        if not employee:send_message(token,chat_id,'Выберите сотрудника из списка.');return True
        saved=state.get('human_intent') or {};deal=run_deal_browser({'action':'get','deal_id':saved.get('deal_id')})
        if not deal.get('ok'):send_message(token,chat_id,'Не удалось свежо прочитать сделку: '+str(deal.get('error')));return True
        saved={**saved,'employee':employee,'before':deal['deal']};update_deal_ui_state(chat_id,pending='human_executor_confirm',human_intent=saved,human_choices=None)
        send_message(token,chat_id,f"Сделка №{saved.get('deal_id')}.\nТекущий исполнитель: {', '.join(deal['deal'].get('executors') or []) or 'не назначен'}.\nНовый: {employee['name']} (ID {employee['id']}).\n\nДанные ещё не записаны.",HUMAN_EXECUTOR_CONFIRM_KEYBOARD);return True
    if pending=='human_executor_confirm':
        if value!='✅ Назначить исполнителя':send_message(token,chat_id,'Нажмите кнопку под предпросмотром или отмените.');return True
        saved=state.get('human_intent') or {};employee=saved.get('employee') or {};result=run_deal_browser({'action':'set_executor','deal_id':saved.get('deal_id'),'employee_id':employee.get('id')})
        if not result.get('ok'):send_message(token,chat_id,'Исполнитель не изменён: '+str(result.get('error')),HUMAN_EXECUTOR_CONFIRM_KEYBOARD);return True
        sync=run_installation_workflow({'action':'sync_executor','deal_id':saved.get('deal_id'),'actor':str(chat_id)})
        if not sync.get('ok'):
            update_deal_ui_state(chat_id,pending=None,human_intent=None)
            send_message(token,chat_id,f"✅ В сделке №{saved.get('deal_id')} исполнитель изменён на {employee.get('name')} и подтверждён чтением Мегаплана. Синхронизация монтажного контура НЕ ВЫПОЛНЕНА: {sync.get('error')}. Повторно менять исполнителя не нужно.",DEAL_ACTIONS_KEYBOARD);return True
        update_deal_ui_state(chat_id,pending=None,human_intent=None);send_message(token,chat_id,f"✅ В сделке №{saved.get('deal_id')} исполнитель: {employee.get('name')}. Мегаплан перечитан; монтажный контур: {'обновлён' if sync.get('installation_exists') else 'ещё не создан'}.",DEAL_ACTIONS_KEYBOARD);return True
    if pending=='human_payment_deal':
        match=re.search(r'\d{2,}',value)
        if not match:send_message(token,chat_id,'Укажите номер сделки.');return True
        intent=human_intents.Intent(human_intents.CHECK_PAYMENT,deal_id=match.group())
    elif pending=='human_status_deal':
        match=re.search(r'\d{2,}',value)
        if not match:send_message(token,chat_id,'Укажите номер сделки.');return True
        saved=state.get('human_intent') or {};update_deal_ui_state(chat_id,pending=None,human_intent=None)
        return _start_human_status(token,chat_id,match.group(),saved.get('target'))
    elif pending=='human_invoice_deal':
        match=re.search(r'\d{2,}',value)
        if not match:send_message(token,chat_id,'Укажите номер сделки.');return True
        saved=state.get('human_intent') or {};update_deal_ui_state(chat_id,pending=None,human_intent=None)
        return _start_human_invoice(token,chat_id,match.group(),saved.get('name') or human_intents.ISSUE_INVOICE)
    else:intent=human_intents.classify(value)
    if not intent:return False
    if intent.name!=human_intents.CREATE_DEAL and not intent.deal_id and state.get('current_deal_id') and not re.search(r'(?i)друг\w*\s+сделк|не\s+в\s+этой',value):
        # The person is inside an open deal card: «смени плательщика на …» refers to it.
        # Every preview below names the deal, so a stale selection is visible before any write.
        intent=human_intents.Intent(intent.name,str(state['current_deal_id']),intent.target,intent.fields,
                                    tuple(x for x in intent.missing if x!='deal'),intent.confidence)
    if intent.name==human_intents.MOVE_STATUS:
        if not intent.deal_id:
            update_deal_ui_state(chat_id,pending='human_status_deal',human_intent={'name':intent.name,'target':intent.target})
            send_message(token,chat_id,'Какую сделку перевести? Укажите номер.');return True
        return _start_human_status(token,chat_id,intent.deal_id,intent.target)
    if intent.name in (human_intents.ISSUE_INVOICE,human_intents.GET_INVOICE):
        if not intent.deal_id:
            update_deal_ui_state(chat_id,pending='human_invoice_deal',human_intent={'name':intent.name})
            send_message(token,chat_id,'По какой сделке? Укажите номер.');return True
        return _start_human_invoice(token,chat_id,intent.deal_id,intent.name)
    if intent.name==human_intents.CREATE_DEAL:
        active = current_deal_ui_state(chat_id)
        if active.get('deal_creation_active') and active.get('deal_create_spec'):
            return False
        update_deal_ui_state(chat_id,**creation_attachment.initial_state(value));invoice_tasks.pause(chat_id)
        if creation_attachment.awaiting_file(value):send_message(token,chat_id,'Задание на новую сделку сохранено. Пришлите счёт или спецификацию; файл будет связан именно с этим поручением.');return True
        return False
    if intent.name==human_intents.CHANGE_PAYER:
        if not intent.deal_id:update_deal_ui_state(chat_id,pending='human_payer_deal',human_intent={'name':intent.name,'target':intent.target});send_message(token,chat_id,'В какой сделке меняем плательщика? Укажите номер.');return True
        return _start_human_payer(token,chat_id,intent.deal_id,intent.target)
    if intent.name in (human_intents.CHANGE_INSTALLER,human_intents.ASSIGN_EXECUTOR):
        if not intent.deal_id:update_deal_ui_state(chat_id,pending='human_executor_deal',human_intent={'name':intent.name,'target':intent.target});send_message(token,chat_id,'Для какой сделки меняем исполнителя? Укажите номер.');return True
        return _start_human_executor(token,chat_id,intent.deal_id,intent.target,intent.name)
    if intent.name==human_intents.CHECK_PAYMENT:
        if not intent.deal_id:update_deal_ui_state(chat_id,pending='human_payment_deal',human_intent={'name':intent.name});send_message(token,chat_id,'По какой сделке проверить оплату? Укажите номер.');return True
        result=_human_payment_summary(intent.deal_id)
        if not result.get('ok'):send_message(token,chat_id,'Оплата НЕ ПРОВЕРЕНА: '+str(result.get('error')));return True
        deal=result['deal'];send_message(token,chat_id,(f"Сделка №{intent.deal_id} — {deal.get('client')}.\nСчетов в Мегаплане: {len(result['invoices'])}, на {bank_money(result['invoice_total'])} ₽.\nПодтверждённых входящих операций, привязанных к сделке: {len(result['operations'])}, на {bank_money(result['paid'])} ₽.\nОстаток по выставленным счетам: {bank_money(result['remainder'])} ₽.\n\nИсточники: свежие счета Мегаплана и подтверждённые привязки банковского реестра. Почтовые уведомления без банковской операции не считались."),DEAL_ACTIONS_KEYBOARD);return True
    return False


def main():
    global MANAGER_CHAT_ID, INSTALLER_NOTIFY_CHAT_ID, RUNTIME_ACTIVE, UI_CONTEXT
    RUNTIME_ACTIVE = True
    runtime_guards.install(globals())
    interrupted_operations = WorkflowStore(WORKFLOW_DB_FILE).recover()
    env = load_env()
    token = env["TELEGRAM_BOT_TOKEN"]
    authorized_chat_id = str(env["TELEGRAM_CHAT_ID"])
    MANAGER_CHAT_ID = authorized_chat_id
    INSTALLER_NOTIFY_CHAT_ID = str(env.get("INSTALLER_TELEGRAM_CHAT_ID") or "") or None
    installer_usernames = {
        item.strip().lstrip("@").casefold()
        for item in env.get("INSTALLER_TELEGRAM_USERNAMES", "").split(",")
        if item.strip()
    }
    edo_username = str(env.get("EDO_NOTIFY_TELEGRAM_USERNAME") or "").strip().lstrip("@").casefold()
    edo_chat_id = str(env.get("EDO_NOTIFY_TELEGRAM_CHAT_ID") or "").strip()
    if not edo_chat_id:
        try:
            edo_chat_id = open(EDO_RECIPIENT_CHAT_FILE, encoding="utf-8").read().strip()
        except OSError:
            edo_chat_id = ""
    session_id = get_or_create_session_id()
    offset = get_offset()
    configure_bot_commands(token)

    print(f"{LOG_PREFIX} started, session_id={session_id}, offset={offset}")
    announce_reload(token, authorized_chat_id)
    report_interrupted_operations(token, interrupted_operations)

    for job in recover_interrupted_document_jobs():
        send_message(
            token, job["chat_id"],
            f"⚠️ Обработка файла «{job.get('original_name') or 'счёт'}» для сделки №{job.get('deal_id')} "
            "была прервана перезапуском. Файл сохранён — откройте закупку и нажмите «🔄 Повторить последний счёт».",
            PROCUREMENT_KEYBOARD,
        )

    owner_state = current_deal_ui_state(authorized_chat_id)
    if owner_state.get("pending") == "developer_task_running" and owner_state.get("developer_task_text"):
        send_message(token, authorized_chat_id, "♻️ После перезапуска продолжаю незавершённую задачу разработчику.", MAIN_KEYBOARD)
        run_background_job(
            lambda: process_developer_task(token, authorized_chat_id, owner_state["developer_task_text"]),
            token, authorized_chat_id,
        )

    def process_business_message(msg, chat_id, is_owner, is_installer):
        from company_cards import handle_request as handle_company_card_request
        if msg.get("text") and handle_company_card_request(
                msg["text"], is_owner,
                lambda path, caption: send_document(token, chat_id, str(path), caption),
                lambda text: send_message(token, chat_id, text)):
            return
        order = current_deal_ui_state(chat_id).get('document_order') or {}
        order_text = str(msg.get('text') or '')
        if is_owner and order and not order.get('complete') and (
                order_text.strip().casefold() == 'продолжить комплект' or
                (current_deal_ui_state(chat_id).get('pending') == 'document_order_details' and order_continuation.parse(order_text))):
            details = order_continuation.parse(order_text)
            run_background_job(lambda: continue_document_order(token, chat_id, order, details), token, chat_id,
                               operation='договор и счёт по сделке:'+str(order['deal_id']))
            return
        if is_owner and msg.get('text') and handle_human_workflow(token, chat_id, msg.get('text')):
            return
        raw_creation = msg.get("text") or msg.get("caption") or ""
        active_creation = current_deal_ui_state(chat_id)
        if (is_owner and active_creation.get("deal_creation_active")
                and active_creation.get("pending") == "deal_create_items"
                and has_explicit_deal_economics(raw_creation)):
            update_deal_ui_state(chat_id, deal_creation_text_spec=raw_creation)
        if is_owner and creation_attachment.explicit(raw_creation):
            update_deal_ui_state(chat_id, **creation_attachment.initial_state(raw_creation))
            invoice_tasks.pause(chat_id)
            if "document" not in msg and creation_attachment.awaiting_file(raw_creation):
                send_message(token, chat_id, "Задание сохранено: " + raw_creation + "\n\nПришлите счёт или спецификацию. Свяжу файл с этим заданием.")
                return
        document_job = None
        supplier_invoice_deal_id = None
        if "video" in msg:
            video_state=current_deal_ui_state(chat_id)
            if video_state.get("pending")!="installation_report_collect":
                send_message(token,chat_id,"Сначала откройте объект в «Моих монтажах» и начните новый отчёт.",home_keyboard(chat_id)); return
            local_path,err=download_telegram_media(token,msg["video"],"video.mp4")
            if err: send_message(token,chat_id,err,INSTALLATION_REPORT_COLLECT_KEYBOARD); return
            video=msg["video"]; added=run_installation_workflow({"action":"add_media","report_id":video_state.get("installation_report_id"),
                "path":local_path,"file_id":video.get("file_id",""),"unique_id":video.get("file_unique_id",""),
                "name":video.get("file_name") or os.path.basename(local_path),"mime":video.get("mime_type") or "video/mp4"})
            caption=(msg.get("caption") or "").strip()
            if caption: run_installation_workflow({"action":"append_report_text","report_id":video_state.get("installation_report_id"),"text":caption})
            send_message(token,chat_id,"🎥 Видео добавлено в текущий отчёт." if added.get("ok") else f"Видео не добавлено: {added.get('error')}",INSTALLATION_REPORT_COLLECT_KEYBOARD)
            return
        if "photo" in msg:
            local_path, err = download_telegram_photo(token, msg["photo"])
            if err:
                send_message(token, chat_id, err)
                return
            caption = (msg.get("caption") or "").strip()
            photo_state=current_deal_ui_state(chat_id)
            if photo_state.get("pending")=="installation_report_collect":
                largest=max(msg["photo"],key=lambda p:p.get("width",0)*p.get("height",0))
                added=run_installation_workflow({"action":"add_media","report_id":photo_state.get("installation_report_id"),
                    "path":local_path,"file_id":largest.get("file_id","")+"","unique_id":largest.get("file_unique_id",""),
                    "name":os.path.basename(local_path),"mime":"image/jpeg"})
                if caption: run_installation_workflow({"action":"append_report_text","report_id":photo_state.get("installation_report_id"),"text":caption})
                send_message(token,chat_id,"📷 Фото добавлено в текущий отчёт." if added.get("ok") else f"Фото не добавлено: {added.get('error')}",INSTALLATION_REPORT_COLLECT_KEYBOARD)
                return
            if is_installer and not is_owner:
                send_message(token, chat_id, "Сначала откройте объект в «Моих монтажах» и нажмите «Новый отчёт».", INSTALLER_USER_KEYBOARD)
                return
            text = (
                f"{caption}\n\n" if caption else ""
            ) + f"[ПРИСЛАН ФАЙЛ: {local_path}]"
            print(f"{LOG_PREFIX} received photo: {local_path}")
            send_message(token, chat_id, "📎 Фото получено, начинаю разбирать...")
        elif "document" in msg:
            local_path, err = download_telegram_document(token, msg["document"])
            if err:
                send_message(token, chat_id, err)
                return
            caption = (msg.get("caption") or "").strip()
            text = (
                f"{caption}\n\n" if caption else ""
            ) + f"[ПРИСЛАН ФАЙЛ: {local_path}]"
            print(f"{LOG_PREFIX} received document: {local_path}")
            report_state = current_deal_ui_state(chat_id)
            report_pending = report_state.get("pending")
            supplier_invoice_deal_id = (
                report_state.get("supplier_invoice_deal_id")
                if report_pending in ("invoice_file", "supplier_invoice_confirm")
                else None
            )
            original_name = msg["document"].get("file_name") or ""
            original_ext = os.path.splitext(original_name)[1].casefold()
            source_document_path = local_path[:-3] if local_path.endswith(".md") else local_path
            if (is_owner and original_ext == '.xlsx' and is_explicit_new_deal_request(caption)
                    and prepare_economics_deal_request(token, chat_id, caption, source_document_path)):
                return
            if supplier_invoice_deal_id:
                document_job = create_document_job(
                    chat_id, supplier_invoice_deal_id, source_document_path, original_name,
                )
                if document_job.get("deduplicated"):
                    # Telegram occasionally redelivers the same update.  The
                    # original worker owns this document; starting another one
                    # would race it and produce two competing previews.
                    send_message(
                        token, chat_id,
                        f"⏳ «{document_job.get('original_name') or 'Счёт'}» уже разбирается "
                        f"для сделки №{supplier_invoice_deal_id} "
                        f"({document_job.get('stage') or 'обработка'}). Повторно не запускаю.",
                        PROCUREMENT_KEYBOARD,
                    )
                    return
                update_deal_ui_state(chat_id, active_document_job_id=document_job["id"])
            if report_pending == "installation_report_collect":
                result=run_installation_workflow({"action":"add_media","report_id":report_state.get("installation_report_id"),
                    "path":source_document_path,"file_id":msg["document"].get("file_id",""),
                    "unique_id":msg["document"].get("file_unique_id",""),"name":original_name,
                    "mime":msg["document"].get("mime_type","")})
                if result.get("ok"):
                    caption=(msg.get("caption") or "").strip()
                    if caption: run_installation_workflow({"action":"append_report_text","report_id":report_state.get("installation_report_id"),"text":caption})
                    send_message(token,chat_id,f"📎 Файл добавлен в отчёт ({bank_money((result['result'].get('size') or 0)/1024/1024)} МБ).",INSTALLATION_REPORT_COLLECT_KEYBOARD)
                else: send_message(token,chat_id,f"Файл не добавлен: {result.get('error')}",INSTALLATION_REPORT_COLLECT_KEYBOARD)
                return
            if report_pending == "installation_project_upload":
                if os.path.getsize(source_document_path)>20*1024*1024:
                    send_message(token,chat_id,"Файл проекта превышает лимит 20 МБ. Пришлите файл меньшего размера."); return
                project_deal_id=str(report_state.get("installation_deal_id") or report_state.get("current_deal_id") or "")
                result=run_installation_workflow({"action":"attach_project","deal_id":project_deal_id,
                    "local_paths":[source_document_path],"actor":str(chat_id)})
                if not result.get("ok"):
                    send_message(token,chat_id,"Проект не привязан: "+str(result.get("error")),DEAL_ACTIONS_KEYBOARD); return
                project=result["result"]; back=report_state.get("installation_project_return") or "deal"
                update_deal_ui_state(chat_id,pending="installation_draft_review" if back=="draft" else None,
                                     installation_project_choices=None,installation_project_selected=None,installation_project_return=None)
                send_message(token,chat_id,f"✅ Файл сохранён как проект версии №{project['version']}.",INSTALLATION_DRAFT_KEYBOARD if back=="draft" else DEAL_ACTIONS_KEYBOARD)
                if project.get("installation_status") in ("transferred","in_progress","review") and INSTALLER_NOTIFY_CHAT_ID:
                    notify_installers(token,f"📐 По сделке №{project_deal_id} опубликована новая версия проекта №{project['version']}.")
                return
            # An XLSX sent while a draft is open is unambiguously the corrected
            # worksheet. Requiring a preliminary button click made a perfectly
            # valid file fall through to the legacy AI/payment interpreter.
            if (report_pending in ("installation_workbook_file", "installation_draft_review")
                    and original_ext == ".xlsx"
                    and report_state.get("installation_deal_id")):
                if original_ext != ".xlsx":
                    send_message(token, chat_id, "Нужен исправленный файл монтажной ведомости в формате .xlsx.", INSTALLATION_DRAFT_KEYBOARD)
                    return
                result = run_installation_workflow({"action":"import_workbook",
                    "deal_id":str(report_state.get("installation_deal_id") or ""),
                    "path":source_document_path,"actor":str(chat_id)})
                if not result.get("ok"):
                    send_message(token,chat_id,f"Файл не применён: {result.get('error')}",INSTALLATION_DRAFT_KEYBOARD)
                    return
                changes=result["result"].get("changes") or []
                update_deal_ui_state(chat_id,pending="installation_draft_review")
                send_message(token,chat_id,f"✅ Исправленная ведомость принята. Изменений: {len(changes)}. Проверьте итоговый файл перед утверждением.",INSTALLATION_DRAFT_KEYBOARD)
                send_document(token,chat_id,result["result"]["workbook"],"Актуальный черновик монтажной ведомости",f"Монтажная ведомость - сделка {report_state.get('installation_deal_id')}.xlsx")
                return
            if report_pending == "supplier_closing_upload":
                if original_ext not in (".pdf", ".doc", ".docx", ".xls", ".xlsx"):
                    send_message(token, chat_id, "Пришлите УПД или акт в PDF, Word либо Excel.")
                    return
                closing_invoice = report_state.get("supplier_closing_invoice") or {}
                closing_deal_id = str(report_state.get("current_deal_id") or "")
                if not closing_deal_id or not closing_invoice.get("id"):
                    update_deal_ui_state(chat_id, pending="procurement_menu", supplier_closing_invoice=None,
                                         supplier_closing_choices=None)
                    send_message(token, chat_id, "Не сохранилась связь со счётом. Начните загрузку УПД/акта заново.", PROCUREMENT_KEYBOARD)
                    return
                document_type = "Акт" if "акт" in original_name.casefold() else "УПД"
                uploaded = run_deal_browser({
                    "action": "upload_supplier_closing", "deal_id": closing_deal_id,
                    "path": source_document_path, "invoice_number": closing_invoice.get("number"),
                    "document_type": document_type,
                })
                if not uploaded.get("ok"):
                    send_message(token, chat_id, "Документ не прикреплён: " + str(uploaded.get("error") or "ошибка Мегаплана"))
                    return
                digest = hashlib.sha256()
                with open(source_document_path, "rb") as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(block)
                registered = run_procurement_workflow({
                    "action": "record_closing_document", "deal_id": closing_deal_id,
                    "invoice_id": closing_invoice["id"], "filename": original_name,
                    "sha256": digest.hexdigest(), "document_type": document_type,
                })
                archive = run_financial_archive({
                    "deal_id": closing_deal_id, "path": source_document_path,
                    "category": "supplier_closing", "document_number": closing_invoice.get("number") or "",
                    "display_name": f"{document_type} по счёту поставщика №{closing_invoice.get('number') or 'б н'}",
                })
                update_deal_ui_state(chat_id, pending="procurement_menu", supplier_closing_invoice=None,
                                     supplier_closing_choices=None)
                publish_procurement_register(token, chat_id, closing_deal_id)
                archive_note = " Копия сохранена в OneDrive." if archive.get("ok") else " ⚠️ Копия в OneDrive пока не сохранена."
                duplicate = " (повторный файл)" if (registered.get("document") or {}).get("duplicate") else ""
                send_message(token, chat_id,
                             f"✅ {document_type} по счёту №{closing_invoice.get('number')} прикреплён к сделке{duplicate}." + archive_note,
                             PROCUREMENT_KEYBOARD)
                return
            if report_state.get("deal_creation_active") and original_ext == ".xlsx":
                original_path = local_path[:-3] if local_path.endswith(".md") else local_path
                economics = parse_deal_economics_xlsx(original_path)
                if economics.get("ok"):
                    update_deal_ui_state(
                        chat_id,
                        deal_creation_items=economics["items"],
                        deal_creation_economics_path=original_path,
                    )
                    print(
                        f"{LOG_PREFIX} fixed economics rows saved: "
                        f"{len(economics['items'])}, total={economics.get('total')}"
                    )
                else:
                    print(f"{LOG_PREFIX} uploaded xlsx is not a deal economics table: {economics.get('error')}", file=sys.stderr)
            if report_pending == "bank_statement_file":
                if os.path.splitext(original_name)[1].casefold() not in (".xlsx", ".txt"):
                    send_message(token, chat_id, "Для банковской выписки нужен Excel (.xlsx) или файл обмена 1С (.txt).", BANK_CANCEL_KEYBOARD)
                    return
                original_path = local_path[:-3] if local_path.endswith(".md") else local_path
                send_message(token, chat_id, "🏦 Выписка получена. Проверяю операции и контрольные суммы...")
                result = run_bank_statement({"action": "import", "path": original_path})
                if not result.get("ok"):
                    send_message(token, chat_id, f"Не удалось импортировать выписку: {result.get('error')}", BANK_CANCEL_KEYBOARD)
                    return
                supplier_payments = run_procurement_workflow({"action": "reconcile_bank"})
                paid_count = len(supplier_payments.get("matched") or []) if supplier_payments.get("ok") else 0
                review_count = len(supplier_payments.get("review") or []) if supplier_payments.get("ok") else 0
                if supplier_payments.get("ok"):
                    for paid_deal_id in {str(item.get("deal_id")) for item in supplier_payments.get("matched") or [] if item.get("deal_id")}:
                        publish_procurement_register(token, chat_id, paid_deal_id)
                update_deal_ui_state(chat_id, pending=None)
                send_message(
                    token, chat_id,
                    f"✅ Выписка импортирована.\n\n"
                    f"Счёт: {result.get('account')}\nПериод: {result.get('period')}\n"
                    f"Расходы: {bank_money(result.get('debit_total'))} ₽\n"
                    f"Поступления: {bank_money(result.get('credit_total'))} ₽\n"
                    f"Операций в файле: {result.get('read_count')}\n"
                    f"Новых: {result.get('new_count')}\n"
                    f"Повторов пропущено: {result.get('duplicate_count')}\n"
                    f"Оплат счетов поставщиков распознано: {paid_count}\n"
                    f"Требуют проверки: {review_count}",
                    BANK_MENU_KEYBOARD,
                )
                return
            if is_installer and not is_owner and not report_pending:
                original_ext = os.path.splitext(msg["document"].get("file_name") or "")[1].casefold()
                if original_ext not in INSTALLER_REPORT_EXTENSIONS:
                    send_message(token, chat_id, "Основной отчёт можно прислать в PDF, Word (.docx), Excel (.xlsx) или TXT.", INSTALLER_USER_KEYBOARD)
                    return
                original_path = local_path[:-3] if local_path.endswith(".md") else local_path
                process_installer_report(token, chat_id, original_path)
                return
            if report_pending == "installer_report_file":
                original_ext = os.path.splitext(msg["document"].get("file_name") or "")[1].casefold()
                if original_ext not in INSTALLER_REPORT_EXTENSIONS:
                    send_message(token, chat_id, "Пришлите основной отчёт в PDF, Word (.docx), Excel (.xlsx) или TXT.")
                    return
                original_path = local_path[:-3] if local_path.endswith(".md") else local_path
                process_installer_report(token, chat_id, original_path)
                return
            if report_pending == "installer_report_tables":
                original_name = msg["document"].get("file_name") or ""
                original_ext = os.path.splitext(original_name)[1].casefold()
                if original_ext not in (".xlsx", ".xls"):
                    send_message(token, chat_id, "Сейчас ожидаются соответствующие таблицы в формате Excel (.xlsx или .xls).", INSTALLER_REPORT_FILES_KEYBOARD)
                    return
                original_path = local_path[:-3] if local_path.endswith(".md") else local_path
                if original_ext == ".xls":
                    send_message(token, chat_id, "Старый формат .xls пока не разбирается надёжно. Сохраните таблицу как .xlsx и пришлите повторно.", INSTALLER_REPORT_FILES_KEYBOARD)
                    return
                session = report_state.get("installer_report") or {}
                paths = session.setdefault("table_paths", [])
                required = int(session.get("required_tables") or 0)
                if required and len(paths) >= required:
                    send_message(
                        token, chat_id,
                        f"Все требуемые таблицы уже получены ({len(paths)} из {required}). "
                        f"Нажмите «✅ Все файлы загружены»; лишний файл в пакет не добавлен.",
                        INSTALLER_REPORT_FILES_KEYBOARD,
                    )
                    return
                if original_path not in paths:
                    paths.append(original_path)
                update_deal_ui_state(chat_id, pending="installer_report_tables", installer_report=session)
                send_message(
                    token, chat_id,
                    f"📊 Таблица получена: {original_name}\nПолучено {len(paths)} из {required}. "
                    f"Пришлите остальные файлы или нажмите «✅ Все файлы загружены».",
                    INSTALLER_REPORT_FILES_KEYBOARD,
                )
                return
            if report_pending == "installer_payment_file":
                original_ext = os.path.splitext(msg["document"].get("file_name") or "")[1].casefold()
                if original_ext != ".pdf":
                    send_message(token, chat_id, "Для первой версии пришлите платёжный документ в PDF.")
                    return
                result = run_installer_settlements({"action": "parse_payment", "path": local_path})
                if not result.get("ok"):
                    send_message(token, chat_id, f"Не удалось разобрать платёжку: {result.get('error')}")
                    return
                payment = result["payment"]
                if payment.get("duplicate"):
                    send_message(token, chat_id, "Эта платёжка уже учтена — повторная запись заблокирована.", INSTALLER_MENU_KEYBOARD)
                    update_deal_ui_state(chat_id, pending=None, installer_payment=None)
                    return
                if payment.get("missing"):
                    send_message(token, chat_id, "Не удалось однозначно определить: " + ", ".join(payment["missing"]) + ". Выплата не записана; пришлите более читаемый PDF.")
                    return
                update_deal_ui_state(chat_id, pending="installer_payment_confirm", installer_payment=payment)
                warning = "\n⚠️ Проверьте получателя: имя монтажника не найдено в распознанной строке." if not any(part in (payment.get("recipient") or "").casefold() for part in ("деревянко", "сергей")) else ""
                send_message(token, chat_id, (
                    f"Платёж №{payment.get('number')} от {payment.get('date')}\n"
                    f"Получатель: {payment.get('recipient')}\n"
                    f"Сумма: {money(payment.get('amount'))}\n"
                    f"Назначение: {payment.get('purpose') or 'не указано'}{warning}\n\n"
                    f"Выберите способ выплаты. Безналичная оплата будет зачтена с коэффициентом 0,94; наличная — 1,00."
                ), INSTALLER_PAYMENT_KEYBOARD)
                return
            # A requisites-card upload is an explicit contract action.  It
            # must never fall through to the generic document model, even
            # when the parser cannot confidently extract its fields.
            if report_pending == "payer_card_file":
                if not begin_payer_card_flow(token, chat_id, local_path):
                    send_message(token, chat_id,
                                 "Не удалось извлечь реквизиты из файла. Пришлите PDF либо Word/Excel с "
                                 "текстовой карточкой (не фотографией); файл не будет передан в другой сценарий.",
                                 PAYER_UPLOAD_KEYBOARD)
                return
            if not report_state.get("deal_creation_active") and begin_payer_card_flow(token, chat_id, local_path):
                return
            if is_owner and report_state.get("deal_creation_active"):
                extracted_creation = extract_document_text_for_model(source_document_path)
                saved_creation = dict(report_state.get("deal_create_spec") or {})
                saved_creation["source_path"] = source_document_path
                update_deal_ui_state(chat_id, deal_create_spec=saved_creation,
                                     deal_creation_source_path=source_document_path)
                text += creation_attachment.prompt(current_deal_ui_state(chat_id), source_document_path, extracted_creation)
            statement_match = None
            if is_owner:
                update_deal_ui_state(chat_id, conversation_invoice=None)
            if is_owner and invoice_tasks.accepts_upload(report_state):
                extracted = extract_document_text_for_model(source_document_path)
                if extracted:
                    update_deal_ui_state(chat_id, conversation_invoice=invoice_continuation.remember(source_document_path, extracted, chat_id))
                    text += "\n\n[ТЕКСТ ПРИЛОЖЕННОГО ДОКУМЕНТА]\n" + extracted
                    text += statement_document_context.deal_candidates(caption)
                    statement_match = statement_document_context.match_document(source_document_path, extracted, chat_id)
                    registered = invoice_tasks.register(chat_id, source_document_path, extracted,
                                                        msg.get("message_id", 0), statement_match)
                    if registered:
                        task_state, registered_doc = registered
                        current_doc = invoice_tasks.active(task_state)
                        update_deal_ui_state(chat_id, conversation_invoice=current_doc)
                        if registered_doc["status"] == "cancelled":
                            return
                        if registered_doc["status"] == "applied":
                            send_message(token, chat_id, f"Счёт №{registered_doc['number']} уже обработан. Повторно не применяю.")
                            return
                        if current_doc and current_doc["sha256"] != registered_doc["sha256"]:
                            send_message(token, chat_id,
                                f"Счёт №{registered_doc['number']} сохранён в очереди. "
                                f"Сейчас продолжаем счёт №{current_doc['number']}.")
                            return
                        if not caption and current_doc and not (statement_match and statement_match.get("already_resolved")):
                            note = (f"Счёт №{current_doc['number']} сохранён. " +
                                    ("Это запрошенный документ для сверки выписки. " if statement_match else ""))
                            send_message(token, chat_id, note + invoice_tasks.question(current_doc))
                            return
                if statement_match:
                    text += statement_document_context.prompt_context(statement_match)
            if statement_match:
                send_message(token, chat_id,
                    f"📎 Счёт №{statement_match['invoice']} от {statement_match['supplier']} сохранён. "
                    f"Нашёл соответствие вопросу №{statement_match['old_question']} по выписке; проверяю состав и объект.")
            else:
                text += ("\n\n[ПРАВИЛО РАБОТЫ С ПРИЛОЖЕНИЕМ] Прочитай файл и доступный контекст. "
                         "Если назначение понятно из переписки или открытых задач, продолжай эту задачу. "
                         "Если неясно именно намерение пользователя, назови, что распознал в файле, "
                         "и задай один конкретный вопрос, что с ним сделать; предложи подходящие варианты. "
                         "Не выдавай отсутствие контекста за техническую ошибку и не обещай действий, которых не выполнил.")
                send_message(token, chat_id, "📎 Файл сохранён, проверяю содержимое и контекст...")
        else:
            text = msg["text"]
            if is_owner and retry_failed_kp(token, chat_id, text):
                return
            # Top-level navigation must bypass every pending wizard and all model/
            # CRM queues. This is the latency-critical path for the main menu.
            if is_owner and handle_global_navigation(token, chat_id, text):
                invoice_tasks.pause(chat_id)
                print(
                    f"{LOG_PREFIX} fast navigation handled in "
                    f"{time.monotonic() - received_at:.3f}s: {text!r}"
                )
                return
            if is_owner and installer_payment_intent(text):
                handle_deal_ui(token,chat_id,'💳 Учесть выплату')
                return
            if is_owner and handle_payer_flow_text(token, chat_id, text):
                return
            if is_owner and handle_deal_comparison_followup(token, chat_id, text):
                return
            if is_owner and handle_explicit_deal_comparison(token, chat_id, text):
                return
            if is_owner and handle_explicit_deal_read(token, chat_id, text):
                return
            if is_owner and handle_deal_search_phrase(token, chat_id, text):
                return
            if is_owner and handle_bare_deal_number(token, chat_id, text):
                return
            if handle_current_execution_ui(token, chat_id, text):
                return
            if is_installer and not is_owner:
                run_background_job(lambda: handle_installer_ui(token, chat_id, text), token, chat_id, operation='Кабинет монтажника')
                return
            if text.strip() in ("/start", "/help", "/помощь", "/menu", "❓ Помощь"):
                if text.strip() in ("/start", "/menu"):
                    update_deal_ui_state(chat_id, pending=None)
                send_message(token, chat_id, HELP_TEXT, MAIN_KEYBOARD)
                return

            if handle_bank_ui(token, chat_id, text):
                return
            if handle_deal_ui(token, chat_id, text):
                return

            if is_owner and text.strip().casefold() in ("/повторить", "повтори необработанный запрос"):
                failed = model_recovery.latest(MODEL_FAILURES_FILE, chat_id)
                if not failed:
                    send_message(token, chat_id, "Необработанных общих запросов нет. Счёт из раздела закупок можно повторить кнопкой «🔄 Повторить последний счёт».")
                    return
                text = failed['prompt']
                send_message(token, chat_id, "Повторяю сохранённый запрос. Повторно отправлять файл не нужно.")
            raw_user_text = text.strip()
            if raw_user_text == "➕ Создать сделку" or is_explicit_new_deal_request(raw_user_text):
                update_deal_ui_state(
                    chat_id, deal_creation_active=True, contract_deal_id=None,
                    deal_creation_items=None, deal_creation_economics_path=None,
                )
            elif is_explicit_contract_request(raw_user_text):
                update_deal_ui_state(chat_id, deal_creation_active=False)

            button_prompts = {
                "📄 Создать КП": "Хочу создать коммерческое предложение. Спроси необходимые данные по одному вопросу.",
                "➕ Создать сделку": "Хочу создать сделку в Мегаплане. Спроси необходимые данные по одному вопросу, включая обязательный выбор НДС.",
                "🧾 Учесть счёт": "Хочу учесть счёт поставщика в существующей сделке. Спроси номер сделки и попроси файл, если он ещё не приложен.",
                "🛠 Ведомость работ": "Хочу рассчитать ведомость работ. Спроси номер сделки.",
            }
            if text.strip() == "💰 Экономика сделки":
                send_message(token, chat_id, "Укажите внутренний ID сделки командой, например: /экономика 887", MAIN_KEYBOARD)
                return
            if text.strip() in button_prompts:
                text = button_prompts[text.strip()]

            invoice_match = INVOICE_CMD_RE.match(text.strip())
            deal_match = DEAL_CMD_RE.match(text.strip())
            if invoice_match or deal_match:
                key, value = ("invoiceId", invoice_match.group(1)) if invoice_match else ("dealId", deal_match.group(1))
                print(f"{LOG_PREFIX} invoice command: {key}={value}")
                send_typing(token, chat_id)
                result = fetch_megaplan_invoice_pdf({key: value})
                if result.get("ok"):
                    send_document(token, chat_id, result["path"], result.get("caption"), result.get("filename"))
                    try:
                        os.remove(result["path"])
                    except OSError:
                        pass
                else:
                    send_message(token, chat_id, f"Не удалось получить счёт: {result.get('error', 'неизвестная ошибка')}")
                return
            economics_match = ECONOMICS_CMD_RE.match(text.strip())
            if economics_match:
                deal_id = economics_match.group(1)
                send_message(token, chat_id, "📊 Читаю актуальные данные сделки из Мегаплана и считаю экономику...")
                result = build_and_store_profitability(deal_id)
                if result.get("ok"):
                    send_message(token, chat_id, format_profitability(deal_id, result), MAIN_KEYBOARD)
                    send_document(token, chat_id, result["path"], "Расчёт рентабельности сделки")
                    try:
                        os.remove(result["path"])
                    except OSError:
                        pass
                else:
                    send_message(token, chat_id, f"Не удалось построить экономику: {result.get('error', 'неизвестная ошибка')}", MAIN_KEYBOARD)
                return
            print(f"{LOG_PREFIX} received: {text[:200]!r}")

        # Model turns can legitimately take minutes (document OCR, KP parsing,
        # catalog searches). Run them in a child so the parent keeps polling
        # Telegram and deterministic menu buttons remain responsive. Serialize
        # model children because they resume one shared Codex conversation.
        # Remember that the assistant is in a conversation: a bare number sent
        # soon after is probably an answer to its question, not a deal to open.
        update_deal_ui_state(chat_id, assistant_turn_at=time.time())
        worker_pid = os.fork()
        if worker_pid:
            # Reap already-finished workers without ever waiting for a live one.
            try:
                while os.waitpid(-1, os.WNOHANG)[0]:
                    pass
            except ChildProcessError:
                pass
            return
        # Fresh document scenarios do not resume the shared chat session. Give
        # them two bounded lanes; one long OCR must not block all other files.
        isolated_document = bool('document' in msg and (supplier_invoice_deal_id or current_deal_ui_state(chat_id).get('deal_creation_active')))
        lane = int(hashlib.sha256(str((msg.get('document') or {}).get('file_unique_id') or msg.get('message_id')).encode()).hexdigest(),16)%2
        lock_path = MODEL_LOCK_FILE + f'.document-{lane}' if isolated_document else MODEL_LOCK_FILE
        model_lock = open(lock_path, "w")
        lock_wait_started = time.monotonic()
        if document_job:
            update_document_job(document_job["id"], stage="ожидание очереди ИИ")
        fcntl.flock(model_lock, fcntl.LOCK_EX)
        if not request_is_current() and not (document_job and supplier_invoice_deal_id):
            send_message(token, chat_id, 'Контекст изменился, пока запрос ожидал очередь. Файл, если был приложен, сохранён; продолжите из нужного раздела.')
            if document_job:
                update_document_job(document_job['id'], status='needs_retry', stage='контекст изменился; доступен повтор')
            os._exit(0)
        lock_wait = time.monotonic() - lock_wait_started
        if lock_wait >= 1:
            print(
                f"{LOG_PREFIX} model queue wait: {lock_wait:.2f}s "
                f"message_id={msg.get('message_id')}", file=sys.stderr,
            )
        send_typing(token, chat_id)
        supplier_invoice_mode = bool("document" in msg and supplier_invoice_deal_id)
        # A document sent while the explicit "Создать сделку" wizard is active
        # belongs to that wizard.  Product names (especially Haier) can naturally
        # trigger a live price lookup, but a lookup is only an intermediate step:
        # it must never replace preparation of the CRM deal.
        creation_state = current_deal_ui_state(chat_id)
        creation_document_mode = bool(
            "document" in msg
            and creation_state.get("deal_creation_active")
            and not supplier_invoice_mode
        )
        creation_request_snapshot = creation_state.get("deal_creation_request")
        creation_source_snapshot = creation_state.get("deal_creation_source_path")
        typed_creation_spec = str(creation_state.get("deal_creation_text_spec") or "")
        if (creation_state.get("deal_creation_active") and typed_creation_spec
                and has_explicit_deal_economics(typed_creation_spec)):
            saved_draft = creation_state.get("deal_create_spec") or {}
            text += (
                "\n\n[АВТОРИТЕТНЫЙ ТЕКСТОВЫЙ ЧЕРНОВИК НОВОЙ СДЕЛКИ]\n" + typed_creation_spec
                + "\nКлиент и название из сохранённого черновика уже подтверждены: "
                + json.dumps({key: saved_draft.get(key) for key in (
                    "description", "client_id", "client_name", "client_kind"
                )}, ensure_ascii=False)
                + "\nПользователь явно указал продажные цены и закупку/себестоимость. "
                  "Не запускай HOGART_SEARCH или DAICHI_SEARCH, не спрашивай клиента повторно "
                  "и не заменяй эти числа каталогом. Подготовь CREATE_MEGAPLAN_DEAL по этому тексту."
            )
        if supplier_invoice_mode:
            if document_job:
                update_document_job(document_job["id"], stage="разбор счёта ИИ",
                                    model_queue_seconds=round(lock_wait, 2))
                notify_document_progress(token, chat_id, document_job["id"])
            ledger = fetch_deal_ledger(supplier_invoice_deal_id)
            if ledger is None:
                send_message(
                    token, chat_id,
                    f"Не удалось прочитать позиции сделки №{supplier_invoice_deal_id}. "
                    "Счёт не потерян и не будет отнесён к другой сделке; попробуйте обработать его ещё раз чуть позже.",
                    PROCUREMENT_KEYBOARD,
                )
                os._exit(0)
            text += (
                "\n\n[СИСТЕМНЫЙ КОНТЕКСТ ЗАКУПКИ]\n"
                f"Файл загружен через кнопку «Загрузить счёт поставщика» в уже выбранной "
                f"сделке №{supplier_invoice_deal_id}. Сделка подтверждена. ЗАПРЕЩЕНО предлагать "
                "создать новую сделку, выбирать другую сделку или запрашивать её номер. "
                "Сопоставь строки счёта с позициями ниже и сразу выведи "
                "SUPPLIER_INVOICE_APPLY_BEGIN/END. Если строка действительно неоднозначна, "
                "задай только вопрос о её сопоставлении, сохраняя эту сделку. В объект invoice "
                f"добавь source_path со значением {source_document_path!r}, чтобы исходный файл сохранился "
                "в карточке сделки после подтверждения.\n"
                "Если часть строк явно не относится к выбранной сделке, НЕ добавляй их в additions: "
                "оставь их нераспределёнными. В updates обязательно передай source_line_key, "
                "source_sku, source_name, source_qty и source_total для каждой строки счёта. "
                "ОБЯЗАТЕЛЬНО укажи invoice.currency (RUB, EUR, USD и т. п.). Если счёт валютный, "
                "invoice.total и суммы строк указывай в исходной валюте; в invoice.payment_note передай "
                "дословное примечание об определении курса (например «ЦБ + 3%»). Не пересчитывай "
                "валюту самостоятельно: курс и рублёвый план определяет сервер.\n"
                "Позиции выбранной сделки:\n" +
                json.dumps(ledger, ensure_ascii=False, indent=2)
            )
            extracted_document_text = extract_document_text_for_model(source_document_path)
            if extracted_document_text:
                text += (
                    "\n\n[ТЕКСТ СЧЁТА ИЗВЛЕЧЁН ЛОКАЛЬНО — ИСПОЛЬЗУЙ ЕГО КАК ОСНОВНОЙ ИСТОЧНИК]\n"
                    + extracted_document_text
                )
        elif creation_state.get("deal_creation_active") and creation_state.get("deal_creation_items"):
            fixed_total = round(sum(
                float(item.get("qty") or 0) * float(item.get("unit_price") or 0)
                for item in (creation_state.get("deal_creation_items") or [])
            ), 2)
            expected_total = creation_state.get("deal_creation_expected_total")
            text += (
                "\n\n[СИСТЕМНЫЙ КОНТЕКСТ СОЗДАНИЯ СДЕЛКИ]\n"
                f"В активном черновике уже есть {len(creation_state.get('deal_creation_items') or [])} "
                f"детальных позиций из загруженной спецификации на {fixed_total:,.2f} ₽. "
                "Эти строки, количества, продажные цены и две составляющие себестоимости "
                "обязательны и будут подставлены сервером; не укрупняй и не заменяй их. "
                + (f"Ранее пользователь указал общую сумму {float(expected_total):,.2f} ₽. "
                   if expected_total is not None else "")
                + "Если суммы различаются, сначала спроси, какую сумму считать верной; "
                "не создавай сделку и не меняй цены молча. Если пользователь подтвердил "
                "сумму спецификации, продолжи создание через CREATE_MEGAPLAN_DEAL."
            )
        routing_text = msg.get("text") or msg.get("caption") or ""
        routing_state = invoice_tasks.read(chat_id) if is_owner else {}
        # A specification typed into the «Создать сделку» wizard belongs to that
        # wizard, even when it names a product (Haier, сплит…) like a catalog query.
        wizard_state = current_deal_ui_state(chat_id)
        creation_wizard_text = bool(wizard_state.get("deal_creation_active")
                                    and str(wizard_state.get("pending") or "").startswith("deal_create_"))
        catalog_task_mode = bool(is_owner and not supplier_invoice_mode and not creation_document_mode
            and not creation_wizard_text
            and "document" not in msg and catalog_conversation.is_turn(routing_text, routing_state))
        if catalog_task_mode:
            routing_state = catalog_conversation.begin(chat_id, routing_text)
            text = catalog_conversation.prompt(routing_state)
        if (is_owner and "text" in msg and not supplier_invoice_mode and not creation_document_mode and not catalog_task_mode and not routing_state.get("paused")
                and msg.get("text", "").strip().casefold() not in ("/повторить", "повтори необработанный запрос")):
            text += statement_document_context.recent_context(chat_id)
            text += statement_document_context.deal_candidates(msg.get("text", ""))
            text += invoice_continuation.context(current_deal_ui_state(chat_id).get("conversation_invoice"))
        task_state = invoice_tasks.read(chat_id) if is_owner else {}
        task_doc = invoice_tasks.active(task_state)
        invoice_task_mode = bool(task_doc and not supplier_invoice_mode and not creation_document_mode and not catalog_task_mode
            and not explicit_catalog_request(msg.get("text") or msg.get("caption") or ""))
        if invoice_task_mode:
            raw_input = msg.get("text") or msg.get("caption") or ""
            if raw_input.strip().casefold() in ("к существующей", "к существующей сделке"):
                invoice_tasks.history(chat_id, "user", raw_input, task_doc["sha256"])
                send_message(token, chat_id, invoice_tasks.question(task_doc))
                os._exit(0)
            task_state = invoice_tasks.history(chat_id, "user", raw_input, task_doc["sha256"])
            text = invoice_tasks.prompt(task_state) + statement_document_context.deal_candidates(raw_input)
            update_deal_ui_state(chat_id, conversation_invoice=task_doc)

        catalog_steps = []
        def ask_current_model(prompt):
            if creation_document_mode:
                return ask_fresh_document_model(text + "\n\n[РЕЗУЛЬТАТ ТЕКУЩЕГО ШАГА]\n" + prompt)
            if catalog_task_mode:
                if prompt != text:
                    catalog_steps.append(prompt)
                return catalog_conversation.guard(ask_fresh_document_model(text + "\n\n[РЕЗУЛЬТАТЫ ТЕКУЩЕГО ПОИСКА]\n" + "\n\n".join(catalog_steps)), routing_state)
            if invoice_task_mode:
                answer = ask_fresh_document_model(text + "\n\n[РЕЗУЛЬТАТ ТЕКУЩЕГО ШАГА]\n" + prompt)
                if isinstance(answer, model_recovery.ModelUnavailable):
                    send_message(token, chat_id, str(answer)); os._exit(0)
                # Cancellation/new input invalidates every later protocol and reply.
                if not request_is_current() or invoice_tasks.cancelled(chat_id, task_doc["path"]):
                    os._exit(0)
                return invoice_tasks.guard_reply(answer, task_doc)
            return ask_claude(session_id, prompt)

        model_started = time.monotonic()
        if creation_document_mode:
            text += '\n\n[СОХРАНЁННЫЙ ЧЕРНОВИК — НЕ БРАТЬ ДАННЫЕ ДРУГОЙ СДЕЛКИ]\n' + json.dumps(creation_state.get('deal_create_spec') or {},ensure_ascii=False)
        reply = ask_fresh_document_model(text) if supplier_invoice_mode or creation_document_mode else ask_current_model(text)
        model_elapsed = round(time.monotonic() - model_started, 2)
        if creation_document_mode and (
                not request_is_current()
                or not creation_attachment.is_current(
                    current_deal_ui_state(chat_id),
                    creation_request_snapshot,
                    creation_source_snapshot,
                )):
            print(
                f"{LOG_PREFIX} discarded stale deal-creation document reply "
                f"message_id={msg.get('message_id')}",
                file=sys.stderr,
            )
            os._exit(0)
        if isinstance(reply, model_recovery.ModelUnavailable):
            record_operation_timing("ИИ: ответ бота", model_elapsed, chat_id, "needs_retry", reply.kind)
            if document_job:
                finish_document_job(document_job['id'], 'needs_retry', reply.kind)
            send_message(token, chat_id, str(reply))
            os._exit(0)

        record_operation_timing("ИИ: разбор счёта" if supplier_invoice_mode else "ИИ: ответ бота",
                                model_elapsed, chat_id, "ok",
                                f"очередь ИИ {lock_wait:.2f} с")
        if supplier_invoice_mode:
            print(f"{LOG_PREFIX} supplier invoice parsed in {model_elapsed:.2f}s "
                  f"job={(document_job or {}).get('id')}", file=sys.stderr)
            if document_job:
                update_document_job(document_job["id"], parse_seconds=model_elapsed,
                                    stage="подготовка распределения")
        if supplier_invoice_mode and not SUPPLIER_INVOICE_APPLY_RE.search(reply):
            legitimate_question = re.search(r"(?i)неоднознач|уточнит|какой позиции|сопостав", reply or "")
            if not legitimate_question:
                print(f"{LOG_PREFIX} isolated invoice parser returned no protocol; retrying once", file=sys.stderr)
                retry_prompt = text + (
                    "\n\nПРЕДЫДУЩАЯ ПОПЫТКА НЕ ВЕРНУЛА ПРОТОКОЛ. Не ищи товары в Hogart/Daichi и не "
                    "обсуждай каталог. Верни только SUPPLIER_INVOICE_APPLY_BEGIN/END для выбранной "
                    "сделки либо один конкретный вопрос о неоднозначном сопоставлении."
                )
                reply = ask_fresh_document_model(retry_prompt)
                if isinstance(reply, model_recovery.ModelUnavailable):
                    if document_job:
                        finish_document_job(document_job['id'], 'needs_retry', reply.kind)
                    send_message(token, chat_id, str(reply))
                    os._exit(0)
            if not SUPPLIER_INVOICE_APPLY_RE.search(reply) and not re.search(
                    r"(?i)неоднознач|уточнит|какой позиции|сопостав", reply or ""):
                reply = (f"Не удалось надёжно сопоставить строки счёта со сделкой "
                         f"№{supplier_invoice_deal_id}. Файл сохранён, данные в Мегаплан не записаны.")

        deal_catalog_bypass = {"used": False}

        def run_hogart_search_round(reply_text):
            """Extract+run a HOGART_SEARCH block if present. Returns (new_reply, fired)."""
            reply_text, keywords = extract_hogart_searches(reply_text)
            if not keywords:
                return reply_text, False
            print(f"{LOG_PREFIX} live hogart search requested: {keywords}")
            send_typing(token, chat_id)
            results = {kw: hogart_live_search(kw) for kw in keywords}
            search_error = catalog_conversation.search_failure('Hogart', results.values())
            if search_error:
                return search_error, True
            for r in results.values():
                if r and len(r.get("items", [])) > MAX_HOGART_ITEMS_IN_PROMPT:
                    r["items"] = r["items"][:MAX_HOGART_ITEMS_IN_PROMPT]
                    r["truncated"] = True
            followup = (
                "Результаты живого поиска через официальный API hogart (актуально прямо "
                "сейчас):\n\n" + json.dumps(results, ensure_ascii=False, indent=2) +
                "\n\nСформулируй финальный ответ пользователю на основе этих данных. "
                "Если каких-то товаров нет в результатах — так и скажи. Если у результата "
                "стоит \"truncated\": true — список неполный, слишком широкий запрос, "
                "попроси у пользователя уточнить артикул точнее. ВАЖНО: если по смыслу "
                "исходного запроса пользователя нужно было ЕЩЁ и сравнение/поиск по Daichi "
                "или ещё по Hogart другими словами, а ты его в этом диалоге ещё не делал — "
                "выведи нужную строку (HOGART_SEARCH и/или DAICHI_SEARCH) прямо в этом "
                "ответе сейчас же, не пиши, что 'ждёшь'/'сейчас поищешь' его отдельно."
            )
            return ask_current_model(followup), True

        def run_daichi_search_round(reply_text):
            """Extract+run a DAICHI_SEARCH block if present. Returns (new_reply, fired)."""
            reply_text, filters_list = extract_daichi_searches(reply_text)
            if not filters_list:
                return reply_text, False
            print(f"{LOG_PREFIX} live daichi search requested: {filters_list}")
            send_typing(token, chat_id)
            results = [daichi_live_search(f) for f in filters_list]
            search_error = catalog_conversation.search_failure('Daichi', results)
            if search_error:
                return search_error, True
            for r in results:
                if r and len(r.get("items", [])) > MAX_DAICHI_ITEMS_IN_PROMPT:
                    r["items"] = r["items"][:MAX_DAICHI_ITEMS_IN_PROMPT]
                    r["truncated"] = True
            followup = (
                "Результаты поиска по каталогу Daichi (кэш, см. свою инструкцию про "
                "cost_price/sell_price):\n\n" + json.dumps(results, ensure_ascii=False, indent=2) +
                "\n\nСформулируй финальный ответ пользователю на основе этих данных. "
                "Если ничего не нашлось — так и скажи, предложи изменить условия поиска "
                "(шире допуск по мощности, без 'только в наличии' и т.п.). Если у результата "
                "стоит \"truncated\": true — список неполный, слишком широкий запрос. ВАЖНО: "
                "если по смыслу запроса нужен ЕЩЁ поиск по Hogart (другими ключевыми словами), "
                "а ты его ещё не делал в этом диалоге — выведи HOGART_SEARCH прямо сейчас, не "
                "пиши, что 'ждёшь'/'сейчас поищешь' его отдельно."
            )
            return ask_current_model(followup), True

        # Safety net (2026-08-26 incident): repeatedly observed the model claim "жду
        # результат(ы)"/"сейчас поищу" about EITHER supplier across multiple turns
        # without ever actually emitting the corresponding search marker - a session-
        # anchoring failure mode (see project memory, 2026-08-24) where the model
        # treats its own earlier claim of "searching" as an already-completed action
        # instead of re-checking whether it really fired. Prompt wording alone failed
        # twice (once per supplier) - this loop is deterministic: keep offering one
        # corrective nudge as long as the reply stalls without firing anything, capped
        # so a persistently confused model can't loop forever.
        STALL_RE = re.compile(r"(?i)жду\s+(?:ещё\s+)?результат|сейчас\s+пои[щс]|попробую\s+(?:поискать|уточнить)")
        # Loop, not a single pass (2026-08-26 incident): a HOGART_SEARCH/DAICHI_SEARCH
        # followup reply can itself contain ANOTHER marker (e.g. Claude's first search
        # only found spare parts, so it self-corrects and searches again with a
        # narrower keyword in the same followup) - a one-shot round_hogart+round_daichi
        # call only ever re-scans the ORIGINAL reply, never the followup's own reply,
        # so that second marker used to leak to the user as raw unprocessed text
        # instead of being executed. Keep re-scanning the latest reply until a pass
        # fires nothing new, capped so a persistently confused model can't loop forever.
        hogart_fired_this_message = False
        forced_hogart_refresh = False
        catalog_fired_this_message = False
        for _ in range(0 if supplier_invoice_mode or creation_document_mode or invoice_task_mode else 5):
            bypass_catalog = (creation_state.get("deal_creation_active") and typed_creation_spec
                              and has_explicit_deal_economics(typed_creation_spec))
            if bypass_catalog:
                reply_without_hogart, hogart_requests = extract_hogart_searches(reply)
                reply_without_catalog, daichi_requests = extract_daichi_searches(reply_without_hogart)
                if hogart_requests or daichi_requests:
                    reply = reply_without_catalog
                    if not deal_catalog_bypass["used"]:
                        deal_catalog_bypass["used"] = True
                        reply = ask_current_model(
                            "ПОИСК ПО КАТАЛОГАМ НЕ ВЫПОЛНЕН: владелец уже явно задал продажные цены "
                            "и закупку/себестоимость. Используй сохранённые название, клиента и текст "
                            "спецификации; верни CREATE_MEGAPLAN_DEAL_BEGIN/END со всеми позициями."
                        )
                    hogart_fired, daichi_fired = bool(hogart_requests), bool(daichi_requests)
                else:
                    hogart_fired = daichi_fired = False
            else:
                reply, hogart_fired = run_hogart_search_round(reply)
                reply, daichi_fired = run_daichi_search_round(reply)
            hogart_fired_this_message = hogart_fired_this_message or hogart_fired
            catalog_fired_this_message = catalog_fired_this_message or hogart_fired or daichi_fired
            if hogart_fired or daichi_fired:
                continue
            if ((catalog_task_mode or needs_fresh_hogart_search(msg.get("text") or msg.get("caption") or "")) and not catalog_fired_this_message
                    and not forced_hogart_refresh and not creation_wizard_text
                    and not CREATE_MEGAPLAN_DEAL_RE.search(reply)):
                forced_hogart_refresh = True
                print(f"{LOG_PREFIX} forcing fresh hogart search for new user query")
                reply = ask_current_model((
                    "Это НОВЫЙ запрос пользователя о цене/наличии товара, "
                    "но ты ответил без нового HOGART_SEARCH и, вероятно, повторил старые "
                    "данные из истории. Предыдущие результаты использовать запрещено. "
                    "Выведи сейчас подходящую команду HOGART_SEARCH или DAICHI_SEARCH для свежей проверки."
                ))
                continue
            if STALL_RE.search(reply):
                print(f"{LOG_PREFIX} detected a search stall - forcing one corrective round: {reply[:200]!r}")
                nudge = (
                    "Ты написал текст о том, что ждёшь/будешь искать что-то у Hogart или "
                    "Daichi, но в этом сообщении не было реального маркера HOGART_SEARCH "
                    "или DAICHI_SEARCH — ничего не произошло и пользователь просто увидел "
                    "тишину. Если для ответа пользователю ещё нужны данные — выведи нужный "
                    "маркер ПРЯМО СЕЙЧАС, в этом ответе. Если не нужны — дай пользователю "
                    "окончательный ответ без упоминаний ожидания/поиска."
                )
                reply = ask_current_model(nudge)
                continue
            break

        if creation_document_mode and not CREATE_MEGAPLAN_DEAL_RE.search(reply):
            print(f"{LOG_PREFIX} continuing active deal creation after document parse")
            send_typing(token, chat_id)
            reply = ask_fresh_document_model(text + '\n\n' + (
                "КРИТИЧЕСКОЕ ПРОДОЛЖЕНИЕ СЦЕНАРИЯ: пользователь прислал этот файл "
                "как спецификацию для УЖЕ подтверждённого создания НОВОЙ сделки. "
                "Таблица цен/наличия, которую ты только что подготовил, не является "
                "финальным ответом и не должна быть показана вместо создания сделки. "
                "Извлеки из только что полученного файла все позиции и количества; "
                "используй уже собранные в диалоге название сделки, клиента, сумму, "
                "дату закрытия, ответственного и выбранный НДС. Сейчас выведи "
                "CREATE_MEGAPLAN_DEAL_BEGIN/END с непустым items. Закупочные цены "
                "не подставляй как цены продажи, если пользователь не попросил этого. "
                "Если в файле невозможно определить хотя бы одну позицию или её "
                "количество, задай ровно один конкретный вопрос о ней; не запускай "
                "новый поиск и не начинай иной сценарий."
            ))

        reply, wants_recent_deals = extract_recent_deals_request(reply)
        if wants_recent_deals:
            print(f"{LOG_PREFIX} recent deals requested")
            send_typing(token, chat_id)
            followup = (
                statement_document_context.deal_candidates(msg.get("text") or msg.get("caption") or "") +
                "\nПоследние сделки, созданные ботом:\n\n" +
                json.dumps(fetch_recent_deals(), ensure_ascii=False, indent=2) +
                "\n\nЭто только недавние сделки, а не полный список. Если пользователь уже назвал объект, "
                "не делай вывод об отсутствии сделки по этому списку. Используй кандидатов из индекса всех сделок "
                "в контексте документа и запроси позиции подходящей сделки. Спрашивай объект только при настоящей неоднозначности. "
                "Если это карточка реквизитов, речь о сделке, к которой нужно "
                "привязать плательщика; если счёт/КП — о сделке заказа."
            )
            reply = ask_current_model(followup)

        reply, ledger_deal_id = extract_deal_ledger_request(reply)
        if ledger_deal_id:
            print(f"{LOG_PREFIX} deal ledger requested for deal {ledger_deal_id}")
            send_typing(token, chat_id)
            ledger = fetch_deal_ledger(ledger_deal_id)
            if ledger is None:
                # 2026-08-24 incident: this used to silently come back as `[]`
                # (same as "deal genuinely has no positions"), and Claude reasonably
                # concluded everything from the supplier invoice was a brand-new
                # position - duplicating items that already existed, with mismatched
                # pricing on top. MUST be phrased so Claude cannot mistake this for
                # an empty deal - never proceed to additions/updates on this path.
                followup = (
                    f"ТЕХНИЧЕСКАЯ ОШИБКА при получении позиций сделки {ledger_deal_id} - "
                    "это НЕ означает, что в сделке нет позиций, просто не удалось их "
                    "прочитать сейчас. НЕ считай сделку пустой, НЕ предлагай добавлять "
                    "позиции как новые. Сообщи пользователю о технической ошибке и "
                    "попроси попробовать ещё раз чуть позже, не выводи блок "
                    "SUPPLIER_INVOICE_APPLY_BEGIN в этом ответе."
                )
            else:
                followup = (
                    f"Позиции сделки {ledger_deal_id}:\n\n" +
                    json.dumps(ledger, ensure_ascii=False, indent=2) +
                    "\n\nСопоставь их с позициями из присланного счёта поставщика по названию "
                    "и продолжай исходную задачу. Если это сверка банковской выписки, определи объект оплаты; "
                    "не меняй состав клиентской сделки, не добавляй позиции и не спрашивай наценку. "
                    "Счёт поставщика и оплата сами по себе не означают отгрузку. "
                    "Если пользователь отказался от добавления, не предлагай ту же мутацию повторно."
                )
            reply = (ask_current_model(followup) if ledger is not None else
                     f"Не удалось прочитать актуальные позиции сделки №{ledger_deal_id}. "
                     "Считать её пустой нельзя. Файл сохранён; новые позиции не добавлены, данные сделки не изменены.")

        reply, kp_spec = extract_build_kp(reply)
        kp_document_path = None
        kp_xlsx_path = None
        if kp_spec is not None:
            if kp_spec.get("__invalid__"):
                reply = (reply + "\n\n" if reply.strip() else "") + "Не удалось разобрать задание на КП (некорректный формат)."
            else:
                print(f"{LOG_PREFIX} building KP: {json.dumps(kp_spec, ensure_ascii=False)[:300]}")
                send_message(token, chat_id, "🧮 Собираю КП, ищу цены и считаю экономику...")
                send_typing(token, chat_id)
                kp_result = run_generate_kp(kp_spec, chat_id)
                if kp_result.get("ok"):
                    kp_document_path = kp_result["path"]
                    kp_xlsx_path = kp_result.get("economics_xlsx_path")
                    summary = format_kp_summary(kp_result)
                    if len(kp_result["variants"]) > 1:
                        # Owner's explicit choice (2026-08-26): a multi-variant KP is
                        # "N options, none chosen yet" - don't auto-create a Megaplan
                        # deal for it like a single-configuration KP does. Ask instead,
                        # holding the real order data in _pending_kp_deal (Python-side,
                        # never re-derived through the model - see marker comment above).
                        global _pending_kp_deal
                        _pending_kp_deal = None
                        summary += "\n\nЭто альтернативные варианты. После выбора варианта откройте «Создать сделку» и приложите его спецификацию. Само КП не создаёт сделку."
                    else:
                        if RUNTIME_ACTIVE or not should_auto_create_kp_deal(text):
                            reply = (reply + "\n\n" if reply.strip() else "") + summary
                            megaplan_deal = None
                            # A revision updates the deliverable only; never create
                            # a duplicate/empty CRM deal implicitly.
                            kp_result["_skip_auto_deal"] = True
                        else:
                            megaplan_deal = create_megaplan_deal(kp_spec, kp_result)
                            if megaplan_deal:
                                summary += f"\n\nСоздана сделка в Мегаплане: {megaplan_deal['url']}"
                            else:
                                summary += "\n\n⚠️ Не удалось создать сделку в Мегаплане (см. лог)."
                            reply = (reply + "\n\n" if reply.strip() else "") + summary
                    if len(kp_result["variants"]) > 1:
                        reply = (reply + "\n\n" if reply.strip() else "") + summary
                else:
                    reply = (reply + "\n\n" if reply.strip() else "") + f"Не удалось собрать КП: {kp_result.get('error', 'неизвестная ошибка')}"

        reply, create_kp_deal_confirmed = extract_create_kp_deal_confirm(reply)
        if create_kp_deal_confirmed is not None:
            if RUNTIME_ACTIVE:
                _pending_kp_deal = None
                reply = 'Для создания сделки откройте «➕ Создать сделку»: выберите клиента и подтвердите спецификацию. По одному ответу «да» сделка не создаётся.'
            elif _pending_kp_deal is None:
                reply = (reply + "\n\n" if reply.strip() else "") + "Нет КП, ожидающего решения по сделке (возможно, уже обработано ранее)."
            elif create_kp_deal_confirmed:
                megaplan_deal = create_megaplan_deal(_pending_kp_deal["kp_spec"], _pending_kp_deal["kp_result"])
                if megaplan_deal:
                    reply = (reply + "\n\n" if reply.strip() else "") + f"Создана сделка в Мегаплане: {megaplan_deal['url']}"
                else:
                    reply = (reply + "\n\n" if reply.strip() else "") + "⚠️ Не удалось создать сделку в Мегаплане (см. лог)."
                _pending_kp_deal = None
            else:
                reply = (reply + "\n\n" if reply.strip() else "") + "Хорошо, сделку не завожу — скажи, когда клиент определится с вариантом."
                _pending_kp_deal = None

        reply, deal_spec = extract_create_megaplan_deal(reply)
        spec_review_xlsx_path = None
        if deal_spec is not None:
            creation_state = current_deal_ui_state(chat_id)
            creation_authorized = bool(creation_state.get("deal_creation_active"))
            if not creation_authorized:
                print(f"{LOG_PREFIX} blocked unauthorized CREATE_MEGAPLAN_DEAL marker")
                reply = (reply + "\n\n" if reply.strip() else "") + (
                    "Создание новой сделки заблокировано: текущий сценарий не был начат командой «Создать сделку»."
                )
                deal_spec = None
            elif deal_spec.get("__invalid__"):
                deal_spec = None
                saved = dict(creation_state.get('deal_create_spec') or {})
                saved.pop('__invalid__', None)
                next_step = 'deal_create_items' if saved.get('client_name') else 'deal_create_client'
                update_deal_ui_state(chat_id, pending=next_step, deal_create_spec=saved)
                reply = ('Не удалось распознать позиции. Сохранённые данные сделки не потеряны. Пришлите спецификацию файлом.'
                         if next_step == 'deal_create_items' else 'Укажите клиента для новой сделки.')
            else:
                # A recognized economics workbook is authoritative.  Never allow
                # an LLM summary such as "materials × 1" to replace its detailed
                # rows, quantities, prices and separate material/work costs.
                fixed_items = creation_state.get("deal_creation_items") or []
                # Identity/permission comes only from the deterministic UI,
                # not from an attachment or model-produced service block.
                for protected_key in ('client_id', 'allow_new_client'):
                    deal_spec.pop(protected_key, None)
                saved_create_spec = creation_state.get("deal_create_spec") or {}
                # The interactive wizard may have already collected client,
                # title and tax before the user attaches the specification.  Keep
                # those confirmed values at the trust boundary: an attachment
                # parser must not make the model re-guess them or borrow a value
                # from an older conversation branch.
                if saved_create_spec:
                    deal_spec = {**deal_spec, **{
                        key: value for key, value in saved_create_spec.items()
                        if value not in (None, "", [], {}) and key != "items"
                    }}
                if fixed_items:
                    deal_spec = {**deal_spec, "items": fixed_items}
                unvalidated_spec = dict(deal_spec)
                deal_spec, validation_error = normalize_create_deal_spec(deal_spec)
                if validation_error:
                    # The LLM must normally ask for the specification before it
                    # emits the marker.  This guard makes a missed question
                    # recoverable: keep the already collected client, tax and
                    # deal fields, and return the user to the missing step
                    # instead of presenting a terminal internal-looking error.
                    if validation_error == "не указаны позиции сделки":
                        incomplete_spec = dict(unvalidated_spec)
                        incomplete_spec.pop("items", None)
                        update_deal_ui_state(
                            chat_id,
                            pending="deal_create_items",
                            deal_create_spec=incomplete_spec,
                            deal_creation_active=True,
                        )
                        reply = (reply + "\n\n" if reply.strip() else "") + (
                            "Для создания сделки не хватает спецификации. Пришлите "
                            "её файлом (PDF, Word или Excel) либо перечислите "
                            "оборудование, материалы и работы с количеством. "
                            "Реквизиты, НДС и остальные введённые данные сохранены."
                        )
                    else:
                        reply = (reply + "\n\n" if reply.strip() else "") + (
                            f"Не удалось подготовить черновик сделки: {validation_error}"
                        )
                    deal_spec = None
            if deal_spec is not None and str(deal_spec.get("tax_mode") or "") not in ("none", "22", "5"):
                # Persist the full parsed order before asking the one remaining
                # question. A later "Без НДС" is handled above without an LLM turn.
                deal_spec["tax_mode"] = "pending"
                update_deal_ui_state(
                    chat_id, pending="deal_create_tax", deal_create_spec=deal_spec,
                    current_deal_id=None, deal_creation_active=True,
                )
                if "TAX_CHOICE_REQUEST" not in reply:
                    reply = (reply + "\n\n" if reply.strip() else "") + "Выберите режим налогообложения для новой сделки.\nTAX_CHOICE_REQUEST"
            elif deal_spec is not None:
                update_deal_ui_state(chat_id, deal_create_spec=deal_spec,
                                     deal_creation_items=deal_spec.get("items"),
                                     deal_creation_active=True)
                prepare_deal_creation_review(token, chat_id, deal_spec)
                # A model narrative is not a receipt and must not claim
                # creation after only preparing the preview.
                reply = ''

        reply, sync_spec = extract_sync_deal_kp(reply)
        if sync_spec is not None:
            if sync_spec.get("__invalid__") or not sync_spec.get("deal_id") or not sync_spec.get("kp"):
                reply = (reply + "\n\n" if reply.strip() else "") + "Не удалось разобрать обновление сделки (некорректный формат)."
            else:
                selected = current_deal_ui_state(chat_id).get('current_deal_id')
                if str(selected) != str(sync_spec['deal_id']):
                    send_message(token, chat_id, 'Выберите сделку, позиции которой нужно заменить. Данные не изменены.', DEALS_KEYBOARD)
                    return
                send_message(token, chat_id, f"Готовлю просмотр замены позиций сделки №{selected}. Пока ничего не записываю.")
                result = run_sync_deal_kp({'deal_id': str(selected), 'kp': sync_spec['kp'], 'preview': True})
                if result.get("ok"):
                    prepared = {'deal_id': str(selected), 'prepared_rows': result['rows'], 'expected_fingerprint': result['fingerprint']}
                    update_deal_ui_state(chat_id, pending='deal_sync_confirm', deal_sync_spec=prepared)
                    lines = [f"• {x['name']}: {x['qty']} × {bank_money(x['unit_price'])} ₽" for x in result['rows']]
                    send_message(token, chat_id, f"Заменить все {result['before_count']} позиций сделки №{selected} на следующие:\n" + '\n'.join(lines) +
                                 f"\nНовый итог: {bank_money(result['total'])} ₽. Цены фиксируются по этому просмотру.",
                                 {'keyboard': [[{'text': '✅ Заменить позиции подтверждённым КП'}], [{'text': '❌ Отмена'}]]})
                    reply = ''
                else:
                    reply = (reply + "\n\n" if reply.strip() else "") + f"Не удалось обновить сделку: {result.get('error')}"

        reply, payer_spec = extract_payer_card_apply(reply)
        if payer_spec is not None:
            # File parsing belongs to the explicit payer flow. A model block
            # is neither a selected client ID nor permission to write.
            reply = ('Реквизиты не записаны. Откройте выбранную сделку → '
                     '«Работа с договором» → «Добавить плательщика» и загрузите карточку. '
                     'Бот покажет данные перед привязкой; клиент сделки не изменится.')

        reply, invoice_apply_spec = extract_supplier_invoice_apply(reply)
        if invoice_apply_spec is not None and not supplier_invoice_mode:
            bound = invoice_continuation.bind(invoice_apply_spec,
                current_deal_ui_state(chat_id).get("conversation_invoice"), chat_id)
            if bound is not None and fetch_deal_ledger(bound["deal_id"]) is not None:
                invoice_apply_spec = bound
                supplier_invoice_mode = True  # Preview only; confirmation below remains mandatory.
                source_document_path = bound["invoice"]["source_path"]
                reply = ""  # Replace model promises with the actual prepared preview.
            else:
                invoice_apply_spec = None
                reply = ("Данные не записаны: не удалось подтвердить связь разбора с текущим файлом "
                         "и прочитать сделку. Сохранённый счёт не потерян; повторную загрузку через меню не требую.")
        if invoice_apply_spec is not None:
            # Foreign document amounts are never silently interpreted as RUB.
            # This turns EUR/USD source rows into a documented RUB *plan* using
            # CBR on the invoice date and the supplier's CBR markup before the
            # generic allocation code performs its all-RUB arithmetic.
            if supplier_invoice_mode and not invoice_apply_spec.get("__invalid__"):
                try:
                    invoice_apply_spec = plan_invoice_spec(invoice_apply_spec)
                except CurrencyPlanningError as exc:
                    reply = (reply + "\n\n" if reply.strip() else "") + (
                        "Валютный счёт распознан, но план не записан: " + str(exc) +
                        ". Данные не применены, чтобы не принять валюту за рубли.")
                    invoice_apply_spec = None
            if invoice_apply_spec is not None:
             if (supplier_invoice_mode and not invoice_apply_spec.get("__invalid__") and
                    float((invoice_apply_spec.get("invoice") or {}).get("total") or 0) > 0):
                parsed_total = float((invoice_apply_spec.get("invoice") or {}).get("total") or 0)
                covered_total = supplier_invoice_spec_coverage(invoice_apply_spec)
                if covered_total + 0.01 < parsed_total:
                    missing_total = round(parsed_total - covered_total, 2)
                    print(f"{LOG_PREFIX} incomplete supplier invoice protocol: covered={covered_total} "
                          f"total={parsed_total}; retrying full-line extraction", file=sys.stderr)
                    corrective_reply = ask_fresh_document_model(text + (
                        "\n\n[ОБЯЗАТЕЛЬНАЯ ПРОВЕРКА ПОЛНОТЫ]\n"
                        f"Предыдущий разбор отразил строки только на {covered_total:.2f} руб. при итоге "
                        f"счёта {parsed_total:.2f} руб.; пропущено {missing_total:.2f} руб. "
                        "Повторно прочитай таблицу счёта целиком. В SUPPLIER_INVOICE_APPLY каждая строка "
                        "должна присутствовать ровно один раз: совпавшая — в updates, любая прочая — "
                        "в unallocated с source_line_key, name, source_sku, qty и amount. Нельзя описывать "
                        "нераспределённые строки только обычным текстом. Сумма source_total/amount всех "
                        "массивов должна точно совпасть с итогом счёта. Верни только исправленный протокол."
                    ))
                    _corrective_clean, corrective_spec = extract_supplier_invoice_apply(corrective_reply)
                    if corrective_spec and not corrective_spec.get("__invalid__"):
                        corrective_spec["deal_id"] = (corrective_spec.get("deal_id") or
                                                      invoice_apply_spec.get("deal_id"))
                        original_doc = invoice_apply_spec.get("invoice") or {}
                        corrected_doc = {**original_doc, **(corrective_spec.get("invoice") or {})}
                        # The first pass established the document identity and total.
                        # A corrective pass only repairs line arrays and must not turn
                        # the invoice into a different/partial document.
                        for field in ("supplier_inn", "buyer_inn", "number", "date", "total", "source_path"):
                            if original_doc.get(field) not in (None, ""):
                                corrected_doc[field] = original_doc[field]
                        corrective_spec["invoice"] = corrected_doc
                        corrected_coverage = supplier_invoice_spec_coverage(corrective_spec)
                        if corrected_coverage + 0.01 >= parsed_total:
                            invoice_apply_spec = corrective_spec
                        else:
                            print(f"{LOG_PREFIX} corrective invoice protocol still incomplete: "
                                  f"covered={corrected_coverage} total={parsed_total}", file=sys.stderr)
                            invoice_apply_spec["__incomplete__"] = {
                                "covered": corrected_coverage, "total": parsed_total}
                    else:
                        invoice_apply_spec["__incomplete__"] = {
                            "covered": covered_total, "total": parsed_total}
            if invoice_apply_spec is not None and invoice_apply_spec.get("__invalid__"):
                reply = (reply + "\n\n" if reply.strip() else "") + "Не удалось разобрать применение счёта поставщика (некорректный формат)."
            elif invoice_apply_spec is not None and invoice_apply_spec.get("__incomplete__"):
                incomplete = invoice_apply_spec["__incomplete__"]
                reply = ("Счёт прочитан не полностью: распознаны строки на "
                         f"{bank_money(incomplete.get('covered'))} ₽ из "
                         f"{bank_money(incomplete.get('total'))} ₽. Данные не записаны, чтобы не исказить "
                         "закупку. Попробуйте загрузить PDF ещё раз или загрузите этот счёт в Excel.")
                invoice_apply_spec = None
            else:
                repeat_status = run_procurement_workflow({"action": "invoice_allocation_status",
                                                           "invoice_spec": invoice_apply_spec})
                if repeat_status.get("ok"):
                    invoice_apply_spec = trim_previously_allocated_invoice_lines(
                        invoice_apply_spec, repeat_status)
                invoice_apply_spec = cap_invoice_allocation_to_deal(invoice_apply_spec)
                allocation_preview, preview_error = prepare_supplier_invoice_preview(
                    invoice_apply_spec, repeat_status)
                if preview_error:
                    reply = (reply + "\n\n" if reply.strip() else "") + (
                        "Не удалось подготовить распределение счёта: " +
                        preview_error)
                    invoice_apply_spec = None
                if invoice_apply_spec is not None:
                    invoice_apply_spec["_allocation_preview"] = allocation_preview
                    nearby_ids = refresh_nearby_procurement_snapshots(invoice_apply_spec.get("deal_id"), 10)
                    distribution = run_procurement_workflow({"action": "suggest_distribution",
                        "invoice_spec": invoice_apply_spec, "limit": 10,
                        "candidate_deal_ids": nearby_ids})
                    if distribution.get("ok"):
                        invoice_apply_spec["_distribution_plan"] = distribution
            if invoice_apply_spec is not None:
                if invoice_tasks.cancelled(chat_id, (invoice_apply_spec.get("invoice") or {}).get("source_path")):
                    os._exit(0)
                if invoice_task_mode and not request_is_current():
                    os._exit(0)
                queue_size = enqueue_supplier_invoice_preview(chat_id, invoice_apply_spec)
                if RUNTIME_ACTIVE and request_is_current():
                    invoice_apply_spec = current_deal_ui_state(chat_id).get('supplier_invoice_preview') or invoice_apply_spec
                doc = invoice_apply_spec.get("invoice") or {}
                updates = invoice_apply_spec.get("updates") or []
                additions = invoice_apply_spec.get("additions") or []
                amount = sum(float(x.get("material_cost_used") or 0) + float(x.get("work_cost_used") or 0) for x in updates)
                amount += sum(float(x.get("cost_material") or 0) * float(x.get("qty") or 0) for x in additions)
                amount += sum(float(x.get("amount") or 0) for x in invoice_apply_spec.get("additional_expenses") or [])
                ledger_names = {str(x.get("offer_id")): x.get("name") for x in (fetch_deal_ledger(invoice_apply_spec.get("deal_id")) or [])}
                mapping_lines = [
                    f"• {x.get('source_name') or x.get('source_sku') or x.get('source_line_key')} "
                    f"→ {ledger_names.get(str(x.get('offer_id'))) or 'позиция сделки'}: "
                    f"{float(x.get('qty_used') or 0):g} на {bank_money(float(x.get('material_cost_used') or 0) + float(x.get('work_cost_used') or 0))} ₽"
                    for x in updates
                ]
                unallocated_lines = [
                    f"• {x.get('name') or x.get('source_name') or x.get('source_line_key')}: "
                    f"{float(x.get('qty') or 0):g}, {bank_money(x.get('amount'))} ₽"
                    for x in invoice_apply_spec.get("unallocated") or []
                ]
                repeat = invoice_apply_spec.get("_repeat_invoice") or {}
                repeat_notice = ""
                if repeat.get("existing"):
                    repeat_notice += (f"\nРанее по этому счёту уже учтено: "
                                      f"{bank_money(repeat.get('allocated_total'))} ₽.\n")
                if float(repeat.get("skipped_amount") or 0) > 0:
                    repeat_notice += ("Повторно не записываю уже распределённые строки: "
                                      f"{bank_money(repeat.get('skipped_amount'))} ₽.\n")
                distribution = invoice_apply_spec.get("_distribution_plan") or {}
                suggestion_lines = [
                    f"• сделка №{x.get('deal_id')} — {float(x.get('qty') or 0):g} из необходимых "
                    f"{float(x.get('needed') or 0):g}: {x.get('target_name')}"
                    + (" ⚠️ подтвердите соответствие" if x.get("requires_confirmation") else "")
                    for x in distribution.get("suggestions") or []
                ]
                stock_lines = [
                    f"• {x.get('name')}: {float(x.get('qty') or 0):g} {x.get('unit') or ''}, "
                    f"{bank_money(x.get('amount'))} ₽"
                    for x in distribution.get("inventory_remainder") or []
                ]
                currency_plan = ""
                if str(doc.get("currency") or "RUB").upper() not in ("RUB", "RUR", ""):
                    currency_plan = (
                        f"Валюта счёта: {bank_money(doc.get('foreign_total'))} {doc.get('currency')}\n"
                        f"Плановый курс: {doc.get('cbr_rate'):,.6f} ₽ (ЦБ РФ на {doc.get('cbr_effective_date')}"
                        f"{(' + ' + str(doc.get('cbr_markup_pct')) + '%') if float(doc.get('cbr_markup_pct') or 0) else ''})\n"
                        f"Плановый эквивалент: {bank_money(doc.get('plan_total_rub'))} ₽\n"
                        "Факт будет заполнен только после оплаты и сопоставления с банковской выпиской.\n"
                    )
                reply = (reply + "\n\n" if reply.strip() else "") + (
                    f"Проверьте привязку перед записью:\n"
                    f"Поставщик: {doc.get('supplier') or 'не указан'}\n"
                    f"Покупатель: {doc.get('buyer') or 'не указан'}; "
                    f"ИНН: {doc.get('buyer_inn') or 'не указан'}\n"
                    f"Счёт №{doc.get('number') or 'не указан'} от {doc.get('date') or 'дата не указана'}\n"
                    f"Сделка №{invoice_apply_spec.get('deal_id')}\n"
                    f"Сопоставлено позиций: {len(updates)}, новых: {len(additions)}\n"
                    + currency_plan
                    + repeat_notice
                    + ("\nКак сопоставлено:\n" + "\n".join(mapping_lines) + "\n" if mapping_lines else "")
                    + ("\nОстанется нераспределено:\n" + "\n".join(unallocated_lines) + "\n" if unallocated_lines else "")
                    + ("\nПредлагаю распределить по соседним сделкам:\n" + "\n".join(suggestion_lines) + "\n"
                       if suggestion_lines else "")
                    + ("\nПосле предложенного распределения останется на внутреннем складе:\n" +
                       "\n".join(stock_lines) + "\n" if stock_lines else "")
                    + f"\nПлановая сумма к учёту: {bank_money(amount)} ₽\n\n"
                    f"Остаток счёта, ещё не отнесённый на сделки: "
                    f"{bank_money((invoice_apply_spec.get('_allocation_preview') or {}).get('remaining_after'))} ₽\n"
                    + ("Этот счёт уже зарегистрирован; будет добавлено только новое распределение.\n"
                       if (invoice_apply_spec.get("_allocation_preview") or {}).get("existing") else "") +
                    (("Данные ещё не записаны. Выберите распределение остатка кнопками ниже."
                      if invoice_apply_spec.get("unallocated") else
                      "Данные ещё не записаны. Нажмите «✅ Применить счёт поставщика».")) +
                    (f"\nВ очереди счетов: {queue_size}." if queue_size > 1 else "")
                )

        reply, resend_deal_id = extract_resend_deal_review(reply)
        profitability_xlsx_path = None
        if resend_deal_id:
            print(f"{LOG_PREFIX} deal review file re-requested for deal {resend_deal_id}")
            ledger = fetch_deal_ledger(resend_deal_id)
            if ledger is None:
                reply = (reply + "\n\n" if reply.strip() else "") + f"Не удалось прочитать позиции сделки {resend_deal_id} (техническая ошибка) - попробуйте ещё раз чуть позже."
            elif not ledger:
                reply = (reply + "\n\n" if reply.strip() else "") + f"В сделке {resend_deal_id} нет сохранённых позиций (либо она не создавалась через бота)."
            else:
                path = build_spec_review_xlsx(deal_client_name(resend_deal_id), ledger)
                if path:
                    spec_review_xlsx_path = path
                else:
                    reply = (reply + "\n\n" if reply.strip() else "") + "Не удалось собрать файл (техническая ошибка)."

        reply, profitability_deal_id = extract_profitability_request(reply)
        if profitability_deal_id:
            print(f"{LOG_PREFIX} profitability requested for deal {profitability_deal_id}")
            send_typing(token, chat_id)
            profit_result = build_and_store_profitability(profitability_deal_id)
            if profit_result.get("ok"):
                profitability_xlsx_path = profit_result["path"]
                reply = (reply + "\n\n" if reply.strip() else "") + format_profitability(profitability_deal_id, profit_result)
            else:
                reply = (reply + "\n\n" if reply.strip() else "") + f"Не удалось построить экономику: {profit_result.get('error', 'неизвестная ошибка')}"

        reply, work_statement_deal_id = extract_work_statement_request(reply)
        work_statement_xlsx_path = None
        if work_statement_deal_id:
            print(f"{LOG_PREFIX} work statement requested for deal {work_statement_deal_id}")
            send_typing(token, chat_id)
            ws_result = run_build_work_statement(work_statement_deal_id)
            if ws_result.get("ok"):
                work_statement_xlsx_path = ws_result["path"]
                total = ws_result.get("total_cost_work", 0)
                summary = f"Себестоимость работ по сделке {work_statement_deal_id}: {bank_money(total)} ₽ ({ws_result.get('position_count', 0)} позиций)."
                if ws_result.get("missing_count"):
                    summary += f"\n⚠️ Без данных о себестоимости работ: {', '.join(ws_result['missing_names'])}"
                else:
                    # Owner's rule (2026-08-25): the moment every position has a known
                    # labour cost, immediately ask for the markup that turns this total
                    # into "Монтажные работы"'s own sell price - don't make the owner
                    # ask separately.
                    summary += "\n\nВсе позиции посчитаны. Какую наценку заложить на эту себестоимость работ, чтобы сформировать стоимость позиции \"Монтажные работы\"?"
                reply = (reply + "\n\n" if reply.strip() else "") + summary
            else:
                reply = (reply + "\n\n" if reply.strip() else "") + f"Не удалось посчитать ведомость работ: {ws_result.get('error', 'неизвестная ошибка')}"

        reply, apply_ws_spec = extract_apply_work_statement(reply)
        if apply_ws_spec is not None:
            selected=current_deal_ui_state(chat_id).get('current_deal_id')
            if apply_ws_spec.get('__invalid__') or str(apply_ws_spec.get('deal_id')) != str(selected):
                reply='Сначала выберите сделку, для которой нужно изменить стоимость работ. Данные не записаны.'
            else:
                preview=run_apply_work_statement(selected,apply_ws_spec.get('markup_pct'),preview=True)
                if preview.get('ok'):
                    prepared={**preview,'markup_pct':apply_ws_spec['markup_pct']}
                    update_deal_ui_state(chat_id,pending='work_price_confirm',work_price_preview=prepared)
                    send_message(token,chat_id,f"Сделка №{selected}. Себестоимость работ: {bank_money(preview['total_cost_work'])} ₽. Наценка: {prepared['markup_pct']}%. Новая стоимость строки «Монтажные работы»: {bank_money(preview['montage_sell_price'])} ₽. Данные ещё не записаны.",
                        {'keyboard':[[{'text':'✅ Записать стоимость монтажных работ'}],[{'text':'❌ Отмена'}]]})
                    reply=''
                else: reply='Расчёт не подготовлен: '+str(preview.get('error'))

        reply, price_spec = extract_update_kemix_prices(reply)
        if price_spec is not None:
            if price_spec.get('__invalid__'):
                reply='Не удалось разобрать обновление прайса. Данные не записаны.'
            else:
                safe_spec={k:v for k,v in price_spec.items() if k in ('pipe_price_per_m','insulation_price_per_m','cable_price_per_m','cable_price_per_m_gost','not_found')}
                rows=[]
                for key,value in safe_spec.items():
                    if key=='not_found': continue
                    if isinstance(value,dict): rows.extend(f'{key} / {k}: {v} ₽/м' for k,v in value.items())
                    else: rows.append(f'{key}: {value} ₽/м')
                if not rows: reply='В прайсе нет распознанных цен. Данные не записаны.'
                else:
                    update_deal_ui_state(chat_id,pending='price_catalog_confirm',price_catalog_spec=safe_spec)
                    send_message(token,chat_id,'Обновить следующие цены внутреннего прайса?\n'+'\n'.join(rows),
                        {'keyboard':[[{'text':'✅ Обновить подтверждённый прайс'}],[{'text':'❌ Отмена'}]]})
                    reply=''

        reply, tax_choice_requested = extract_tax_choice_request(reply)
        clean_text, attachments = extract_attachments(reply)
        clean_text, image_urls = extract_image_urls(clean_text)
        clean_text = sanitize_service_protocol(clean_text)
        print(f"{LOG_PREFIX} replying: {clean_text[:200]!r} attachments={attachments} image_urls={image_urls} kp={kp_document_path}")
        if clean_text:
            reply_keyboard = TAX_KEYBOARD if tax_choice_requested else listed_deals_keyboard(clean_text)
            if invoice_apply_spec is not None and not invoice_apply_spec.get("__invalid__"):
                plan = invoice_apply_spec.get("_distribution_plan") or {}
                # Any unallocated source line requires an explicit manager
                # decision, even when there are no nearby deals or stock
                # suggestions.  Previously this branch showed only
                # "Применить счёт", hiding the ways to handle the remainder.
                reply_keyboard = (SUPPLIER_DISTRIBUTION_KEYBOARD
                                  if invoice_apply_spec.get("unallocated") or
                                     plan.get("suggestions") or plan.get("inventory_remainder")
                                  else SUPPLIER_INVOICE_CONFIRM_KEYBOARD)
            if catalog_task_mode:
                if not request_is_current():
                    os._exit(0)
                catalog_conversation.finish(chat_id, clean_text)
            if invoice_task_mode:
                if not request_is_current() or invoice_tasks.cancelled(chat_id, task_doc["path"]):
                    os._exit(0)
                invoice_tasks.history(chat_id, "assistant", clean_text, task_doc["sha256"])
            send_message(token, chat_id, clean_text, reply_keyboard)
        if document_job:
            # A preview is a durable checkpoint: the user can confirm or
            # edit it later.  Any other model outcome remains visible in
            # the queue instead of becoming a silent "processing" state.
            finish_document_job(
                document_job["id"],
                "preview_ready" if invoice_apply_spec is not None else "needs_retry",
                "" if invoice_apply_spec is not None else clean_text[:500],
            )
            update_deal_ui_state(chat_id, active_document_job_id=None)
        for path in attachments:
            send_document(token, chat_id, path)
        for url in image_urls:
            local_path = download_image_url(url)
            if local_path:
                send_photo(token, chat_id, local_path)
                try:
                    os.remove(local_path)
                except OSError:
                    pass
        if kp_document_path:
            send_document(token, chat_id, kp_document_path)
        if kp_xlsx_path:
            send_document(token, chat_id, kp_xlsx_path)
        if spec_review_xlsx_path:
            send_document(token, chat_id, spec_review_xlsx_path, "Проверьте цену и себестоимость (жёлтым — нужна сверка, красным — цена не найдена; см. столбец \"Требует подтверждения\" по каждой строке)")
            try:
                os.remove(spec_review_xlsx_path)
            except OSError:
                pass
        if work_statement_xlsx_path:
            send_document(token, chat_id, work_statement_xlsx_path, "Ведомость работ (красным — себестоимость работ не найдена ни в сделке, ни в каталоге, ни в тарифе)")
            try:
                os.remove(work_statement_xlsx_path)
            except OSError:
                pass
        if profitability_xlsx_path:
            send_document(token, chat_id, profitability_xlsx_path, "Расчёт рентабельности сделки")
            try:
                os.remove(profitability_xlsx_path)
            except OSError:
                pass
        model_lock.close()
        os._exit(0)


    # Do not flood a slow Megaplan immediately on every bridge restart.  Stage
    # watchers are advisory; user commands have priority.  Five-minute polling
    # is sufficient and leaves CRM capacity for interactive work.
    next_procurement_check = time.time() + 900
    next_transition_retry = time.time() + 300
    next_email_payment_check = 0
    next_publication_check = time.time() + 30
    next_closing_check = time.time() + 60
    next_qa_check = 0
    next_qa_autopilot_check = 0
    while True:
        UI_CONTEXT = None
        active_children=True
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            active_children=False
        safe_reload.apply_if_idle(RELOAD_REQUEST_FILE,__file__,active_children,
                                  lambda:os.execv(sys.executable,[sys.executable,__file__]))
        draining_reload=safe_reload.pending_reviewed(RELOAD_REQUEST_FILE,__file__)
        if not draining_reload:
            report_stale_reload(token, authorized_chat_id)
        if not draining_reload and time.time() >= next_qa_check:
            show_qa_findings(token, authorized_chat_id, only_unnotified=True)
            next_qa_check = time.time() + 60
        if not draining_reload and time.time() >= next_qa_autopilot_check:
            qa_plan = qa_schedule.load()
            if (qa_schedule.morning_brief_due(datetime.now(timezone.utc), qa_plan)
                    and periodic_schedule.claim_daily(os.path.join(BASE_DIR, 'watcher_schedule.json'),
                                                      'owner-morning-brief', 0)):
                run_singleton_background_job(
                    'owner-morning-brief',
                    lambda: send_morning_brief(token, authorized_chat_id,
                                               qa_schedule.morning_brief_config(qa_plan)),
                    token, authorized_chat_id,
                )
            # One night cycle per night: the explorer spends model calls.
            if (nightly_qa_window()
                    and periodic_schedule.claim(os.path.join(BASE_DIR, 'watcher_schedule.json'),
                                                'qa-night-autopilot', 20 * 3600)):
                run_singleton_background_job(
                    'qa-night-autopilot',
                    lambda: run_nightly_qa(token, authorized_chat_id),
                    token, authorized_chat_id,
                )
            if periodic_schedule.claim(os.path.join(BASE_DIR, 'watcher_schedule.json'), 'qa-human-autopilot',
                                       qa_schedule.human_interval_seconds(qa_plan)):
                run_singleton_background_job('qa-human-autopilot', lambda: run_qa_autopilot(token, authorized_chat_id, 'human'), token, authorized_chat_id)
            # Full offline gate once a day; it is isolated and never writes business data.
            if periodic_schedule.claim_daily(os.path.join(BASE_DIR, 'watcher_schedule.json'), 'qa-full-autopilot',
                                             qa_schedule.full_daily_utc_hour(qa_plan)):
                run_singleton_background_job('qa-full-autopilot', lambda: run_qa_autopilot(token, authorized_chat_id, 'full'), token, authorized_chat_id)
            # Tester → developer tasks committed to Git (handoff/inbox).
            handoff_minutes = int(qa_schedule.handoff_config(qa_plan).get('every_minutes') or 15)
            if periodic_schedule.claim(os.path.join(BASE_DIR, 'watcher_schedule.json'), 'qa-handoff', handoff_minutes * 60):
                run_singleton_background_job('qa-handoff', lambda: poll_handoff(token, authorized_chat_id),
                                             token, authorized_chat_id)
            # One concise owner digest per Moscow day, with the coming night's plan.
            if (qa_schedule.digest_due(datetime.now(timezone.utc), qa_plan)
                    and periodic_schedule.claim(os.path.join(BASE_DIR, 'watcher_schedule.json'), 'qa-owner-digest', 20 * 3600)):
                send_owner_digest(token, authorized_chat_id, qa_plan)
            next_qa_autopilot_check = time.time() + 60
        if not draining_reload and time.time() >= next_procurement_check:
            run_singleton_background_job(
                'proposal-status',
                lambda: check_external_proposal_transitions(token, authorized_chat_id),
                token, authorized_chat_id,
            )
            run_singleton_background_job(
                "procurement-status",
                lambda: check_external_procurement_transitions(token, authorized_chat_id),
                token, authorized_chat_id,
            )
            next_procurement_check = time.time() + 900
        if not draining_reload and time.time() >= next_closing_check:
            run_singleton_background_job(
                "closing-documents", closing_runtime.poll_in_document_environment, token, authorized_chat_id)
            run_singleton_background_job("product-matching", product_matching_runtime.poll, token, authorized_chat_id)
            run_singleton_background_job("procurement-intake", procurement_intake_runtime.poll_in_environment, token, authorized_chat_id)
            run_singleton_background_job("supplier-allocation", allocation_runtime.poll_in_environment, token, authorized_chat_id)
            next_closing_check = time.time() + 60
        if not draining_reload and time.time() >= next_transition_retry:
            if durable_json.read(PENDING_TRANSITIONS_FILE, dict):
                run_singleton_background_job(
                    "deal-transition-retry", lambda: retry_queued_deal_transitions(token),
                    token, authorized_chat_id,
                )
            next_transition_retry = time.time() + 300
        if not draining_reload and time.time() >= next_email_payment_check:
            run_singleton_background_job(
                "email-payments",
                lambda: poll_email_payments(token, authorized_chat_id),
                token, authorized_chat_id,
            )
            # Bank notifications are informational and the mailbox is not a
            # real-time channel.  Poll no more often than once per hour; manual
            # statement uploads remain immediate.
            next_email_payment_check = time.time() + 60 * 60
        if not draining_reload and time.time() >= next_publication_check:
            run_singleton_background_job('megaplan-protection-notice',
                lambda:notify_megaplan_protection(token,authorized_chat_id),token,authorized_chat_id)
            run_singleton_background_job('installation-handoff-notifications',
                lambda: deliver_installation_handoffs(token),token,authorized_chat_id)
            run_singleton_background_job('installation-publication',
                lambda: run_installation_workflow({'action':'retry_publications','limit':1}), token, authorized_chat_id)
            run_singleton_background_job('financial-archive',
                lambda: run_financial_archive({'action':'drain','limit':1}),token,authorized_chat_id)
            next_publication_check = time.time() + 30
        try:
            resp = tg_api(token, "getUpdates", {
                "offset": offset,
                "timeout": 15,
                "allowed_updates": json.dumps(["message", "callback_query"]),
            }, timeout=20)
        except Exception as e:
            print(f"{LOG_PREFIX} getUpdates failed: {e}", file=sys.stderr)
            time.sleep(5)
            continue

        import incoming_dispatch
        for update in incoming_dispatch.tracked(resp.get("result", []),WorkflowStore(WORKFLOW_DB_FILE)):
            # Durable inbox precedes Telegram acknowledgement. If the process
            # stops before routing, the original text/file reference is retained
            # for reconciliation; financial writes are never blindly replayed.
            offset = update["update_id"] + 1
            save_offset(offset)

            UI_CONTEXT = None
            import installer_onboarding
            linked_accounts=installer_onboarding.members()
            INSTALLER_CHAT_IDS.update(linked_accounts)
            try:
                onboarding_handled=installer_onboarding.handle(update,authorized_chat_id,
                    linked_accounts | {authorized_chat_id,str(INSTALLER_NOTIFY_CHAT_ID or ''),str(edo_chat_id or '')},
                    lambda method,args:tg_api(token,method,args,timeout=10),INSTALLER_USER_KEYBOARD)
            except Exception as exc:
                print(f'{LOG_PREFIX} onboarding delivery failed: {type(exc).__name__}',file=sys.stderr)
                continue
            if onboarding_handled:continue
            callback = update.get('callback_query')
            if callback:
                callback_chat = str(((callback.get('message') or {}).get('chat') or {}).get('id') or '')
                callback_user = str((callback.get('from') or {}).get('id') or '')
                data = str(callback.get('data') or '')
                if data.startswith('closing:'):
                    try:
                        closing_runtime.callback(callback)
                    except Exception as exc:
                        if callback_chat == edo_chat_id:
                            send_message(token, callback_chat, 'Не удалось обработать подтверждение: ' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
                    continue
                if not data.startswith('wf:') or callback_chat != callback_user:
                    try: tg_api(token, 'answerCallbackQuery', {'callback_query_id': callback['id'], 'text': 'Недоступное действие'}, timeout=2)
                    except Exception: pass
                    continue
                control = WorkflowStore(WORKFLOW_DB_FILE).take_control(callback_chat, data[3:])
                try:
                    tg_api(token, 'answerCallbackQuery', {'callback_query_id': callback['id'],
                        'text': 'Принято' if control.get('ok') else 'Эта кнопка уже использована или устарела. Откройте /menu.'}, timeout=2)
                except Exception:
                    pass
                if not control.get('ok'):
                    continue
                msg = {'chat': {'id': callback_chat}, 'from': callback.get('from') or {},
                       'message_id': 'callback:' + str(callback['id']), 'text': control['text'],
                       '_workflow_callback': True, '_view_id': control['view_id'], 'date': time.time()}
            else:
                msg = update.get("message")
            sender_chat = str(((msg or {}).get("chat") or {}).get("id") or "")
            if (msg and "voice" in msg and voice_intake.configured(env)
                    and (sender_chat == authorized_chat_id or sender_chat in linked_accounts)):
                # A dictated request becomes ordinary text (owner decision 23.10, OpenAI).
                transcript = transcribe_voice_message(token, sender_chat, msg, env)
                if not transcript:
                    continue
                msg = {**msg, "text": transcript, "_voice": True}
            if msg and not any(key in msg for key in ("text", "document", "photo", "video")):
                unsupported = next((label for key, label in UNSUPPORTED_MESSAGE_KINDS if key in msg), None)
                if unsupported and (sender_chat == authorized_chat_id or sender_chat in linked_accounts):
                    # A dictated request used to vanish without any answer.
                    send_message(token, sender_chat, f"{unsupported} бот пока не распознаёт, поручение не принято. "
                                 "Напишите его текстом или выберите действие кнопкой.", home_keyboard(sender_chat))
                continue
            if not msg:
                continue

            chat_id = str(msg["chat"]["id"])
            username = str((msg.get("from") or {}).get("username") or "").casefold()
            is_owner = chat_id == authorized_chat_id
            # Telegram usernames can change or be reassigned. The configured
            # stable account ID identifies the linked installer profile.
            is_installer = chat_id in linked_accounts or bool(INSTALLER_NOTIFY_CHAT_ID and chat_id == str(INSTALLER_NOTIFY_CHAT_ID))
            is_edo_recipient = bool((edo_chat_id and chat_id == edo_chat_id)
                                    or (edo_username and username == edo_username))

            if not is_owner and not is_installer and not is_edo_recipient:
                print(f"{LOG_PREFIX} ignored message from unauthorized chat_id={chat_id}, username={username!r}")
                continue
            if is_edo_recipient and chat_id == edo_chat_id and (msg.get("photo") or msg.get("document")):
                try:
                    if closing_runtime.screenshot(msg, lambda m: download_telegram_photo(token,m["photo"]) if m.get("photo") else download_telegram_document(token,m["document"])):
                        continue
                except Exception as exc:
                    send_message(token,chat_id,"Скриншот не принят: " + (str(exc) if isinstance(exc,ValueError) else "не удалось сохранить файл; повторите отправку"))
                    continue
            if is_edo_recipient and chat_id == edo_chat_id and msg.get("text"):
                try:
                    if closing_runtime.message(chat_id, msg["text"]):
                        continue
                except (ValueError, KeyError) as exc:
                    send_message(token, chat_id, "Подтверждение не принято: " + str(exc))
                    continue
            if is_edo_recipient and not is_owner and not is_installer:
                if chat_id != edo_chat_id:
                    with open(EDO_RECIPIENT_CHAT_FILE, "w", encoding="utf-8") as target:
                        target.write(chat_id)
                    os.chmod(EDO_RECIPIENT_CHAT_FILE, 0o600)
                    edo_chat_id = chat_id
                send_message(
                    token, chat_id,
                    "Татьяна, регистрация завершена. Сюда будут приходить договоры и счета, которые нужно отправить клиентам по ЭДО.",
                )
                continue
            received_at = time.monotonic()
            telegram_age = max(0, time.time() - float(msg.get("date") or time.time()))
            print(
                f"{LOG_PREFIX} update received: message_id={msg.get('message_id')} "
                f"chat={chat_id} telegram_age={telegram_age:.2f}s kind="
                f"{'text' if 'text' in msg else 'document' if 'document' in msg else 'photo' if 'photo' in msg else 'video'}"
            )
            if is_installer and not is_owner:
                INSTALLER_CHAT_IDS.add(chat_id)

            # A status question observes the running request; it must not advance
            # its UI revision, invalidate confirmation buttons or cancel a worker.
            if is_owner and handle_status_query(token,chat_id,msg.get('text')):
                continue

            # Owner clarification replies belong to their question, never to a
            # deal wizard or a separate developer session. No second getUpdates.
            if is_owner and ('reply_to_message' in msg or decision_channel.CODE.match(str(msg.get('text') or ''))):
                answer = decision_channel.consume(msg, authorized_chat_id, WorkflowStore(WORKFLOW_DB_FILE))
                if answer:
                    send_message(token, chat_id, f"Ответ по вопросу {answer['code']} сохранён. Он будет учтён при продолжении этого пункта плана.")
                    continue

            # Forked workers inherit a fixed snapshot. A later message advances
            # the revision and an older worker cannot replace its selected deal.
            UI_CONTEXT = ui_state_store().bind(chat_id, update['update_id'])
            if UI_CONTEXT is None:
                continue
            UI_CONTEXT.confirmed_control = bool(msg.get('_workflow_callback'))
            WorkflowStore(WORKFLOW_DB_FILE).invalidate_views(chat_id)
            if not msg.get('_workflow_callback') and str(msg.get('text') or '').startswith('✅ '):
                send_message(token, chat_id, 'Для подтверждения нажмите актуальную кнопку под сообщением бота. Старое текстовое подтверждение не применено.', home_keyboard(chat_id))
                continue

            if is_installer and not is_owner and any(k in msg for k in ('document','photo','video')):
                if not installer_media_allowed(msg,current_deal_ui_state(chat_id).get('pending')):
                    send_message(token,chat_id,'Для PDF по нескольким объектам выберите «📤 Сборный отчёт». Для фото, видео и отчёта одного объекта откройте «Мои монтажи» → объект → «Новый отчёт».',INSTALLER_USER_KEYBOARD)
                    continue

            if is_owner and handle_invoice_cancellation(token, chat_id, msg):
                continue

            direct_slow_command=any(pattern.match(str(msg.get('text') or '').strip()) for pattern in (INVOICE_CMD_RE,DEAL_CMD_RE,ECONOMICS_CMD_RE))
            human_route = human_intents.classify(msg.get('text') or '')
            human_pending = str(current_deal_ui_state(chat_id).get('pending') or '').startswith('human_')
            # Inline workflow buttons may launch CRM/report work too.  They were
            # acknowledged immediately by Telegram but then executed in the
            # polling process, freezing every subsequent click for 30–75 seconds.
            if (msg.get('_workflow_callback') or any(key in msg for key in ('document','photo','video'))
                    or direct_slow_command
                    or (human_route and human_route.name != human_intents.CREATE_DEAL)
                    or human_pending
                    or str(current_deal_ui_state(chat_id).get('pending') or '').startswith('payer_')):
                run_background_job(lambda: process_business_message(msg,chat_id,is_owner,is_installer), token,chat_id,
                                   operation='получение файла/плательщик', allow_stale=True)
            else:
                run_foreground(lambda: process_business_message(msg,chat_id,is_owner,is_installer))


if __name__ == "__main__":
    main()
