import json,re,hashlib,sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from payment_allocations import normalize_allocations, allocation_key as make_allocation_key
from pathlib import Path
R=Path(__file__).resolve().parents[1];rows=json.loads((R/'reports/ledger.json').read_text());ac={'40702810902570001580':'22','40702810402570001572':'20'};proc=json.loads(Path('/home/kocher.av/megaplan-crm/procurement_registry.json').read_text())['invoices'];out=[]
journal=json.loads((R/'data/posting_journal.json').read_text()).get('operations',{})
def allocation_key(row, allocation):
 return make_allocation_key(row,allocation,journal)
for r in rows:
 if r['flags'] or r['group']!='Внешняя' or not r['project'] or r.get('installer_payment_id'):continue
 if r.get('confirmed_payment_allocations'):
  alloc=normalize_allocations(r)
 elif r.get('project_allocations'):
  alloc=[{'deal_id':'862' if 'Примавера' in a['project'] else '864','cents':a['amount_cents'],'invoice':'1794'} for a in r['project_allocations']]
 elif r['date']=='2026-09-25' and r['number']=='140' and r['amount_cents']==25169237 and r['account'].endswith('1572'):
  alloc=[{'deal_id':'887','cents':16701120,'invoice':'79566'},{'deal_id':'887','cents':8468117,'invoice':'79567'}]
 else:
  deal=r.get('verified_deal_id') or next(iter(re.findall(r'Мегаплан №(\d+)',r['project'])),None)
  if not deal:continue
  alloc=[{'deal_id':deal,'cents':r['amount_cents'],'invoice':r.get('document_numbers') or r.get('references') or ''}]
 assert sum(a['cents'] for a in alloc)==r['amount_cents']
 sibling_markers=['BANK:'+allocation_key(r,a) for a in alloc]
 for a in alloc:
  key=allocation_key(r,a)
  marker='BANK:'+key
  desc=f"[{marker}] {'Поступление' if r['direction']=='in' else 'Оплата'}; ИНН {r['inn']}; счёт {a['invoice']}; банк №{r['number']}; сделка {a['deal_id']}. {r['purpose']}"[:255]
  out.append(dict(key=key,bank_operation_id=r['id'],date=r['date'],document_number=r['number'],account_id=ac[r['account']],kind='income' if r['direction']=='in' else 'expense',amount_cents=a['cents'],deal_id=a['deal_id'],invoice_number=a['invoice'],counterparty_inn=r['inn'],operation_type='31' if r['direction']=='in' else ('25' if r['category'] in ['Подрядные работы','Доставка оборудования'] else '23'),description=desc,marker=marker,evidence=r.get('crm_evidence',''),sibling_markers=sibling_markers))
  if a.get('allocation_scope')=='company':
   out[-1].update(allocation_scope='company',category=a['category'],operation_type=a.get('operation_type') or '25')
  elif a.get('operation_type'):out[-1]['operation_type']=a['operation_type']
# Bank commissions are company overhead; a fictitious deal must not be created.
for r in rows:
 if r['flags'] or r['category']!='Банковские комиссии' or r['direction']!='out' or r['inn']!='7728168971' or r['group']!='Внешняя':continue
 key=hashlib.sha256((r['id']+'|company|bank_fee').encode()).hexdigest()[:24]
 out.append(dict(key=key,bank_operation_id=r['id'],date=r['date'],document_number=r['number'],account_id=ac[r['account']],kind='expense',amount_cents=r['amount_cents'],deal_id='',allocation_scope='company',category=r['category'],invoice_number='',counterparty_inn=r['inn'],operation_type='25',contractor_id='1000609',description=f"[BANK:{key}] Банковская комиссия; {r['company']}; банк №{r['number']}. {r['purpose']}"[:255],marker='BANK:'+key,evidence='Банковская выписка: комиссия банка, ИНН7728168971. Карточка контрагента1000609 подтверждена плательщиком1000625 с этим ИНН. Общехозяйственный расход, привязка к объекту не требуется.'))
for r in rows:
 if r['flags'] or r['category']!='Проценты по депозиту' or r['direction']!='in' or r['inn']!='7728168971' or r['group']!='Внешняя':continue
 key=hashlib.sha256((r['id']+'|company|deposit_interest').encode()).hexdigest()[:24]
 out.append(dict(key=key,bank_operation_id=r['id'],date=r['date'],document_number=r['number'],account_id=ac[r['account']],kind='income',amount_cents=r['amount_cents'],deal_id='',allocation_scope='company',category=r['category'],invoice_number='',counterparty_inn=r['inn'],operation_type='32',contractor_id='1000609',description=f"[BANK:{key}] Проценты по депозиту; {r['company']}; банк №{r['number']}. {r['purpose']}"[:255],marker='BANK:'+key,evidence='Банковская выписка: прямо указана уплата процентов по депозиту и номер депозитной сделки; плательщик Альфа-Банк ИНН7728168971. Доход компании, не продажа; клиентский счёт не требуется.'))
# Exact reviewed company movements, retained across daily rebuilds.
reviewed=R/'evidence/finish_all/company_plan.json'
if reviewed.exists():
 by_id={r['id']:r for r in rows}
 for p in json.loads(reviewed.read_text()):
  r=by_id[p['bank_operation_id']]
  assert r['amount_cents']==p['amount_cents'] and r['inn']==p['counterparty_inn'] and r['date']==p['date'] and r['number']==p['document_number']
  if not any(x['key']==p['key'] for x in out):out.append(p)
journal=json.loads((R/'data/posting_journal.json').read_text()).get('operations',{}) if (R/'data/posting_journal.json').exists() else {}
for p in out:
 old=journal.get(p['key'],{})
 for field in ['crm_invoice_id','contractor_id']:
  if old.get(field):p[field]=old[field]
 if p['kind']=='expense' and not p.get('contractor_id'):
  mp=R/'evidence/payment_correction/supplier_mapping.json'
  suppliers=json.loads(mp.read_text()) if mp.exists() else {}
  p['contractor_id']=suppliers.get(p['counterparty_inn'],{}).get('contractor_id')
 if p['kind']=='income' and not p.get('crm_invoice_id'):
  match=re.search(r'invoice_(\d+)\.json',p['evidence'])
  if match:
   inv=json.loads((R/'evidence'/('invoice_'+match.group(1)+'.json')).read_text())['data']
   p['crm_invoice_id']=inv['id'];p['contractor_id']=inv['payer']['contractor']['id']
(R/'evidence/posting/plan.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('planned_parts',len(out),'bank_payments',len({x['bank_operation_id'] for x in out}), 'total',sum(x['amount_cents'] for x in out)/100)
