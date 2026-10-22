import sys,json,hashlib
from pathlib import Path
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance','/home/kocher.av/megaplan-crm']
from post_confirmed import *
import deal_ledger,procurement_workflow as pw
D=ROOT/'evidence/invoice1624';a=MegaplanAPI();source=ROOT.parent/'incoming/1791365968-Счет_оферта_на_оплату___1624_от_22_июня_2026_г.xlsx'
spec={'deal_id':'807','invoice':{'number':'1624','date':'2026-06-22','supplier':'ООО «КОМФОРТНАЯ ВЕНТИЛЯЦИЯ-М»','supplier_inn':'7743949955','buyer':'ООО «ИНСИС»','buyer_inn':'7743926877','total':27600,'vat':4977.05,'currency':'RUB','source_path':str(source)},'updates':[],'additions':[{'name':'Пульт управления C1G','qty':1,'sell_price':43000,'cost_material':27600,'cost_work':0,'source_line_key':'1','source_name':'Пульт управления C1G','source_qty':1,'source_total':27600}],'unallocated':[]}
atomic(D/'supplier_spec.json',spec)
pre=pw.prepare_invoice_allocation(spec);atomic(D/'preflight.json',pre);assert pre['ok'],pre
statepath=D/'commercial_state.json';assert not statepath.exists(),'Already started: inspect live state before retry'
before=wait_budget(a._call,'GET','/deal/807')['data'];assert len(before['positions'])==24
assert not any('c1g' in p['name'].lower() for p in before['positions'])
atomic(statepath,{'state':'creating_offer','authorized_by':'Owner Telegram deal807 + да добавь + 43000; screenshot 2026-10-07'})
offer=wait_budget(a._call,'POST','/offer',json_body={'contentType':'Offer','name':'Пульт управления C1G','price':{'contentType':'Money','currency':'RUB','value':43000},'unit':{'contentType':'Unit','id':'1'},**a._cost_fields(27600,0)})['data'];atomic(D/'offer_created.json',offer)
atomic(statepath,{'state':'adding_position','offer_id':offer['id']})
a.add_position_to_deal('807',offer['id'],1,43000)
after=wait_budget(a._call,'GET','/deal/807')['data'];atomic(D/'deal_807_after.json',{'data':after})
old={p['id']:p for p in before['positions']};new={p['id']:p for p in after['positions']};assert len(new)==25 and set(old)<set(new)
for id,p in old.items():
 assert new[id]['quantity']==p['quantity'] and new[id]['price']['value']==p['price']['value'] and new[id]['offer']['id']==p['offer']['id']
added=[p for p in after['positions'] if p['id'] not in old];assert len(added)==1
p=added[0];assert p['name']=='Пульт управления C1G' and p['quantity']==1 and p['price']['value']==43000
assert p['offer']['Category1000045CustomFieldTsenaZakupki']['value']==27600
entries=a.ledger_from_deal(after,price_source='megaplan_live');deal_ledger.save('807',entries)
result={'ok':True,'added_count':1,'updated_count':0,'offer_row_id':p['id'],'offer_id':p['offer']['id']}
atomic(statepath,{'state':'position_verified',**result})
record=pw.record_invoice(spec,result);atomic(D/'procurement_record.json',record)
row=next(r for r in json.loads((ROOT/'reports/ledger.json').read_text()) if r['id']=='0be57183903e34f3674f2c6e0c575b4dc77775ee19c587a41bb365edd4504e6b')
assert row['amount_cents']==2760000 and row['inn']=='7743949955' and row['company']=='ИНСИС'
x={'confirmed':True,'reviewed_by':'assistant','inn':row['inn'],'number':'1624','amount_cents':2760000,'source':'Владелец явно указал Павелецкая Сити Наталья, сделка807, подтвердил добавление C1G и продажу43000 в Telegram07.10.2026. Счёт1624 содержит1C1G 27600; ИНН обеих сторон и платёж22.06 №62 сверены. Только оплата, без отгрузки.','invoice_source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'allocations':[{'deal_id':'807','project':'Павелецкая Сити — Наталья','amount_cents':2760000}],'cleared_flags':[],'old_question_number':35}
allocpath=ROOT/'evidence/deep_review/reviewed_allocations.json';alloc=json.loads(allocpath.read_text());alloc[row['id']]=x;atomic(allocpath,alloc);atomic(D/'reviewed_allocations.json',{row['id']:x});atomic(D/'archive_links.json',[{'deal_id':'807','source':str(source),'number':'1624'}]);print('Verified new controller',result,'cash allocation prepared',flush=True)
