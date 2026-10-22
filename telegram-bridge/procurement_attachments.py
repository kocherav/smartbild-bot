"""Verified originals for accountant delivery; OneDrive remains an internal archive."""
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path


def download(remote, target):
    subprocess.run(['rclone', 'copyto', remote, str(target)], capture_output=True, timeout=120, check=True)


def build(deal_id, folder, archive_path, invoices, downloader=download):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    entries = json.loads(Path(archive_path).read_text()).get('documents', [])
    sources = [x for x in entries if str(x.get('deal_id')) == str(deal_id)
               and x.get('category') in ('supplier_invoice', 'supplier_closing')
               and x.get('status', 'uploaded') == 'uploaded']
    docs, seen = [], set()
    for entry in sources:
        sha = entry.get('sha256')
        if not sha:
            raise ValueError('У закупочного оригинала нет контрольной суммы: ' + entry['filename'])
        if sha in seen: continue
        seen.add(sha)
        name = re.sub(r'[\\/\x00-\x1f]', '_', entry['filename'])
        name = f'{len(docs)+1:02d} — {name}'
        path = folder / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            downloader(entry['onedrive_remote'], path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('Не совпала контрольная сумма закупочного оригинала: ' + name)
        docs.append(dict(name=name, path=str(path), sha256=sha, number=entry.get('document_number',''), category=entry['category']))
    lines = ['РЕЕСТР ЗАКУПОЧНЫХ ДОКУМЕНТОВ', f'Сделка №{deal_id}. Внутренние документы для бухгалтера.',
             'Файлы внутри архива открываются без входа в OneDrive.',
             'Оплаты указаны по реестру закупок; повторно не проводить.', '']
    for inv in invoices:
        lines.append(f"{inv.get('supplier','Поставщик')} — счёт №{inv.get('number')} от {inv.get('date')}; сумма {inv.get('total')} ₽; оплачено {inv.get('paid_total',0)} ₽; покупатель {inv.get('buyer','не указан')}.")
        matched = [d['name'] for d in docs if d['category']=='supplier_invoice' and str(d['number'])==str(inv.get('number'))]
        lines.append('Счёт: ' + ('; '.join(matched) if matched else 'ФАЙЛ НЕ ВКЛЮЧЁН — требуется получить оригинал.'))
        closing = inv.get('closing_documents') or []
        if not closing: lines.append('Закрывающий документ не зарегистрирован; товарный состав смотреть по счёту.')
        for item in closing:
            matched = [d['name'] for d in docs if d['sha256']==item.get('sha256')]
            lines.append('Закрывающий документ: ' + ('; '.join(matched) if matched else item.get('filename','УПД')+' — ФАЙЛ НЕ ВКЛЮЧЁН, требуется получить оригинал.'))
        lines.append('')
    lines += ['Состав архива:'] + [d['name'] for d in docs]
    text = '\n'.join(lines)
    # Separate ZIP volumes keep typical mail messages small; never omit a file silently.
    groups = [[]]; size = 0
    for doc in docs:
        length = Path(doc['path']).stat().st_size
        if length > 8*1024*1024: raise ValueError('Закупочный файл превышает лимит вложения 8 МБ: '+doc['name'])
        if size+length > 8*1024*1024 and groups[-1]: groups.append([]); size = 0
        groups[-1].append(doc); size += length
    attachments = []
    for idx, group in enumerate(groups, 1):
        path = folder / f'Закупочные документы — {deal_id} — часть {idx}.zip'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('00 — Реестр документов.txt', text + f'\n\nЭтот архив: часть {idx} из {len(groups)}.\n')
            for doc in group: z.write(doc['path'],doc['name'])
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None: raise ValueError('Ошибка проверки ZIP')
        attachments.append(str(path))
    return {'attachments':attachments, 'files':docs, 'register':text}


def email_messages(sender, recipient, subject, text, paths, message_id, limit=18*1024*1024):
    """Return numbered messages, each bounded by actual MIME size (incl. base64)."""
    from email.message import EmailMessage
    def message(group, idx, count):
        m=EmailMessage();m['From']=sender;m['To']=recipient
        m['Subject']=subject + (f' — часть {idx}/{count}' if count>1 else '')
        m['Message-ID']=f'<{message_id}-{idx}@cliwell.ru>'
        m.set_content(text+'\n\nВложения этого письма:\n'+'\n'.join(Path(p).name for p in group))
        for p in group:
            p=Path(p);m.add_attachment(p.read_bytes(),maintype='application',subtype='zip' if p.suffix.lower()=='.zip' else 'pdf',filename=p.name)
        return m
    groups=[[]]
    for path in paths:
        if len(message([path],999,999).as_bytes())>limit:raise ValueError('Файл превышает допустимый размер письма: '+Path(path).name)
        if groups[-1] and len(message(groups[-1]+[path],999,999).as_bytes())>limit:groups.append([])
        groups[-1].append(path)
    return [message(group,idx,len(groups)) for idx,group in enumerate(groups,1)]
