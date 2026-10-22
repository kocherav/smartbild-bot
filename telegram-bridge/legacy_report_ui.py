"""Manager preview/mapping for the transition from collected legacy reports."""
import copy
import hashlib
import math
import os
import re

CONFIRM='✅ Принять сборный отчёт'
PENDING_CONFIRM='installer_report_bundle_confirm'
PENDING_MAP='installer_report_bundle_map'
PENDING_COST='installer_report_material_review'
EXTRA='🧾 Учесть отдельной затратой'
EDIT='✏️ Изменить распределение'
PENDING_EDIT='installer_report_bundle_edit'
COST_ADD='✅ Учесть материалы отдельно'
COST_SKIP='🧾 Уже учтено по счёту'

def stage(bridge,token,chat_id,session):
    result=bridge.run_installation_workflow({'action':'preview_legacy_report','session':session})
    if not result.get('ok'):
        bridge.send_message(token,chat_id,'Предварительная проверка сборного отчёта не завершена: '+str(result.get('error')))
        return False
    preview=result['result']
    if preview.get('already_accepted'):
        receipt=preview.get('receipt') or {}
        deals=', '.join('№'+str(x['deal_id']) for x in receipt.get('reports') or [])
        bridge.update_deal_ui_state(chat_id,pending=None)
        bridge.send_message(token,chat_id,f"Этот оригинал сборного отчёта уже принят. Сделки: {deals}; сумма принятых работ: {receipt.get('total')} ₽. Повторных начислений не будет. Для изменения принятого отчёта нужна отдельная корректировка.")
        return False
    if preview.get('cost_review'):
        bridge.update_deal_ui_state(chat_id,pending=PENDING_COST,installer_report=session,installer_bundle_preview=preview)
        row=preview['cost_review'][0]
        candidates=(preview.get('material_context') or {}).get(row.get('deal_id')) or []
        invoices='\n'.join(f"• Счёт №{r.get('number') or 'б/н'}, {r.get('supplier') or 'поставщик не указан'}" for r in candidates)
        bridge.send_message(token,chat_id,f"Материалы монтажника: {row.get('source')} — {row.get('amount')} ₽. Сделка №{row.get('deal_id') or 'не выбрана'}.\n"
            f"Связанные счета для проверки дубля:\n{invoices or 'Связанных счетов в реестре нет.'}\n"
            "Без чека учитывать разрешено. «Учесть материалы отдельно» подтверждает, что этот расход ещё не включён в себестоимость по счёту. "
            "«Уже учтено по счёту» не добавляет повторную себестоимость. Ни один вариант не закрывает объём работ. "
            "Чтобы изменить сделку, отправьте её номер. Итог начисления монтажнику будет показан отдельно перед приёмкой всего отчёта.",
            {'keyboard':[[{'text':COST_ADD}],[{'text':COST_SKIP}],[{'text':'❌ Отмена'}]],'resize_keyboard':True})
        return False
    if preview.get('review'):
        row=preview['review'][0]; works=(preview.get('candidates_by_deal') or {}).get(row['deal_id']) or []
        bridge.update_deal_ui_state(chat_id,pending=PENDING_MAP,installer_report=session,installer_bundle_preview=preview)
        choices='\n'.join(f"ID {w['id']} — {w['name']}, {w.get('unit')}; плановая расценка {bridge.money(w['rate'])}" for w in works if w.get('active',True))
        text=(f"Сборный отчёт: нужно сопоставить строку со сделкой №{row['deal_id']}.\n"
              f"{row['name']}\nОбъём отчёта: {row.get('quantity')}; единица: {row.get('unit')}; сумма: {row.get('amount')} ₽.\n"
              f"Причина: {row['reason']}\n\n{choices}\n\n"
              "Введите ID работы. Если количество или единицы отличаются — ID и объём в единицах ведомости через точку с запятой: 123; 2.5. "
              "Сумма строки отчёта останется прежней и будет показана перед утверждением. Данные ещё не записаны.")
        text+='\nЕсли соответствующей работы нет, выберите «Учесть отдельной затратой»: сумма войдёт в фактическую себестоимость этой сделки без закрытия объёма чужой работы.'
        bridge.send_message(token,chat_id,text,{'keyboard':[[{'text':EXTRA}],[{'text':'❌ Отмена'}]],'resize_keyboard':True})
        return False
    if not preview.get('ready'):
        bridge.send_message(token,chat_id,'В сборном отчёте нет сопоставленных работ для приёмки. Отдельные расчёты и нераспределённые строки не превращены в работы автоматически.')
        return False
    path=session.get('source_path')
    if not path or not os.path.isfile(path):
        bridge.send_message(token,chat_id,'Не найден оригинал сборного отчёта. Пришлите файл заново; начисления не записаны.')
        return False
    digest=hashlib.sha256()
    with open(path,'rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    bridge.update_deal_ui_state(chat_id,pending=PENDING_CONFIRM,installer_report=session,
        installer_bundle_preview=preview,installer_bundle_digest=digest.hexdigest())
    rows='\n'.join(f"• №{r['deal_id']}, ID работы {r['work_item_id']}: {r['name']} — {r['quantity']} {r.get('unit')}, {r['amount']} ₽"+
        (' (отличается от плановой расценки)' if r.get('rate_difference') else '') for r in preview['matched'])
    separate=len(preview.get('separate_settlements') or [])
    separate_lines='\n'.join(f"• {r.get('source') or r.get('kind') or r.get('type') or 'Отдельная строка'}: {r.get('amount','не указано')} ₽" for r in preview.get('separate_settlements') or [])
    payable=session.get('payable_amount') if session.get('payable_amount') is not None else session.get('net_total')
    material_lines='\n'.join(f"• Материалы, №{r['deal_id']}: {r.get('source')} — {r['amount']} ₽ ({'добавить себестоимость' if r['cost_decision']=='additional' else 'себестоимость уже учтена'})" for r in preview.get('materials') or [])
    material_lines+='\n'+'\n'.join(f"• Отдельная затрата, №{r['deal_id']}: {r['name']} — {r['amount']} ₽ (без закрытия работ)" for r in preview.get('additional_costs') or [])
    bridge.send_message(token,chat_id,f"Проверьте единое распределение сборного отчёта:\n{rows}\n\n"
        f"Начисление за сопоставленные работы: {preview['total']} ₽.\n{material_lines}\nОтдельных расчётных/нераспределённых строк: {separate}. "
        f"Они сохраняются в разборе и не прибавляются к объёму работ.\n{separate_lines}\nИтог взаиморасчётов исходного разбора: {payable} ₽. "
        "Он учитывается отдельно от объёма принятых работ. Исторические отчёты не меняются.\nПодтвердить?",
        {'keyboard':[[{'text':CONFIRM}],[{'text':EDIT}],[{'text':'❌ Отмена'}]],'resize_keyboard':True})
    return True

def apply_material_decision(session,preview,text):
    rows=preview.get('cost_review') or []
    if not rows:raise ValueError('Нет текущей строки материалов')
    row=rows[0];updated=copy.deepcopy(session)
    index=int(row['source_key'].split(':')[1]);target=updated['report_lines'][index]
    if target.get('kind')!='Материал':raise ValueError('Строка отчёта изменилась')
    if text.strip().isdigit():
        target['deal_id']=text.strip();target.pop('cost_confirmed',None);return updated
    if text not in (COST_ADD,COST_SKIP):raise ValueError('Выберите действие кнопкой или укажите номер сделки')
    if not row.get('deal_id') or row['deal_id'] not in preview.get('candidates_by_deal',{}):raise ValueError('Сначала укажите номер подготовленной сделки')
    target.update(cost_decision='additional' if text==COST_ADD else 'already_accounted',cost_confirmed=True)
    return updated

def apply_mapping(session,preview,text):
    row=preview['review'][0]
    if text==EXTRA:
        updated=copy.deepcopy(session);target,_=source_target(updated,row)
        target['extra_cost_confirmed']=True
        target.pop('work_item_id',None)
        return updated
    match=re.fullmatch(r'\s*(?:ID\s*)?(\d+)(?:\s*;\s*(\d+(?:[.,]\d+)?))?\s*',text,re.I)
    if not match:raise ValueError('Введите ID работы или ID; количество')
    row=preview['review'][0]
    work=next((w for w in preview['candidates_by_deal'].get(row['deal_id'],[]) if str(w['id'])==match.group(1) and w.get('active',True)),None)
    if not work:raise ValueError('Такого ID нет среди активных работ этой сделки')
    qty=match.group(2)
    if qty is None:
        if not row.get('quantity') or str(row.get('unit') or '').strip()!=str(work.get('unit') or '').strip():
            raise ValueError('Укажите объём в единицах выбранной работы: ID; количество')
        qty=row['quantity']
    qty=float(str(qty).replace(',','.'))
    if not math.isfinite(qty) or qty<=0:raise ValueError('Количество должно быть больше нуля')
    updated=copy.deepcopy(session);target,quantity_key=source_target(updated,row)
    target.pop('extra_cost_confirmed',None)
    target.update(work_item_id=str(work['id']),unit=work['unit'],manual_amount_confirmed=True)
    target[quantity_key]=qty
    return updated

def source_target(session,row):
    parts=row['source_key'].split(':')
    if parts[0]=='table':return session['exceptions'][int(parts[1])]['table_rows'][int(parts[3])],'current_qty'
    if parts[0]=='line':return session['report_lines'][int(parts[1])],'qty'
    return session['exceptions'][int(parts[1])],'qty'

def edit_rows(preview):
    return list(preview.get('matched') or [])+list(preview.get('additional_costs') or [])
