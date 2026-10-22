#!/usr/bin/env python3
"""Client-only proposal from live CRM amounts. No supplier APIs or deal creation.

Run under .report-venv; stdin {action: publish|scan|ack, deal_id: ...}.
The per-deal lock serializes manual generation and status-triggered generation.
"""
import fcntl
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from megaplan_api import MegaplanAPI, MegaplanAPIError

ROOT = Path(__file__).resolve().parent / 'deal_proposals'
LETTERHEAD = Path('/home/kocher.av/sites/cliwell/pack/04-print/blank-a4-2026-letterhead.pdf')
STAGE = 'коммерческое предложение'
STAGE_ID = '131'  # Verified from live program 16 transitions, 2026-09-29.
CENT = Decimal('0.01')
RENDER_VERSION = 4


def dec(value):
    n = Decimal(str(value))
    if not n.is_finite():
        raise ValueError('Некорректная сумма или количество в сделке')
    return n


def money(value):
    if not isinstance(value, dict) or value.get('value') is None:
        raise ValueError('В сделке отсутствует подтверждённая сумма')
    if value.get('currency') != 'RUB':
        raise ValueError('КП требует фиксированных рублёвых цен; валютные позиции не пересчитываю')
    return dec(value['value']).quantize(CENT, rounding=ROUND_HALF_UP)


def num(n, precision=2):
    value = dec(n).quantize(Decimal(10) ** -precision, rounding=ROUND_HALF_UP)
    return f'{value:,.{precision}f}'.replace(',', ' ').replace('.', ',')


def snapshot(deal, units=None, taxes=None):
    """Whitelist public fields. row.sum already includes the CRM discount."""
    units, taxes = units or {}, taxes or {}
    rows = []
    for row in deal.get('positions') or []:
        offer = row.get('offer') or {}
        qty = dec(row.get('quantity'))
        if qty <= 0 or not offer.get('name'):
            raise ValueError('В спецификации есть пустое название или неположительное количество')
        total = money(row.get('sum'))
        if total < 0:
            raise ValueError('В спецификации отрицательная сумма')
        unit = row.get('unit') or offer.get('unit') or {}
        tax = row.get('tax') or {}
        rate = tax.get('rate', taxes.get(str(tax.get('id'))))
        if rate is None:
            raise ValueError('Не удалось определить НДС позиции')
        from generate_contract import classify_position
        section = 'Работы и логистика' if classify_position(row) == 'work' else 'Оборудование и материалы'
        rows.append({'name': str(offer['name']), 'qty': str(qty), 'section': section,
                     'unit': unit.get('name') or units.get(str(unit.get('id'))) or 'шт.',
                     'total': str(total), 'tax_rate': str(rate)})
    if not rows:
        raise ValueError('В сделке нет позиций для КП')
    total = money(deal.get('price'))
    if sum(dec(r['total']) for r in rows) != total:
        raise ValueError('Суммы позиций не совпадают с итогом сделки. КП не сформировано')
    client = (deal.get('contractor') or {}).get('name')
    if not client:
        raise ValueError('В сделке не указан клиент')
    return {'deal_id': str(deal['id']), 'client': str(client),
            'subject': str(deal.get('Category1000068CustomFieldPredmetDogovora') or deal.get('description') or ''),
            'rows': rows, 'total': str(total)}


def render(data, path):
    from weasyprint import HTML
    from pypdf import PdfReader, PdfWriter
    esc = html.escape
    recipient = str(data.get('recipient') or '').strip()
    if not recipient:
        raise ValueError('Укажите, кому адресовать КП')
    greeting = recipient if re.match(r'(?i)^(уважаем|добрый|доброе|здравствуйте)', recipient) else f'Добрый день, {recipient.rstrip(".,!")}!'
    rows = []
    for i, r in enumerate(data['rows'], 1):
        qty = dec(r['qty'])
        price = dec(r['total']) / qty
        # Do not turn 1260.544 × 200 into 1260.54 × 200. Show sufficient
        # precision; the authoritative line amount is never recomputed here.
        precision = 2
        while precision < 8 and (price.quantize(Decimal(10) ** -precision, rounding=ROUND_HALF_UP) * qty).quantize(CENT, rounding=ROUND_HALF_UP) != dec(r['total']):
            precision += 1
        if (price.quantize(Decimal(10) ** -precision, rounding=ROUND_HALF_UP) * qty).quantize(CENT, rounding=ROUND_HALF_UP) != dec(r['total']):
            raise ValueError('Нельзя отобразить цену за единицу без расхождения с суммой строки')
        quantity_text = format(qty, 'f')
        if '.' in quantity_text:
            quantity_text = quantity_text.rstrip('0').rstrip('.')
        section = 'Работы' if r.get('section') == 'Работы и логистика' else 'Материалы'
        rows.append(f'<tr><td>{i}</td><td>{section}</td><td>{esc(r["name"])}</td><td>{esc(r["unit"])}</td><td class="num">{quantity_text.replace(".", ",")}</td><td class="num">{num(price, precision)}</td><td class="num">{num(r["total"])}</td></tr>')
    rates = {r['tax_rate'] for r in data['rows']}
    from document_tax_policy import vat
    tax_total=sum((vat(r['total'],r['tax_rate']) for r in data['rows']),Decimal('0'))
    tax_note = 'Без НДС.' if rates == {'-1'} else 'В том числе НДС '+', '.join(sorted(r+'%' for r in rates if r!='-1'))+': '+num(tax_total)+' ₽.'+(' Часть позиций без НДС.' if '-1' in rates else '')
    categories = [(label, sum(dec(r['total']) for r in data['rows'] if r.get('section', 'Оборудование и материалы') == label))
                  for label in ('Оборудование и материалы', 'Работы и логистика')]
    subtotals = ''.join(f'<div class="summary-row"><span>{esc(label)}</span><span>{num(value)} руб.</span></div>' for label, value in categories if value)
    work_rows = [r for r in data['rows'] if r.get('section') == 'Работы и логистика']
    highlights = work_rows or data['rows']
    bullets = ''.join(f'<li>{esc(r["name"][:135])}{"…" if len(r["name"]) > 135 else ""}</li>' for r in highlights[:6])
    source = f'''<html lang="ru"><meta charset="utf-8"><style>
      @page {{size:A4; margin:34mm 18mm 24mm; @top-right {{content:"стр. " counter(page);font-size:7pt;color:#70818b;}}}}
      @page:first {{margin:50mm 18mm 42mm; @top-right {{content:none;}}}}
      body {{font-family:"DejaVu Sans";font-size:9pt;color:#203b46;}}
      h1 {{font-size:14pt;margin:0;}} h2 {{font-size:11pt;}} p {{line-height:1.5;}}
      .heading {{display:flex;justify-content:space-between;align-items:center;margin-bottom:11mm;}}
      .number {{font-size:8pt;color:#70818b;}}
      .greeting {{font-size:11pt;margin-bottom:7mm;}}
      .intro {{margin-bottom:8mm;}}
      ul {{padding-left:5mm;margin-bottom:7mm;}} li {{padding-left:1mm;line-height:1.4;margin-bottom:2mm;}}
      li::marker {{color:#25bad4;}}
      .summary {{background:#eaf7fa;border-radius:9pt;padding:5mm 6mm;margin-top:8mm;break-inside:avoid;}}
      .summary-row {{display:flex;justify-content:space-between;padding:2mm 0;}}
      .grand {{border-top:0.7pt solid #25bad4;font-size:13pt;font-weight:bold;margin-top:2mm;padding-top:3mm;}}
      .note {{font-size:7.5pt;color:#70818b;margin-top:3mm;}}
      .sign {{margin-top:7mm;font-size:9pt;line-height:1.8;}}
      .detail {{break-before:page;}}
      table {{width:100%;border-collapse:collapse;font-size:7.3pt;}}
      thead {{display:table-header-group;}} tr {{break-inside:avoid;}}
      th,td {{border-bottom:0.4pt solid #d9e5e9;padding:4pt;vertical-align:top;}}
      th {{background:#eaf7fa;color:#203b46;}} .num {{text-align:right;white-space:nowrap;}}
      .total {{font-size:12pt;text-align:right;break-inside:avoid;background:#eaf7fa;padding:5mm;}}
    </style><body>
    <div class="heading"><h1>Коммерческое предложение</h1><span class="number">№ КП-{esc(data['deal_id'])} от {esc(data['date'])}</span></div>
    <p class="greeting">{esc(greeting)}</p>
    <p class="intro">Направляем коммерческое предложение по проекту «{esc(' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', data['subject'])).split())[:300] or data['client'])}».</p>
    <h2>{'Основные работы' if work_rows else 'Состав предложения'}</h2><ul>{bullets}</ul>
    <div class="summary">{subtotals}<div class="summary-row grand"><span>Итого к оплате</span><span>{num(data['total'])} руб.</span></div></div>
    <p class="note">{tax_note} Полный перечень позиций и детальный расчёт приведены на следующих страницах.</p>
    <div class="sign">С уважением,<br><br><b>Генеральный директор ООО «КЛИВЭЛ»</b><br>Кочержинская С.В.</div>
    <section class="detail"><h2>Детальный расчёт</h2>
    <p class="note">{esc(data['client'])} · КП-{esc(data['deal_id'])} от {esc(data['date'])}</p>
    <table><thead><tr><th>№</th><th>Раздел</th><th>Наименование</th><th>Ед.</th><th>Кол-во</th><th>Цена, руб.</th><th>Сумма, руб.</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    <p class="total"><b>ИТОГО К ОПЛАТЕ: {num(data['total'])} руб.</b><br>{tax_note}</p></section></body></html>'''
    content = PdfReader(__import__('io').BytesIO(HTML(string=source).write_pdf()))
    writer = PdfWriter()
    for i, page in enumerate(content.pages):
        # A fresh reader per page is essential: PdfWriter caches indirect source
        # references and otherwise repeats page 2 for every continuation page.
        background = PdfReader(str(LETTERHEAD))
        target = background.pages[min(i, len(background.pages) - 1)]
        target.merge_page(page)
        writer.add_page(target)
    with open(path, 'wb') as f:
        writer.write(f)
    text = ' '.join(p.extract_text() for p in PdfReader(str(path)).pages)
    if num(data['total']) not in text:
        raise ValueError('Не пройдена проверка итоговой суммы в готовом PDF')


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {} if default is None else default


def save(path, data):
    tmp = path.with_suffix(f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def publish(deal_id, api=None, recipient=None):
    recipient = ' '.join(str(recipient or '').split())
    if not recipient or len(recipient) > 200:
        raise ValueError('Укажите, кому адресовать КП (до 200 символов)')
    if not str(deal_id).isdigit():
        raise ValueError('Некорректный номер сделки')
    api = api or MegaplanAPI()
    folder = ROOT / str(deal_id)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / 'lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        deal = api._call('GET', f'/deal/{deal_id}')['data']
        from document_tax_policy import settings,require_document_tax
        if settings().get('companies'):require_document_tax(deal,api)
        units = {str(x['id']): x['name'] for x in api._call('GET', '/unit')['data']}
        taxes = {str(x['id']): x['rate'] for x in api._call('GET', '/tax')['data']}
        data = snapshot(deal, units, taxes)
        data['date'] = datetime.now(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y')
        data['recipient'] = recipient
        data['letterhead_sha256'] = hashlib.sha256(LETTERHEAD.read_bytes()).hexdigest()
        data['render_version'] = RENDER_VERSION
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        stored = read(folder / 'published.json')
        if stored.get('fingerprint') == fingerprint and Path(stored.get('path', '')).is_file():
            verify_attachment(api, deal_id, stored['file_id'])
            return {**stored, 'reused': True}
        safe_client = re.sub(r'[^\w .-]', '_', data['client'])[:65]
        path = folder / f'КП КЛИВЭЛ — сделка {deal_id} — {safe_client} — {fingerprint[:8]}.pdf'
        render(data, path)
        # Refuse to attach a file built from a concurrently changed specification.
        live = snapshot(api._call('GET', f'/deal/{deal_id}')['data'], units, taxes)
        if live != {k: v for k, v in data.items() if k not in ('date', 'letterhead_sha256', 'render_version', 'recipient')}:
            raise ValueError('Сделка изменилась во время подготовки КП. Повторите формирование')
        receipt_path = folder / 'pending-upload.json'
        receipt = read(receipt_path)
        if receipt.get('fingerprint') == fingerprint and receipt.get('file_id'):
            uploaded = {'id': receipt['file_id']}
        else:
            uploaded = api.upload_file(str(path))
            save(receipt_path, {'fingerprint': fingerprint, 'file_id': str(uploaded['id'])})
        payload = {'contentType': 'Comment', 'subject': {'contentType': 'Deal', 'id': str(deal_id)},
                   'content': f'КП КЛИВЭЛ по актуальной спецификации сделки. Версия {fingerprint[:12]}.',
                   'attaches': [{'contentType': 'File', 'id': str(uploaded['id'])}]}
        # Preserve previous published versions. Updating an old comment may be
        # forbidden even when adding a comment is allowed; that 403 also trips
        # the shared transport breaker, so a fallback cannot safely run.
        comment = api._call('POST', f'/deal/{deal_id}/comments', json_body=payload)['data']
        result = {'ok': True, 'deal_id': str(deal_id), 'path': str(path), 'total': data['total'],
                  'count': len(data['rows']), 'fingerprint': fingerprint, 'file_id': str(uploaded['id']),
                  'comment_id': str(comment['id'])}
        save(folder / 'published.json', result)
        save(folder / f'{fingerprint}.json', data)
        verify_attachment(api, deal_id, result['file_id'])
        return result


def verify_attachment(api, deal_id, file_id):
    files = api._call('GET', f'/deal/{deal_id}/allFiles', params={'limit': 100}).get('data') or []
    if str(file_id) not in {str(f.get('id')) for f in files}:
        raise ValueError('PDF подготовлен, но Мегаплан пока не подтвердил вложение в сделке. Повторите получение КП')


def scan(api=None):
    """Use the shared 5-minute CRM cache. Bootstrap never publishes old deals."""
    from deal_browser import fetch_all
    api = api or MegaplanAPI()
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / 'transitions.json'
    with open(ROOT / 'scan.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = read(path)
        deals = fetch_all(api)
        stages = {str(d['id']): (STAGE if str((d.get('state') or {}).get('id')) == STAGE_ID else str((d.get('state') or {}).get('name') or '').casefold().strip()) for d in deals}
        pending = dict(old.get('pending') or {})
        if old:
            for deal_id, stage in stages.items():
                if stage == STAGE and old.get('stages', {}).get(deal_id) != STAGE:
                    pending[deal_id] = True
        work_ids = list(pending)[:3]
        rotated = dict(pending)
        for deal_id in work_ids:
            rotated[deal_id] = rotated.pop(deal_id)
        save(path, {**old, 'stages': stages, 'pending': rotated})
    result = []
    for deal_id in work_ids:
        try:
            live = api._call('GET', f'/deal/{deal_id}')['data']
            event = str((live.get('stateTimeUpdated') or {}).get('value') or '')
            if str((live.get('state') or {}).get('id')) != STAGE_ID:
                ack(deal_id)
                continue
            if event and old.get('completed_events', {}).get(deal_id) == event:
                ack(deal_id)
                continue
            # Never reuse an addressee from another document or guess a contact.
            # The owner must supply the recipient before PDF generation.
            result.append({'ok': True, 'deal_id': deal_id, 'event': event, 'needs_recipient': True})
        except Exception:
            # Keep pending for retry, but don't expose API traces or credentials.
            first_error = pending[deal_id] != 'error_reported'
            if first_error:
                with open(ROOT / 'scan.lock', 'w') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    state = read(path)
                    if deal_id in state.get('pending', {}):
                        state['pending'][deal_id] = 'error_reported'
                        save(path, state)
            result.append({'ok': False, 'deal_id': deal_id, 'notify': first_error,
                           'error': 'КП не сформировано; повторная попытка при следующей проверке'})
    return {'ok': True, 'results': result}


def ack(deal_id, event=None, enqueue=False):
    ROOT.mkdir(parents=True, exist_ok=True)
    with open(ROOT / 'scan.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = ROOT / 'transitions.json'
        data = read(path)
        if enqueue:
            data.setdefault('pending', {})[str(deal_id)] = True
        else:
            data.setdefault('pending', {}).pop(str(deal_id), None)
            if event:
                data.setdefault('completed_events', {})[str(deal_id)] = event
        save(path, data)
    return {'ok': True}


if __name__ == '__main__':
    try:
        spec = json.load(sys.stdin)
        action = spec.get('action', 'publish')
        if action == 'scan':
            result = scan()
        elif action in ('ack', 'enqueue'):
            result = ack(spec['deal_id'], spec.get('event'), enqueue=action == 'enqueue')
        else:
            result = publish(spec['deal_id'], recipient=spec.get('recipient'))
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        # Keep diagnostics useful without sending CRM trace blobs or secrets to chat.
        print(f'deal_proposal failed: {type(exc).__name__}; HTTP {getattr(exc, "status", "n/a")}', file=sys.stderr)
        message = str(exc) if isinstance(exc, ValueError) else 'Не удалось получить данные или сохранить КП в Мегаплане'
        print(json.dumps({'ok': False, 'error': message}, ensure_ascii=False))
        sys.exit(1)
