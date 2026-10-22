import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/continuation_oct6c';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';mapping=json.loads(mp.read_text());inn='7719228261'
if not mapping.get(inn,{}).get('contractor_id'):
 if mapping.get(inn,{}).get('state')=='creating':raise ValueError('Previous creation unresolved')
 res=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':'МИГ Электро'});atomic(D/'mig_search.json',res)
 companies=[x for x in res['data'] if x.get('contentType')=='ContractorCompany']
 if companies:raise ValueError('Inspect possible existing Ozon Group supplier cards')
 payload={'contentType':'ContractorCompany','name':'ООО «МИГ Электро»','type':{'contentType':'ContractorType','id':'5'},'description':'ИНН7719228261. Реквизиты по счётуУТ-12795 от06.07.2026.','contactInfo':[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':'107553, г. Москва, Окружной проезд, д.8, стр.1, пом.4'}]}
 mapping[inn]={'state':'creating','payload':payload};atomic(mp,mapping)
 resp=wait_budget(a._call,'POST','/contractorCompany',json_body=payload);atomic(D/'mig_supplier_created.json',resp);mapping[inn].update(contractor_id=resp['data']['id'],state='created',basis='InvoiceУТ-12795 legal identity; full payer INN registry and company name search checked');atomic(mp,mapping)
print(mapping[inn]['contractor_id'])
