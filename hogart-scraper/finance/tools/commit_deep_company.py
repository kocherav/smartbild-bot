import sys,json,hashlib
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/deep_review';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';m=json.loads(mp.read_text())
for inn,name,address,term,basis in [('4345115602','ООО «БАКСЭТ»','610007, г. Киров, ул. Ленина, 164','БАКСЭТ','Официальные реквизиты JustHost https://kb.justhost.ru/article/80: точный ИНН4345115602. Услуги по оферте: https://kb.justhost.ru/article/87. КатегорияИТ определена по поставщику и оферте; период услуг не выдуман.'),('7714887870','ГКУ «АМПП»','г. Москва','АМПП','ИНН7714887870 из выписки и официальных реквизитов parking.mos.ru. Письмо kav UID66298 содержит жалобу с тем же точным номером постановления0355431010126070201071756; прочитано изображение документа. Регистрируется факт уплаты штрафа, не решение о виновнике или налоговом учёте.')]:
 if not m.get(inn,{}).get('contractor_id'):
  assert m.get(inn,{}).get('state')!='creating'
  assert not json.loads((D/('search_'+inn+'.json')).read_text())['data'] and not json.loads((D/('search_'+term+'.json')).read_text())['data']
  payload={'contentType':'ContractorCompany','name':name,'type':{'contentType':'ContractorType','id':'5'},'description':'ИНН '+inn+'. '+basis,'contactInfo':[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':address}]}
  m[inn]={'state':'creating','payload':payload};atomic(mp,m)
  res=wait_budget(a._call,'POST','/contractorCompany',json_body=payload);atomic(D/('supplier_created_'+inn+'.json'),res);m[inn].update(state='created',contractor_id=res['data']['id'],basis=basis);atomic(mp,m)
 m[inn]['basis']=basis
m['7710045520']={'state':'existing','contractor_id':'1002777','basis':'Точный ИНН7710045520 проверен в актуальном плательщике1002871; банк указывает полисТТТ7105455658. Страховая премия компании без привязки к сделке; вид страхования и период покрытия не выдуманы.'};atomic(mp,m)
rows=json.loads((ROOT/'reports/ledger.json').read_text());manifest=ROOT/'evidence/finish_all/company_plan.json';out=json.loads(manifest.read_text());new=[]
for inn,cat,amount in [('4345115602','ИТ и подписки',343455),('7710045520','Страхование',1080634),('7714887870','Штрафы',2500000)]:
 r=next(x for x in rows if x['inn']==inn and x['amount_cents']==amount);assert r['direction']=='out'
 key=hashlib.sha256((r['id']+'|company|'+cat).encode()).hexdigest()[:24]
 p=dict(key=key,bank_operation_id=r['id'],date=r['date'],document_number=r['number'],account_id={'40702810402570001572':'20','40702810902570001580':'22'}[r['account']],kind='expense',amount_cents=amount,deal_id='',allocation_scope='company',category=cat,invoice_number=r.get('references',''),counterparty_inn=inn,operation_type='25',contractor_id=m[inn]['contractor_id'],description=f"[BANK:{key}] {cat}; банк №{r['number']}. {r['purpose']}"[:255],marker='BANK:'+key,evidence=m[inn]['basis']+' Только денежное движение; SecondarySum=0. Не включать в затраты конкретной сделки.')
 if not any(x['key']==key for x in out):out.append(p)
 new.append(p)
atomic(manifest,out);atomic(D/'company_plan.json',new);print('company reviewed',len(new),flush=True)
