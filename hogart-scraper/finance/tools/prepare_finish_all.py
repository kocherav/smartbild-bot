import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/finish_all';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';m=json.loads(mp.read_text())
known={'7703363868':('1000112','ОСФР'),'7702388235':('1000214','ВЕСТ КОЛЛ'),'7727406020':('1002852','ФНС'),'7812014560':('1002861','МЕГАФОН'),'690501575701':('1002905','Кочержинская Светлана')}
for inn,(cid,name) in known.items():
 m[inn]={'contractor_id':cid,'state':'existing','basis':'Полный список плательщиков: точный ИНН; выбрана действующая карточка с финансовой историей либо первая карточка физлица'}
atomic(mp,m)
for inn,name in [('7807391482','ООО «МАРКЕР»'),('7734268607','Ассоциация «СТРОЙСПЕЦПРОЕКТ»'),('7709501144','ООО «МАНГО ТЕЛЕКОМ»'),('7714415613','ООО «ВК Цифровые Технологии»'),('7810945525','ООО «ТАЙМВЭБ.КЛАУД»')]:
 if m.get(inn,{}).get('contractor_id'):continue
 if m.get(inn,{}).get('state')=='creating':
  assert inn=='7807391482' and '422' in (D/'prepare.log').read_text(), 'Uncertain supplier creation'
 res=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':inn});atomic(D/('search_inn_'+inn+'.json'),res);assert not res['data']
 payload={'contentType':'ContractorCompany','name':name,'type':{'contentType':'ContractorType','id':'5'},'description':'ИНН '+inn+'. Идентичность подтверждена банковской выпиской; полный реестр плательщиков и поиск CRM проверены.'}
 address,source=json.loads((D/'supplier_addresses.json').read_text())[inn]
 payload['contactInfo']=[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':address}]
 payload['description']+=' Адрес: '+source
 m[inn]={'state':'creating','payload':payload};atomic(mp,m)
 res=wait_budget(a._call,'POST','/contractorCompany',json_body=payload);atomic(D/('created_'+inn+'.json'),res);m[inn].update(state='created',contractor_id=res['data']['id'],basis='Точные наименование и ИНН в банковской выписке; совпадений в реестре плательщиков/поиске нет');atomic(mp,m);print(inn,res['data']['id'],flush=True)
