import sys,json,copy,uuid,subprocess
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
sys.path.insert(0,'/home/kocher.av/telegram-bridge')
import closing_runtime as c
import partial_shipments as p
from closing_workflow import Registry
import hogart_closing,procurement_attachments,procurement_workflow,shipment_finance
root=Path(__file__).resolve().parent
for name in ('trial-shipments.sqlite3','trial-jobs.json'):(root/name).unlink(missing_ok=True)
api=c.api();original_call=api._call
def read_call(method,*args,**kw):
 assert method=='GET','Business writes forbidden in trial'
 return original_call(method,*args,**kw)
api._call=read_call
source=p.snapshot('861',api);assert not source['blocking_errors']
(root/'source.json').write_text(json.dumps(source,ensure_ascii=False,indent=2))
with ExitStack() as stack:
 stack.enter_context(patch.object(p.workspace,'DB',root/'trial-shipments.sqlite3'))
 stack.enter_context(patch.object(c,'REGISTRY',root/'trial-jobs.json'))
 stack.enter_context(patch.object(c,'OUT',root/'documents'))
 stack.enter_context(patch.object(c,'api',return_value=api))
 stack.enter_context(patch.object(hogart_closing,'sync',return_value=[]))
 stack.enter_context(patch.object(procurement_attachments,'build',return_value={'files':[],'attachments':[],'register':'Закупочные вложения не загружались в проверочном прогоне.'}))
 stack.enter_context(patch.object(procurement_workflow,'supplier_invoices_for_deal',return_value=[]))
 stack.enter_context(patch.object(procurement_workflow,'accounting_hints',return_value={'hints':[]}))
 book=p.workspace.save_book('861',source)
 body={'deal_id':'861','request_id':str(uuid.uuid4()),'fingerprint':book['fingerprint'],'transfer_date':'2026-09-30','positions':[{'id':'7628','quantity':'1'}]}
 preview=p.workspace.preview(body);created=p.workspace.confirm(body,'isolated-trial');shipment=p.workspace.shipments('861')[-1]
 job={'id':created['id'],'shipment_id':created['id'],'deal_id':'861','mode':'test','status':'preparing','receipts':{},'shipment':shipment['payload']}
 c.registry().change(lambda data:data['jobs'].update({job['id']:job}))
 result=c.prepare(job)
 plan=shipment_finance.plans({**result,'mode':'live'})
 assert result['status']=='ready' and plan[0]['date']=='2026-09-30'
 assert len(result['documents'])==2
 assert '5 500 000,00' in result['note']
 assert 'Стоимость работ увеличена' not in result['note']
 text=subprocess.run(['pdftotext','-layout',result['act'],'-'],capture_output=True,text=True,check=True).stdout
 assert '30.09.2026' in text and '35 520,30' in text
 assert 'НДС 5%' not in text
 (root/'act-text.txt').write_text(text)
 (root/'result.json').write_text(json.dumps({'preview':preview,'job_id':job['id'],'documents':result['documents'],'act':result['act'],'finance_plan':plan,'paid_cents':550000000,'status':result['status']},ensure_ascii=False,indent=2))
 print(json.dumps({'status':result['status'],'date':plan[0]['date'],'amount':plan[0]['amount_cents'],'documents':result['documents'],'paid_cents':550000000},ensure_ascii=False))
