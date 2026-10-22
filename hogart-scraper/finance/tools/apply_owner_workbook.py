import sys,json,hashlib,copy,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/owner_workbook_20261007';answers=json.loads((D/'answers.json').read_text());byq={x['number']:x for x in answers};rows={r['id']:r for r in json.loads((ROOT/'reports/ledger.json').read_text())};rulespath=ROOT/'user_rules.json';rules=json.loads(rulespath.read_text());splits=rules.setdefault('confirmed_payment_allocations',{});reviewed=json.loads((ROOT/'evidence/deep_review/reviewed_allocations.json').read_text());classpath=ROOT/'evidence/deep_review/classifications.json';classes=json.loads(classpath.read_text());mappingpath=ROOT/'evidence/payment_correction/supplier_mapping.json';mapping=json.loads(mappingpath.read_text());companypath=ROOT/'evidence/finish_all/company_plan.json';company=json.loads(companypath.read_text());newcompany=[];newalloc={};actions=[]
a=MegaplanAPI();auth=wait_budget(v1_auth,a)
for inn,id in [('502805650665','1002765'),('770504195313','1002904'),('9703149995','1002845')]:
 payer=next(p for p in json.loads((D/('payers_'+id+'.json')).read_text())['data'] if p.get('inn')==inn)
 mapping[inn]={'state':'existing','contractor_id':id,'basis':'Точный ИНН в актуальном плательщике '+payer['id']+'; ответ владельца в Excel07.10.2026.'}
mapping['332904300538']={'state':'existing','contractor_id':'1003020','basis':'Существующий единственный контрагент «Шишаев Дмитрий», описание «Проектировщик ОВиК». Получатель банка Шишаев Дмитрий Андреевич ИНН332904300538; владелец указал проектирование847. Плательщик CRM не содержит ИНН; соответствие установлено по имени, роли и ответу владельца, не по несуществующему ИНН в карточке.'}
atomic(mappingpath,mapping)
newdeal=json.loads((D/'new_deal_state.json').read_text())['deal_id']
projects={4:(newdeal,'Квартира 44 м² — электрика'),5:('861','JetCar — электрика 1 этажа'),7:('862','Примавера'),10:('853','JetCar — кондиционирование 1 этажа'),11:('863','Level Мичуринский — Алёна Бородина'),25:('836','JetCar — электропроект мойки'),50:('847','JetCar — инженерные проекты 1 этажа')}
docs=json.loads((ROOT/'evidence/kav/reviewed.json').read_text())
with locked(REG):
 journal=json.loads(JOURNAL.read_text());reg=json.loads(REG.read_text())
 # Correct two existing portions in place; retain immutable bank markers.
 for qnum,olddeal,target in [(3,'861','894'),(9,'883','862')]:
  ans=byq[qnum];oid=ans['bank_ids'][0];x=copy.deepcopy(reviewed[oid]);parts=[p for p in journal['operations'].values() if p['bank_operation_id']==oid];p=next(p for p in parts if p['deal_id']==olddeal) if any(p['deal_id']==olddeal for p in parts) else next(p for p in parts if p.get('owner_workbook_question')==qnum)
  before=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':p['operation_id']},auth)['data']['item'];assert money_match(before,p);verify_cash_operation(before,p)
  if str((before.get('Deal') or {}).get('Id'))!=target:
   assert str(before['Deal']['Id'])==olddeal
   atomic(D/('correction_before_'+p['operation_id']+'.json'),before)
   result=wait_budget(a._call,'POST','/finOperation/'+p['operation_id']+'/linkWith',json_body={'contentType':'Deal','id':target});assert str(result['data']['id'])==target
  desc=p['description'].replace('сделка '+olddeal+'.','сделка '+target+'.')
  v1_call(a,'/BumsFinApiV01/Operation/save.api',{'Id':p['operation_id'],'Model[Description]':desc},auth)
  after=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':p['operation_id']},auth)['data']['item'];assert money_match(after,p) and str(after['Deal']['Id'])==target;verify_cash_operation(after,p);atomic(D/('correction_after_'+p['operation_id']+'.json'),after)
  basis='Ответ владельца в Excel07.10.2026, вопрос '+str(qnum)+': '+ans['answer']+'. '
  if qnum==3:basis+='Остальные кабели и мелкие наконечники99390,96 перенесены с1-го на6-й этаж; вводы5×35 оставлены в расчётной пропорции44:76 по спецификациям двух указанных объектов. '
  else:basis+='Заменяет прежнее расчётное отнесение на883. '
  p.update(deal_id=target,description=desc,evidence=basis,owner_workbook_question=qnum)
  for rp in reg['operations']:
   if str(rp.get('operation_id'))==p['operation_id']:rp['deal_ids']=[target];rp['owner_workbook_question']=qnum
  for alloc in x['allocations']:
   matching=next(v for v in parts if v['amount_cents']==alloc['amount_cents'])
   alloc['posting_key']=matching['key']
   if alloc['deal_id']==olddeal:alloc.update(deal_id=target,project='JetCar — электрика 6 этажа' if qnum==3 else 'Примавера')
  x.update(reviewed_by='user',source=basis,owner_workbook_question=qnum);splits[oid]=x;newalloc[oid]=x;actions.append({'question':qnum,'result':'Исправлена привязка существующей операции','operation_id':p['operation_id'],'old_deal':olddeal,'deal_id':target})
  atomic(JOURNAL,journal);atomic(REG,reg)
 for num,(deal,project) in projects.items():
  ans=byq[num];assert len(ans['bank_ids'])==1;oid=ans['bank_ids'][0];r=rows[oid]
  from document_review import refs
  numbers=refs(r);assert numbers
  number=numbers[0];alloc={'deal_id':deal,'project':project,'amount_cents':r['amount_cents']}
  if num==50:alloc['invoice_number']='29529926; 29529888'
  x={'confirmed':True,'reviewed_by':'user','inn':r['inn'],'number':number,'amount_cents':r['amount_cents'],'source':'Ответ владельца в Excel07.10.2026, вопрос '+str(num)+': '+ans['answer']+'. Банк сверен по компании, дате, номеру, сумме и ИНН. Только денежная оплата, не отгрузка/приёмка.','allocations':[alloc],'cleared_flags':r['flags'],'old_question_number':num}
  matches=[v for v in docs if v.get('supplier_inn')==r['inn'] and v.get('number')==number]
  if matches:
   x['invoice_source']=matches[-1]['source'];x['sha256']=hashlib.sha256(Path(x['invoice_source']).read_bytes()).hexdigest()
  if num==7:x['source']+=' Подтверждено направление всего платежа107230,90; итоговая версия счёта этим ответом не установлена, ни остаток долга, ни приёмка не выдуманы.'
  splits[oid]=x;newalloc[oid]=x;actions.append({'question':num,'result':'Подготовлено проведение по ответу владельца','deal_id':deal})
 # Preserve every answer, including confirmations of work already completed.
 for ans in answers:
  if not ans['answer']:continue
  own='собственные нужды' in ans['answer'].lower()
  for oid in ans['bank_ids']:
   r=rows[oid];old=classes.get(oid,{})
   fields={**old.get('fields',{}),'owner_answer':ans['answer'],'owner_answer_source':'Excel07.10.2026, вопрос'+str(ans['number'])}
   cleared=set(old.get('cleared_flags',[]))
   if own:
    fields.update(project='',review_owner='Ассистент: техническое оформление' if not r.get('crm_operations') else 'Не требуется',decision_note='Владелец: «'+ans['answer']+'». Вне проектных сделок. Ответ сам по себе не устанавливает личный/налоговый характер и факт оказания услуг.',owner_allocation_scope='outside_projects')
    if r['category']!='Личные расходы' and not r.get('crm_operations'):fields['status']='Назначение подтверждено; оформление отдельно'
    cleared.update(r['flags'])
   classes[oid]={**{k:r[k] for k in ('inn','amount_cents','date','account')},'fields':fields,'cleared_flags':sorted(cleared)}
   if own and not any(p['bank_operation_id']==oid for p in journal['operations'].values()) and r['inn']!='7728168971' and mapping.get(r['inn'],{}).get('contractor_id'):
    cat='Внепроектные закупки и услуги';key=hashlib.sha256((oid+'|company|'+cat).encode()).hexdigest()[:24]
    p=dict(key=key,bank_operation_id=oid,date=r['date'],document_number=r['number'],account_id={'40702810402570001572':'20','40702810902570001580':'22'}[r['account']],kind='expense',amount_cents=r['amount_cents'],deal_id='',allocation_scope='company',category=cat,invoice_number=r.get('references') or '',counterparty_inn=r['inn'],operation_type='25',contractor_id=mapping[r['inn']]['contractor_id'],description=f"[BANK:{key}] Собственные нужды; банк №{r['number']}. {r['purpose']}"[:255],marker='BANK:'+key,evidence='Ответ владельцаExcel07.10.2026: собственные нужды; без проектной сделки. Подтверждён только платёж, SecondarySum0; не является утверждением о налоговом расходе/приёмке.')
    if not any(v['key']==key for v in company):company.append(p)
    newcompany.append(p)
 atomic(rulespath,rules);atomic(classpath,classes);atomic(companypath,company);atomic(D/'reviewed_allocations.json',newalloc);atomic(D/'company_plan.json',newcompany);atomic(D/'actions.json',actions)
print('Prepared project groups',len(newalloc),'company rows',len(newcompany),'corrected2; created deal',newdeal,flush=True)
