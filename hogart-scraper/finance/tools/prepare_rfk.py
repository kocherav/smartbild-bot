import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/continuation_oct6';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';mapping=json.loads(mp.read_text());inn='9717003403'
if not mapping.get(inn,{}).get('contractor_id'):
 if mapping.get(inn,{}).get('state')=='creating':raise ValueError('Previous creation unresolved')
 res=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':'РФК'});atomic(D/'rfk_search.json',res)
 companies=[x for x in res['data'] if x.get('contentType')=='ContractorCompany']
 if companies:raise ValueError('Inspect possible existing RFK supplier cards')
 payload={'contentType':'ContractorCompany','name':'ООО «РФК Климатические системы»','type':{'contentType':'ContractorType','id':'5'},'description':'ИНН9717003403. Реквизиты по счёту5399/МА15421 от10.08.2026.','contactInfo':[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':'129515, г. Москва, ул. Академика Королева, д.13, стр.1, пом.3Н'}]}
 mapping[inn]={'state':'creating','payload':payload};atomic(mp,mapping)
 resp=wait_budget(a._call,'POST','/contractorCompany',json_body=payload);atomic(D/'rfk_supplier_created.json',resp);mapping[inn].update(contractor_id=resp['data']['id'],state='created',basis='Invoice5399/МА15421 legal identity; full payer INN registry and company name search checked');atomic(mp,mapping)
print(mapping[inn]['contractor_id'])
