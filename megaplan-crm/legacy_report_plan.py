"""Read-only bridge from an old reviewed report to canonical installation rows.

No accrual, payment, plan quantity or price is changed here. A table's current
quantity is a delta, never its cumulative total. Ambiguity remains a review item.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

def norm(value):
    return re.sub(r'[^a-zа-я0-9]+',' ',str(value or '').casefold().replace('ё','е')).strip()

def unit(value):
    text=norm(value)
    return {'метр':'м','метры':'м','шт':'шт','штука':'шт','усл':'усл','услуга':'усл'}.get(text,text)

def number(value):
    try: result=Decimal(str(value).replace(' ', '').replace(',', '.'))
    except (InvalidOperation,ValueError): raise ValueError('Не указано корректное число') from None
    if not result.is_finite() or result<0: raise ValueError('Отрицательное или неконечное значение')
    return result

def plan(session,works_by_deal):
    matched=[]; review=[]; sources=[]; represented=set()
    for table_index,table in enumerate(session.get('exceptions') or []):
        if table.get('type')!='table' or not table.get('table_rows'): continue
        deal=str(table.get('deal_id') or '')
        represented.add((deal,norm(table.get('source'))))
        for index,row in enumerate(table['table_rows']):
            qty=number(row.get('current_qty')); amount=number(row.get('current_amount'))
            represented.add((deal,norm(row.get('name'))))
            if qty==0 and amount==0: continue
            sources.append({'deal_id':deal,'source_key':f'table:{table_index}:{table.get("id",0)}:{index}',
                'accepted_baseline':row.get('accepted_baseline'),'name':row.get('name'),'unit':row.get('unit'),'quantity':str(qty),'amount':str(amount),
                'extra_cost_confirmed':row.get('extra_cost_confirmed',False),'work_item_id':row.get('work_item_id'),'manual_amount_confirmed':row.get('manual_amount_confirmed',False)})
    nonwork={'Аванс','Удержание','Премия','Зачёт оборудования','Заголовок','Итог из PDF','Итог начислений из PDF','Подытог из PDF'}
    separate=[]; line_keys=set(); material_keys=set(); cost_review=[]; materials=[]
    for index,row in enumerate(session.get('report_lines') or []):
        deal=str(row.get('deal_id') or '')
        if row.get('kind')=='Материал':
            material_keys.add((deal,norm(row.get('source')),str(row.get('amount'))))
            material={**row,'deal_id':deal,'source_key':f'line:{index}'}
            try:
                amount=number(row.get('amount'))
                if not deal or deal not in works_by_deal:raise ValueError('Выберите подготовленную сделку')
                if amount<=0:raise ValueError('Нужна положительная сумма материалов')
                if row.get('cost_decision') not in ('additional','already_accounted') or row.get('cost_confirmed') is not True:
                    raise ValueError('Подтвердите отнесение затрат и отсутствие дубля счёта')
                materials.append({**material,'amount':str(amount)})
            except ValueError as exc:cost_review.append({**material,'reason':str(exc)})
            continue
        if row.get('kind') in nonwork or row.get('sign')==-1 or not deal:
            separate.append(dict(row)); continue
        if (deal,norm(row.get('source'))) in represented: continue
        line_keys.add((deal,norm(row.get('source'))))
        sources.append({'deal_id':deal,'source_key':f'line:{index}','name':row.get('source'),
            'unit':row.get('unit'),'quantity':row.get('qty'),'amount':row.get('amount'),
            'extra_cost_confirmed':row.get('extra_cost_confirmed',False),'work_item_id':row.get('work_item_id'),'manual_amount_confirmed':row.get('manual_amount_confirmed',False)})
    for index,item in enumerate(session.get('exceptions') or []):
        if item.get('type')=='table': continue
        deal=str(item.get('deal_id') or '')
        # The exception is a review annotation of the same source material,
        # not a second work item. Preserve the explicit material decision above.
        if item.get('type')=='material' and (deal,norm(item.get('source')),str(item.get('amount'))) in material_keys:
            continue
        if item.get('type') in ('settlement','discrepancy') or not deal or item.get('bucket')=='Всякая всячина':
            separate.append(dict(item)); continue
        if (deal,norm(item.get('source'))) in line_keys or (deal,norm(item.get('source'))) in represented: continue
        sources.append({'deal_id':deal,'source_key':f'exception:{index}','name':item.get('source'),
            'unit':item.get('unit'),'quantity':item.get('qty'),'amount':item.get('amount'),
            'extra_cost_confirmed':item.get('extra_cost_confirmed',False),'work_item_id':item.get('work_item_id'),'manual_amount_confirmed':item.get('manual_amount_confirmed',False)})
    used={}; additional=[]
    for row in sources:
        try:
            if row.get('extra_cost_confirmed') is True:
                amount=number(row['amount'])
                if amount<=0 or row['deal_id'] not in works_by_deal:raise ValueError('Нужны положительная сумма и подготовленная сделка')
                additional.append({**row,'amount':str(amount)});continue
            qty=number(row['quantity']); amount=number(row['amount'])
            if qty<=0: raise ValueError('Нужен объём выполнения, а не только сумма')
            works=works_by_deal.get(row['deal_id'])
            if works is None: raise ValueError('Монтажная ведомость сделки ещё не подготовлена')
            if row.get('work_item_id') is not None:
                candidates=[w for w in works if str(w['id'])==str(row['work_item_id'])]
            else:
                candidates=[w for w in works if norm(w['name'])==norm(row['name']) and unit(w.get('unit'))==unit(row.get('unit'))]
            if len(candidates)!=1: raise ValueError('Требуется явное сопоставление с позицией ведомости')
            work=candidates[0]
            if row.get('accepted_baseline') is not None and number(row['accepted_baseline'])!=number(work.get('accepted_qty',0)):
                raise ValueError('Принятый объём изменился после загрузки. Загрузите ведомость повторно для пересчёта нового выполнения')
            if not work.get('active',True): raise ValueError('Позиция исключена руководителем из ведомости')
            if unit(work.get('unit'))!=unit(row.get('unit')): raise ValueError('Единицы измерения различаются')
            rate_difference=abs(qty*number(work['rate'])-amount)>Decimal('0.01')
            if rate_difference and row.get('manual_amount_confirmed') is not True:
                raise ValueError('Сумма отчёта не соответствует утверждённой расценке')
            key=(row['deal_id'],str(work['id']))
            consumed=used.get(key,Decimal(0))+qty
            remaining=number(work['planned_qty'])-number(work.get('accepted_qty',0))
            if consumed>remaining+Decimal('0.000001'): raise ValueError('Выполнение превышает незакрытый объём ведомости')
            used[key]=consumed
            matched.append({**row,'work_item_id':str(work['id']),'quantity':str(qty),'amount':str(amount),'rate_difference':rate_difference})
        except ValueError as exc:
            review.append({**row,'reason':str(exc)})
    explicit_separate=any(r.get('bucket')=='Всякая всячина' or r.get('kind') in ('Премия','Аванс','Удержание','Зачёт оборудования') for r in separate)
    result={'matched':matched,'review':review,'separate_settlements':separate,
            'additional_costs':additional,'cost_review':cost_review,'materials':materials,'ready':bool(matched or explicit_separate or materials or additional) and not review and not cost_review,
            'total':str(sum((number(r['amount']) for r in matched),Decimal(0)))}
    result['fingerprint']=hashlib.sha256(json.dumps({'plan':result,'works':works_by_deal},sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    return result
