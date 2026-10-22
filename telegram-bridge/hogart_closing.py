"""Fetch verified Trio Climate closing originals before composing accountant hints.

No financial entries. CRM, archive and registry are separate resumable effects.
"""
import hashlib
import re
import sys
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'hogart-scraper'))
sys.path.insert(0, str(ROOT / 'megaplan-crm'))


def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'))


class DocumentList(list):
    warning = ''


def documents(api):
    result, seen = [], set()
    for page in range(1, 101):
        response = api._call('GET', '/document', params={'page': page})
        meta = response.get('meta', {})
        items = response.get('items')
        if not isinstance(items, list) or int(meta.get('currentPage', 0)) != page:
            raise ValueError('Хогарт: не подтверждена страница документов')
        for item in items:
            if item['id'] in seen:
                raise ValueError('Хогарт: повтор страницы документов')
            seen.add(item['id']); result.append(item)
        if page == int(meta.get('pageCount', 0)):
            result = DocumentList(result)
            if len(result) != int(meta.get('totalCount', -1)):
                result.warning = f"Хогарт: прочитаны все {page} страницы, но API сообщает {meta.get('totalCount')} документов и возвращает {len(result)}. Найденные оригиналы сверены отдельно; отсутствие других документов этим списком не подтверждено."
            return result
    raise ValueError('Хогарт: превышен предел страниц документов')


def candidates(invoice, docs):
    date = datetime.strptime(invoice['date'], '%d.%m.%Y').strftime('%Y-%m-%d')
    matched = [d for d in docs if str(d.get('type', {}).get('id')) == '1'
               and str(d.get('number')) == str(invoice['number'])
               and d.get('docDate') == date
               and d.get('legalEntity', {}).get('inn') == invoice.get('buyer_inn')
               and money(d.get('documentItemsTotalPrice', 0)) == money(invoice['total'])]
    if len(matched) != 1:
        raise ValueError('счёт не найден однозначно по номеру, дате, покупателю и сумме')
    order = matched[0].get('orderId')
    if not order:
        raise ValueError('нет связи счёта с заказом Хогарт')
    closing = [d for d in docs if d.get('orderId') == order
               and str(d.get('type', {}).get('id')) == '2'
               and d.get('legalEntity', {}).get('inn') == invoice['buyer_inn']]
    if len(closing) != 1 or money(closing[0].get('documentItemsTotalPrice', 0)) != money(invoice['total']):
        raise ValueError('полный УПД не найден однозначно; частичные/несколько УПД требуют сверки')
    return closing[0]


def validate_text(text, invoice, doc):
    normalized = re.sub(r'\s+', ' ', text)
    for label, inn in [('продавца', invoice['supplier_inn']), ('покупателя', invoice['buyer_inn'])]:
        if not re.search(r'ИНН/КПП ' + label + r':\s*' + re.escape(inn) + r'/', normalized, re.I):
            raise ValueError('УПД: не подтверждён ИНН ' + label)
    if not re.search(r'Счет-фактура №\s*' + re.escape(doc['number']) + r'\s+от', normalized):
        raise ValueError('УПД: номер PDF отличается от карточки')
    if not re.search(r'Основание передачи.*?Сч[её]т №\s*' + re.escape(str(invoice['number'])) + r'\s+от', normalized):
        raise ValueError('УПД: не подтверждено основание — нужный счёт')
    day, month, year = invoice['date'].split('.')
    months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
    basis = re.search(r'Основание передачи.*?Сч[её]т №\s*' + re.escape(str(invoice['number'])) + r'\s+от\s+(.*)', normalized)
    if not basis or not re.match(r'0?' + str(int(day)) + r'\s+' + months[int(month)-1] + r'\s+' + year + r'\b', basis[1]):
        raise ValueError('УПД: дата исходного счёта не совпадает')
    totals = re.findall(r'Всего к оплате \(9\)(.*?)(?:Документ|Руководитель)', normalized)
    amounts = re.findall(r'\d[\d ]*,\d{2}', totals[0]) if len(totals) == 1 else []
    if not amounts or money(amounts[-1].replace(' ', '').replace(',', '.')) != money(invoice['total']):
        raise ValueError('УПД: не подтверждён итог PDF')


def fetch(doc, invoice, folder):
    url = doc.get('fileUrl', '')
    if not url.startswith('https://admin.b2b.hogart.ru/file/download?'):
        raise ValueError('Хогарт: неподдерживаемый адрес оригинала')
    with urllib.request.urlopen(url, timeout=40) as response:
        if not response.geturl().startswith('https://admin.b2b.hogart.ru/'):
            raise ValueError('Хогарт: неожиданный адрес скачивания')
        data = response.read(20 * 1024 * 1024 + 1)
    if not data.startswith(b'%PDF') or len(data) > 20 * 1024 * 1024:
        raise ValueError('Хогарт: оригинал не PDF или превышает 20 МБ')
    import fitz
    with fitz.open(stream=data, filetype='pdf') as pdf:
        text = '\n'.join(page.get_text(sort=True) for page in pdf)
    validate_text(text, invoice, doc)
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    name = re.sub(r'[^\w.-]', '_', doc['number'])
    path = folder / ('УПД ' + name + ' — Трио Климат.pdf')
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def sync(deal_id, folder, crm, effect, publish=True):
    from hogart_api import HogartAPI
    from procurement_workflow import supplier_invoices_for_deal, record_closing_document
    from financial_archive import archive_document
    invoices = [i for i in supplier_invoices_for_deal(deal_id)
                if i.get('supplier_inn') == '7717632694' and not i.get('closing_documents')]
    if not invoices:
        return []
    try:
        docs = documents(HogartAPI())
    except Exception:
        return ['Хогарт: проверка закрывающих документов недоступна; требуется повторная проверка сопровождающим ассистентом перед выпуском исправленного комплекта.']
    messages = [docs.warning] if getattr(docs, 'warning', '') else []
    for invoice in invoices:
        prefix = 'Хогарт, счёт №' + str(invoice['number']) + ': '
        stage = 'поиск и сверка оригинала'
        try:
            doc = candidates(invoice, docs)
            path, sha = fetch(doc, invoice, folder)
            if not publish:
                messages.append(prefix + 'найден и проверен УПД ' + doc['number'] + '; тестовая проверка без записи в CRM и архив.')
                continue
            key = 'hogart-' + str(doc['id']) + '-' + sha[:16]
            stage = 'загрузка файла в CRM'
            f = effect(key + '-upload', lambda: {'ok': True, 'file': crm.upload_file(str(path))})['file']
            def attach():
                comment = crm._call('POST', f'/deal/{deal_id}/comments', json_body={
                    'contentType': 'Comment', 'subject': {'contentType': 'Deal', 'id': str(deal_id)},
                    'content': 'Оригинал УПД из личного кабинета Хогарт; счёт №' + str(invoice['number']),
                    'attaches': [{'contentType': 'File', 'id': f['id']}]})['data']
                if not comment.get('id'):
                    raise ValueError('Мегаплан не подтвердил прикрепление УПД')
                return {'ok': True, 'file_id': f['id'], 'comment_id': comment['id']}
            stage = 'прикрепление в сделку CRM'
            effect(key + '-crm', attach)
            stage = 'сохранение в OneDrive'
            effect(key + '-archive', lambda: archive_document(deal_id, str(path), 'supplier_closing', document_number=doc['number'], api=crm))
            stage = 'регистрация закрывающего документа'
            record_closing_document(deal_id, invoice['id'], path.name, sha, 'УПД')
            messages.append(prefix + 'УПД ' + doc['number'] + ' проверен, прикреплён в CRM и сохранён в OneDrive.')
        except Exception as exc:
            # Keep the original invoice warning; never mark an uncertain effect as complete.
            reason = str(exc) if stage == 'поиск и сверка оригинала' and type(exc) is ValueError else type(exc).__name__
            messages.append(prefix + stage + ' не завершены: ' + reason + '. Сопровождающему ассистенту проверить этот этап перед повторным выпуском комплекта; финансовые записи не повторять.')
    return messages
