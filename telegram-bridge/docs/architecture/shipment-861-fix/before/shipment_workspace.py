"""One shipment ledger shared by the dashboard and the document worker."""
import copy, hashlib, json, os, re, sqlite3, time, uuid
from contextlib import contextmanager
from datetime import date, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
DB=Path(__file__).resolve().parent/'data/shipments.sqlite3'

def decimal(v):
 try:n=Decimal(str(v))
 except Exception:raise ValueError('Некорректное количество или сумма')
 if not n.is_finite():raise ValueError('Неконечное количество или сумма')
 return n

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

@contextmanager
def connection(path=None):
 path=Path(path or DB);path.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(path,timeout=15);db.row_factory=sqlite3.Row
 try:
  db.executescript('CREATE TABLE IF NOT EXISTS books(deal TEXT PRIMARY KEY,state TEXT NOT NULL,data TEXT,error TEXT,updated REAL NOT NULL); CREATE TABLE IF NOT EXISTS shipments(id TEXT PRIMARY KEY,deal TEXT NOT NULL,serial INTEGER NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,created REAL NOT NULL,UNIQUE(deal,serial));')
  if path.stat().st_uid==os.geteuid():path.chmod(0o660)
  with db:yield db
 finally:db.close()

def book(deal,path=None):
 with connection(path) as db:
  row=db.execute('SELECT * FROM books WHERE deal=?',(str(deal),)).fetchone()
  return {**dict(row),'data':json.loads(row['data']) if row['data'] else None} if row else None

def request(deal,path=None):
 if not str(deal).isdigit():raise ValueError('Некорректная сделка')
 with connection(path) as db:
  db.execute("INSERT INTO books VALUES(?,'loading',NULL,NULL,?) ON CONFLICT(deal) DO UPDATE SET state='loading',error=NULL,updated=excluded.updated",(str(deal),time.time()))
 return {'state':'loading'}

def save_book(deal,data=None,error=None,path=None):
 if data is not None:data={**data,'fingerprint':digest(data)}
 with connection(path) as db:db.execute('INSERT INTO books VALUES(?,?,?,?,?) ON CONFLICT(deal) DO UPDATE SET state=excluded.state,data=excluded.data,error=excluded.error,updated=excluded.updated',(str(deal),'error' if error else 'ready',json.dumps(data,ensure_ascii=False) if data else None,error,time.time()))
 return data

def pending_books(path=None):
 with connection(path) as db:return [r['deal'] for r in db.execute("SELECT deal FROM books WHERE state='loading'")]

def shipments(deal=None,path=None):
 with connection(path) as db:
  rows=db.execute('SELECT * FROM shipments'+(' WHERE deal=?' if deal else '')+' ORDER BY created', (str(deal),) if deal else ()).fetchall()
  return [{**dict(r),'payload':json.loads(r['payload'])} for r in rows]

def patch(ident,state=None,values=None,path=None):
 with connection(path) as db:
  db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT * FROM shipments WHERE id=?',(ident,)).fetchone()
  if not r:raise ValueError('Отгрузка не найдена')
  payload=json.loads(r['payload']);payload.update(values or {})
  db.execute('UPDATE shipments SET state=?,payload=? WHERE id=?',(state or r['state'],json.dumps(payload,ensure_ascii=False),ident))

def used(rows):
 totals={}
 for shipment in rows:
  if shipment['state']=='cancelled':continue
  for r in shipment['payload']['positions']:
   d=totals.setdefault(str(r['source_id']),{'quantity':Decimal(0),'total':Decimal(0)})
   d['quantity']+=decimal(r['source_quantity']);d['total']+=decimal(r['total'])
 return totals

def projection(deal,path=None):
 b=book(deal,path);ss=shipments(deal,path);u=used(ss)
 if b and b['data']:
  for r in b['data']['positions']:
   old=u.get(str(r['id']),{'quantity':Decimal(0),'total':Decimal(0)})
   r.update(delivered_quantity=str(old['quantity']),remaining_quantity=str(decimal(r['quantity'])-old['quantity']))
 return {'book':b,'shipments':ss}

def select(data, choices, previous):
 source={str(r['id']):r for r in data['positions']};u=used(previous);result=[];seen=set()
 if not isinstance(choices,list) or not choices:raise ValueError('Выберите позиции для передачи')
 for c in choices:
  ident=str(c.get('id'))
  if ident in seen or ident not in source:raise ValueError('Повтор или неизвестная позиция')
  seen.add(ident);r=source[ident];qty=decimal(c.get('quantity'));full=decimal(r['quantity']);old=u.get(ident,{'quantity':Decimal(0),'total':Decimal(0)})
  if qty<=0 or qty>full-old['quantity']:raise ValueError('Количество превышает неотгруженный остаток: '+r['name'])
  if qty.as_tuple().exponent < -6:raise ValueError('Не более шести знаков количества')
  indivisible=r.get('unit','').rstrip('.').lower() in ('шт','компл','к-т','комплект')
  stage=str(c.get('stage') or '').strip();basis=str(c.get('stage_basis') or '').strip()
  if indivisible and qty!=qty.to_integral_value() and (r['kind']!='work' or not stage or not basis):raise ValueError('Для неделимой работы укажите согласованный этап и основание; товар делится только целыми единицами')
  if len(stage)>200 or len(basis)>1000:raise ValueError('Слишком длинное описание этапа')
  if stage:
   if r['kind']!='work' or not basis:raise ValueError('Нужно основание согласования этапа работ')
   amount=decimal(c.get('stage_amount'))
   if amount<=0 or amount!=amount.quantize(Decimal('.01')) or amount>decimal(r['total'])-old['total']:raise ValueError('Стоимость этапа превышает остаток')
  else:
   amount=(decimal(r['total'])*(old['quantity']+qty)/full).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)-old['total']
  if amount<=0:raise ValueError('Стоимость передачи должна быть положительной')
  if qty==full-old['quantity'] and amount!=decimal(r['total'])-old['total']:raise ValueError('Последний этап должен закрывать остаток согласованной стоимости')
  rate=int(r['tax_rate']);vat=Decimal(0) if rate<0 else (amount*rate/(100+rate)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
  result.append({**r,'id':ident,'source_id':ident,'source_quantity':str(qty),'source_number':data['positions'].index(r)+1,'quantity':'1' if stage else str(qty),'name':r['name']+(' — '+stage if stage else ''),'unit':'этап' if stage else r['unit'],'unit_price':str(amount if stage else (amount/qty).quantize(Decimal('.01'))),'total':str(amount),'vat_amount':str(vat),'stage_basis':basis})
 return result

def confirm(body,actor,path=None):
 deal=str(body.get('deal_id'));key=str(body.get('request_id') or '')
 if not re.fullmatch('[a-zA-Z0-9-]{12,80}',key):raise ValueError('Нет ключа запроса')
 ident=hashlib.sha256((deal+':'+key).encode()).hexdigest()[:16]
 with connection(path) as db:
  db.execute('BEGIN IMMEDIATE')
  existing=db.execute('SELECT * FROM shipments WHERE id=?',(ident,)).fetchone()
  if existing:
   payload=json.loads(existing['payload'])
   if payload['request']!=body:raise ValueError('Повторный запрос содержит другие данные')
   return {'id':ident,'state':existing['state']}
  b=db.execute('SELECT * FROM books WHERE deal=?',(deal,)).fetchone()
  if not b or b['state']!='ready' or time.time()-b['updated']>900:raise ValueError('Обновите данные сделки перед подтверждением')
  data=json.loads(b['data'])
  if data['fingerprint']!=body.get('fingerprint'):raise ValueError('Исходные данные изменились')
  day=date.fromisoformat(str(body.get('transfer_date')))
  if day>datetime.now(ZoneInfo('Europe/Moscow')).date():raise ValueError('Нельзя подтвердить будущую передачу')
  if day<date.fromisoformat(data['contract_date_iso']):raise ValueError('Передача раньше договора')
  previous=[{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM shipments WHERE deal=?',(deal,))]
  positions=select(data,body.get('positions'),previous)
  payment=body.get('payment') or {}
  if payment:
   if not str(payment.get('basis') or '').strip() or not str(payment.get('clause') or '').strip():raise ValueError('Укажите пункт договора и основание частичного платежа')
   if len(str(payment['basis']))>1000 or len(str(payment['clause']))>80:raise ValueError('Слишком длинное основание платежа')
   amount=decimal(payment.get('amount'))
   if amount<=0 or amount!=amount.quantize(Decimal('.01')):raise ValueError('Проверьте сумму частичного платежа')
   if amount>sum(decimal(r['total']) for r in positions):raise ValueError('Счёт превышает стоимость этой передачи')
  serial=max([r['serial'] for r in previous] or [0])+1
  payload={'request':body,'actor':str(actor),'fingerprint':data['fingerprint'],'positions':positions,'total':str(sum(decimal(r['total']) for r in positions)),'transfer_date':day.strftime('%d.%m.%Y'),'act_number':f'{deal}-АПП/{serial:02d}','payment':payment,'source':data}
  db.execute('INSERT INTO shipments VALUES(?,?,?,?,?,?)',(ident,deal,serial,'confirmed',json.dumps(payload,ensure_ascii=False),time.time()))
 return {'id':ident,'state':'confirmed'}

def complete_volume(deal,path=None):
 b=book(deal,path)
 if not b or not b['data']:return False
 u=used(shipments(deal,path))
 return all(u.get(str(r['id']),{}).get('quantity',0)==decimal(r['quantity']) and u.get(str(r['id']),{}).get('total',0)==decimal(r['total']) for r in b['data']['positions'])


def preview(body,path=None):
 b=book(str(body.get('deal_id')),path)
 if not b or b['state']!='ready' or b['data']['fingerprint']!=body.get('fingerprint'):raise ValueError('Обновите исходные данные')
 positions=select(b['data'],body.get('positions'),shipments(body['deal_id'],path))
 return {'positions':positions,'total':str(sum(decimal(r['total']) for r in positions)),'vat':str(sum(decimal(r['vat_amount']) for r in positions))}
