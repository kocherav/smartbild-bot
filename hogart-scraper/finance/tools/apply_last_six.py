from pathlib import Path as _QueuePath
if (_QueuePath(__file__).resolve().parents[1]/'data/review_registry.json').exists():
    raise SystemExit('Архивный обработчик отключён: рабочий реестр — finance/data/review_registry.json; обновление — finance/review_registry.py')
import sys,json,hashlib
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
from openpyxl import load_workbook
from document_review import refs
D=ROOT/'evidence/last_six_20261007';src=Path('/home/kocher.av/.cloudcli/assets/1791380785166-236988506-____________________________________07_10_2026_______________.xlsx');w=load_workbook(src,read_only=True);answers={r[0]:r[7] for r in list(w['Только ваши вопросы'].values)[1:]};assert len(answers)==6 and all(answers.values());qpath=ROOT/'evidence/finish_all/owner_questions.json';qs=json.loads(qpath.read_text());atomic(D/'questions_before.json',qs);atomic(D/'answers.json',answers);atomic(D/'source.json',{'source':str(src),'sha256':hashlib.sha256(src.read_bytes()).hexdigest()});rows={r['id']:r for r in json.loads((ROOT/'reports/ledger.json').read_text())};rulespath=ROOT/'user_rules.json';rules=json.loads(rulespath.read_text());cp=ROOT/'evidence/deep_review/classifications.json';classes=json.loads(cp.read_text());new={};a=MegaplanAPI()
for ident in ['790','847','855','869','861']:
 x=wait_budget(a._call,'GET','/deal/'+ident);atomic(D/('deal_'+ident+'.json'),x);print('verified deal',ident,x['data']['description'],flush=True)
def project(deal,name,cents,invoice=None):
 d={'deal_id':deal,'project':name,'amount_cents':cents}
 if invoice:d['invoice_number']=invoice
 return d
def own(cents,invoice=None):return {**project('','Собственные нужды',cents,invoice),'allocation_scope':'company','category':'Внепроектные закупки и услуги','operation_type':'25'}
for g in qs['groups']:
 num=g['number'];answer=answers[num];basis='Новый ответ владельца Excel07.10.2026, пункт'+str(num)+': '+answer+'.'
 for oid in g['bank_ids']:
  r=rows[oid];old=classes.get(oid,{});fields={**old.get('fields',{}),'owner_answer':answer,'owner_answer_source':'Последние6ответов Excel07.10.2026'}
  if num==54:
   fields.update(project='',owner_allocation_scope='outside_projects',decision_note=basis+' Объект уточнять не требуется. Для корректной карточки продавца нужен чек, банковский ИНН не является ИНН продавца.',status='Назначение подтверждено; оформление отдельно',review_owner='Ассистент: реквизиты продавца/чек')
  else:
   if num==37:
    if r['amount_cents']==5243112:alloc=[project('855','Зоовет — кабинет директора',2621556,'42965'),project('869','Автошума — кондиционер Илье',2621556,'42965')]
    else:assert r['amount_cents']==2748816;alloc=[own(2748816,'44245 (в банке42965)')]
    note=' По одинаковым AS20 принято последовательное распределение закупок: две единицы раннего счёта42965 по26215,56 на Зоовет/Илью; единица44245 за27488,16 на собственные нужды. Это правило распределения стоимости, не установление серийных номеров/факта отгрузки. Отличие моделей в клиентской спецификации не изменяет прямое указание владельца; спецификации не редактировались.'
   elif num==52:
    if r['amount_cents']==10100000:alloc=[project('790','Новогорск',9800000,'31421282'),own(300000,'31421282')]
    else:assert r['amount_cents']==7000000;alloc=[own(7000000,'31421282')]
    note=' Из171000 ровно98000 на Новогорск,73000 на собственные нужды. Проектная часть распределена по хронологии оплат:98000 из первого платежа101000; оставшиеся3000 и следующий70000 вне проекта.'
   else:
    deal,name={44:('861','JetCar — электрика1этажа'),51:('847','JetCar — проектирование ОВиК'),71:('861','JetCar — электрика1этажа')}[num];alloc=[project(deal,name,r['amount_cents'])];note=''
   if num in [51,52]:
    for item in alloc:item['operation_type']='25'
   x={'confirmed':True,'reviewed_by':'user','inn':r['inn'],'number':refs(r)[0],'amount_cents':r['amount_cents'],'source':basis+note+' Проведение только денег, товарное движение0.','allocations':alloc,'cleared_flags':r['flags'],'old_question_number':num};rules.setdefault('confirmed_payment_allocations',{})[oid]=x;new[oid]=x
  classes[oid]={**{k:r[k] for k in ('inn','amount_cents','date','account')},'fields':fields,'cleared_flags':list(set(old.get('cleared_flags',[])+r['flags']))}
atomic(rulespath,rules);atomic(cp,classes);atomic(D/'reviewed_allocations.json',new);atomic(D/'company_plan.json',[])
print('prepared',len(new),'bank rows',sum(len(x['allocations']) for x in new.values()),'parts',flush=True)
