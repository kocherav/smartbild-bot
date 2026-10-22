"""Delivery-only settlement operations. Cash and bank-payment ledgers are untouched."""
import hashlib
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from registry_transaction import locked
from contract_invoice import v1_auth, v1_call
from megaplan_finance import megaplan_operations
from megaplan_transport import ProtectionPause

ROOT = Path(__file__).resolve().parent
JOURNAL = ROOT / 'shipment_finance_registry.json'
ACCOUNTS = {'40702810902570001580': '22', '40702810402570001572': '20', '40802810300007034866': '23'}


def cents(value):
    n = Decimal(str(value))
    if not n.is_finite() or n != n.quantize(Decimal('.01')):
        raise ValueError('Некорректная сумма передачи')
    return int(n * 100)


def plans(job):
    if job.get('mode') != 'live': return []
    data = job['data']
    contractor = str((data['payer'].get('contractor') or {}).get('id') or '')
    accounts = {ACCOUNTS[x] for x in data['seller']['accounts'] if x in ACCOUNTS}
    if not contractor or len(accounts) != 1:
        raise ValueError('Не определены контрагент и счёт организации для отражения передачи')
    groups = {}
    for row in data['positions']:
        kind = 'work' if row['kind'] == 'work' else 'goods'
        day = (data.get('transfer_dates') or {}).get(kind) or data['act_date']
        day = datetime.strptime(day, '%d.%m.%Y').date().isoformat()
        groups.setdefault(day, []).append(row)
    result = []
    for day, rows in sorted(groups.items()):
        amount = sum(cents(r['total']) for r in rows)
        if amount <= 0: raise ValueError('Сумма передачи должна быть положительной')
        # The business identity belongs to the shipment, never a document revision.
        shipment = job.get('shipment_id') or 'full-' + str(job['deal_id'])
        key = hashlib.sha256(f'{shipment}:{day}'.encode()).hexdigest()[:24]
        result.append({'key': key, 'shipment_id': shipment, 'deal_id': str(job['deal_id']),
                       'date': day, 'contractor_id': contractor, 'account_id': next(iter(accounts)),
                       'amount_cents': amount, 'act_number': data.get('act_number') or str(job['deal_id'])+'-АПП',
                       'marker': '[SHIPMENT:'+key+']',
                       'control_date':(datetime.strptime(data['act_date'],'%d.%m.%Y').date()+timedelta(days=1)).isoformat(),
                       'rows': [{'id':str(r['id']), 'quantity':str(r['quantity']), 'total_cents':cents(r['total'])} for r in rows]})
    if sum(x['amount_cents'] for x in result) != cents(data['total']):
        raise ValueError('Итог передачи не совпадает с документами')
    return result


def form(plan):
    return {'Model[OperationType]':'31', 'Model[Kind]':'income',
            'Model[Sum][Value]':'0.00', 'Model[Sum][Currency]':'1',
            'Model[SecondarySum][Value]':format(Decimal(plan['amount_cents'])/100,'.2f'),
            'Model[SecondarySum][Currency]':'1', 'Model[RealAccount]':plan['account_id'],
            'Model[Contractor]':plan['contractor_id'], 'Model[Date]':plan['date']+' 12:00:00',
            'Model[ControlDate]':plan['control_date'], 'Model[DocumentNumber]':plan['act_number'],
            'Model[Description]':f"{plan['marker']} Передача по акту {plan['act_number']}; сделка {plan['deal_id']}. Без движения денег. Контрольная дата — сверка взаиморасчётов, не договорный срок оплаты."}


def verify(operation, plan):
    if (operation.get('Kind')!='income' or str((operation.get('OperationType') or {}).get('Id'))!='31'
        or cents(operation['Sum']['Value'])!=0
        or cents(operation['SecondarySum']['Value'])!=plan['amount_cents']
        or str((operation.get('RealAccount') or {}).get('Id'))!=plan['account_id']
        or str((operation.get('Contractor') or {}).get('Id'))!=plan['contractor_id']
        or operation.get('Date','')[:10]!=plan['date']
        or str(operation.get('DocumentNumber'))!=plan['act_number']
        or plan['marker'] not in operation.get('Description','')):
        raise ValueError('Мегаплан вернул другую сумму, стороны или дату передачи')
    if operation.get('Deal') and str(operation['Deal'].get('Id'))!=plan['deal_id']:
        raise ValueError('Операция уже привязана к другой сделке')
    for field in ('Sum','SecondarySum'):
        currency=operation[field].get('CurrencyId') or operation[field].get('Currency')
        if str(currency.get('Id') if isinstance(currency,dict) else currency) != '1':
            raise ValueError('Валюта передачи не подтверждена как рубли')


class Backend:
    def __init__(self, api): self.api=api; self.auth=v1_auth(api)
    def list(self): return megaplan_operations(self.api,self.auth)
    def create(self, p):
        d=v1_call(self.api,'/BumsFinApiV01/Operation/save.api',form(p),self.auth)['data']
        item=d.get('item') or d.get('Operation') or d
        ident=str(item.get('Id') or item.get('id') or '')
        if not ident: raise ValueError('Мегаплан не вернул номер финансовой операции')
        return ident
    def card(self, ident):
        return v1_call(self.api,'/BumsFinApiV01/Operation/card.api',{'Id':ident},self.auth)['data']['item']
    def linked(self, ident, deal):
        d=self.api._call('GET','/deal/'+deal)['data']
        return any(str(x['id'])==ident for x in d.get('financeOperations',[]))
    def link(self, ident, deal):
        self.api._call('POST',f'/finOperation/{ident}/linkWith',json_body={'contentType':'Deal','id':deal})


def load(path):
    return json.loads(path.read_text()) if path.exists() else {'operations':{}}


def save(path, data):
    # Same durable atomic writer as the closing registry; callers hold the lock.
    import os, tempfile
    fd,tmp=tempfile.mkstemp(prefix='.shipment-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def ensure(planned, backend, path=JOURNAL):
    """Persist intent before POST. An uncertain POST is reconciled, never blindly repeated."""
    path=Path(path)
    with locked(str(path)):
        journal=load(path); history=None; receipts=[]
        for plan in planned:
            old=journal['operations'].get(plan['key'])
            if old and old['plan']!=plan: raise ValueError('Передача уже зарегистрирована с другими данными; нужно исправление')
            if old and old['state']=='linked':
                receipts.append(old); continue
            if history is None: history=backend.list()
            matches=[o for o in history if plan['marker'] in o.get('Description','')]
            if len(matches)>1: raise ValueError('Найдены дубли финансовой операции передачи')
            existing=matches[0] if matches else None
            if old and old.get('operation_id'):
                ident=old['operation_id']; existing=backend.card(ident)
                if matches and str(matches[0]['Id'])!=ident:raise ValueError('Реестр и Мегаплан расходятся')
            elif existing: ident=str(existing['Id'])
            else:
                if old and old['state']!='unsent':raise ValueError('Результат предыдущего создания неизвестен; повторная операция заблокирована')
                # A historical unmarked delivery for these parties/date must be reviewed.
                ambiguous=[o for o in history if o.get('Kind')=='income'
                           and str((o.get('Contractor') or {}).get('Id'))==plan['contractor_id']
                           and o.get('Date','')[:10]==plan['date']
                           and cents((o.get('SecondarySum') or {}).get('Value',0))==plan['amount_cents']
                           and '[SHIPMENT:' not in o.get('Description','')]
                if ambiguous:raise ValueError('В Мегаплане уже есть похожая передача; нужна сверка перед созданием')
                old={'plan':plan,'state':'creating','attempted_at':datetime.now().isoformat()}
                journal['operations'][plan['key']]=old;save(path,journal)
                try:ident=backend.create(plan)
                except ProtectionPause as exc:
                    if 'запрос не отправлен' in str(exc).lower():
                        old.update(state='unsent',reason=str(exc));save(path,journal)
                    raise
                old.update(operation_id=ident,state='created');save(path,journal)
                existing=backend.card(ident);history.append(existing)
            verify(existing,plan)
            old={'plan':plan,'operation_id':ident,'state':'verified'}
            journal['operations'][plan['key']]=old;save(path,journal)
            if not backend.linked(ident,plan['deal_id']):backend.link(ident,plan['deal_id'])
            if not backend.linked(ident,plan['deal_id']):raise ValueError('Привязка финансовой операции к сделке не подтверждена')
            old.update(state='linked',verified_at=datetime.now().isoformat());save(path,journal);receipts.append(old)
        return {'ok':True,'operations':[{'id':r['operation_id'],'date':r['plan']['date'],'amount_cents':r['plan']['amount_cents'],'cash_cents':0} for r in receipts]}
