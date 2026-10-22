"""Bind a conversational invoice draft to a real, recent attachment.

This authorizes preparation of a preview only; the existing confirmation gate
still owns all CRM writes. Never trust a model-supplied filesystem path.
"""
import copy
import hashlib
import re
import time
from pathlib import Path


def remember(path, text, chat_id):
    return {'path': str(path), 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'text': text, 'chat_id': str(chat_id), 'received_at': time.time()}


def bind(spec, attachment, chat_id, now=None):
    if not isinstance(spec, dict) or not attachment:
        return None
    if attachment.get('chat_id') != str(chat_id):
        return None
    age = (time.time() if now is None else now) - attachment.get('received_at', 0)
    if not 0 <= age <= 86400:
        return None
    try:
        if hashlib.sha256(Path(attachment['path']).read_bytes()).hexdigest() != attachment['sha256']:
            return None
    except (OSError, KeyError):
        return None
    doc = spec.get('invoice') or {}
    text = attachment.get('text', '')
    number = str(doc.get('number') or '').strip()
    # The title must name this exact document, not an old invoice mentioned in chat.
    title = re.search(r'Сч[её]т(?:[-–—](?:оферта|договор))?\s+(?:на\s+оплату\s*)?№\s*([^\s]+)', text, re.I)
    if not title or not number or title.group(1).strip() != number:
        return None
    for field in ('supplier_inn', 'buyer_inn'):
        inn = str(doc.get(field) or '')
        if not re.fullmatch(r'\d{10}|\d{12}', inn) or not re.search(r'(?<!\d)' + inn + r'(?!\d)', text):
            return None
    if not str(spec.get('deal_id') or '').isdigit():
        return None
    bound = copy.deepcopy(spec)
    bound['invoice']['source_path'] = attachment['path']
    return bound


def context(attachment):
    if not attachment or time.time() - attachment.get('received_at', 0) > 86400:
        return ''
    return ('\n\n[ТЕКУЩИЙ СОХРАНЁННЫЙ ФАЙЛ — ПРОДОЛЖЕНИЕ ОБРАБОТКИ]\n'
            'Файл уже загружен. Не проси загружать его через другую кнопку. '
            'После выбора сделки подготовь SUPPLIER_INVOICE_APPLY для проверки. '
            'Это только проект распределения; не утверждай, что данные уже записаны. '
            'Не добавляй товары и не меняй продажные цены без указания пользователя.\n'
            + attachment['path'] + '\n' + attachment.get('text', ''))
