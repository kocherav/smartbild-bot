import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/continuation_oct6';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';mapping=json.loads(mp.read_text());inn='4004022080'
if not mapping.get(inn,{}).get('contractor_id'):
 if mapping.get(inn,{}).get('state')=='creating':raise ValueError('Previous creation unresolved')
 # Existing ООО ТУРКОВ cards have INN7723837971, a different legal entity.
 payload={'contentType':'ContractorCompany','name':'ООО «ТУРКОВ ЗАВОД»','type':{'contentType':'ContractorType','id':'5'},'description':'ИНН4004022080. Реквизиты по счёту1952 от24.06.2026.','contactInfo':[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':'249832, Калужская область, Дзержинский район, г. Кондрово, ул. Советская, комната15'}]}
 mapping[inn]={'state':'creating','payload':payload};atomic(mp,mapping)
 resp=wait_budget(a._call,'POST','/contractorCompany',json_body=payload);atomic(D/'turkov_supplier_created.json',resp);cid=resp['data']['id'];mapping[inn].update(contractor_id=cid,state='created',basis='Different supplier INN4004022080; existing TURKOV cards have INN7723837971; source invoice1952 legal address');atomic(mp,mapping)
print(mapping[inn]['contractor_id'])
