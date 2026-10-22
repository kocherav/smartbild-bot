from pathlib import Path as _QueuePath
if (_QueuePath(__file__).resolve().parents[1]/'data/review_registry.json').exists():
    raise SystemExit('Архивный обработчик отключён: рабочий реестр — finance/data/review_registry.json; обновление — finance/review_registry.py')
import json,re,collections
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/finish_all';rows=json.loads((R/'reports/ledger.json').read_text());remaining={r['id']:r for r in rows if not r.get('crm_operations') and not r.get('installer_payment_id')};requests=json.loads((R/'reports/document_requests.json').read_text());questions=[];assigned=set()
def add(kind,label,refs,rs,question,evidence=''):
 if not rs:return
 questions.append(dict(number=len(questions)+1,kind=kind,supplier=label,invoices=refs,bank_ids=[r['id'] for r in rs],payments='; '.join(f"{r['company']} {r['date']} №{r['number']}: {r['amount_cents']/100:.2f} ₽" for r in rs),amount_cents=sum(r['amount_cents'] for r in rs),question=question,evidence=evidence));assigned.update(r['id'] for r in rs)
for kind in ['found','pending_assistant_review']:
 for x in requests[kind]:
  targets={(d,n) for d,n in re.findall(r'(\d{4}-\d{2}-\d{2}) №([^, ]+)',x[4])}
  rs=[r for r in remaining.values() if r['company']==x[2] and r['inn']==x[1] and (r['date'],r['number']) in targets]
  if not rs:continue
  if kind=='found':q='Укажите объект/сделку; если счёт относится к нескольким объектам — распределение позиций. Документ повторно присылать не нужно.'
  else:q='Пришлите оплаченный счёт/заказ (или укажите, к какой сделке он приложен) и объект либо назначение платежа.'
  if x[3]=='ПКБ-00002943':q='Платёж 107230,90 ₽ целиком относится к Примавере? Какая версия итоговая: 164460,55 или 114370,90 ₽? Документы уже есть.'
  if x[3]=='ПКБ-00003477':q='Укажите объекты для счёта 3477 на 87255,35 ₽ и платежа 13505,65 ₽. Последний относится к найденному счёту 3617, несмотря на номер 3477 в назначении?'
  if x[3]=='ЭК00-119581':q='Распределение: из 96 м лотка 76 м уже запланированы на сделку 894; куда оставшиеся 20 м? Платёж 83129,92 ₽ — частичный по счёту 89036,80 ₽ или есть исправленная версия?'
  if x[3]=='42' and x[1]=='615518680653':q='Для какого раздела/этажа на Подвойского 5/19 выполнено бурение (два отверстия 600×100 и одно 100 мм под углом)? Счёт есть; по этому адресу несколько сделок.'
  if x[3]=='42965':q='На какие объекты кондиционеры? Счёт 42965 на 52431,12 ₽ есть; доплата 27488,16 ₽ относится к нему или к счёту 44245 на эту же сумму?'
  if x[3]=='44472':q='Нужен объект и подтверждение связи счёта 44472 с УПД TR0000013461/TR00000134661: в переписке уже найдено подтверждение учёта суммы 34207,49 ₽, но нет однозначной связи со сделкой.'
  if x[1]=='183513773502':q='Мероприятие по счёту 37 на 55000 ₽ — деловое или личное? Если деловое, укажите цель; если для объекта — объект.'
  add('Объект по найденному счёту' if kind=='found' else 'Документ или назначение',x[0],x[3],rs,q,x[8])
# Corporate-card purchases grouped by merchant, not one request for each payment.
cards=collections.defaultdict(list)
for r in remaining.values():
 if r['id'] not in assigned and 'по карте ' in r['purpose'] and r['category']!='Личные расходы':
  merchant=r['purpose'].split(' по чеку ')[0].split('\\')[-1];cards[merchant].append(r)
for merchant,rs in sorted(cards.items()):
 q='Для чего покупка: объект (название), общие нужды компании или личное? Для рабочих покупок нужен чек с составом, если его нет в документах сделки.';e='В выписке видны продавец, дата и сумма; состава и объекта недостаточно.'
 if 'HUAWEI' in merchant:q='Детские часы HUAWEI WATCH KIDS X1 с Care+ за 18000 ₽ — личная покупка? Чеки уже найдены, присылать их не нужно.';e='16.09 предоплата18000;18.09 полный расчёт с зачётом18000, новых денег0. Это одна покупка, не две.'
 add('Покупки по карте',merchant,'',rs,q,e)
personal=[r for r in remaining.values() if r['category']=='Личные расходы'];add('Личные — назначение уже подтверждено','Карта 8387','',personal,'Кто держатель карты 8387 и как закрываем личные траты: возмещает компании или требуется другое оформление? Повторно подтверждать, что эти 16 покупок личные, не нужно.','Личные траты уже исключены из затрат объектов. Без основания не записываются как зарплата, дивиденды или заём.')
own=[r for r in remaining.values() if r['category']=='Перевод между своими счетами'];add('Встречные выписки','ИНСИС — свои счета','Т-Банк …00895; Озон Банк …00658',own,'Нужны выписки ИНСИС: Т-Банк 40702810910000000895 и Озон Банк 40702810700000200658 за май–октябрь. Даты списаний известны; зачисление на другие счета пока не подтверждено.','Т-Банк5 переводов по350000 ₽; Озон18000 ₽. В почтовых заголовках найдена выписка Т-Бизнес по ИП, не по ИНСИС.')
for r in remaining.values():
 if r['id'] not in assigned:
  q='Уточните назначение и основание платежа: '+r['purpose']
  if r['category']=='Штрафы':q='Штраф АМПП25000 ₽ по постановлению0355431010126070201071756: за какую машину и кто несёт расход — компания или водитель?'
  add('Назначение',r['counterparty'],r['references'],[r],q,'; '.join(r['flags']))
assert assigned==set(remaining)
for cat,q in [('Выдача под отчёт','Выдача Светлане300000 ₽ уже внесена. Нужен авансовый отчёт/перечень покупок, чтобы распределить фактические расходы и остаток.'),('Взыскание','Списание143011,98 ₽ уже внесено. Нужна детализация ФНС по решению10630 от29.05.2026 для разделения налога, пеней и штрафов.')]:
 rs=[r for r in rows if r['category']==cat];add('Документ к проведённой выплате',rs[0]['counterparty'],'',rs,q)
rs=[r for r in rows if r['inn']=='9728104795' and r['date']=='2026-07-30' and r['amount_cents']==1280665];add('Сверка суммы проведённого счёта','ОЗОНЭЙР','208098',rs,'Обе оплаты отнесены на сделку858. Всего87642,35 ₽, найденный счёт74835,70 ₽. Нужна итоговая версия на доплату12806,65 ₽ либо подтверждение переплаты.','Объект подтверждён исходным счётом в архиве сделки; товарная приёмка не создавалась.')
# Preserve question numbers when confirmed payments disappear from the remaining list.
old_path=D/'owner_questions.json';old=json.loads(old_path.read_text()) if old_path.exists() else {}
def signature(q):return (q['kind'],q['supplier'],q['invoices'],tuple(sorted(q['bank_ids'])))
old_items=old.get('groups',[])+old.get('resolved_groups',[])
number_by_signature={signature(q):q['number'] for q in old_items};next_number=max([q['number'] for q in old_items]+[0])+1
for q in questions:
 if signature(q) in number_by_signature:q['number']=number_by_signature[signature(q)]
 elif old_items:q['number']=next_number;next_number+=1
out={'bank_rows':len(rows),'posted_bank_rows':sum(bool(r.get('crm_operations')) for r in rows),'installer_rows':sum(bool(r.get('installer_payment_id')) for r in rows),'unposted_rows':len(remaining),'personal_classified_rows':len(personal),'groups':questions,'mail_scope':'Проверены доступные вложения обеих почт, переписка/файлы сделок, реестры закупок и монтажа, OneDrive и дополнительно 40 писем с чеками и банковским уведомлением. Полнотекстовый поиск IMAP возвращал ошибки сервера; отсутствие документа во всей почте не утверждается.'}
out['resolved_groups']=old.get('resolved_groups',[])
(D/'owner_questions.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('questions',len(questions),'unposted bankrows',len(remaining),'categories',dict(collections.Counter(q['kind'] for q in questions)))
lines=['ОСТАТОК ПО ВЫПИСКЕ — 06.10.2026','Не нужно пересматривать все337 строк. Вопросы сгруппированы; найденные документы повторно не запрашиваются.','']
for q in questions:
 lines.extend([f"{q['number']}. {q['supplier']} — {q['invoices'] or q['kind']}",q['payments'],q['question'],('Уже проверено: '+q['evidence']) if q['evidence'] else '', ''])
(R/'reports/Только_вопросы_по_выписке.txt').write_text('\n'.join(lines))
