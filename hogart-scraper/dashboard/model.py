import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'megaplan-crm'))
from procurement_projection import effective_registry
"""Dashboard projection. Monetary values are integer kopecks; CRM is never written."""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CRM = Path('/home/kocher.av/megaplan-crm')


def cents(value):
    if value is None or value == '': return None
    try:
        n = Decimal(str(value))
        if not n.is_finite(): return None
        return int((n * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError): return None


def money(obj):
    if not isinstance(obj, dict) or obj.get('currency') not in ('RUB', 'RUR'): return None
    return cents(obj.get('value'))


def stamp(value):
    if isinstance(value, dict):
        if value.get('value'): return str(value['value'])
        if value.get('year') and value.get('month') and value.get('day'):
            return f"{int(value['year']):04d}-{int(value['month']):02d}-{int(value['day']):02d}"
        return ''
    return str(value or '')


def load(path, default=None):
    try: return json.loads(Path(path).read_text())
    except FileNotFoundError: return default


def ref_index(payload):
    refs = {}
    def walk(value):
        if isinstance(value, dict):
            if value.get('contentType') and value.get('id') is not None:
                key = (value['contentType'], str(value['id']))
                refs.setdefault(key, {}).update(value)
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(payload)
    return refs


def project(snapshot, procurement=None, registry=None, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    procurement = effective_registry(procurement or {})
    registry = registry or {}
    refs = ref_index(snapshot)
    def resolve(ref):
        if not isinstance(ref, dict): return {}
        return {**refs.get((ref.get('contentType'), str(ref.get('id'))), {}), **ref}
    def name(ref):
        r = resolve(ref)
        return r.get('name') or ' '.join(x for x in [r.get('firstName'), r.get('lastName')] if x) or ''

    deals, owners, native_links, invoice_map = [], defaultdict(set), defaultdict(set), defaultdict(list)
    ops = {}
    for raw in snapshot['deals']:
        for op in raw.get('financeOperations') or []:
            oid = str(op['id']); owners[oid].add(str(raw['id'])); native_links[str(raw['id'])].add(oid)
            ops[oid] = resolve(op)
    for inv0 in snapshot.get('invoices') or []:
        inv = resolve(inv0)
        did = str((inv.get('deal') or {}).get('id') or '')
        if did:
            invoice_map[did].append(inv)
            for op in inv.get('financeOperations') or []:
                oid = str(op['id']); owners[oid].add(did); ops[oid] = resolve(op)
    # A local verified registry can enrich a native operation, never create a second cash event.
    registered = {str(x['operation_id']): x for x in registry.get('operations', []) if x.get('operation_id')}
    payments_by_deal = defaultdict(list)
    bad_ops = defaultdict(set)
    for oid, op in ops.items():
        targets = owners[oid]
        if len(targets) != 1:
            for did in targets: bad_ops[did].add('Платёж связан с несколькими сделками: требуется распределение')
            continue
        did = next(iter(targets)); kind = op.get('kind')
        typ = str((op.get('type') or {}).get('id') or '')
        amount = money(op.get('incomeSum') if kind == 'income' else op.get('expenseSum'))
        day = stamp(op.get('date'))[:10]
        if kind not in ('income', 'expense') or amount is None or not day or amount < 0:
            bad_ops[did].add('Часть финансовых операций требует проверки'); continue
        if day > today:
            bad_ops[did].add('Будущие финансовые операции не включены в факт'); continue
        # Sale/purchase types determine the cash side. Secondary goods amounts are never cash.
        if typ == '31': category = 'client' if kind == 'income' else 'client_refund'
        elif typ == '23': category = 'supplier' if kind == 'expense' else 'supplier_refund'
        elif typ == '25' and kind == 'expense': category = 'other_expense'
        else:
            bad_ops[did].add('Есть операции вне продаж и закупок; они не включены в оплату'); continue
        payments_by_deal[did].append({'id': oid, 'amount': amount, 'kind': kind, 'category': category,
            'date': day, 'description': op.get('description') or '', 'counterparty': name(op.get('contractor')),
            'account': name(op.get('realAccount')), 'bank_verified': oid in registered})

    for raw in snapshot['deals']:
        d = resolve(raw); did = str(d['id']); state = resolve(d.get('state')); program = resolve(d.get('program'))
        pay = sorted(payments_by_deal[did], key=lambda x: (x['date'], x['id']), reverse=True)
        warnings = list(sorted(bad_ops[did]))
        count = d.get('financeOperationsCount')
        payment_complete = count is not None and int(count) == len(native_links[did]) and not bad_ops[did]
        for inv in invoice_map[did]:
            if inv.get('financeOperationsCount') is not None and int(inv['financeOperationsCount']) != len(inv.get('financeOperations') or []):
                payment_complete = False
        if not payment_complete: warnings.append('Состав платежей неполон или требует сверки')
        received = sum(p['amount'] * (-1 if p['category'] == 'client_refund' else 1)
            for p in pay if p['category'] in ('client', 'client_refund'))
        spent = sum(p['amount'] * (-1 if p['category'] == 'supplier_refund' else 1)
            for p in pay if p['category'] in ('supplier', 'supplier_refund'))
        total = money(d.get('price'))
        if total is None: warnings.append('Стоимость сделки не определена в рублях')
        elif total == 0: warnings.append('Стоимость сделки пока нулевая')
        outstanding = max(0, total - received) if total is not None and payment_complete else None
        overpaid = max(0, received - total) if total is not None and payment_complete else None
        record = (procurement.get('deals') or {}).get(did)
        items = []
        order = (record or {}).get('hogart_order') or {}
        order_confirmed = bool(order.get('hogart_order_id')) and (order.get('state') in ('submitted', 'complete', 'completed') or order.get('procurement_complete_across_orders') is True)
        for item in (record or {}).get('items') or []:
            qty = float(item.get('qty') or 0)
            actual = float(item.get('actual_qty') or 0)
            received_qty = item.get('received_qty')
            received_qty = float(received_qty) if received_qty is not None else None
            # Existing procurement 'status' is a supplier default, not evidence of an order.
            ordered_qty = qty if order_confirmed and item.get('supplier') == 'hogart' else None
            items.append({'id': str(item.get('offer_row_id') or item.get('offer_id')), 'name': item.get('name') or '',
                'sku': item.get('sku') or '', 'supplier': item.get('supplier') or '', 'qty': qty,
                'unit': item.get('unit') or '', 'invoice_qty': min(qty, actual), 'received_qty': received_qty,
                'ordered_qty': ordered_qty, 'planned_total': cents(item.get('planned_total'))})
        supplier_invoices = []
        for inv in procurement.get('invoices') or []:
            allocs = inv.get('allocations') or []
            selected = [x for x in allocs if str(x.get('deal_id')) == did]
            if not selected and str(inv.get('deal_id')) != did: continue
            amount = sum(cents(x.get('amount')) or 0 for x in selected) if selected else cents(inv.get('total'))
            all_deal_ids = {str(x.get('deal_id')) for x in allocs if x.get('deal_id')}
            # A partial invoice allocation is not a payment allocation. Do not
            # attribute the full invoice payment to a single partial deal share.
            paid = cents(inv.get('paid_total')) if len(all_deal_ids) <= 1 and amount == cents(inv.get('total')) else None
            supplier_invoices.append({'id': str(inv.get('id')), 'number': str(inv.get('number') or ''),
                'date': str(inv.get('date') or ''), 'supplier': inv.get('supplier') or '',
                'amount': amount, 'paid': paid, 'shared': len(all_deal_ids) > 1})
        if record is None: warnings.append('Нет спецификации в реестре закупок')
        procurement_date = (record or {}).get('updated_at')
        invoices = []
        companies = set()
        for inv in invoice_map[did]:
            if name(inv.get('recipient')): companies.add(name(inv.get('recipient')))
            if inv.get('status') == 'rejected': continue
            inv_pay = {str(op['id']) for op in inv.get('financeOperations') or []}
            inv_received = sum(p['amount'] * (-1 if p['category'] == 'client_refund' else 1) for p in pay
                if p['id'] in inv_pay and p['category'] in ('client', 'client_refund'))
            invoices.append({'id': str(inv['id']), 'number': inv.get('number') or '',
                'amount': money(inv.get('sum')), 'received': inv_received, 'status': inv.get('status'),
                'date': stamp(inv.get('invoiceDate'))})
        company = ((record or {}).get('selling_company') or {}).get('name') or ', '.join(sorted(companies)) or 'Компания не указана'
        updated = stamp(d.get('timeUpdated'))
        try: age = (now - datetime.fromisoformat(updated)).days
        except (ValueError, TypeError): age = None
        result = d.get('result') or state.get('type') or 'unknown'
        alerts = []
        if result == 'active' and age is not None and age >= 90: alerts.append('stale')
        if warnings: alerts.append('data')
        if outstanding and total and received > 0: alerts.append('partial')
        if received > 0 and not order_confirmed: alerts.append('procurement')
        if overpaid: alerts.append('overpaid')
        if items and any((x['received_qty'] or 0) < x['qty'] for x in items): alerts.append('delivery')
        deals.append({'id': did, 'name': d.get('name') or 'Сделка ' + did,
            'client': name(d.get('contractor')) or 'Клиент не указан', 'address': d.get('Category1000068CustomFieldAdresObEkta') or '',
            'manager': name(d.get('manager')) or 'Ответственный не указан', 'company': company,
            'program': program.get('name') or 'Схема ' + str(program.get('id') or ''), 'program_id': str(program.get('id') or ''),
            'is_purchase': str(program.get('id')) == '17' or 'покупк' in str(program.get('name') or '').lower(),
            'state': state.get('name') or 'Статус ' + str(state.get('id') or ''), 'state_id': str(state.get('id') or ''),
            'result': result, 'total': total, 'received': received, 'spent': spent, 'outstanding': outstanding,
            'overpaid': overpaid, 'payments_complete': payment_complete, 'payments': pay,
            'invoices': invoices, 'supplier_invoices': supplier_invoices, 'items': items,
            'procurement_known': record is not None, 'procurement_at': procurement_date,
            'created_at': stamp(d.get('timeCreated')), 'updated_at': updated, 'age_days': age,
            'alerts': alerts, 'warnings': warnings, 'url': 'https://' + snapshot['domain'] + '/deals/' + did + '/card/'})
    deals.sort(key=lambda x: int(x['id']), reverse=True)
    return {'synced_at': snapshot['synced_at'], 'generated_at': now.isoformat(), 'deals': deals,
        'definitions': {'received': 'Денежная сторона операций продаж минус возвраты. Без товарного движения.',
            'outstanding': 'Стоимость сделки минус подтверждённые поступления. Это не просрочка.',
            'procurement': 'Только позиции доступных закупочных спецификаций. Учёт счёта не подтверждает заказ или получение.',
            'scope': 'По умолчанию активные продажи всех лет. Закупочные сделки исключены.'}}


def build():
    raw = load(ROOT / 'data/crm.json')
    if raw is None: raise FileNotFoundError('No CRM snapshot')
    data = project(raw, load(CRM / 'procurement_registry.json', {}), load(CRM / 'megaplan_finance_registry.json', {}))
    data['sync_status'] = load(ROOT / 'data/sync-status.json', {})
    bank = load(ROOT.parent / 'finance/reports/status.json', {})
    data['bank_status'] = {'ran_at': bank.get('ran_at'), 'accounts': [
        {k: account.get(k) for k in ('company', 'complete_through', 'needs_statement', 'internal_gaps')}
        for account in bank.get('accounts', []) if account.get('owner_confirmed')]}
    return data
