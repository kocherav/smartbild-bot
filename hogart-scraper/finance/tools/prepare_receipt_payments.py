import sys,json,hashlib
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/finish_all';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';m=json.loads(mp.read_text());inn='9704259180'
if not m.get(inn,{}).get('contractor_id'):
 assert m.get(inn,{}).get('state')!='creating','Uncertain creation'
 a=MegaplanAPI();r=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':'Яндекс 360'});atomic(D/'search_Yandex360.json',r);assert not r['data']
 payload={'contentType':'ContractorCompany','name':'ООО «Яндекс 360 для бизнеса»','type':{'contentType':'ContractorType','id':'5'},'description':'ИНН 9704259180. Подтверждён кассовыми чеками от 23.06.2026 и 20.09.2026 в kav@innsis.ru; адрес места расчётов из чека, не юридический адрес.','contactInfo':[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':'Россия, Владимирская обл., г. Владимир, микрорайон Энергетик, улица Поисковая, дом 1, корпус 3 (место расчётов по чеку)'}]}
 m[inn]={'state':'creating','payload':payload};atomic(mp,m)
 r=wait_budget(a._call,'POST','/contractorCompany',json_body=payload);atomic(D/'created_9704259180.json',r);m[inn].update(state='created',contractor_id=r['data']['id'],basis='ИНН и наименование из двух кассовых чеков');atomic(mp,m)
rows=json.loads((ROOT/'reports/ledger.json').read_text());path=D/'company_plan.json';plan=json.loads(path.read_text())
def add(r,cat,typ,cid,extra,evidence):
 k=hashlib.sha256((r['id']+'|company|'+cat).encode()).hexdigest()[:24]
 p=dict(key=k,bank_operation_id=r['id'],date=r['date'],document_number=r['number'],account_id={'ИНСИС':'20','КЛИВЭЛ':'22'}[r['company']],kind='income' if r['direction']=='in' else 'expense',amount_cents=r['amount_cents'],deal_id='',allocation_scope='company',category=cat,invoice_number='',counterparty_inn=r['inn'],operation_type=typ,contractor_id=cid,description=f"[BANK:{k}] {cat}; банк №{r['number']}. {r['purpose']}"[:255],marker='BANK:'+k,evidence=evidence,**extra)
 if not any(x['key']==k for x in plan):plan.append(p)
for r in rows:
 if 'YANDEX 7372 360B2B' in r['purpose']:
  uid={'3805':'66111','1459':'67420'}[r['number']];receipt=D/'receipts'/('kav_83ecb521bf32_'+uid+'.txt');txt=receipt.read_text();assert f"{r['amount_cents']/100:.2f}" in txt and inn in txt and '2624' in r['purpose']
  add(r,'ИТ и подписки','25',m[inn]['contractor_id'],dict(receipt_supplier_inn=inn,receipt_verified=True,card_last4='2624',receipt_source=str(receipt)), 'Корпоративная подписка Яндекс 360; точные сумма, дата чека и продавец сверены с банковским эквайрингом. '+str(receipt)+'. Предоплата, услуги не начисляются.')
pair=[r for r in rows if r['inn']=='7704845920' and r['amount_cents']==30000000];assert len(pair)==2 and {r['direction'] for r in pair}=={'in','out'} and {r['date'] for r in pair}=={'2026-07-27','2026-07-29'}
pairid=hashlib.sha256('|'.join(sorted(r['id'] for r in pair)).encode()).hexdigest()[:24]
for r in pair:add(r,'Возвращённый аванс СТК','23' if r['direction']=='out' else '30','1002588',{'refund_pair_id':pairid},'Платёж СТК по счёту137 от27.07.2026 полностью возвращён29.07.2026 №365. Точные ИНН, счёт компании и сумма300000 совпадают; нет расхода/дохода по проекту. Возврат дебиторской задолженности, не выручка.')
atomic(path,plan);atomic(D/'stk_refund_reconciliation.json',{'pair_id':pairid,'bank_rows':pair,'net_cents':0});print('plan',len(plan),'yandex',m[inn]['contractor_id'])
