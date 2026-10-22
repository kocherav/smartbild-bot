"""Reconcile document types without replacing immutable OfferRow/Offer clones.

Explicit custom field is authoritative. Native type alone is an old default and
is not mutated on clones. Dry-run plan is versioned against names/IDs. No finance.
"""
from position_types import name_kind,FIELD,GOODS,WORK


def plan(deal, all_rows=False):
    result=[]
    for row in deal.get('positions') or []:
        offer=row.get('offer') or {};name=row.get('name') or offer.get('name') or ''
        if offer.get(FIELD):continue
        expected=WORK if offer.get('type')=='service' or name_kind(name)=='work' else GOODS
        if all_rows or expected==WORK:
            result.append({'deal_id':str(deal['id']),'row_id':str(row['id']),
                'offer_id':str(offer['id']),'name':name,'before':offer.get(FIELD) or '',
                'after':expected})
    return result


def invariant(offer):
    return {k:offer.get(k) for k in ('name','price','unit','tax',
        'Category1000045CustomFieldTsenaZakupki','Category1000045CustomFieldSebesRabot')}


def apply(api,change):
    before=api._call('GET','/offer/'+change['offer_id'])['data']
    if before.get('name')!=change['name']:
        raise ValueError('Название товара изменилось; заново сверить тип')
    if before.get(FIELD)==change['after']:
        return {**change,'verified':True,'unchanged':True}
    if (before.get(FIELD) or '')!=change['before'] or change['after'] not in (GOODS,WORK):
        raise ValueError('Тип или основание миграции изменились')
    api._call('POST','/offer/'+change['offer_id'],json_body={'contentType':'Offer',FIELD:change['after']})
    after=api._call('GET','/offer/'+change['offer_id'])['data']
    if after.get(FIELD)!=change['after'] or invariant(before)!=invariant(after):
        raise ValueError('Обратное чтение типа или сохранности реквизитов не прошло; повторную запись не выполнять')
    return {**change,'verified':True,'unchanged':False}
