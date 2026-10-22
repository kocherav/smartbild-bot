import sys,json,hashlib
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
from document_review import refs
D=ROOT/'evidence/final_answers_20261007';answers=json.loads((D/'answers.json').read_text());rows={r['id']:r for r in json.loads((ROOT/'reports/ledger.json').read_text())};rp=ROOT/'user_rules.json';rules=json.loads(rp.read_text());splits=rules.setdefault('confirmed_payment_allocations',{});cp=ROOT/'evidence/deep_review/classifications.json';classes=json.loads(cp.read_text());mp=json.loads((ROOT/'evidence/payment_correction/supplier_mapping.json').read_text());companypath=ROOT/'evidence/finish_all/company_plan.json';company=json.loads(companypath.read_text());newcompany=[];newalloc={};newdeal=json.loads((D/'new_deal_state.json').read_text())['deal_id'];posted={p['bank_operation_id'] for p in json.loads(JOURNAL.read_text())['operations'].values()};archive=[]
project={18:('892','Зоовет — офис103'),40:('857','JetCar — отопление1этажа'),42:(newdeal,'JetCar — закупки Элевел061898/065961'),43:(newdeal,'JetCar — закупки Элевел061898/065961'),46:('861','JetCar — электрика1этажа'),47:('861','JetCar — электрика1этажа')}
def prepare_company(r,cat,answer,typ='25'):
 if r['id'] in posted:return
 cid=mp.get(r['inn'],{}).get('contractor_id')
 if not cid:return
 key=hashlib.sha256((r['id']+'|company|'+cat).encode()).hexdigest()[:24]
 p=dict(key=key,bank_operation_id=r['id'],date=r['date'],document_number=r['number'],account_id={'40702810402570001572':'20','40702810902570001580':'22'}[r['account']],kind='expense',amount_cents=r['amount_cents'],deal_id='',allocation_scope='company',category=cat,invoice_number=r.get('references') or '',counterparty_inn=r['inn'],operation_type=typ,contractor_id=cid,description=f"[BANK:{key}] {cat}; банк №{r['number']}. {r['purpose']}"[:255],marker='BANK:'+key,evidence=answer+' Фиксируется только платёж поставщику. Отгрузка/приёмка и дополнительное удержание с монтажника не создаются.')
 if not any(v['key']==key for v in company):company.append(p)
 newcompany.append(p)
for ans in answers:
 if not ans['answer']:continue
 num=ans['number'];basis='Ответ владельца в обновлённом Excel07.10.2026, пункт'+str(num)+': '+ans['answer']+'.'
 for oid in ans['bank_ids']:
  r=rows[oid];old=classes.get(oid,{});fields={**old.get('fields',{}),'owner_answer':ans['answer'],'owner_answer_source':'Обновлённый Excel07.10.2026, пункт'+str(num)};clear=old.get('cleared_flags',[])
  if num!=37:clear=list(set(clear+r['flags']))
  if num in project or num==41:
   if num==41:
    allocations=[{'deal_id':'851','project':'JetCar — БП и пульты на замену','amount_cents':9889470,'invoice_number':'ЭК00-054832'},{'deal_id':'','project':'Собственные нужды','amount_cents':1983218,'invoice_number':'ЭК00-054835','allocation_scope':'company','category':'Внепроектные закупки и услуги','operation_type':'25'}];assert r['amount_cents']==11872688
    basis+=' Счёт054832: товары98894,70 и доставка900;054835:19832,18. Оплата точно равна98894,70+19832,18. Доставка900 не включена в проведённый платёж, состояние её оплаты отдельно не установлено. Новое указание заменяет прежний отказ обработки054835.'
   else:
    deal,name=project[num];allocations=[{'deal_id':deal,'project':name,'amount_cents':r['amount_cents']}]
   x={'confirmed':True,'reviewed_by':'user','inn':r['inn'],'number':refs(r)[0],'amount_cents':r['amount_cents'],'source':basis,'allocations':allocations,'cleared_flags':r['flags'],'old_question_number':num};splits[oid]=x;newalloc[oid]=x
  elif num in (15,16,17,19,38):
   fields.update(category='Закупки для Деревянко',project='',owner_allocation_scope='installer_equipment',decision_note=basis+' Оплата Трио учтена отдельно от начислений/выплат монтажнику; повторное удержание не производится.')
   prepare_company(r,'Закупки для Деревянко',basis,'23')
  elif num in (39,45):
   fields.update(project='',owner_allocation_scope='outside_projects',decision_note=basis)
   prepare_company(r,'Внепроектные закупки и услуги',basis)
  classes[oid]={**{k:r[k] for k in ('inn','amount_cents','date','account')},'fields':fields,'cleared_flags':clear}
# Previously answered own-needs payments whose verified supplier was missing.
for r in rows.values():
 if r.get('owner_answer') and 'собственные нужды' in r['owner_answer'].lower() and r['inn'] in ['782704631045','9726067241','183513773502','770406087486']:
  prepare_company(r,'Внепроектные закупки и услуги','Ранее принятый ответ владельца: '+r['owner_answer'])
for number,prefix in [('4772','1791378975814'),('5769','1791378976232')]:
 p=next(Path('/home/kocher.av/.cloudcli/assets').glob(prefix+'*'));archive.append({'deal_id':'861','source':str(p),'number':number})
archive.append({'deal_id':'851','source':'/home/kocher.av/hogart-scraper/incoming/1791375794-Счет_договор___ЭК00_054832_от_12_мая_2026_г_.pdf','number':'ЭК00-054832'})
for obj,name in [(rules,rp),(classes,cp),(company,companypath),(newcompany,D/'company_plan.json'),(newalloc,D/'reviewed_allocations.json'),(archive,D/'archive_links.json')]:atomic(name,obj)
atomic(D/'installer_equipment_links.json',[{'question':16,'bank_ids':next(x['bank_ids'] for x in answers if x['number']==16),'supplier_cost_cents':12478188,'settlement_cents':12600000,'source':'/home/kocher.av/hogart-scraper/incoming/1789550689-Зп_Арт_м__260713_070143_2_.pdf','lines':['Касета-99.000','Сплит27.000'],'status':'Удержание уже содержится в утверждённом отчёте13.07.2026. По указанию владельца сопоставлены модель и близкая сумма; закупочная стоимость отличается от суммы взаиморасчёта. Второе удержание не создавалось.'},{'question':19,'bank_ids':next(x['bank_ids'] for x in answers if x['number']==19),'supplier_cost_cents':3095040,'settlement_cents':3100000,'source':'/home/kocher.av/hogart-scraper/incoming/1790774458-Зп_Артем_260911_152447.pdf','lines':['Кондеи мои-31.000'],'status':'Совпадают период, два кондиционера для Деревянко и близкая сумма. Удержание уже в утверждённом отчёте11.09.2026; не повторяется.'}])
print('Prepared',len(newalloc),'project bank rows',len(newcompany),'company rows')
