import sys,json
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,'/home/kocher.av/telegram-bridge')
import closing_runtime as c
from shipment_finance import Backend
from contract_invoice import v1_call
root=Path(__file__).resolve().parent;receipt=root/'cash-receipt.json';r=json.loads(receipt.read_text()) if receipt.exists() else {};b=Backend(c.api());marker='[CASH:861:20260701:advance:1000000]'
def save():receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2))
accounts=v1_call(b.api,'/BumsFinApiV01/RealAccount/list.api',{},b.auth)['data']['items'];cash=next(x for x in accounts if str(x['Id'])=='19');assert cash['Name']=='Касса' and str(cash['Currency']['Id'])=='1'
d=b.api._call('GET','/deal/861')['data'];party=str(d['contractor']['id']);assert party=='1002845'
ops=b.list();matches=[o for o in ops if marker in str(o.get('Description',''))]
if not matches and not r.get('operation_id'):
 possible=[o for o in ops if o.get('Kind')=='income' and str((o.get('RealAccount') or {}).get('Id'))=='19' and Decimal(str(o['Sum']['Value']))==Decimal('1000000') and str(o.get('Date','')).startswith('2026-07-01')]
 if possible:raise ValueError('В кассе есть возможный дубль; автоматическое создание остановлено')
 if r.get('state')=='intent':raise ValueError('Предыдущая запись не подтверждена; повтор запрещён')
 form={'Model[OperationType]':'31','Model[Kind]':'income','Model[Sum][Value]':'1000000.00','Model[Sum][Currency]':'1','Model[SecondarySum][Value]':'0.00','Model[SecondarySum][Currency]':'1','Model[RealAccount]':'19','Model[Contractor]':party,'Model[Date]':'2026-07-01 12:00:00','Model[ControlDate]':'2026-07-02','Model[DocumentNumber]':'CASH-861-20260701-01','Model[Description]':marker+' Наличный аванс за дополнительные монтажные работы 1 500 000 руб., сделка 861. Факт и дата подтверждены владельцем 13.10.2026; дата совпадает с банковским авансом №1762. Без передачи товаров/услуг.'}
 r.update(state='intent',form=form,account_before=cash);save()
 result=v1_call(b.api,'/BumsFinApiV01/Operation/save.api',form,b.auth)['data'];item=result.get('item') or result.get('Operation') or result;ident=str(item.get('Id') or item.get('id') or '');assert ident
 r.update(operation_id=ident,state='created');save()
elif matches:
 assert len(matches)==1;r['operation_id']=str(matches[0]['Id']);save()
o=b.card(r['operation_id']);assert o['Kind']=='income' and str(o['OperationType']['Id'])=='31' and Decimal(str(o['Sum']['Value']))==1000000 and Decimal(str(o['SecondarySum']['Value']))==0 and str(o['RealAccount']['Id'])=='19' and str(o['Contractor']['Id'])==party and o['Date'].startswith('2026-07-01') and marker in o['Description']
if not b.linked(r['operation_id'],'861'):b.link(r['operation_id'],'861')
assert b.linked(r['operation_id'],'861');r.update(state='linked',operation=o);save()
after=b.list();before=json.loads((root/'operations-before.json').read_text());byid={str(o['Id']):o for o in after};assert all(byid[str(o['Id'])]==o for o in before)
account=next(x for x in v1_call(b.api,'/BumsFinApiV01/RealAccount/list.api',{},b.auth)['data']['items'] if str(x['Id'])=='19');r['account_after']=account;r['previous_operations_unchanged']=True;save()
print(json.dumps({'operation_id':r['operation_id'],'state':r['state'],'date':o['Date'],'amount':o['Sum']['Value'],'cash_balance':account['Balance'],'previous_operations_unchanged':True},ensure_ascii=False))
