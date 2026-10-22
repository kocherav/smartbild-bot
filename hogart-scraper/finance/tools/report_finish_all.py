import sys,json,collections,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook,load_workbook
from report import sheet,HEADERS,op_values
from xlsx_compat import save_workbook
R=Path(__file__).resolve().parents[1];D=R/'evidence/finish_all';a=json.loads((D/'audit.json').read_text());assert not a['errors']
for supplement in [R/'evidence/diaflex6856/verified.json',R/'evidence/mirkli65835/verified.json',R/'evidence/deep_review/verified.json']:
 if supplement.exists():
  extra=json.loads(supplement.read_text());assert not extra['errors']
  by_operation={x['operation_id']:x for x in a['operations']}
  by_operation.update({x['operation_id']:x for x in extra['operations']});a['operations']=list(by_operation.values())
a['bank_payments']=len({x['bank_operation_id'] for x in a['operations']})
parts_count=len(a['operations']);bank_count=a['bank_payments']
rows=json.loads((R/'reports/ledger.json').read_text());byid={r['id']:r for r in rows};q=json.loads((D/'owner_questions.json').read_text());assert len(rows)==337 and parts_count==len(json.loads((R/'data/posting_journal.json').read_text())['operations'])
w=Workbook();w.remove(w.active)
sheet(w,'Итог',['Показатель','Результат'],[
 ['Всего строк исходной выписки',337],['Внесено и проверено в Мегаплане: строк банка',bank_count],['Финансовых операций CRM (есть разбивки)',parts_count],['Уже учтено в реестре монтажников; повторно не создавались',5],['Осталось без операции CRM',q['unposted_rows']],['Из них: личные классифицированы (16 ответ владельца + 1 по чеку)',q.get('personal_classified_rows',16)],['Оставшиеся без CRM: рабочие покупки, внутренние переводы и техническое оформление',q['unposted_rows']-q.get('personal_classified_rows',16)],['Новых операций CRM за это продолжение',parts_count-111],['Отдельных вопросов/групп в реестре',len(q['groups'])],['Что уже есть',''+str(sum(x['kind']=='Объект по найденному счёту' for x in q['groups']))+' групп найденных счетов требуют только объекта/разбивки, а не повторной загрузки'],['Товарное движение','У всех оплат и авансов по сделкам — 0. Отгрузка/приёмка учитываются отдельно.'],['Выписка разобрана полностью?','Нет. Доступные однозначные операции проведены; остаток требует сведений владельца.'],['Сверка CRM','Суммы, даты, счета компаний, контрагенты, сделки, типы операций, отсутствие дублей и связи с клиентскими счетами проверены чтением из CRM.'],['Клиентские счета','14: 10 оплачены полностью, 4 частично; связи оплаты со счётом проверены в обе стороны.'],['Автоматизация','Таймер каждые30 минут; повторные выписки не дублируются. Новые однозначные совпадения и известные общехозяйственные платежи; неоднозначные остаются на уточнение.'],['Достоверность поиска',q['mail_scope']],['Депозиты','20 движений тела депозита; 9 полных пар и 2 возврата размещений до начала периода. Для проверки начальной задолженности нужен апрель.'],['Счёт без движений','В архиве также есть счёт …11782 с остатком370 ₽ и без операций. Владелец не указан; к двум компаниям он не отнесён.']])
qheads=['№ вопроса','Поставщик / получатель','Счёт / заказ','Тип вопроса','Платежи','Сумма платежей, ₽','Что нужно от вас','Уже проверено','Ваш ответ']
qvalues=[[x['number'],x['supplier'],x['invoices'],x['kind'],x['payments'],x['amount_cents']/100,x['question'],x['evidence'],''] for x in q['groups']]
sheet(w,'Только ваши вопросы',qheads,qvalues,(6,))
sheet(w,'Документы уже найдены',qheads,[v for v in qvalues if v[3]=='Объект по найденному счёту'],(6,))
sheet(w,'Операции',HEADERS, [op_values(r) for r in rows],(6,7))
sheet(w,'Проверено в CRM',['Операция CRM','Компания','Дата','№ банка','Контрагент по банку','Сумма, ₽','Направление','Сделка','Счёт поставщика','Счёт CRM','Статья','Товарное движение/вторая сумма, ₽','Тип'],[[p['operation_id'],byid[p['bank_operation_id']]['company'],p['date'],p['document_number'],byid[p['bank_operation_id']]['counterparty'],p['amount_cents']/100,p['kind'],p.get('deal_id',''),p['invoice_number'],p.get('crm_invoice_id',''),p.get('category','Оплата по сделке'),p.get('secondary_cents',0)/100,p['operation_type']] for p in a['operations']],(6,12))
sheet(w,'Клиентские счета',['ID','Номер','Сумма, ₽','Оплачено, ₽','Статус'],[[i['id'],i['number'],i['total_cents']/100,i['paid_cents']/100,'Оплачен' if i['status']=='paid' else 'Частично оплачен'] for i in a['invoices']],(3,4))
sheet(w,'Монтажники без дублей',['Дата','№ банка','Получатель','Сумма, ₽','Уже учтено'],[[r['date'],r['number'],r['counterparty'],r['amount_cents']/100,r['installer_payment_id']] for r in rows if r.get('installer_payment_id')],(4,))
archives=[]
for path in [R/'evidence/posting/archive_results.json',R/'evidence/final111/client_archive.json',D/'receipt_archive.json',D/'company_document_archive.json',R/'evidence/diaflex6856/archive_results.json',R/'evidence/mirkli65835/archive_results.json',R/'evidence/deep_review/archive_results.json']:
 for x in json.loads(path.read_text()):archives.append([x.get('number',''),x.get('deal_id','') or '',x.get('source',''),x['remote'].removeprefix('onedrive:'),x.get('note','')])
for x in json.loads((R/'evidence/final111/supplier_archive_audit.json').read_text())['operations']:
 for d in x['documents']:
  if not any(row[3]==d['remote'].removeprefix('onedrive:') for row in archives):archives.append([x['invoice'],x['deal_id'],d['source'],d['remote'].removeprefix('onedrive:'),'Оплата и архив проверены'])
sheet(w,'Архив документов',['Документ','Сделка','Локальный источник','OneDrive','Примечание'],archives)
p=R/'reports/Итог_всей_выписки_06.10.2026.xlsx';save_workbook(w,p)
with zipfile.ZipFile(p) as z:
 assert z.testzip() is None
 for n in z.namelist():
  if n.endswith('.xml'):ET.fromstring(z.read(n))
t=load_workbook(p,read_only=True);assert t['Операции'].max_row==338 and t['Проверено в CRM'].max_row==parts_count+1 and t['Только ваши вопросы'].max_row==len(q['groups'])+1;t.close()
(D/'completion.json').write_text(json.dumps({'bank_rows':337,'posted_bank_rows':bank_count,'crm_operations':parts_count,'installer_rows':5,'unposted_rows':q['unposted_rows'],'personal_confirmed_rows':16,'owner_question_groups':len(q['groups']),'crm_audit_errors':0,'workbook':str(p),'all_operations_completed':False},ensure_ascii=False,indent=2));print(p)
