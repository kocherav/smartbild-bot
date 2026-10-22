"""Browser acceptance on loopback with fake auth and isolated write stores."""
import hashlib,hmac,json,subprocess,sys,tempfile,threading,time,urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import allocation_workspace as allocation
ROOT=Path(__file__).resolve().parents[2]

def main():
    results=[]
    # A boundary in age_days must not invalidate before/after business-data assertions.
    from datetime import datetime, timezone
    clock=datetime.now(timezone.utc);original_project=server.model.project
    server.model.project=lambda snapshot,procurement=None,registry=None,now=None:original_project(snapshot,procurement,registry,now or clock)
    with tempfile.TemporaryDirectory(prefix='smartbild-browser-') as d:
        root=Path(d);server.matching_store.DB=root/'matching.sqlite3';server.shipment_workspace.DB=root/'shipments.sqlite3';server.DB=root/'dashboard.sqlite3';server.credentials=lambda:('fixture-token',{77});server.initialize()
        def signed(uid):
            data={'auth_date':str(int(time.time())),'user':json.dumps({'id':uid}),'query_id':'offline'}
            key=hmac.new(b'WebAppData',b'fixture-token',hashlib.sha256).digest()
            data['hash']=hmac.new(key,'\n'.join(f'{k}={v}' for k,v in sorted(data.items())).encode(),hashlib.sha256).hexdigest()
            return urllib.parse.urlencode(data)
        fixture=Path('/tmp/deal-dashboard-test-auth.json')
        # This contains only disposable fixture signatures, never real credentials.
        fixture.write_text(json.dumps({'valid':signed(77),'other':signed(1)}));fixture.chmod(0o600)
        finance=root/'finance';(finance/'data').mkdir(parents=True)
        queue_data=json.loads((ROOT/'finance/data/review_registry.json').read_text())
        # Test new allocations of actual remaining stock, independent of live CRM jobs.
        queue_data['allocation_drafts']={k:v for k,v in queue_data.get('allocation_drafts',{}).items() if v.get('execution',{}).get('actor')!='automatic-procurement'}
        (finance/'data/review_registry.json').write_text(json.dumps(queue_data))
        original_projection=allocation.projection;original_save=allocation.save_draft
        proc=root/'procurement.json';proc_data=json.loads(allocation.queue.PROCUREMENT.read_text())
        # Stable legacy allocation fixture. Real documents may correctly enter version review.
        proc_data['invoices'].append({'id':'browser-allocation','document_key':'browser-allocation','number':'TEST-ALLOC','supplier':'Изолированная фикстура','total':12751.2,'allocations':[],'payments':[]})
        proc_data['unallocated_stock'].append({'id':'browser-stock','document_key':'browser-allocation','source_line_key':'fixture','name':'Изолированный расход браузерного теста','unit':'шт','initial_qty':14,'available_qty':14,'initial_amount':12751.2,'available_amount':12751.2,'allocations':[]})
        proc_data['invoices'].append({'id':'browser-kit','document_key':'browser-kit','number':'TEST-KIT','supplier':'Изолированная фикстура','total':100,'candidate_deal_ids':['887'],'intake':{'state':'review','error':'Расшифруйте комплект'},'lines':[{'line_no':1,'name':'Наружный блок','sku':'OUT','key':'1:out','unit':'шт','qty':1,'amount_cents':6000},{'line_no':2,'name':'Внутренний блок','sku':'IN','key':'2:in','unit':'шт','qty':1,'amount_cents':4000}],'allocations':[{'deal_id':'887','amount':100,'source_lines':[{'offer_row_id':'8012','qty_used':1,'amount_used':100}]}],'payments':[]})
        # Replay the real 14 x 4m invoice BEFORE allocation, only in this isolated store.
        # Production now correctly has zero remaining pipe; it is not a reusable fixture.
        pipe_invoice=next(i for i in proc_data['invoices'] if i.get('number')=='22427744/SA')
        pipe_key=pipe_invoice['document_key']
        pipe_invoice['allocations']=[]
        for stock in proc_data['unallocated_stock']:
            if stock.get('document_key')==pipe_key:
                stock.update(available_qty=stock['initial_qty'],available_amount=stock['initial_amount'],allocations=[])
        queue_data['allocation_drafts'].pop(pipe_key,None)
        (finance/'data/review_registry.json').write_text(json.dumps(queue_data))
        original_ledger=server.allocation_apply.ledger
        def fixture_ledger(did):
            rows=original_ledger(did)
            if str(did)=='890':
                for row in rows:
                    if str(row.get('offer_row_id'))=='8031':row.update(consumed_qty=0,cumulative_cost_material=0)
            return rows
        original_prepare=server.allocation_apply.prepare
        server.allocation_apply.prepare=lambda body,deals,procurement,loader=None:original_prepare(body,deals,procurement,loader=fixture_ledger)
        original_ledgers=server.procurement_workspace.ledgers
        server.procurement_workspace.ledgers=lambda deals,loader=None:original_ledgers(deals,loader=fixture_ledger)
        proc.write_text(json.dumps(proc_data))
        allocation.queue.PROCUREMENT=proc
        original_load=server.model.load
        server.model.load=lambda path,default=None:original_load(proc if Path(path).name=='procurement_registry.json' else path,default)
        original_workspace=server.procurement_workspace.projection;original_command=server.procurement_workspace.command
        server.procurement_workspace.projection=lambda deals:original_workspace(deals,root=finance,procurement_path=proc)
        server.procurement_workspace.command=lambda body,user:original_command(body,user,root=finance,procurement_path=proc)
        original_request=server.allocation_apply.request
        server.allocation_apply.request=lambda body,deals,user:original_request(body,deals,user,root=finance,procurement_path=proc)
        allocation.projection=lambda deals,*args,**kwargs:original_projection(deals,root=finance,procurement_path=proc)
        allocation.save_draft=lambda body,deals,user:original_save(body,deals,user,root=finance,procurement_path=proc)
        server.shipment_workspace.save_book('894',{'contract_date_iso':'2026-09-01','total':'200.00','positions':[{'id':'fake-1','name':'Проверка <img src=x onerror=alert(1)>','kind':'goods','unit':'шт.','quantity':'2','total':'200.00','unit_price':'100.00','tax_rate':5}]})
        server.shipment_workspace.save_book('861',{'total':'71040.60','positions':[{'id':'7628','name':'Компактный корпус RAM fit с боковыми вырезами 2000х800х250','quantity':2,'unit':'шт.','total':'71040.60','unit_price':'35520.30','tax_rate':-1}]})
        server.shipment_workspace.save_book('853',{'contract_date_iso':'2026-06-10','total':'709686.00','positions':[{'id':'7487','name':'Монтажные работы','kind':'work','unit':'шт.','quantity':'1','total':'709686.00','unit_price':'709686.00','tax_rate':-1}]})
        for port,scripts in ((8097,['browser.cjs','workspace-browser.cjs']),(8098,['filters-browser.cjs','allocation-browser.cjs','shipments-browser.cjs','work-stage-browser.cjs','shipment-loading-browser.cjs','shipment-procurement-browser.cjs','supplier-document-browser.cjs','matching-browser.cjs','procurement-flow-browser.cjs','procurement-kit-browser.cjs'])):
            server.ORIGIN=f'http://127.0.0.1:{port}'
            if port==8098:server.session_user=lambda token:77 if token=='fixture' else None
            http=server.Server(('127.0.0.1',port),server.Handler)
            thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            try:
                for script in scripts:
                    run=subprocess.run(['node',str(Path(__file__).parent/script)],cwd=ROOT,capture_output=True,text=True,timeout=150)
                    results.append({'script':script,'ok':run.returncode==0,'output':run.stdout[-2000:],'error':run.stderr[-2000:]})
                    print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            finally:http.shutdown();http.server_close();thread.join(timeout=5)
        fixture.unlink(missing_ok=True)
    (ROOT/'dashboard/evidence/browser-audit-20261012.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    return 0 if all(x['ok'] for x in results) else 1
if __name__=='__main__':raise SystemExit(main())
