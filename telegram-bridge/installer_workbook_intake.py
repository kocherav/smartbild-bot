"""Read our quantity-based workbook as a draft, with canonical accepted quantities."""
import math
import re
import sqlite3
from pathlib import Path

DB = Path('/home/kocher.av/megaplan-crm/installations.sqlite3')
CURRENT = 'Выполнено за этот отчёт, кол-во'

def canonical(deal_id):
    with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        return {str(r['id']):dict(r) for r in db.execute("""SELECT w.*, COALESCE((SELECT SUM(ri.accepted_qty) FROM report_items ri JOIN reports r ON r.id=ri.report_id WHERE ri.work_item_id=w.id AND r.status IN ('approved','partially_approved')),0) accepted_qty FROM work_items w WHERE w.deal_id=? AND w.active=1 AND w.cost_kind='work'""",(str(deal_id),))}

def read(book):
    if 'Монтажная ведомость' not in book.sheetnames:return None
    ws=book['Монтажная ведомость'];headers={str(c.value):c.column for c in ws[2]}
    if not all(x in headers for x in ('ID','Работа','План','Расценка','Выполнено всего','Принято к оплате')):return None
    match=re.match(r'Сделка №(\d+)\s*-',str(ws['A1'].value))
    if not match:raise ValueError('В ведомости отсутствует номер сделки; скачайте её заново из «Мои монтажи»')
    did=match[1];works=canonical(did);rows=[];seen=set();current=headers.get(CURRENT)
    def num(v):
        try:n=float(str(v).replace(',','.'))
        except (ValueError,TypeError):raise ValueError('Выполнение укажите числом в единицах строки, без формулы') from None
        if not math.isfinite(n) or n<0:raise ValueError('Объём должен быть неотрицательным числом')
        return n
    for row in ws.iter_rows(min_row=3):
        ident=str(row[0].value or '')
        if not ident.isdigit():continue
        if ident in seen or ident not in works:raise ValueError('Состав ведомости изменён; скачайте актуальную ведомость из «Мои монтажи»')
        seen.add(ident);w=works[ident]
        if (' '.join(str(row[1].value).split())!=' '.join(w['name'].split()) or num(row[3].value)!=float(w['planned_qty']) or num(row[4].value)!=float(w['rate']) or str(row[2].value)!=w['unit']):
            raise ValueError('План, единицы или расценка изменились; скачайте актуальную ведомость из «Мои монтажи»')
        previous=float(w['accepted_qty']);value=ws.cell(row[0].row,current or headers['Выполнено всего']).value
        qty=(num(value) if value not in (None,'') else 0) if current else num(value)-previous
        if qty < -1e-6:raise ValueError('Накопленное выполнение меньше уже принятого; скачайте актуальную ведомость')
        if previous+qty>float(w['planned_qty'])+1e-6:raise ValueError('Выполнение превышает остаток; проверьте количество за этот отчёт')
        qty=max(0,qty);amount=round(qty*float(w['rate']),2)
        rows.append({'number':int(ident),'work_item_id':int(ident),'name':w['name'],'unit':w['unit'],'plan_qty':w['planned_qty'],'rate':w['rate'],'plan_amount':w['planned_qty']*w['rate'],'accepted_baseline':previous,'previous_qty':previous,'current_qty':qty,'current_amount':amount,'cumulative_qty':previous+qty,'remaining_qty':max(0,w['planned_qty']-previous-qty)})
    if not rows or not any(r['current_qty'] for r in rows):raise ValueError('Нового выполнения нет. В актуальной ведомости заполните «'+CURRENT+'» и пришлите файл; уже принятые объёмы повторять не нужно')
    return {'deal_id':did,'rows':rows,'column':current or headers['Выполнено всего'],'total':round(sum(r['current_amount'] for r in rows),2)}
