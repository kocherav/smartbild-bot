import json,re,hashlib,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/finish_all';rows=json.loads((R/'reports/ledger.json').read_text());db=sqlite3.connect(R/'data/ledger.sqlite');ac={'40702810402570001572':'20','40702810902570001580':'22'};parts=[];groups={}
for r in rows:
 if r['category'] not in ['Размещение депозита','Возврат депозита']:continue
 raw=json.loads(db.execute('select payload from operations where id=?',(r['id'],)).fetchone()[0]);contract=re.search(r'CB\d+',r['purpose']).group();assert raw.get('ПлательщикБИК')=='044525593' and raw.get('ПолучательБИК')=='044525593';assert r['inn'] in ['7743926877','7743151323'];assert raw['ПлательщикИНН']==raw['ПолучательИНН']==r['inn']
 groups.setdefault(contract,[]).append(r);k=hashlib.sha256((r['id']+'|company|deposit_principal').encode()).hexdigest()[:24];typ='30' if r['direction']=='in' else '22'
 parts.append(dict(key=k,bank_operation_id=r['id'],date=r['date'],document_number=r['number'],account_id=ac[r['account']],kind='income' if typ=='30' else 'expense',amount_cents=r['amount_cents'],deal_id='',allocation_scope='company',category=r['category'],invoice_number='',counterparty_inn=r['inn'],contractor_id='1000609',operation_type=typ,deposit_contract=contract,marker='BANK:'+k,description=f"[BANK:{k}] Тело депозита {contract}; не доход/расход. Банк №{r['number']}.",evidence='Оба банковских счёта и ИНН принадлежат одной организации, БИК обоих банков044525593. Денежное размещение/возврат обязательства Альфа-Банка, не продажа. Депозитный договор'+contract+'. Товарное движение0.'))
reconciliation=[]
for contract,rr in groups.items():
 ins=sum(r['amount_cents'] for r in rr if r['direction']=='in');outs=sum(r['amount_cents'] for r in rr if r['direction']=='out')
 assert (len(rr)==2 and ins==outs) or (len(rr)==1 and ins>0 and '04.2026' in rr[0]['purpose'])
 reconciliation.append({'contract':contract,'ids':[r['id'] for r in rr],'returned_cents':ins,'placed_cents':outs,'status':'matched' if ins==outs else 'return_of_preperiod_deposit'})
(D/'deposit_plan.json').write_text(json.dumps(parts,ensure_ascii=False,indent=2));(D/'deposit_reconciliation.json').write_text(json.dumps(reconciliation,ensure_ascii=False,indent=2));print(len(parts),'deposit payments',len(reconciliation),'contracts')
p=D/'company_plan.json';data=json.loads(p.read_text());keys={x['key'] for x in data};data.extend(x for x in parts if x['key'] not in keys);p.write_text(json.dumps(data,ensure_ascii=False,indent=2))
