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
