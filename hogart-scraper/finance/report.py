#!/usr/bin/env python3
"""Rebuild review workbook from ledger; workbook is a report, never the source database."""
import collections, csv, datetime as dt, json
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from xlsx_compat import save_workbook
from ledger import ROOT, connect, records
from review_registry import sync, active, atomic, document_projection

HEADERS=['ID','Компания','Дата движения','Дата документа','№ документа','Приход, ₽','Расход, ₽','Контрагент','ИНН','Статья ДДС','Объект / заказ','Статус','Вид потока','Внутригрупповой','Основания из назначения','НДС из текста','Требует уточнения','Связанный платёж','Назначение платежа','Счёт организации','Основание связи с Мегапланом','Операции Мегаплана','Кандидат сделки — не подтверждён','Кто разбирает','Период зарплаты','Решение пользователя']

def op_values(r):
    return [r['id'],r['company'],dt.date.fromisoformat(r['date']),dt.date.fromisoformat(r['document_date']),r['number'],r['amount_cents']/100 if r['direction']=='in' else 0,r['amount_cents']/100 if r['direction']=='out' else 0,r['counterparty'],r['inn'],r['category'],r['project'],r['status'],r['flow'],r['group'],r['references'],r['vat'],'; '.join(r['flags']),r['link'],r['purpose'],r['account'],r.get('crm_evidence',''),r.get('crm_operations',''),r.get('crm_candidate',''),r.get('review_owner',''),r.get('salary_period',''),r.get('decision_note','')]

def sheet(wb,name,headers,values,money_cols=()):
    ws=wb.create_sheet(name);ws.append(headers)
    for row in values:
        ws.append(row)
        for cell in ws[ws.max_row]:
            if isinstance(cell.value,str):cell.data_type='s' # Never execute content as a formula.
    ws.freeze_panes='C2';ws.sheet_view.showGridLines=False;ws.auto_filter.ref=ws.dimensions
    for c in ws[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='153E4D');c.alignment=Alignment(wrap_text=True,vertical='center')
    ws.row_dimensions[1].height=34
    for idx,h in enumerate(headers,1):
        width=20
        if h in ['Назначение платежа','Требует уточнения','Что требуется','Причина']:width=65
        elif h in ['Контрагент','Статья ДДС','Вопрос / действие']:width=36
        elif h=='ID':width=18
        elif h in ['ИНН','№ документа']:width=16
        ws.column_dimensions[get_column_letter(idx)].width=width
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment=Alignment(vertical='top',wrap_text=True)
            if isinstance(c.value,dt.date):c.number_format='DD.MM.YYYY'
            if c.column in money_cols:c.number_format='#,##0.00;[Red]-#,##0.00'
        if row[0].row%2==0:
            for c in row:c.fill=PatternFill('solid',fgColor='EFF5F7')
    return ws

def main():
    db=connect(ROOT/'data/ledger.sqlite');accounts=json.loads((ROOT/'accounts.json').read_text());rows=records(db,accounts)
    wb=Workbook();wb.remove(wb.active)
    statuses=collections.Counter(r['status'] for r in rows)
    checks=[['Назначение','Управленческий учёт движения денег. Не бухгалтерские проводки и не расчёт прибыли.'],['Период','Периоды и время формирования каждой выписки — на листе Контроль.'],['Операций',len(rows)],['Статья определена по правилу',statuses['По правилу ДДС']],['Требуют уточнения',statuses['Требует уточнения']],['Сверены с реестром Мегаплана',statuses['Сверено с реестром Мегаплана']],['Сверены с реестром монтажников',statuses['Сверено с реестром монтажников']],['Подтверждены пользователем',statuses['Подтверждено пользователем']],['Деньги','Все суммы получены из банковских полей, а не из текста назначения.'],['Объекты','Пустое поле означает отсутствие подтверждённой привязки. Объекты не придуманы.'],['НДС','Текст из назначения; правильность ставки и суммы требует первичных документов.'],['Как читать очередь','Рабочая очередь — задачи ассистента, не анкета для владельца. Лист Вам — только вопросы, требующие вашего решения.'],['Как исправить','Сообщить ID операций или группу с конкретной разбивкой. Решение вносится в базу с комментарием; отчёт пересоздаётся.'],['Автоматизация','Почта info@innsis.ru: существующий доступ Яндекс IMAP проверен. Мегаплан и реестр закупок используются для сопоставления. Проверка ZIP ежедневно в 10:30 по Москве. Однозначные оплаты проводятся с защитой от дублей; спорные остаются в очереди.'],['Полнота','Выписка за день создания может быть промежуточной. Окончание периода не доказывает закрытие дня.'],['Хранение','Реестр SQLite — источник данных; этот Excel — отчёт. Правки в Excel не импортируются автоматически.']]
    sheet(wb,'Начало',['Показатель','Значение'],checks)
    ws=sheet(wb,'Операции',HEADERS,[op_values(r) for r in rows],(6,7));ws.column_dimensions['A'].hidden=True
    ws=sheet(wb,'Уточнения',HEADERS,[op_values(r) for r in rows if r['status']=='Требует уточнения'],(6,7));ws.column_dimensions['A'].hidden=True
    registry=sync(rows)
    work=active(registry)
    questions=[]
    for t in work:
        questions.append([t['id'],t.get('company',''),t['supplier'],t.get('inn',''),
            t.get('category',t['kind']),len(t['bank_ids']),t['amount_cents']/100,
            t['action'],'Пользователь' if t['owner']=='user' else 'Ассистент',', '.join(t['bank_ids']),t.get('invoices',''),t.get('name',''),t.get('qty','')])
    ws=sheet(wb,'Рабочая очередь',['Задача','Компания','Контрагент','ИНН','Тип','Операций','Сумма, ₽','Что требуется','Ответственный','ID операций','Счёт','Позиция','Остаток, ед.'],questions,(7,))
    ws.column_dimensions['J'].hidden=True
    owner_questions=[[t['action'],''] for t in work if t['owner']=='user']
    sheet(wb,'История ответов',['Поставщик','Счета','Ответ','Результат'],[
        [q.get('supplier',''),q.get('invoices',''),q.get('owner_answer') or q.get('answer',''),q.get('resolution','')]
        for q in registry['historical_answers']])
    sheet(wb,'Вам',['Вопрос','Ваш ответ'],owner_questions or [['Открытых вопросов к вам сейчас нет','Ваши ответы сохранены; остальные позиции разбирает ассистент.']])
    sheet(wb,'Сверка монтажника',['Дата','Платёж №','Банк, ₽','Расчётная сумма, ₽','Запись существующего реестра','Отчёты','Связанные сделки','Результат'],[[r['date'],r['number'],r['amount_cents']/100,r['installer_settlement_cents']/100,r['installer_payment_id'],', '.join(x['report_date'] for x in r['installer_report_links']),r['project'],'Уже учтено; повторное начисление не создавалось'] for r in rows if r.get('installer_payment_id')],(3,4))
    allocations=[]
    for r in rows:
        for a in r.get('project_allocations',[]):
            allocations.append([r['company'],r['date'],r['number'],r['document_numbers'],a['project'],a['unit_model'],a['unit_cents']/100,a['controllers'],a['controller_cents']/100,a['valves'],a['valve_unit_cents']*a['valves']/100,a['amount_cents']/100,r['decision_note'],r.get('crm_posting_status','')])
    sheet(wb,'Распределение по объектам',['Компания','Дата платежа','Платёж №','Счёт','Объект','Модель установки','Установка, ₽','Пультов','Пульты, ₽','Клапанов','Клапаны, ₽','Всего по объекту, ₽','Основание','Статус Мегаплана'],allocations,(7,9,11,12))
    grouped=collections.defaultdict(lambda:[0,0,0])
    for r in rows:
        k=(r['company'],r['date'][:7],r['category'],r['group']);v=grouped[k];v[0 if r['direction']=='in' else 1]+=r['amount_cents'];v[2]+=1
    sheet(wb,'ДДС по месяцам',['Компания','Месяц','Статья ДДС','Внутригрупповой','Приход, ₽','Расход, ₽','Движение нетто, ₽','Операций'],[[*k,v[0]/100,v[1]/100,(v[0]-v[1])/100,v[2]] for k,v in sorted(grouped.items())],(5,6,7))
    # Group cash flow excludes ONLY paired intercompany movements; unpaired transfers remain visible.
    groupflow=collections.defaultdict(lambda:[0,0])
    for r in rows:
        if r['group']=='Между компаниями группы' and r['link'].startswith('Парный перевод'):continue
        groupflow[(r['date'][:7],r['flow'],r['category'])][0 if r['direction']=='in' else 1]+=r['amount_cents']
    sheet(wb,'ДДС группы',['Месяц','Вид потока','Статья ДДС','Приход, ₽','Расход, ₽','Движение нетто, ₽'],[[*k,v[0]/100,v[1]/100,(v[0]-v[1])/100] for k,v in sorted(groupflow.items())],(4,5,6))
    control=[]
    for sh,source,account,start,end,metadata in db.execute('SELECT * FROM statements ORDER BY account,start,end'):
        s=json.loads(metadata);b=s['balance'];h=s['header']
        control.append([accounts.get(account,{}).get('name','Неизвестно'),account,date_text(start),date_text(end),float(b['НачальныйОстаток']),float(b['ВсегоПоступило']),float(b['ВсегоСписано']),float(b['КонечныйОстаток']),'Обороты и остатки сходятся',h.get('ДатаСоздания','')+' '+h.get('ВремяСоздания',''),source,sh])
    sheet(wb,'Контроль',['Компания','Счёт','С','По','Начальный остаток, ₽','Поступило, ₽','Списано, ₽','Конечный остаток, ₽','Проверка','Создано банком','Источник','SHA256'],control,(5,6,7,8))
    sheet(wb,'Между компаниями',HEADERS,[op_values(r) for r in rows if r['group']=='Между компаниями группы'],(6,7))
    sheet(wb,'Справочник счетов',['Счёт','Компания','ИНН','Статус'],[[a,x['name'],x['inn'],'Подтверждён выпиской' if x['inn'] else 'Нужно определить владельца'] for a,x in accounts.items()])
    dest=ROOT/'reports/Разнесение_выписок.xlsx';temp=dest.with_suffix('.tmp.xlsx');save_workbook(wb,temp);temp.replace(dest)
    # Verify structure and all operation amounts after serialization.
    verify=load_workbook(dest,data_only=False);ops=verify['Операции']
    assert ops.max_row==len(rows)+1
    assert round(sum((ops.cell(i,6).value or 0) for i in range(2,ops.max_row+1))*100)==sum(r['amount_cents'] for r in rows if r['direction']=='in')
    assert not any(c.data_type=='f' for ws in verify for row in ws for c in row)
    with (ROOT/'reports/operations.csv').open('w',encoding='utf-8-sig',newline='') as out:
        writer=csv.writer(out,delimiter=';');writer.writerow(HEADERS)
        for r in rows:
            vals=op_values(r);writer.writerow([("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for v in vals])
    atomic(ROOT/'reports/questions.json',questions)  # Compatibility projection; never an input queue.
    atomic(ROOT/'reports/document_requests.json',document_projection(registry))
    legacy=ROOT/'reports/Недостающие_счета_по_поставщикам.xlsx'
    if not legacy.is_symlink():
        if legacy.exists():
            backup=ROOT/'evidence/registry_reconciliation_20261010/Недостающие_счета_по_поставщикам.before.xlsx'
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists():
                import shutil
                shutil.copy2(legacy,backup)
            legacy.unlink()
        legacy.symlink_to(dest.name)
    print(json.dumps({'operations':len(rows),'question_groups':len(questions),'review_registry':str(ROOT/'data/review_registry.json'),'statuses':dict(statuses),'xlsx':str(dest),
                     'owner_questions':[q[0] for q in owner_questions],
                     'assistant_queue':[{'group':q[0],'company':q[1],'counterparty':q[2],'count':q[5],'amount':q[6],'reason':q[7]} for q in questions if q[8]=='Ассистент']},ensure_ascii=False))

def date_text(value):return dt.date.fromisoformat(value)
if __name__=='__main__':main()
