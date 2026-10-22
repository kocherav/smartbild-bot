from pathlib import Path as _QueuePath
if (_QueuePath(__file__).resolve().parents[1]/'data/review_registry.json').exists():
    raise SystemExit('Архивный обработчик отключён: рабочий реестр — finance/data/review_registry.json; обновление — finance/review_registry.py')
import sys,json,hashlib,datetime
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance','/home/kocher.av/telegram-bridge']
from post_confirmed import *
import procurement_workflow as pw,own_companies,statement_document_context as ctx
from registry_transaction import transaction
D=ROOT/'evidence/invoice1624';v=json.loads((D/'verified.json').read_text());assert v['operations'][0]['operation_id']=='3198'
@transaction(lambda: pw.REGISTRY)
def link_payment():
 data=pw.ensure_schema(pw.load_json(pw.REGISTRY,pw.empty_registry()));bank=pw.load_json(pw.BANK_REGISTRY,{})
 inv=next(x for x in data['invoices'] if x['number']=='1624' and x['supplier_inn']=='7743949955' and x['buyer_inn']=='7743926877');assert inv['deal_id']=='807' and inv['allocated_total']==27600
 tx=next(x for x in bank['transactions'] if x['id']=='a7fe8ad2507161488b0e');assert tx['account']=='40702810402570001572' and float(tx['amount'])==27600
 if not any(p['transaction_id']==tx['id'] for p in inv['payments']):
  assert not inv['payments'] and not inv['paid_total']
  company=pw.company_ref(own_companies.resolve_company(account=tx['account']))
  inv['payments'].append({'transaction_id':tx['id'],'date':tx['date'],'amount':27600,'document_number':'62','paying_company':company,'account':tx['account'],'crm_operation_id':'3198'})
 inv.update(paid_total=27600,status='оплачен');tx.update(status='assigned',deal_id='807',deal_name='Оплата счёта поставщика №1624',supplier_invoice_id=inv['id'],assigned_at=datetime.datetime.now().isoformat(timespec='seconds'))
 atomic(Path(pw.REGISTRY),data);atomic(Path(pw.BANK_REGISTRY),bank);atomic(D/'paid_invoice.json',inv)
link_payment()
qpath=ROOT/'evidence/finish_all/owner_questions.json';q=json.loads(qpath.read_text());hits=[g for g in q['groups'] if g['number']==35]
if hits:
 g=hits[0];g.update(resolved=True,owner_question_closed=True,resolution='Владелец указал807 Павелецкая Сити Наталья; C1G1шт добавлен с продажей43000/закупкой27600. Оплата3198 проверена, SecondarySum0; исходный счёт в архиве.',crm_operation_ids=['3198']);q['resolved_groups'].append(g);q['groups']=[x for x in q['groups'] if x['number']!=35];atomic(qpath,q)
source=Path(json.loads((D/'supplier_spec.json').read_text())['invoice']['source_path'])
import subprocess
text=subprocess.check_output(['/home/kocher.av/.report-venv/bin/python','/home/kocher.av/telegram-bridge/extract_document_text.py'],input=json.dumps({'path':str(source)}),text=True)
entry=ctx.match_document(source,text,'289622514');assert entry
manifest=ROOT/'evidence/telegram_intake/manifest.json'
with ctx.durable_json.locked(str(manifest)):
 m=ctx.durable_json.read(str(manifest),dict);m[entry['sha256']].update(status='processed',resolution='807 Павелецкая Сити Наталья. C1G1шт: продажа43000, закупка27600; платёж3198 без отгрузки.',crm_operation_ids=['3198'],archive_remotes=[x['remote'] for x in json.loads((D/'archive_results.json').read_text())]);ctx.durable_json.save(str(manifest),m)
print('Invoice paid, owner question35 closed; remaining',len(q['groups']))
