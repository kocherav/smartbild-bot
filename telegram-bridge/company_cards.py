"""Serve approved own-company cards without model generation or CRM writes."""
import hashlib
import json
import re
from pathlib import Path

CATALOG = Path(__file__).resolve().parent.parent / 'megaplan-crm' / 'own_companies.json'

def normalize(text):
    return ' '.join(re.findall(r'[а-яa-z0-9]+', str(text).casefold().replace('ё', 'е')))

def handle_request(text, is_owner, send_file, send_text, catalog=CATALOG):
    query = normalize(text)
    if not is_owner or not re.search(r'\b(карточк\w*|реквизит\w*)\b', query):
        return False
    if not re.search(r'\b(пришли|пришлите|отправь|отправьте|дай|покажи|карточка|реквизиты)\b', query):
        return False
    catalog = Path(catalog)
    companies = json.loads(catalog.read_text())['companies']
    matches = []
    for company in companies:
        aliases = [company.get('name',''), company.get('legal_name',''), company.get('inn','')] + company.get('aliases', [])
        if any(normalize(a) and (' '+normalize(a)+' ') in (' '+query+' ') for a in aliases):
            matches.append(company)
    if not matches:
        # Do not steal payer uploads or unrelated requests from other workflows.
        if not re.search(r'\b(нашу|наши|нашей)\b', query):
            return False
        matches = companies
    if len(matches) != 1:
        send_text('Уточните организацию: '+', '.join(c['name'] for c in matches)+'. Например: пришли карточку ИП Кочержинский.')
        return True
    company = matches[0]
    card = company.get('requisites_card') or {}
    if not card.get('path'):
        send_text('Для '+company['name']+' утверждённая карточка ещё не сохранена.')
        return True
    path = (catalog.parent / card['path']).resolve()
    if not path.is_relative_to(catalog.parent.resolve()) or not path.is_file():
        send_text('Файл карточки '+company['name']+' недоступен. Требуется восстановить сохранённый файл; после восстановления повторите запрос.')
        return True
    if hashlib.sha256(path.read_bytes()).hexdigest() != card.get('sha256'):
        send_text('Версия карточки '+company['name']+' не совпадает с утверждённой. Требуется восстановить утверждённый файл.')
        return True
    try:
        result = send_file(path, 'Реквизиты — '+company['name']+' · утверждённая карточка')
        if not result or (isinstance(result, dict) and not result.get('ok')):
            raise RuntimeError('delivery not confirmed')
    except Exception:
        send_text('Telegram не подтвердил отправку карточки. Повторите запрос «пришли карточку '+company['name']+'».')
    return True
