"""Apply explicit owner answers, retaining original bank data and decision provenance."""
import json,re
from pathlib import Path

def apply(rows):
    path=Path(__file__).with_suffix('.json')
    if not path.exists():return
    rules=json.loads(path.read_text());card=rules['personal_card']
    for r in rows:
        note=None
        if r['category']=='Покупки по корпоративной карте' and re.search(r'по карте\s+\d+\++'+re.escape(card['card_suffix'])+r'\.',r['purpose'],re.I) and any('\\'+m.upper()+' ПО ЧЕКУ' in r['purpose'].upper() for m in card['merchants']):
            r['category']='Личные расходы';r['project']='';r['flow']='Личные расходы'
            r['flags']=[f for f in r['flags'] if f not in ('Нужны чек, назначение покупки и объект','Нет подтверждённой привязки к объекту/заказу')]
            note='Пользователь подтвердил личный характер RUSFIT, TICKETLAND, питания и автосервиса по карте …8387. Не относится к расходам проектов.'
        if r['id'] in rules['salary_periods']:
            r['salary_period']=rules['salary_periods'][r['id']]
            r['flags']=[f for f in r['flags'] if f!='Повтор суммы и периода: проверить назначение / начисления']
            note='Пользователь уточнил: октябрьская выплата за сентябрь. Учётный период этой выплаты: '+r['salary_period']+'. Банковское назначение сохранено.'
        if note:
            r['decision_note']=note;r['crm_evidence']='; '.join(filter(None,[r.get('crm_evidence'),note]))
            r['status']='Требует уточнения' if r['flags'] else 'Подтверждено пользователем'
            r['review_owner']='Ассистент: оставшиеся замечания' if r['flags'] else 'Не требуется'
