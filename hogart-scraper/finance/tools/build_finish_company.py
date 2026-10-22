import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from payment_semantics import COMPANY_CASH
R=Path(__file__).resolve().parents[1];rows=json.loads((R/'reports/ledger.json').read_text());m=json.loads((R/'evidence/payment_correction/supplier_mapping.json').read_text());out=[];ac={'40702810402570001572':'20','40702810902570001580':'22'}
for r in rows:
 typ=COMPANY_CASH.get((r['category'],r['inn']))
 if r['category'] in ['Проценты по займу','Пени по займу'] and r['inn']=='7807391482' and r['direction']=='in':typ='32'
 if not typ:continue
 assert (r['direction']=='in')==(typ=='32')
 k=hashlib.sha256((r['id']+'|company|'+r['category']).encode()).hexdigest()[:24]
 evidence='Факт движения, организация, контрагент, основание и сумма подтверждены выпиской. Общехозяйственная операция без проекта. '+('Нетоварный доход: проценты/пени по займу, не продажа и не возврат тела займа.' if typ=='32' else 'Регистрируется только выплата/аванс, без начисления расхода и без товарного движения. Налоговый период и оказание услуг этой записью не устанавливаются.')
 if r.get('salary_period'):evidence+=' Период зарплаты: '+r['salary_period']
 out.append(dict(key=k,bank_operation_id=r['id'],date=r['date'],document_number=r['number'],account_id=ac[r['account']],kind='income' if typ=='32' else 'expense',amount_cents=r['amount_cents'],deal_id='',allocation_scope='company',category=r['category'],invoice_number='',counterparty_inn=r['inn'],operation_type=typ,contractor_id=m[r['inn']]['contractor_id'],description=f"[BANK:{k}] {r['category']}; банк №{r['number']}. {r['purpose']}"[:255],marker='BANK:'+k,evidence=evidence))
path=R/'evidence/finish_all/company_plan.json'
old=json.loads(path.read_text()) if path.exists() else []
keys={p['key'] for p in out}
out.extend(p for p in old if p['key'] not in keys)
path.write_text(json.dumps(out,ensure_ascii=False,indent=2));print('Company payments',len(out),'cash',sum(p['amount_cents'] for p in out)/100)
