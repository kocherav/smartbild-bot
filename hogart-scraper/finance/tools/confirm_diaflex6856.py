import sys,json,hashlib
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/diaflex6856';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';m=json.loads(mp.read_text());inn='7719618222'
if not m.get(inn,{}).get('contractor_id'):
 assert m.get(inn,{}).get('state')!='creating'
 assert not json.loads((D/'search_ДИАФЛЕКС.json').read_text())['data']
 assert not json.loads((D/'search_7719618222.json').read_text())['data']
 payload={'contentType':'ContractorCompany','name':'ООО «ДИАФЛЕКС»','type':{'contentType':'ContractorType','id':'5'},'description':'ИНН 7719618222. Реквизиты из счёта-договора6856 от14.08.2026, покупатель ИНСИС.','contactInfo':[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':'143912, Московская область, г. Балашиха, ш Энтузиастов (западная Промзона Тер), дом 2, помещение 141/1'}]}
 m[inn]={'state':'creating','payload':payload};atomic(mp,m)
 res=wait_budget(MegaplanAPI()._call,'POST','/contractorCompany',json_body=payload);atomic(D/'supplier_created.json',res);m[inn].update(state='created',contractor_id=res['data']['id'],basis='ИНН и адрес из счёта6856; реестр плательщиков и поиск CRM проверены');atomic(mp,m)
r=next(x for x in json.loads((ROOT/'reports/ledger.json').read_text()) if x['inn']==inn and x['date']=='2026-08-14' and x['number']=='112');assert r['amount_cents']==1638300
d=next(x for x in json.loads((ROOT/'evidence/kav/reviewed.json').read_text()) if x['supplier_inn']==inn and x['number']=='6856');assert d['amount_cents']==r['amount_cents']
evidence='Пользователь подтвердил: счёт ДИАФЛЕКС6856 делим пополам на Примаверу и JetCar 1 этаж Вентиляция. По8191,50 ₽ на сделки862 и858. Только распределение оплаты, без товарной приёмки.'
x={'confirmed':True,'inn':inn,'number':'6856','amount_cents':1638300,'source':evidence,'invoice_source':d['source'],'sha256':hashlib.sha256(Path(d['source']).read_bytes()).hexdigest(),'allocations':[{'deal_id':'862','project':'ЖК Примавера','amount_cents':819150},{'deal_id':'858','project':'JetCar — 1 этаж, вентиляция','amount_cents':819150}]}
u=ROOT/'user_rules.json';rules=json.loads(u.read_text());old=rules.setdefault('confirmed_payment_allocations',{}).get(r['id']);assert not old or old==x;rules['confirmed_payment_allocations'][r['id']]=x;atomic(u,rules);atomic(D/'confirmation.json',{'bank_operation_id':r['id'],**x});print('confirmed',r['id'],m[inn]['contractor_id'])
