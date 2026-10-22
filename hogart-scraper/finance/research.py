"""Document-backed enrichment; never represents research as owner approval."""
import json,re
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).resolve().parent
MISSING='Нет подтверждённой привязки к объекту/заказу'
def enrich(rows,accounts):
    classification_path=ROOT/'evidence/continuation_oct6b/classifications.json'
    classifications=json.loads(classification_path.read_text()) if classification_path.exists() else []
    vat_path=ROOT/'evidence/remaining_oct6/vat_review.json'
    vat_reviews=json.loads(vat_path.read_text()) if vat_path.exists() else []
    invoices=[]
    for p in (ROOT/'evidence').glob('invoice_*.json'):
        d=json.loads(p.read_text()).get('data',{})
        if isinstance(d,dict) and d.get('deal'): invoices.append((d,p.name))
    for r in rows:
        notes=[]; did=None
        for review in vat_reviews:
            if all(r.get(k)==review[k] for k in ['id','inn','date','amount_cents']):
                r['flags']=[f for f in r['flags'] if f not in review['remove_flags']]
                r['document_vat_rate']='22%'
                notes.append(review['evidence']+' Источник: '+review['source'])
        for decision in classifications:
            if all(r.get(k)==decision[k] for k in ['id','inn','account','date','number','amount_cents']):
                r['category']=decision['category']
                r['flags']=[f for f in r['flags'] if f!='Подтвердить статью']
                if decision['remaining_flag'] not in r['flags']:r['flags'].append(decision['remaining_flag'])
                notes.append(decision['evidence'])
        if r['direction']=='in' and r['group']=='Внешняя':
            hits=[]
            for d,source in invoices:
                recipient=d.get('recipient') or {};payer=d.get('payer') or {}
                if payer.get('inn')!=r['inn'] or recipient.get('inn')!=accounts[r['account']]['inn'] or recipient.get('currentAccount')!=r['account']:continue
                invoice_match=re.search(r'(?<!\d)'+re.escape(d['number'])+r'(?!\d)',r['purpose'])
                contract=d['deal'].get('number','')
                contract_match=contract and contract in r['purpose']
                limit=Decimal(str(d['sum']['value']))*100
                if (invoice_match or contract_match) and r['amount_cents']<=limit:hits.append((d,source))
            if len(hits)==1:
                d,source=hits[0];did=str(d['deal']['id'])
                notes.append(f"Карточка счёта {d['number']}: совпали плательщик, получатель, счёт организации и номер счёта/договора; платёж в пределах суммы. Источник {source}")
            # Second invoice absent, but explicit contract and exact combined price verified.
            if r['number']=='1242' and r['date']=='2026-05-06' and r['inn']=='7733356410' and r['amount_cents']==13009000 and '1.851-0505/2026' in r['purpose'] and r['account'].endswith('1580'):
                d=json.loads((ROOT/'evidence/deal_851.json').read_text())['data']
                if Decimal(str(d['price']['value']))==Decimal('257240'):
                    did='851';notes.append('Договор 1.851-0505/2026; два поступления 130090 + 127150 = цена сделки 257240. Счёт 05487 отдельно не найден.')
        if r['direction']=='out' and 'DAER' in r['purpose'].upper() and '023701' in r['purpose'] and r['amount_cents']==256155907:
            if (ROOT/'evidence/1790426140.txt').exists() and '84,5863' in r['purpose'] and r['inn']=='7703675923' and r['account']=='40702810402570001572':
                did='853';notes.append('DAER023701: 30283,38 EUR × 84,5863 = 2561559,07 RUB. Счёт прикреплён к сделке 853. Историческую себестоимость не меняли.')
        if did:
            r['project']='Мегаплан №'+did;r['verified_deal_id']=did
            r['flags']=[f for f in r['flags'] if f!=MISSING and 'Счёт найден в реестре' not in f]
            r['crm_candidate']=''
        if r['account'].endswith('1572') and r['number']=='99' and r['date']=='2026-07-22' and r['amount_cents']==376000:
            notes.append('Счёт 2607-466489-69135, mail_13544_2.pdf: 3760 руб., НДС 678,03. Сумма НДС 2026,70 ошибочно перенесена в назначение; оригинал сохранён.')
            r['document_vat']='678.03';r['flags']=[f for f in r['flags'] if f!='Разные суммы НДС в назначении']
        if r['date']=='2026-08-29' and r['account'].endswith('1572') and (r['number'],r['amount_cents']) in [('23145',417000),('23101',29000)]:
            notes.append('Чеки mail_13609/mail_13614 от 27.08: 4170 + 290 = 4460; заказ 2608-487733-77932, клапаны VALTEC. Покупатель ИНСИС. Объект пока не подтверждён.')
            r['category']='Оборудование и материалы';r['flags']=[f for f in r['flags'] if f!='Нужны чек, назначение покупки и объект']
        if r['account'].endswith('1580') and r['number']=='31' and r['date']=='2026-07-01' and r['amount_cents']==5000000:
            notes.append('Остаток оплаты: предыдущий платёж 115000 + 50000 = 165000; сумма назначения относится к полному счёту.')
            r['flags']=[f for f in r['flags'] if 'Сумма в назначении' not in f and '165 000' not in f]
        if r['group']=='Между компаниями группы' and r['link'].startswith('Парный перевод'):
            r['category']='Расчёты между компаниями группы'
            notes.append('Встречные записи сопоставлены; из внешнего ДДС группы исключены. Распределение по проектам остаётся отдельной задачей.')
        r['crm_evidence']='; '.join(filter(None,[r.get('crm_evidence',''),*notes]))
        # Owner answers are a separate queue. Missing documents/projects remain visible work.
        if r['flags']:
            r['status']='Требует уточнения';r['review_owner']='Ассистент: документы и распределение'
        else:r['status']='Сверено с реестром Мегаплана' if r.get('project') else 'По правилу ДДС';r['review_owner']='Не требуется'
        if r['category']=='Покупки по корпоративной карте':r['review_owner']='Пользователь: общее правило по карте'
        if any('Повтор суммы и периода' in f for f in r['flags']):r['review_owner']='Пользователь: период зарплаты'
    return rows
