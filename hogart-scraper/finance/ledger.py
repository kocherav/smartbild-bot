#!/usr/bin/env python3
"""Auditable cash ledger. No accounting postings; money is integer kopecks."""
import argparse, collections, datetime as dt, hashlib, json, re, sqlite3, zipfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def cents(value):
    n = Decimal(value)
    if not n.is_finite() or n != n.quantize(Decimal('.01')):
        raise ValueError('Invalid money: '+value)
    return int(n * 100)

def date(value):
    return dt.datetime.strptime(value, '%d.%m.%Y').date().isoformat()

def parse(raw):
    text = raw.decode('cp1251')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != '1CClientBankExchange' or lines[-1] != 'КонецФайла':
        raise ValueError('Incomplete / unsupported statement')
    header, balance, docs, current = {}, {}, [], None
    in_balance = False
    for line in lines[1:]:
        if line == 'СекцияРасчСчет':
            if balance or current is not None: raise ValueError('Multiple account sections unsupported')
            in_balance = True
        elif line == 'КонецРасчСчет': in_balance = False
        elif line.startswith('СекцияДокумент='):
            if current is not None: raise ValueError('Unclosed document')
            current = {'СекцияДокумент': line.split('=', 1)[1]}
        elif line == 'КонецДокумента':
            if current is None: raise ValueError('Unexpected document end')
            docs.append(current); current = None
        elif '=' in line:
            k, v = line.split('=', 1)
            target = current if current is not None else balance if in_balance else header
            if k in target: raise ValueError('Repeated field '+k)
            target[k] = v
    if current is not None or in_balance: raise ValueError('Unclosed section')
    if header.get('ВерсияФормата') != '1.03' or header.get('Кодировка') != 'Windows':
        raise ValueError('Unsupported format / encoding')
    account = balance['РасчСчет']
    if account != header['РасчСчет']: raise ValueError('Account mismatch')
    start, end = date(balance['ДатаНачала']), date(balance['ДатаКонца'])
    if start > end or (start, end) != (date(header['ДатаНачала']), date(header['ДатаКонца'])):
        raise ValueError('Invalid statement period')
    total = {'in': 0, 'out': 0}
    keys = set()
    for d in docs:
        outgoing = d['ПлательщикСчет'] == account
        incoming = d['ПолучательСчет'] == account
        if outgoing == incoming: raise ValueError('Ambiguous account direction')
        direction = 'out' if outgoing else 'in'
        movement = d.get('ДатаСписано' if outgoing else 'ДатаПоступило')
        other_date = d.get('ДатаПоступило' if outgoing else 'ДатаСписано')
        if not movement or other_date: raise ValueError('Invalid movement dates')
        movement = date(movement)
        if not start <= movement <= end: raise ValueError('Movement outside statement')
        amount = cents(d['Сумма'])
        if amount <= 0: raise ValueError('Nonpositive amount')
        total[direction] += amount
        identity = [account, direction, movement, date(d['Дата']), d['СекцияДокумент'], d['Номер'], d['ПлательщикСчет'], d['ПолучательСчет']]
        key = digest(identity + [amount])
        if key in keys: raise ValueError('Indistinguishable operations in one statement; manual reconciliation needed')
        keys.add(key)
        d['_key'], d['_identity'] = key, digest(identity)
        d['_account'], d['_direction'], d['_date'], d['_cents'] = account, direction, movement, amount
    opening, closing = cents(balance['НачальныйОстаток']), cents(balance['КонечныйОстаток'])
    if total != {'in': cents(balance['ВсегоПоступило']), 'out': cents(balance['ВсегоСписано'])}:
        raise ValueError('Turnover does not match documents')
    if opening + total['in'] - total['out'] != closing: raise ValueError('Balance mismatch')
    return {'header': header, 'balance': balance, 'docs': docs}

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript('''
      CREATE TABLE IF NOT EXISTS statements(hash TEXT PRIMARY KEY, source TEXT, account TEXT, start TEXT, end TEXT, metadata TEXT);
      CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, identity TEXT, payload TEXT);
      CREATE TABLE IF NOT EXISTS observations(statement_hash TEXT, operation_id TEXT, PRIMARY KEY(statement_hash,operation_id));
      CREATE TABLE IF NOT EXISTS decisions(operation_id TEXT PRIMARY KEY, category TEXT, project TEXT, note TEXT, updated TEXT);
      CREATE TABLE IF NOT EXISTS decision_history(operation_id TEXT, category TEXT, project TEXT, note TEXT, updated TEXT);
    ''')
    return db

def import_zip(db, path):
    loaded = []
    with zipfile.ZipFile(path) as z:
        if len(z.infolist()) > 100 or sum(i.file_size for i in z.infolist()) > 30_000_000:
            raise ValueError('Archive limits exceeded')
        for i in z.infolist():
            if i.is_dir(): continue
            if not i.filename.lower().endswith('.txt'): raise ValueError('Unexpected archive member')
            raw = z.read(i)
            loaded.append((i.filename, hashlib.sha256(raw).hexdigest(), parse(raw)))
    if not loaded: raise ValueError('Empty archive')
    added, repeated = 0, 0
    new_ids = []
    statement_details = []
    with db:
        for filename, sh, s in loaded:
            b = s['balance']; account = b['РасчСчет']
            # Consecutive nonoverlapping statements must reconcile at their boundary.
            start, end = date(b['ДатаНачала']), date(b['ДатаКонца'])
            statement_details.append({'account': account, 'start': start, 'end': end})
            for prev_start, prev_end, metadata in db.execute('SELECT start,end,metadata FROM statements WHERE account=?', (account,)):
                pb = json.loads(metadata)['balance']
                if dt.date.fromisoformat(prev_end) + dt.timedelta(days=1) == dt.date.fromisoformat(start):
                    if cents(pb['КонечныйОстаток']) != cents(b['НачальныйОстаток']): raise ValueError('Opening balance gap')
                if dt.date.fromisoformat(end) + dt.timedelta(days=1) == dt.date.fromisoformat(prev_start):
                    if cents(b['КонечныйОстаток']) != cents(pb['НачальныйОстаток']): raise ValueError('Closing balance gap')
            # A repeated overlapping snapshot must not silently remove earlier operations.
            incoming_ids = {d['_key'] for d in s['docs']}
            for oid, payload in db.execute('SELECT id,payload FROM operations'):
                old = json.loads(payload)
                if old['_account'] == account and start <= old['_date'] <= end and oid not in incoming_ids:
                    raise ValueError('Changed overlapping statement: existing operation missing; review required')
            db.execute('INSERT OR IGNORE INTO statements VALUES(?,?,?,?,?,?)', (sh, filename, account, start, end, json.dumps({'header':s['header'],'balance':b},ensure_ascii=False)))
            for d in s['docs']:
                old = db.execute('SELECT payload FROM operations WHERE id=?',(d['_key'],)).fetchone()
                if old:
                    # A changed purpose or material bank field is a revision, not a new payment.
                    prior = json.loads(old[0])
                    if any(prior.get(k) != d.get(k) for k in ['НазначениеПлатежа','ПлательщикИНН','ПолучательИНН']):
                        raise ValueError('Revised operation; explicit review required: '+d['_key'])
                    repeated += 1
                else:
                    if db.execute('SELECT 1 FROM operations WHERE identity=?',(d['_identity'],)).fetchone():
                        raise ValueError('Possible amount correction / number collision; review required')
                    db.execute('INSERT INTO operations VALUES(?,?,?)',(d['_key'],d['_identity'],json.dumps(d,ensure_ascii=False)))
                    added += 1
                    new_ids.append(d['_key'])
                db.execute('INSERT OR IGNORE INTO observations VALUES(?,?)',(sh,d['_key']))
    return {'new': added, 'repeated': repeated, 'statements':len(loaded), 'new_ids':new_ids, 'statement_details':statement_details}

def invoice_refs(purpose):
    match = re.search(r'сч[её]т[уа]?\s*(?:№\s*|N\s*)*', purpose, re.I)
    if not match: return []
    tail = re.split(r'\b(?:в том числе|ндс|на сумму|сумма|к договору|курс)\b', purpose[match.end():], flags=re.I)[0]
    found = []
    for m in re.finditer(r'(?:^|,\s*)([A-Za-zА-Яа-я0-9/_.-]+)(?=\s|,|$)', tail):
        token = m.group(1)
        if re.search(r'\d', token): found.append(token)
    return list(dict.fromkeys(found))

def classify(d, accounts):
    purpose = d.get('НазначениеПлатежа',''); p = purpose.lower()
    out = d['_direction']=='out'; side = 'Получатель' if out else 'Плательщик'
    cp, inn = d.get(side,''), d.get(side+'ИНН','')
    owner = accounts.get(d['_account'], {'name':'Неизвестный счёт','inn':''})
    own_side = 'Плательщик' if out else 'Получатель'
    flags=[]; project_needed=False; category='Не определено'; flow='Операционная'; group='Внешняя'
    if not owner['inn'] or d.get(own_side+'ИНН') != owner['inn']: flags.append('Подтвердить владельца счёта / ИНН')
    if 'расчеты через ту' in p:
        category='Покупки по корпоративной карте'; flags.append('Нужны чек, назначение покупки и объект'); project_needed=True
    elif 'размещение денежных средств во вклад' in p:
        category='Размещение депозита'; flow='Перемещение'
    elif 'возврат депозит' in p:
        category='Возврат депозита'; flow='Перемещение'
    elif 'процент' in p and 'депозит' in p:
        category='Проценты по депозиту'; flow='Финансовая'
    elif 'перемещение собственных' in p and inn==owner['inn']:
        category='Перевод между своими счетами'; flow='Перемещение'; flags.append('Нужна встречная выписка по другому счёту')
    elif 'комис' in p:
        category='Банковские комиссии'
    elif 'единый налоговый платеж' in p:
        category='Единый налоговый платёж'
    elif 'страховые взносы' in p:
        category='Страховые взносы'
    elif 'взыскани' in p or d['СекцияДокумент']=='Инкассовое поручение':
        category='Взыскание'; flags.append('Проверить основание взыскания')
    elif 'штраф' in p:
        category='Штрафы'; flags.append('Уточнить основание и ответственного')
    elif 'заработной платы' in p:
        category='Заработная плата'
    elif 'подотчет' in p:
        category='Выдача под отчёт'; flags.append('Нужен авансовый отчёт'); project_needed=True
    elif 'возврат ошибочно' in p:
        category='Возврат ошибочного платежа'
    elif re.search(r'пен[ия]',p) and 'займ' in p:
        category='Пени по займу'; flow='Финансовая'; flags.append('Подтвердить: пени или проценты по договору займа')
    elif 'процент' in p and 'займ' in p:
        category='Проценты по займу'; flow='Финансовая'
    elif 'членские взносы' in p:
        category='Членские взносы'
    elif any(x in p for x in ['услуги связи','телекоммуникацион','лицевого счета']):
        category='Связь'
    elif any(x in p for x in ['лицензионн','таймвэб','сервисов']) or 'таймвэб' in cp.lower():
        category='ИТ и подписки'
    elif out and any(x in p for x in ['проектирован','проектных работ','проектной документации']):
        category='Проектные работы'; project_needed=True
    elif out and any(x in p for x in ['монтаж','бурени']):
        category='Подрядные работы'; project_needed=True
    elif out and any(x in p for x in ['оборудован','материал','комплектующ','труб','электро','светотех','воздуховод','вентилятор','фанкойл','автоматик','шумоглушител','клемм','увлажнител','шлюз','блоки питания','профиль','издели','кондиционер']):
        category='Оборудование и материалы'; project_needed=True
    elif not out and any(x in p for x in ['оплата','платеж','предоплата']):
        category='Поступления от заказчиков'; project_needed=True
    elif out:
        category='Прочие платежи — уточнить'; flags.append('Подтвердить статью')
    else: flags.append('Подтвердить статью')
    if inn in {'7743151323','7743926877'} and inn != owner['inn']:
        group='Между компаниями группы'
    if project_needed: flags.append('Нет подтверждённой привязки к объекту/заказу')
    if re.search(r'сч[её]ту\s*№\s*В том',purpose,re.I): flags.append('Пропущен номер счёта')
    if len(invoice_refs(purpose)) > 1:
        flags.append('Возможна оплата нескольких счетов — нужна разбивка')
    rates=sorted(set(re.findall(r'НДС\s*\(?\s*(\d{1,2})\s*%',purpose,re.I)))
    vat='; '.join(r+'%' for r in rates) or ('Без НДС' if re.search(r'без налога|ндс не облаг|без ндс',p) else 'Не определён')
    if '20' in rates: flags.append('Проверить указанную ставку НДС по первичному документу')
    vat_values=re.findall(r'НДС\s*(?:\d{1,2}\s*%\s*[,;]?\s*)?([\d ]+[.,]\d{2})',purpose,re.I)
    if len(set(v.replace(' ','').replace(',','.') for v in vat_values))>1: flags.append('Разные суммы НДС в назначении')
    sm=re.search(r'СУММА\s+(\d[\d ]*[.,-]\d{2})',purpose,re.I)
    if sm:
        value=sm.group(1).replace(' ','').replace(',','.').replace('-','.')
        if cents(value)!=d['_cents']: flags.append('Сумма в назначении отличается от банковской')
    if d['_account'].endswith('1580') and d['Номер']=='31' and d['_date']=='2026-07-01':
        flags.append('В назначении 165 000 ₽, платёж 50 000 ₽: проверить остаток счёта')
    refs=invoice_refs(purpose) + [v for v in re.findall(r'(?:договор[уа]?|сделк[еаи])\s*(?:№|N)?\s*([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9/_.-]*)',purpose,re.I) if re.search(r'\d',v)]
    return dict(id=d['_key'],company=owner['name'],account=d['_account'],date=d['_date'],document_date=date(d['Дата']),number=d['Номер'],direction=d['_direction'],amount_cents=d['_cents'],counterparty=cp,inn=inn,category=category,flow=flow,group=group,project='',references='; '.join(refs),vat=vat,purpose=purpose,flags=flags,link='',status='Требует уточнения' if flags else 'По правилу ДДС')

def records(db,accounts):
    ds=[json.loads(r[0]) for r in db.execute('SELECT payload FROM operations')]
    rows=[classify(d,accounts) for d in ds]; by_id={r['id']:r for r in rows}
    # Pair corresponding movements without deleting either organisation's entry.
    pairs=collections.defaultdict(list)
    for d in ds:
        k=digest([d['Дата'],d['Номер'],d['Сумма'],d['ПлательщикСчет'],d['ПолучательСчет']])
        pairs[k].append(d)
    for k, group in pairs.items():
        if len(group)==2 and {d['_direction'] for d in group}=={'in','out'}:
            for d in group: by_id[d['_key']]['link']='Парный перевод '+k[:12]
    # Repeated payroll / contributions for the same stated period are review candidates, not duplicates.
    similar=collections.defaultdict(list)
    for r in rows:
        if r['category'] in ['Заработная плата','Страховые взносы']:
            similar[(r['company'],r['inn'],r['amount_cents'],r['purpose'].lower())].append(r)
    for group in similar.values():
        if len(group)>1:
            for r in group: r['flags'].append('Повтор суммы и периода: проверить назначение / начисления')
    refunds=[d for d in ds if 'возврат ошибочно' in d.get('НазначениеПлатежа','').lower()]
    for d in refunds:
        candidates=[x for x in ds if x['_account']==d['_account'] and x['_direction']=='out' and x['_cents']==d['_cents'] and x['ПолучательИНН']==d['ПлательщикИНН'] and x['_date']<=d['_date']]
        if len(candidates)==1:
            by_id[d['_key']]['link']='Возврат к '+candidates[0]['_key'][:12]
            by_id[candidates[0]['_key']]['link']='Возвращён платежом '+d['_key'][:12]
        else: by_id[d['_key']]['flags'].append('Нужно сопоставить возврат с исходным платежом')
    for r in rows:
        r['status']='Требует уточнения' if r['flags'] else 'По правилу ДДС'
    from crm_context import enrich
    enrich(rows, accounts)
    from research import enrich as research_enrich
    research_enrich(rows, accounts)
    from user_rules import apply as apply_user_rules
    apply_user_rules(rows)
    from document_review import apply as apply_document_review
    apply_document_review(rows)
    from installer_context import apply as apply_installer_context
    apply_installer_context(rows)
    for oid,cat,project,note,updated in db.execute('SELECT * FROM decisions'):
        if oid in by_id:
            r=by_id[oid];r.update(category=cat,project=project,status='Подтверждено пользователем',decision_note=note)
    # Reviewed classifications are distinct from owner answers and CRM postings.
    classified_path=ROOT/'evidence/deep_review/classifications.json'
    if classified_path.exists():
        for oid,decision in json.loads(classified_path.read_text()).items():
            if oid not in by_id:continue
            r=by_id[oid]
            assert all(r[k]==decision[k] for k in ('inn','amount_cents','date','account'))
            r.update(decision['fields'])
            r['flags']=[f for f in r['flags'] if f not in decision['cleared_flags']]
    posting=ROOT/'data/posting_journal.json'
    journal=json.loads(posting.read_text()).get('operations',{}) if posting.exists() else {}
    for r in rows:
        linked=[p for p in journal.values() if p.get('bank_operation_id')==r['id'] and p.get('state')=='linked']
        if linked:
            r['crm_operations']=', '.join(p['operation_id'] for p in linked)
            r['crm_posting_status']='Проведено и привязано к сделке' if sum(p['amount_cents'] for p in linked)==r['amount_cents'] else 'Частично проведено; требуется завершить'
            if all(p.get('allocation_scope')=='company' for p in linked):
                r['crm_posting_status']='Проведено на уровне компании без сделки'
                
                if all(p.get('payment_semantics')=='bank_service_settled' for p in linked):r['crm_evidence']+='; Банковская комиссия: услуга оказана, задолженности нет'
                elif all(p.get('payment_semantics')=='nontrade_income' for p in linked):r['crm_evidence']+='; Нетоварный доход; клиентский счёт и отгрузка не требуются'
                else:r['crm_evidence']+='; Денежное движение компании; начисление расхода и оказание услуг этой оплатой не подтверждаются'
            if sum(p['amount_cents'] for p in linked)==r['amount_cents']:
                r['status']='Проведено в Мегаплане'
                if all(p.get('allocation_scope')=='company' for p in linked):
                    r['flags']=[f for f in r['flags'] if f!='Нет подтверждённой привязки к объекту/заказу']
                    if all(p.get('receipt_verified') for p in linked):
                        r['category']='ИТ и подписки'
                        r['flags']=[f for f in r['flags'] if f!='Нужны чек, назначение покупки и объект']
                    if all(p.get('refund_pair_id') for p in linked):r['category']='Возвращённый аванс поставщику'
                r['review_owner']='Пользователь: недостающие сведения' if r['flags'] else 'Не требуется'
            r['crm_evidence']+='; Финансовые операции Мегаплана: '+r['crm_operations']
            if all(p.get('payment_semantics')=='cash_only' for p in linked):
                r['crm_evidence']+='; Денежная операция: товарное движение 0, отгрузка/приёмка учитываются отдельно'
            invoice_ids=sorted({p['crm_invoice_id'] for p in linked if p.get('crm_invoice_id')})
            if invoice_ids:r['crm_evidence']+='; Связанные счета CRM: '+', '.join(invoice_ids)
    # Historical owner files are evidence, never an active queue.
    queue_path=ROOT/'data/review_registry.json'
    if queue_path.exists():
        queue=json.loads(queue_path.read_text())
        for r in rows:
            task=queue.get('tasks',{}).get('bank:'+r['id'],{})
            if task.get('state')=='open' and task.get('owner')=='user' and r['status']=='Требует уточнения':
                r['review_owner']='Пользователь: '+task['id']
                r['owner_question']=task['action']
    return sorted(rows,key=lambda r:(r['date'],r['company'],r['number'],r['id']))

def main():
    p=argparse.ArgumentParser(); p.add_argument('--db',default=str(ROOT/'data/ledger.sqlite')); p.add_argument('--accounts',default=str(ROOT/'accounts.json'))
    sub=p.add_subparsers(dest='command',required=True)
    i=sub.add_parser('import');i.add_argument('archive')
    e=sub.add_parser('export');e.add_argument('--output',default=str(ROOT/'reports/ledger.json'))
    a=sub.add_parser('decide');a.add_argument('id');a.add_argument('--category',required=True);a.add_argument('--project',default='');a.add_argument('--note',required=True)
    args=p.parse_args(); db=connect(args.db)
    if args.command=='import': print(json.dumps(import_zip(db,args.archive),ensure_ascii=False))
    elif args.command=='export':
        rows=records(db,json.loads(Path(args.accounts).read_text()));Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps(dict(operations=len(rows),statuses=dict(collections.Counter(r['status'] for r in rows))),ensure_ascii=False))
    else:
        if not db.execute('SELECT 1 FROM operations WHERE id=?',(args.id,)).fetchone(): raise ValueError('Unknown operation ID')
        values=(args.id,args.category,args.project,args.note,dt.datetime.now(dt.timezone.utc).isoformat())
        with db:
            db.execute('INSERT INTO decision_history VALUES(?,?,?,?,?)',values)
            db.execute('INSERT OR REPLACE INTO decisions VALUES(?,?,?,?,?)',values)

if __name__=='__main__':main()
