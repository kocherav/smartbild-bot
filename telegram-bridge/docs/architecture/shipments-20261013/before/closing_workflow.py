"""Closing workflow decisions and durable state. No remote effects in this module."""
import copy, hashlib, json, re
from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import durable_json

SHIP='138'; PAYMENT='137'; COMPLETE='139'
HOLIDAYS_2026={date(2026,1,d) for d in range(1,12)}|{date(2026,2,23),date(2026,3,9),date(2026,5,1),date(2026,5,11),date(2026,6,12),date(2026,11,4),date(2026,12,31)}

def cents(value):
    if isinstance(value,dict):value=value.get('value')
    v=Decimal(str(value))
    if not v.is_finite() or v!=v.quantize(Decimal('.01')):raise ValueError('Сумма должна быть конечной и заданной до копеек')
    return int(v*100)

def next_business_day(now):
    day=now.date()+timedelta(days=1)
    while True:
        if day.year!=2026:raise ValueError('Для напоминания нужен утверждённый производственный календарь '+str(day.year))
        if day.weekday()<5 and day not in HOLIDAYS_2026:return datetime.combine(day,datetime.min.time()).replace(hour=10,tzinfo=now.tzinfo)
        day+=timedelta(days=1)

def final_clause(text):
    candidates=[]
    for n in ('6.4.2','6.4.3'):
        m=re.search(r'(?ms)^\s*'+re.escape(n)+r'\s+(.+?)(?=^\s*\d+(?:\.\d+)*[. ]\s*[А-ЯA-Z]|\Z)',text)
        if m and re.search('окончательн',m[1],re.I):candidates.append(n)
    if len(candidates)!=1:raise ValueError('В договоре не определён однозначный окончательный расчёт по п. 6.4.2 / 6.4.3')
    return candidates[0]

def settled_amount(transactions,deal_id,payer_inn,accounts):
    """Only assigned bank operations for the exact parties; email is not bank proof."""
    seen={};total=0;proof=[]
    if not payer_inn or not accounts:raise ValueError('Не заданы стороны для сверки оплаты')
    for tx in transactions:
        if str(tx.get('deal_id'))!=str(deal_id) or tx.get('status')!='assigned':continue
        if tx.get('counterparty_inn')!=payer_inn or tx.get('account') not in accounts:continue
        if tx.get('source')=='email' or str(tx.get('id','')).startswith('email:'):continue
        if tx.get('direction')=='income':sign=1
        elif tx.get('direction')=='expense' and re.search('возврат',tx.get('purpose',''),re.I):sign=-1
        else:continue
        key=tx.get('source_operation_id') or tx.get('id')
        if not key or not tx.get('date') or not tx.get('document_number'):raise ValueError('Недостаточно банковских реквизитов для подтверждения оплаты')
        amount=cents(tx['amount'])*sign
        if key in seen:
            if seen[key]!=amount:raise ValueError('Противоречивые суммы одной банковской операции')
            continue
        seen[key]=amount;total+=amount;proof.append({'id':key,'amount_cents':amount,'date':tx['date'],'number':tx['document_number']})
    return total,proof

def bank_closure_allowed(job,current_deal,transactions):
    if job.get('mode')!='live' or not job.get('edo_confirmation'):return False,{'reason':'Нет боевого подтверждения отправки ЭДО'}
    if str((current_deal.get('state')or{}).get('id'))!=PAYMENT:return False,{'reason':'Сделка не в Оплате'}
    paid,proof=settled_amount(transactions,job['deal_id'],job['payer_inn'],job['seller_accounts'])
    payer=current_deal.get('payer') or {}
    if payer and str(payer.get('id'))!=str((job.get('data') or {}).get('payer_id')):return False,{'reason':'Плательщик изменился после выпуска комплекта'}
    total=cents(current_deal['price'])
    if total!=job['total_cents']:return False,{'reason':'Сумма сделки изменилась после выпуска комплекта'}
    if not proof:return False,{'reason':'Нет подтверждённых поступлений по выписке'}
    return paid>=total,{'paid_cents':paid,'balance_cents':total-paid,'operations':proof}

class Registry:
    def __init__(self,path):self.path=str(path)
    def read(self):return durable_json.read(self.path,lambda:{'jobs':{},'stages':{}})
    def change(self,fn):
        with durable_json.locked(self.path):
            data=self.read();value=fn(data);durable_json.save(self.path,data);return copy.deepcopy(value)
    def get(self,key):return self.read()['jobs'][key]
    def patch(self,key,**values):
        def apply(d):d['jobs'][key].update(values);return d['jobs'][key]
        return self.change(apply)
    def enqueue(self,deal_id,mode='live'):
        if mode not in ('test','live'):raise ValueError('Неизвестный режим')
        key=hashlib.sha256(f'closing-v1:{mode}:{deal_id}'.encode()).hexdigest()[:16]
        def apply(d):
            return d['jobs'].setdefault(key,{'id':key,'deal_id':str(deal_id),'mode':mode,'status':'preparing','created_at':datetime.now().isoformat(),'receipts':{}})
        return self.change(apply)
    def observe(self,deal_id,state):
        result=self.observe_many([(deal_id,state)])
        return result[0] if result else None
    def observe_many(self,states):
        def apply(d):
            added=[]
            for deal_id,state in states:
                deal_id=str(deal_id);state=str(state);prev=d['stages'].get(deal_id)
                d['stages'][deal_id]=state
                if prev is not None and prev!=SHIP and state==SHIP:
                    key=hashlib.sha256(f'closing-v1:live:{deal_id}'.encode()).hexdigest()[:16]
                    added.append(d['jobs'].setdefault(key,{'id':key,'deal_id':deal_id,'mode':'live','status':'preparing','created_at':datetime.now().isoformat(),'receipts':{}}))
            return added
        return self.change(apply)
    def confirm(self,key,actor,recipient,refs,now):
        if str(actor)!=str(recipient):raise ValueError('Подтверждать ЭДО может только Татьяна')
        def apply(d):
            j=d['jobs'][key]
            if j['mode']!='live':raise ValueError('Тестовый комплект не отправляется клиенту и не меняет стадию')
            if j.get('edo_confirmation'):return j
            if j['status'] not in ('awaiting_edo','needs_info'):raise ValueError('Комплект ещё не доставлен или уже неактуален')
            if not all(str(refs.get(k,'')).strip() for k in ('act','upd','invoice')):raise ValueError('Нужны реквизиты отправленных акта, УПД и счёта')
            j.update(status='edo_confirmed',edo_confirmation={'actor':str(actor),'documents':refs,'at':now.isoformat()})
            return j
        return self.change(apply)
