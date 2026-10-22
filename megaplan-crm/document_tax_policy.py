"""Guard the existing no-VAT contract template; never silently relabel tax."""
def require_no_vat(deal,api):
    rows=deal.get('positions') or []
    if not rows: raise ValueError('В сделке нет позиций для проверки режима НДС')
    catalog=None
    for row in rows:
        tax=row.get('tax') or (row.get('offer') or {}).get('tax') or {}
        rate=tax.get('rate')
        if rate is None and tax.get('id'):
            if catalog is None:
                catalog={str(item['id']):item.get('rate') for item in (api._call('GET','/tax').get('data') or [])}
            rate=catalog.get(str(tax['id']))
        if rate is None:
            raise ValueError('У позиции не подтверждён режим НДС. Документ не сформирован')
        if str(rate) not in ('-1','-1.0'):
            raise ValueError('Текущий шаблон договора и счёт по этапу рассчитаны на «Без НДС». Нельзя сформировать их для позиции с другой ставкой')

# Price values in CRM/document positions are gross, after discounts. Tax is not
# added a second time during rendering. Approved price migrations are explicit.
import json
from pathlib import Path
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
POLICY_FILE=Path(__file__).with_name('tax_policies.json')

def settings():
    if not POLICY_FILE.exists():return {'companies':{},'deals':{}}
    return json.loads(POLICY_FILE.read_text())

def company_rate(company_id, on_date=None):
    day=str(on_date or date.today().isoformat())
    rules=settings().get('companies',{}).get(company_id,[])
    matching=[r for r in rules if r['from']<=day]
    return int(max(matching,key=lambda r:r['from'])['rate']) if matching else None

def approved_deal(deal_id):
    return settings().get('deals',{}).get(str(deal_id),{})

def vat(gross,rate):
    gross=Decimal(str(gross));rate=Decimal(str(rate))
    if not gross.is_finite() or gross<0 or (not rate.is_finite() or rate<0 and rate!=-1 or rate>100):
        raise ValueError('Некорректная сумма или неподдерживаемая ставка НДС')
    return Decimal('0.00') if rate<=0 else (gross*rate/(100+rate)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

def tax_label(gross,rate):
    if int(rate)==-1:return 'Без НДС'
    amount=f'{vat(gross,rate):,.2f}'.replace(',',' ').replace('.',',')
    return f'В том числе НДС {int(rate)}% — {amount} ₽'

def row_rates(deal,api=None):
    rates=[];catalog=None
    for row in deal.get('positions') or []:
        tax=row.get('tax') or (row.get('offer') or {}).get('tax') or {}
        rate=tax.get('rate')
        if rate is None and tax.get('id') and api:
            if catalog is None:catalog={str(x['id']):x['rate'] for x in api._call('GET','/tax')['data']}
            rate=catalog.get(str(tax['id']))
        if rate is None:raise ValueError('Не подтверждена ставка НДС позиции '+str(row.get('id')))
        rates.append(int(rate))
    if not rates:raise ValueError('В сделке нет позиций для проверки режима НДС')
    return rates

def require_document_tax(deal,api):
    from seller_documents import selected_seller
    rates=row_rates(deal,api)
    approved=approved_deal(deal.get('id'))
    if approved:
        expected=approved['rows']
        if set(expected)!=set(str(x['id']) for x in deal['positions']):raise ValueError('Состав налогового перехода изменился')
        for row,rate in zip(deal['positions'],rates):
            item=expected[str(row['id'])]
            if rate!=item['rate'] or Decimal(str(row['sum']['value']))!=Decimal(item['gross']):
                raise ValueError('Позиция не соответствует согласованному переходу на НДС: '+str(row['id']))
    else:
        policy=company_rate(selected_seller(deal.get('id'))['id'])
        if policy is not None and any(r!=policy for r in rates):
            raise ValueError(f'По политике продавца требуется НДС {policy}%; уточните дату передачи и обновите налог позиций перед выпуском')
        if len(set(rates))!=1:raise ValueError('Для смешанных ставок требуется согласованная разбивка передачи')
    return rates

def decorate(data,rates=None):
    for i,row in enumerate(data['positions']):
        rate=int(rates[i] if rates is not None else row.get('tax_rate',-1))
        row.update(tax_rate=rate,vat_amount=str(vat(row['total'],rate)))
    amount=sum((Decimal(r['vat_amount']) for r in data['positions']),Decimal('0'))
    rates=set(r['tax_rate'] for r in data['positions'])
    data['vat_amount']=str(amount)
    data['tax_text']=('НДС не облагается на основании п. 1 ст. 145 НК РФ' if rates=={-1} else
        'В том числе НДС '+('/'.join(str(r)+'%' for r in sorted(rates) if r>=0))+' — '+f'{amount:,.2f}'.replace(',',' ').replace('.',',')+' руб.'+('; часть товаров передана без НДС' if -1 in rates else ''))
    return data

def creation_rate(spec):
    seller=spec.get('selling_company_id') or spec.get('seller_id') or 'cliwell'
    rate=company_rate(seller)
    return spec.get('tax_mode') if rate is None else 'none' if rate==-1 else str(rate)

def contract_positions(positions,deal_id):
    """Compare signed old specification against approved base, never edited gross."""
    approved=approved_deal(deal_id)
    if not approved:return positions
    return [{**r,'total':approved['rows'][str(r['id'])]['base_total']} for r in positions]

def payment_tax(parsed,deal,api):
    rates=require_document_tax(deal,api);approved=approved_deal(deal.get('id'))
    migration=approved.get('payments',{}).get(parsed['clause'])
    if migration:
        if Decimal(str(parsed['amount']))!=Decimal(migration['base']):raise ValueError('Базовая сумма пункта договора изменилась')
        parsed['amount']=float(migration['gross']);rate=migration['rate']
        parsed['line']=parsed['line'].replace('сумма '+f"{Decimal(migration['base']):,.2f}".replace(',',' ').replace('.',',')+' руб.', 'сумма '+f"{Decimal(migration['gross']):,.2f}".replace(',',' ').replace('.',',')+' руб., '+tax_label(migration['gross'],rate))
    else:
        if len(set(rates))!=1:raise ValueError('Не определена ставка для платежа смешанной сделки')
        rate=rates[0]
    parsed.update(tax_id=str(api.resolve_tax_id('none' if rate==-1 else str(rate))),tax_rate=rate,vat_amount=str(vat(parsed['amount'],rate)))
    return parsed


def stored_row_rate(row):
    tax=row.get('tax') or (row.get('offer') or {}).get('tax') or {}
    if tax.get('rate') is not None:return int(tax['rate'])
    config=settings()
    if tax.get('id') is not None:
        rate=config.get('tax_ids',{}).get(str(tax['id']))
        if rate is not None:return int(rate)
        if config.get('companies'):raise ValueError('Не определена ставка НДС для экономики: '+str(tax['id']))
    return -1
