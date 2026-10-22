"""Reconcile bank movements with existing installer settlements, without posting twice."""
import json
from pathlib import Path
from decimal import Decimal
ROOT=Path('/home/kocher.av/telegram-bridge')
def cents(value):return int((Decimal(str(value))*100).quantize(Decimal('1')))
def apply(rows):
 p=ROOT/'installer_settlements.json'
 if not p.exists():return
 registry=json.loads(p.read_text());ops={o['id']:o for o in registry['operations']}
 reports=json.loads((ROOT/'installer_approved_reports.json').read_text())['reports']
 for r in rows:
  if r['inn']!='325301654021' or r['direction']!='out' or r['account']!='40702810902570001580':continue
  hits=[o for o in ops.values() if o['type']=='payment' and o.get('payment_method')=='cashless' and o.get('recipient')==r['counterparty'] and o['date']=='.'.join(reversed(r['date'].split('-'))) and str(o['number'])==r['number'] and cents(o.get('gross_amount',o['amount']))==r['amount_cents']]
  if len(hits)!=1:continue
  payment=hits[0];links=[a for a in registry['allocations'] if a['payment_id']==payment['id']]
  if not links or abs(sum(cents(a['amount']) for a in links)-cents(payment['settlement_amount']))>1:continue
  linked=[];deal_ids=set()
  for a in links:
   accrual=ops[a['accrual_id']];matching=[p for p in reports if p['date']==accrual['date']]
   if len(matching)!=1:break
   report=matching[0];deal_ids.update(str(x['deal_id']) for x in report['deals'])
   linked.append({'accrual_id':accrual['id'],'report_id':report['id'],'report_date':report['date'],'settlement_cents':cents(a['amount'])})
  if len(linked)!=len(links):continue
  r['installer_payment_id']=payment['id'];r['installer_settlement_cents']=cents(payment['settlement_amount']);r['installer_report_links']=linked
  r['project']='Учтено в отчётах монтажника; связанные сделки: '+', '.join(sorted(deal_ids))
  r['crm_evidence']='; '.join(filter(None,[r.get('crm_evidence'),f"Платёж {payment['id']} в installer_settlements.json: дата, номер, получатель и банковская сумма совпали. Распределение расчётной суммы {payment['settlement_amount']} при коэффициенте {payment['coefficient']} уже существует; отчёты: "+', '.join(x['report_date'] for x in linked)+'. Банковская сумма сохранена; повторное начисление/распределение не создано.']))
  r['flags']=[f for f in r['flags'] if f!='Нет подтверждённой привязки к объекту/заказу']
  r['status']='Требует уточнения' if r['flags'] else 'Сверено с реестром монтажников';r['review_owner']='Не требуется' if not r['flags'] else 'Ассистент: сверка'
