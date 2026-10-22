"""Preserve cash identity when a bank payment covers both projects and own needs."""
import hashlib

def normalize_allocations(row):
    result=[]
    for item in row['confirmed_payment_allocations']:
        scope=item.get('allocation_scope','project')
        deal=str(item.get('deal_id') or '')
        if scope not in ('project','company') or (scope=='project') != bool(deal):
            raise ValueError('Allocation scope and deal disagree')
        if item['amount_cents']<=0:raise ValueError('Nonpositive allocation')
        if scope=='company' and not item.get('category'):raise ValueError('Company category required')
        result.append(dict(deal_id=deal,cents=item['amount_cents'],invoice=item.get('invoice_number') or row['document_numbers'],posting_key=item.get('posting_key'),allocation_scope=scope,category=item.get('category'),operation_type=item.get('operation_type')))
    if sum(x['cents'] for x in result)!=row['amount_cents']:raise ValueError('Bank amount differs from allocations')
    if len({(x['deal_id'],x['invoice'],x.get('category'),x.get('posting_key')) for x in result})!=len(result):raise ValueError('Duplicate allocation identity')
    return result

def allocation_key(row,allocation,journal):
    key=allocation.get('posting_key')
    if key:
        old=journal[key]
        if old['bank_operation_id']!=row['id'] or old['amount_cents']!=allocation['cents']:raise ValueError('Correction changed payment identity')
        return key
    scope=allocation['deal_id']
    if allocation.get('allocation_scope')=='company':scope='company:'+allocation['category']
    return hashlib.sha256((row['id']+'|'+scope+'|'+allocation['invoice']).encode()).hexdigest()[:24]
