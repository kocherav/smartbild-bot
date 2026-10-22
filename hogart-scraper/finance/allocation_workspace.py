"""Validated allocation drafts in the single review registry; no CRM writes."""
import collections
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import fcntl
import hashlib
import json
from pathlib import Path
import review_registry as queue

class Conflict(ValueError): pass

def number(value):
    try: result=Decimal(str(value))
    except (InvalidOperation,ValueError):raise ValueError('Некорректное количество или сумма')
    if not result.is_finite():raise ValueError('Количество и сумма должны быть конечными')
    return result

def cents(value):return int((number(value or 0)*100).quantize(Decimal(1),rounding=ROUND_HALF_UP))

def fingerprint(value):
    if isinstance(value,dict) and set(value)=={'invoice','stocks'}:
        inv=value['invoice']
        value={'invoice':{k:inv.get(k) for k in ('id','document_key','number','supplier_inn','buyer_inn','total','source_sha256','lines','allocations','payments','paid_total')},'intake_state':inv.get('intake',{}).get('state'),'stocks':value['stocks']}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def prorate(total, weights):
    """Integer largest-remainder apportionment. Every kopeck has one destination."""
    if total<0 or any(number(v)<0 for v in weights.values()):raise ValueError('Отрицательная сумма')
    denom=sum((number(v) for v in weights.values()),Decimal(0))
    if not denom:
        if total:raise ValueError('Нет основания для распределения суммы')
        return {k:0 for k in weights}
    exact={k:Decimal(total)*number(v)/denom for k,v in weights.items()}
    result={k:int(v) for k,v in exact.items()}
    for k in sorted(weights,key=lambda k:(-(exact[k]-result[k]),str(k)))[:total-sum(result.values())]:result[k]+=1
    return result

def source_document(procurement, key):
    invoice=next((i for i in procurement.get('invoices',[]) if i.get('document_key')==key),None)
    if not invoice:raise ValueError('Счёт не найден')
    stocks=[s for s in procurement.get('unallocated_stock',[]) if s.get('document_key')==key]
    return {'invoice':invoice,'stocks':stocks}

def public_document(source, registry):
    inv=source['invoice'];key=inv['document_key']
    import copy
    draft=copy.deepcopy(registry.get('allocation_drafts',{}).get(key))
    if draft:
        draft.pop('ledger_before',None)
        if draft.get('execution'):draft['execution']['plan'].pop('ledger_before',None)
    lines=[dict(id=s['id'],name=s['name'],sku=s.get('sku',''),qty=s['available_qty'],
                unit=s.get('unit',''),amount_cents=cents(s['available_amount']))
           for s in source['stocks'] if number(s['available_qty'])>0 or cents(s['available_amount'])>0]
    direct=sum(cents(a.get('amount')) for a in inv.get('allocations',[]))
    used=sum(cents(a.get('amount')) for s in source['stocks'] for a in s.get('allocations',[]))
    difference=cents(inv['total'])-direct-used-sum(x['amount_cents'] for x in lines)
    return dict(key=key,number=inv['number'],supplier=inv['supplier'],buyer=inv.get('buyer',''),
        total_cents=cents(inv['total']),lines=lines,revision=fingerprint(source),
        allocated_cents=direct+used,unexplained_cents=difference,
        editable=bool(lines) and abs(difference)<=1 and inv.get('intake',{}).get('state') in (None,'ready'),
        blocked_reason=inv.get('intake',{}).get('error') or ('Сначала требуется сверка версии и полного состава счёта' if abs(difference)>1 else 'Завершите разбор счёта' if inv.get('intake',{}).get('state') not in (None,'ready') else ''),
        reconciliation_stocks=[{k:s.get(k) for k in ('id','name','sku','source_line_key','available_qty','available_amount')} for s in source['stocks']],automatic_error=inv.get('automatic_error',''),invoice_id=str(inv.get('id','')),date=inv.get('date',''),intake=inv.get('intake',{}),source_available=bool(inv.get('source_path')),parsed_lines=inv.get('lines',[]),candidate_deal_ids=inv.get('candidate_deal_ids',[]),allocations=inv.get('allocations',[]),
        draft=draft,draft_revision=(draft or {}).get('revision',0),
        draft_stale=bool(draft and not draft.get('execution') and draft['source_revision']!=fingerprint(source)))

def projection(deals, root=queue.ROOT, procurement_path=queue.PROCUREMENT):
    registry=json.loads((root/'data/review_registry.json').read_text())
    procurement=json.loads(procurement_path.read_text())
    documents=[]
    for inv in procurement.get('invoices',[]):
        doc=public_document(source_document(procurement,inv['document_key']),registry)
        documents.append(doc)
    tasks=[{k:t.get(k) for k in ('id','kind','state','owner','supplier','invoices','amount_cents','action')}
           for t in queue.active(registry)]
    return dict(documents=documents,tasks=tasks,updated_at=registry['updated_at'],
                deals=[{'id':str(d['id']),'name':' · '.join(str(x) for x in (d.get('client'),d.get('address'),d['name']) if x),'url':d.get('url','')} for d in deals if not d.get('is_purchase')],
                mode='apply',explanation='Сохраните черновик или проверьте суммы и подтвердите распределение затрат. Себестоимость и рентабельность будут проверены в Мегаплане; банковские оплаты отдельно не переносятся.')

def preview(body, deals, procurement):
    key=body.get('document_key');source=source_document(procurement,key)
    if body.get('source_revision')!=fingerprint(source):raise Conflict('Счёт или остатки изменились. Обновите данные.')
    doc=public_document(source,{})
    if not doc['editable']:raise ValueError(doc['blocked_reason'] or 'Нет доступных позиций')
    selections=body.get('allocations')
    if not isinstance(selections,list) or len(selections)>1000:raise ValueError('Некорректное распределение')
    deal_ids={str(d['id']) for d in deals if not d.get('is_purchase')}
    lines={x['id']:x for x in doc['lines']};grouped=collections.defaultdict(dict)
    for part in selections:
        line_id=part.get('line_id');deal_id=str(part.get('deal_id',''));qty=number(part.get('qty'))
        if line_id not in lines or deal_id not in deal_ids or qty<=0:raise ValueError('Проверьте позицию, сделку и положительное количество')
        token=deal_id+':'+str(part.get('offer_row_id') or '')
        if token in grouped[line_id]:raise ValueError('Одна сделка повторяется в распределении строки')
        grouped[line_id][token]=qty
    attributes={(p['line_id'],str(p['deal_id'])+':'+str(p.get('offer_row_id') or '')):{k:p[k] for k in ('offer_row_id','covered_qty','identity_confirmed','reason','match_id') if k in p} for p in selections}
    allocations=[];residual=[];cost_by_deal=collections.defaultdict(int)
    for line_id,line in lines.items():
        quantities=grouped[line_id];available=number(line['qty']);assigned=sum(quantities.values(),Decimal(0))
        if assigned>available:raise ValueError('Распределено больше доступного количества: '+line['name'])
        quantities={**quantities,'unallocated':available-assigned}
        portions=prorate(line['amount_cents'],quantities)
        for token,qty in quantities.items():
            if not qty:continue
            did=token.split(':',1)[0] if token!='unallocated' else token
            item=dict(line_id=line_id,name=line['name'],source_unit=line.get('unit',''),deal_id=did,qty=str(qty),amount_cents=portions[token])
            if did=='unallocated':residual.append(item)
            else:item.update(attributes.get((line_id,token),{}));allocations.append(item);cost_by_deal[did]+=portions[token]
    # Existing allocations participate in the financial preview; never replace
    # them with just the newly selected lines or create a second payment.
    complete=collections.defaultdict(int)
    for a in source['invoice'].get('allocations',[]):complete[str(a['deal_id'])]+=cents(a['amount'])
    for s in source['stocks']:
        for a in s.get('allocations',[]):complete[str(a['deal_id'])]+=cents(a['amount'])
    for did,amount in cost_by_deal.items():complete[did]+=amount
    complete['unallocated']=sum(x['amount_cents'] for x in residual)
    total=doc['total_cents']
    rounding=total-sum(complete.values())
    if abs(rounding)>1:raise ValueError('Контроль суммы счёта не пройден')
    complete['unallocated']+=rounding
    if complete['unallocated']<0:raise ValueError('Копеечное превышение требует сверки перед распределением оплаты')
    payments=source['invoice'].get('payments',[])
    ids=[p.get('transaction_id') for p in payments]
    payment_verified=bool(payments) and all(ids) and len(ids)==len(set(ids))
    paid=sum(cents(p['amount']) for p in payments) if payment_verified else None
    if paid is not None and paid!=cents(source['invoice'].get('paid_total')):raise ValueError('Реестр оплат расходится с итогом: нужна сверка')
    shares=prorate(paid,complete) if paid is not None else {}
    summary=[dict(deal_id=did,cost_cents=amount,added_cost_cents=cost_by_deal.get(did,0),
                  proposed_payment_cents=shares.get(did)) for did,amount in sorted(complete.items()) if amount or did in cost_by_deal]
    return dict(document_key=key,source_revision=body['source_revision'],allocations=allocations,
                remainder=residual,summary=summary,total_cents=total,paid_cents=paid,
                allocated_now_cents=sum(cost_by_deal.values()),remaining_cents=sum(x['amount_cents'] for x in residual),
                payment_basis='Пропорционально стоимости позиций; требует подтверждения перед изменением связей оплаты',
                payment_warning='Оплата в реестре не подтверждена. Это не означает отсутствие оплаты.' if paid is None else '',
                state='draft',crm_applied=False)

def save_draft(body, deals, actor, root=queue.ROOT, procurement_path=queue.PROCUREMENT):
    path=root/'data/review_registry.json'
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        registry=json.loads(path.read_text());procurement=json.loads(procurement_path.read_text())
        existing=registry.get('allocation_drafts',{}).get(body.get('document_key'),{})
        if existing.get('execution',{}).get('state') in ('queued','processing','error'):raise Conflict('Распределение уже подтверждено. Дождитесь результата или продолжите обработку.')
        result=preview(body,deals,procurement);key=result['document_key']
        drafts=registry.setdefault('allocation_drafts',{});old=drafts.get(key,{})
        if body.get('draft_revision',0)!=old.get('revision',0):raise Conflict('Черновик уже изменён. Обновите данные.')
        result.update(revision=old.get('revision',0)+1,actor=str(actor),updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        drafts[key]=result
        registry.setdefault('workflow_audit',[]).append(dict(action='allocation_draft_saved',document_key=key,
            revision=result['revision'],actor=str(actor),at=result['updated_at'],snapshot=result))
        queue.atomic(path,registry)
        return result
