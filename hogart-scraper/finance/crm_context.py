"""Read existing Megaplan registries. Enrich reports, never create CRM payments."""
import hashlib,json,re
from pathlib import Path
from decimal import Decimal
CRM=Path('/home/kocher.av/megaplan-crm')

def read(name,default):
    path=CRM/name
    return json.loads(path.read_text()) if path.exists() else default

def norm(value):return re.sub(r'[^0-9A-ZА-ЯЁ/.-]','',str(value).upper())
def money(value):return int(Decimal(str(value or 0))*100)

def enrich(rows,accounts):
    procurement=read('procurement_registry.json',{}).get('invoices',[])
    prior=read('bank_statement_registry.json',{}).get('transactions',[])
    candidates=read('email_payment_registry.json',{}).get('candidates',[])
    finance=read('megaplan_finance_registry.json',{}).get('operations',[])
    index=read('bank_match_index.json',{})
    deals={str(x['id']):x for x in read('deal_browser_cache.json',[])}
    for r in rows:
        r['crm_evidence']='';r['crm_operations']='';r['crm_candidate']=''
        ids=[]; evidence=[]
        existing=[x for x in prior if x.get('account')==r['account'] and x.get('date')=='.'.join(reversed(r['date'].split('-'))) and str(x.get('document_number'))==r['number'] and money(x.get('amount'))==r['amount_cents'] and str(x.get('counterparty_inn'))==r['inn'] and x.get('direction')==('income' if r['direction']=='in' else 'expense')]
        if len(existing)==1 and existing[0].get('status')=='assigned':
            ids=[str(existing[0]['deal_id'])];evidence=['Ранее подтверждённое разнесение в банковском реестре']
        if not ids and r['direction']=='out':
            # Match only invoice references, supplier INN and OUR purchasing company.
            from ledger import invoice_refs
            refs={norm(v) for v in invoice_refs(r['purpose'])}
            invoices=[x for x in procurement if norm(x.get('number')) in refs and str(x.get('supplier_inn'))==r['inn'] and str(x.get('buyer_inn'))==accounts[r['account']]['inn']]
            exact=bool(invoices and {norm(x.get('number')) for x in invoices}==refs and len(invoices)==len(refs) and sum(money(x.get('total')) for x in invoices)==r['amount_cents'])
            allocation_complete=exact and all(sum(money(a.get('amount')) for a in x.get('allocations',[]))==money(x['total']) for x in invoices)
            deal_ids=sorted({str(a['deal_id']) for x in invoices for a in x.get('allocations',[]) if a.get('deal_id')})
            if allocation_complete and len(deal_ids)==1:
                ids=deal_ids;evidence=['Счёт поставщика + ИНН поставщика/покупателя + сумма + полное распределение']
                # Existing CRM payments must cover the exact bank movement AND each invoice.
                matching_candidates=[c for c in candidates if str(c.get('payment_number'))==r['number'] and c.get('date')=='.'.join(reversed(r['date'].split('-'))) and money(c.get('amount'))==r['amount_cents'] and {norm(v) for v in c.get('invoice_numbers',[])}==refs]
                cids={c['id'] for c in matching_candidates}
                old_ops=[x for x in finance if x.get('candidate_id') in cids]
                supported=[]
                for inv in invoices:
                    hits=[x for x in old_ops if norm(x.get('invoice_number'))==norm(inv['number']) and money(x.get('amount'))==money(inv['total']) and any(str(p.get('megaplan_operation_id'))==str(x.get('operation_id')) for p in inv.get('payments',[]))]
                    if len(hits)==1:supported.extend(hits)
                if len(supported)==len(invoices):
                    r['crm_operations']=', '.join(str(x['operation_id']) for x in supported)
                    evidence.append('Уже учтено в финансовом реестре Мегаплана; повторное создание исключено')
            elif invoices:
                r['crm_candidate']=', '.join(deal_ids)
                r['flags'].append('Счёт найден в реестре Мегаплана; сумма или распределение требуют сверки')
                r['crm_evidence']='Кандидат по номеру счёта и ИНН; не подтверждённая привязка'
        if not ids and r['direction']=='in':
            # Invoice + payer INN can suggest a deal. Cached API index does not prove
            # receiving company, so leave it as a candidate rather than silently assigning.
            from ledger import invoice_refs
            refs=invoice_refs(r['purpose']);found=[]
            for ref in refs:
                key=str(int(ref)) if ref.isdigit() else norm(ref)
                found.extend(x for x in index.get('invoice_numbers',{}).get(key,[]) if str(x.get('payer_inn'))==r['inn'])
            options=sorted({str(x['deal_id']) for x in found})
            if len(options)==1:
                r['crm_candidate']=options[0]
                r['crm_evidence']='Клиентский счёт + ИНН плательщика в индексе Мегаплана; проверить юрлицо-получателя и актуальность'
        if ids:
            label=[]
            for did in ids:
                d=deals.get(did,{})
                label.append('Мегаплан №'+did+': '+str(d.get('shortDescription') or d.get('name') or ''))
            r['project']='; '.join(label);r['crm_evidence']='; '.join(evidence)
            r['flags']=[f for f in r['flags'] if f not in ['Нет подтверждённой привязки к объекту/заказу','Возможна оплата нескольких счетов — нужна разбивка']]
        if r['status']!='Подтверждено пользователем':
            r['status']='Требует уточнения' if r['flags'] else 'Сверено с реестром Мегаплана' if ids else 'По правилу ДДС'
    return rows
