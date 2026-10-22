import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/final_answers_20261007';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';m=json.loads(mp.read_text());rows=json.loads((ROOT/'reports/ledger.json').read_text());allp=json.loads((ROOT/'evidence/payment_correction/all_payers.json').read_text())
for inn in ['9709017890','9704254424','782704631045','9726067241','183513773502','770406087486']:
 if m.get(inn,{}).get('contractor_id'):continue
 assert m.get(inn,{}).get('state')!='creating' or (inn=='9704254424' and not (D/('created_supplier_'+inn+'.json')).exists()),'Uncertain earlier creation'
 hits=[p for p in allp if p.get('inn')==inn and not p.get('isDropped')];assert not hits,'Existing INN must be verified first'
 for kind in ['contractorCompany','contractorHuman']:
  x=wait_budget(a._call,'GET','/'+kind+'/search',params={'q':inn});atomic(D/('search_'+kind+'_'+inn+'.json'),x)
  assert not x['data'],'Search found candidates; inspect before create'
 r=next(r for r in rows if r['inn']==inn)
 payload={'contentType':'ContractorCompany','name':r['counterparty'],'type':{'contentType':'ContractorType','id':'5'},'description':'ИНН '+inn+'. Получатель платежа подтверждён банковской выпиской. Проверен полный реестр плательщиков и точный поиск ИНН; не является признанием приёмки/налогового расхода.'}
 if inn=='9709017890':payload['contactInfo']=[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':'105005, Москва, ул. Радио, д.10, стр.3, этаж2, помещения11,13'}]
 if inn!='9709017890':
  addr=json.loads((D/'supplier_address_sources.json').read_text())[inn];payload['contactInfo']=[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':addr['address']}];payload['description']+=' Адрес: '+addr['source']+'. '+addr.get('note','')
 m[inn]={'state':'creating','payload':payload};atomic(mp,m);x=wait_budget(a._call,'POST','/contractorCompany',json_body=payload);atomic(D/('created_supplier_'+inn+'.json'),x);cid=x['data']['id'];live=wait_budget(a._call,'GET','/contractorCompany/'+cid);assert inn in live['data']['description'];atomic(D/('verified_supplier_'+inn+'.json'),live);m[inn].update(state='created',contractor_id=cid,basis='Наименование и ИНН из банка; точный поиск CRM и полный реестр плательщиков без совпадений. Для ИНТТЕХНО дополнительно оба присланных счёта4772/5769.');atomic(mp,m);print('supplier verified',inn,cid,flush=True)
