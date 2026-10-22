import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'megaplan-crm'))
from procurement_projection import effective_registry
"""Read-only supplier invoice coverage; never alters shipment snapshots or reservations."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import re
from product_matching import compare
from matching_store import candidate


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def normalized(value):
    return re.sub(r'\s+', ' ', str(value or '').casefold().replace('ё', 'е')).strip()


def coverage(deal, positions, registry, decisions=None):
    registry=effective_registry(registry)
    decisions=decisions or {}
    record = (registry.get('deals') or {}).get(str(deal))
    items = defaultdict(list)
    for item in (record or {}).get('items', []):
        if item.get('offer_row_id'): items[str(item['offer_row_id'])].append(item)
    links = defaultdict(list)
    for invoice in registry.get('invoices', []):
        for allocation in invoice.get('allocations', []):
            if str(allocation.get('deal_id')) != str(deal): continue
            # Both arrays represent the same allocation, not two purchases.
            for line in allocation.get('source_lines') or allocation.get('updates') or []:
                if line.get('offer_row_id'):
                    links[str(line['offer_row_id'])].append((line, invoice))
    result = {}
    for row in positions:
        rid = str(row['id']); candidates = items[rid]; evidence = links[rid]
        reasons = []; reviews = []; bases = []; qty = number(row.get('quantity')); bought = Decimal(0)
        if record is None: reasons.append('Реестр закупок по сделке пока не загружен')
        if len(candidates) > 1: reasons.append('Несколько записей закупок для одной позиции')
        item = candidates[0] if len(candidates) == 1 else {}
        if item:
            if not compare(item.get('name'), row.get('name'))['same']: reasons.append('Название в реестре отличается от позиции сделки')
            if normalized(item.get('unit')).rstrip('.') != normalized(row.get('unit')).rstrip('.'): reasons.append('Единицы измерения требуют сверки')
            if number(item.get('qty')) != qty: reasons.append('Количество в реестре отличается от сделки')
        for line, inv in evidence:
            # A supplier quantity cannot cover more than one allocation twice.
            source_key=line.get('key') or line.get('source_line_key')
            source_qty=number(line.get('source_qty'))
            if source_key and source_qty is not None:
                shares=[x for a in inv.get('allocations',[]) for x in (a.get('source_lines') or a.get('updates') or []) if str(x.get('key') or x.get('source_line_key')).casefold()==str(source_key).casefold()]
                amounts=[number(x.get('source_qty_used',x.get('qty_used'))) for x in shares]
                if all(x is not None for x in amounts) and sum(amounts)>source_qty:
                    reasons.append('Количество строки счёта распределено сверх закупленного объёма')
            used = number(line.get('qty_used'))
            if used is None: reasons.append('Количество в счёте требует проверки')
            else: bought += used
            rule=compare(row.get('name'),line.get('source_name'))
            key,_=candidate(deal,row,line,inv)
            decision=decisions.get(key,{})
            if line.get('identity_confirmed'):
                bases.append(line.get('identity_reason') or 'Сопоставление подтверждено');continue
            if rule['same']: bases.append(rule['basis'])
            else:
                accepted=decision.get('state') in ('auto','accepted') and not rule['conflicts']
                if not accepted: reasons.append('; '.join(rule['conflicts']) or 'Название в счёте: ' + str(line.get('source_name') or 'не указано'))
                else: bases.append('Подтверждено пользователем' if decision['state']=='accepted' else 'Соответствие подтверждено ИИ')
                reviews.append({**decision,'id':key,'state':decision.get('state','blocked' if rule['conflicts'] else 'queued'),'source_name':line.get('source_name') or '', 'quantity':line.get('qty_used'),'invoice_number':inv.get('number') or '', 'hard_conflicts':rule['conflicts'],'conflicts':rule['conflicts'] or decision.get('conflicts',[])})
        if item and number(item.get('actual_qty')) != bought: reasons.append('Итог реестра не совпадает с распределёнными строками счетов')
        if qty is None or qty <= 0: reasons.append('Объём сделки требует проверки')
        elif bought and bought != qty:
            reasons.append('Не хватает ' + str(qty-bought) + ' ' + str(row.get('unit','')) if bought < qty else 'Количество закупки превышает объём сделки')
        if evidence and not item: reasons.append('Нет сопоставленной строки в спецификации закупок')
        if not evidence and item and number(item.get('actual_qty')) and number(item.get('actual_qty')) > 0:
            reasons.append('Нет подтверждающих строк счетов')
        state = 'attention' if reasons else 'full' if bought > 0 else 'missing'
        if not reasons and not evidence and row.get('kind') == 'work' and item and number(item.get('planned_total')) == 0:
            state = 'not_required'
        labels = {'full':'Закуплено полностью', 'attention':'Требует проверки', 'missing':'Нет в закупках', 'not_required':'Работы — без закупки материалов'}
        detail = f'По счетам: {bought} из {row.get("quantity")} {row.get("unit", "")}'
        if state == 'missing': reasons.append('Связанные строки счетов поставщиков не найдены')
        if state == 'not_required': detail = 'Для этой строки закупка материалов не предусмотрена'
        result[rid] = {'state':state, 'label':labels[state], 'reason':'; '.join(dict.fromkeys(reasons)), 'detail':detail,
                       'matches':reviews,'match_basis':list(dict.fromkeys(bases)),
                       'invoices':list({str(n.get('id') or n.get('number')):{k:str(n.get(k) or '') for k in ('id','number','date','supplier')} for _, n in evidence}.values())}
    return result
