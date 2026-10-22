import json,re,hashlib,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/finish_all';rows=json.loads((R/'reports/ledger.json').read_text());rr=[r for r in rows if r['category']=='Расчёты между компаниями группы'];invoices=json.loads((D/'all_invoices.json').read_text());assert not [i for i in invoices if (i.get('payer') or {}).get('inn') in ['7743926877','7743151323']]
groups={};ac={'40702810402570001572':'20','40702810902570001580':'22'};cid={'7743926877':'1000001','7743151323':'1000549'}
for r in rr:groups.setdefault(r['link'],[]).append(r)
parts=[];proof=[]
for pair,group in groups.items():
 assert len(group)==2 and group[0]['amount_cents']==group[1]['amount_cents'] and {r['direction'] for r in group}=={'in','out'} and len({r['account'] for r in group})==2 and len({r['date'] for r in group})==1
 pairid=hashlib.sha256('|'.join(sorted(r['id'] for r in group)).encode()).hexdigest()[:16];proof.append({'pair':pairid,'rows':[r['id'] for r in group],'amount_cents':group[0]['amount_cents'],'date':group[0]['date']})
 for r in group:
  assert '1407/18' in r['purpose'];k=hashlib.sha256((r['id']+'|company|intercompany_advance').encode()).hexdigest()[:24];typ='31' if r['direction']=='in' else '23'
  parts.append(dict(key=k,bank_operation_id=r['id'],date=r['date'],document_number=r['number'],account_id=ac[r['account']],kind='income' if typ=='31' else 'expense',amount_cents=r['amount_cents'],deal_id='',allocation_scope='company',category=r['category'],invoice_number='',counterparty_inn=r['inn'],contractor_id=cid[r['inn']],operation_type=typ,intercompany_pair_id=pairid,marker='BANK:'+k,description=f"[BANK:{k}] Межфирменный аванс по1407/18; пара{pairid}; банк №{r['number']}. Без товарного движения; исключён из внешнего ДДС группы.",evidence='Обе стороны перевода найдены в выписках ИНСИС/КЛИВЭЛ; совпали дата, сумма, счета организаций и договор1407/18. Сверен полный список709 клиентских счетов: счетов с нашими организациями-плательщиками нет. Аванс по договору без клиентского счёта и объекта; распределение себестоимости не выполняется, товарное движение0.'))
assert len(parts)==34
(D/'intercompany_plan.json').write_text(json.dumps(parts,ensure_ascii=False,indent=2));(D/'intercompany_reconciliation.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));p=D/'company_plan.json';data=json.loads(p.read_text());keys={x['key'] for x in data};data.extend(x for x in parts if x['key'] not in keys);p.write_text(json.dumps(data,ensure_ascii=False,indent=2));print('17 paired intercompany transfers, 34 bank entries',sum(g['amount_cents'] for g in proof)/100)
