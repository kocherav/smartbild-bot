#!/usr/bin/env python3
"""Read bank payment notifications over IMAP without changing mailbox state."""
import email
import hashlib
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.header import decode_header, make_header
from html import unescape
from registry_transaction import transaction

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_ENV = os.path.expanduser("~/telegram-bridge/.env")
PROCUREMENT_REGISTRY = os.path.join(BASE_DIR, "procurement_registry.json")
REGISTRY = os.path.join(BASE_DIR, "email_payment_registry.json")


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path, value):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(tmp, path)


def load_env():
    result = {}
    for line in open(BRIDGE_ENV, encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.strip().split("=", 1); result[key] = value
    return result


def message_text(message):
    chunks = []
    for part in message.walk():
        if part.get_content_type() not in ("text/plain", "text/html"): continue
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        try: value = payload.decode(charset, "replace")
        except LookupError: value = payload.decode("utf-8", "replace")
        if part.get_content_type() == "text/html":
            value = re.sub(r"<[^>]+>", " ", value)
        chunks.append(unescape(value))
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()


def parse_notification(text):
    number = re.search(r"(?i)уведомление\s+о\s+платеже\s*№\s*([^\s]+)", text)
    date = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", text)
    amount = re.search(r"(?i)сумма\s+платежа\s*:.*?\(([\d\s]+[.,]\d{2})\s*RUR\)", text)
    purpose = re.search(r"(?i)назначение\s+платежа\s*:\s*(.+?)(?:плат[её]ж,\s*отправленный|с уважением|$)", text)
    payer = re.search(r"(?i)был\s+отправлен\s+плат[её]ж\s+от\s+(.+?)\s+сумма\s+платежа", text)
    recipient = re.search(r"(?i)в\s+адрес\s+организации\s+(.+?)\s+был\s+отправлен", text)
    if not all((number, date, amount, purpose)):
        raise ValueError("письмо не соответствует уведомлению о платеже Альфа-Банка")
    purpose_text = purpose.group(1).strip()
    invoice_part = re.search(r"(?i)сч[её]т(?:у|ам)?\s*№?\s*(.+?)(?:\s+от\s+\d|\s+к\s+договор|\.|$)", purpose_text)
    invoice_numbers = re.findall(r"[0-9A-Za-zА-Яа-яЁё/_-]+", invoice_part.group(1)) if invoice_part else []
    invoice_numbers = [x for x in invoice_numbers if re.search(r"\d", x)]
    return {"payment_number": number.group(1), "date": date.group(1),
            "amount": float(amount.group(1).replace(" ", "").replace(",", ".")),
            "purpose": purpose_text, "payer": payer.group(1).strip() if payer else "",
            "recipient": recipient.group(1).strip() if recipient else "",
            "invoice_numbers": invoice_numbers}


def match_invoices(payment):
    procurement = load_json(PROCUREMENT_REGISTRY, {"invoices": []})
    from own_companies import companies
    def supplier_name(value):
        value=str(value or '').casefold().replace('ё','е')
        for form in ('общество с ограниченной ответственностью','публичное акционерное общество','акционерное общество'):
            value=value.replace(form,' ')
        value=re.sub(r'\b(?:ооо|пао|ао|оао|зао)\b',' ',value)
        return re.sub(r'[^a-zа-я0-9]','',value)
    recipient=supplier_name(payment.get('recipient'))
    payer_candidates=[x for x in companies() if supplier_name(payment.get('payer')) in
                      {supplier_name(name) for name in [x.get('name'),*(x.get('aliases') or [])]}]
    payer=payer_candidates[0] if len(payer_candidates)==1 else None
    candidates=[x for x in procurement.get('invoices') or [] if str(x.get('number')) in payment['invoice_numbers']]
    matches=[x for x in candidates if payer and str(x.get('buyer_inn'))==str(payer.get('inn'))
             and recipient and supplier_name(x.get('supplier'))==recipient]
    found = {str(x.get("number")) for x in matches}
    missing = [x for x in payment["invoice_numbers"] if x not in found]
    total = round(sum(float(x.get("total") or 0) for x in matches), 2)
    deal_ids = sorted({str(a.get("deal_id")) for x in matches for a in x.get("allocations") or []})
    exact = bool(matches and len(found)==len(matches) and not missing and abs(total - payment["amount"]) <= .01 and len(deal_ids) == 1)
    return {"exact": exact, "missing": missing, "matched_total": total, "deal_ids": deal_ids,
            "invoices": [{"id": x.get("id"), "number": x.get("number"), "total": x.get("total"),
                          "supplier": x.get("supplier"), "supplier_inn": x.get("supplier_inn"),
                          "buyer": x.get("buyer"), "buyer_inn": x.get("buyer_inn")} for x in matches]}


@transaction(lambda:REGISTRY)
def poll():
    env = load_env(); host = env.get("IMAP_HOST") or "imap.yandex.ru"
    port = int(env.get("IMAP_PORT") or 993); user = env.get("IMAP_USERNAME") or env["SMTP_USERNAME"]
    password = env.get("IMAP_PASSWORD") or env["SMTP_PASSWORD"]
    state = load_json(REGISTRY, {"messages": [], "candidates": []})
    known = {x.get("message_id") for x in state["messages"]}
    box = imaplib.IMAP4_SSL(host, port); box.login(user, password); box.select("INBOX", readonly=True)
    # IMAP SEARCH is ASCII unless UTF8=ACCEPT is negotiated; Yandex rejects a
    # Cyrillic SUBJECT literal here. Filter the trusted sender on the server and
    # validate the Russian subject/body locally.
    _, data = box.search(None, 'FROM "payment@alfa-bank.info"')
    created = []
    for uid in (data[0].split() if data and data[0] else [])[-100:]:
        _, raw_data = box.fetch(uid, "(BODY.PEEK[])")
        raw = next((x[1] for x in raw_data if isinstance(x, tuple)), b"")
        message = email.message_from_bytes(raw)
        subject = str(make_header(decode_header(message.get("Subject", ""))))
        if "уведомление о платеже" not in subject.casefold():
            continue
        message_id = message.get("Message-ID") or hashlib.sha256(raw).hexdigest()
        if message_id in known: continue
        record = {"message_id": message_id, "uid": uid.decode(), "received_at": datetime.now(timezone.utc).isoformat()}
        try:
            payment = parse_notification(message_text(message)); match = match_invoices(payment)
            candidate_id = hashlib.sha256(message_id.encode()).hexdigest()[:20]
            candidate = {"id": candidate_id, **payment, **match, "status": "pending",
                         "message_id": message_id, "created_at": record["received_at"]}
            state["candidates"].append(candidate); created.append(candidate); record["candidate_id"] = candidate_id
        except Exception as exc:
            record["error"] = str(exc)
        state["messages"].append(record); known.add(message_id)
    box.logout(); save_json(REGISTRY, state)
    return {"ok": True, "created": created}


@transaction(lambda:REGISTRY)
def update_status(candidate_id, status, result=None):
    state = load_json(REGISTRY, {"messages": [], "candidates": []})
    row = next((x for x in state["candidates"] if x.get("id") == candidate_id), None)
    if not row: raise ValueError("уведомление не найдено")
    row["status"] = status; row["result"] = result or {}; row["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_json(REGISTRY, state); return row


def list_candidates(offset=0):
    rows=[x for x in load_json(REGISTRY,{'candidates':[]})['candidates'] if x.get('status') in ('pending','postponed')]
    rows.sort(key=lambda x:x.get('created_at') or '',reverse=True)
    offset=max(0,int(offset or 0));limit=10
    return {'ok':True,'candidates':rows[offset:offset+limit],'total':len(rows),'offset':offset,'has_more':offset+limit<len(rows)}


def main():
    request = json.load(sys.stdin); action = request.get("action")
    if action == "poll": result = poll()
    elif action == 'list':result=list_candidates(request.get('offset',0))
    elif action == "get":
        row = next((x for x in load_json(REGISTRY, {"candidates": []})["candidates"] if x.get("id") == request.get("id")), None)
        result = {"ok": bool(row), "candidate": row, "error": None if row else "не найдено"}
    elif action == "status": result = {"ok": True, "candidate": update_status(request["id"], request["status"], request.get("result"))}
    else: result = {"ok": False, "error": "неизвестное действие"}
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)); raise SystemExit(1)
