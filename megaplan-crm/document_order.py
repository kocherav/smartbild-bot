"""Finish a requested contract + full invoice with per-stage durable receipts."""
import copy,hashlib,json,re,sys,shutil,tempfile
from pathlib import Path
from datetime import datetime
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'telegram-bridge'))
from megaplan_api import MegaplanAPI
from generate_contract import contract_data,generate,validate_confirmed_source
from payer_signatory_store import get_signatory
from seller_documents import selected_seller
from document_tax_policy import require_document_tax,decorate
from workflow_runtime import Store
from effect_runner import execute


class OrderStepError(RuntimeError):
    def __init__(self, stage, result):
        super().__init__(stage + ': ' + str(result.get('error')))
        self.result = {**result, 'ok': False, 'stage': stage, 'error': str(self),
                       'requires_reconciliation': bool(result.get('uncertain') or result.get('requires_reconciliation'))}


def document_fingerprint(data):
    stable = copy.deepcopy(data)
    # CRM expansion, last-access timestamps and unrelated balances are not legal terms.
    stable['payer'] = {key: data['payer'].get(key, '') for key in (
        'id', 'name', 'legalAddress', 'ogrn', 'inn', 'kpp', 'currentAccount',
        'bank', 'bik', 'correspondentAccount')}
    stable['_seller'] = selected_seller(data['deal_id'])
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def named_invoice_file(fetched):
    filename = fetched.get('filename')
    if not filename or Path(filename).name != filename or not filename.lower().endswith('.pdf'):
        raise ValueError('Мегаплан не вернул корректное имя файла счёта')
    path = Path(tempfile.mkdtemp(prefix='invoice-delivery-')) / filename
    shutil.copyfile(fetched['path'], path)
    return str(path)


def norm(s):return ''.join(re.findall(r'[a-zа-я0-9]',str(s).casefold().replace('ё','е')))

def plan(spec,api):
    deal=copy.deepcopy(api._call('GET','/deal/'+str(spec['deal_id']))['data'])
    details=spec.get('details') or {};missing=[]
    for key,label in [('date','Дата'),('address','Адрес'),('payer','Плательщик')]:
        if not str(details.get(key) or '').strip():missing.append(label)
    ref=deal['contractor'];kind=ref['contentType'];endpoint=kind[0].lower()+kind[1:]
    client=api._call('GET',f'/{endpoint}/{ref["id"]}')['data']
    payers=client.get('payers') or []
    wanted=norm(details.get('payer',''))
    chosen=[p for p in payers if wanted and wanted in (norm(p.get('id')),norm(p.get('name')),norm(p.get('inn')))]
    if not chosen and wanted.isdigit() and len(wanted) in (10,12):
        payers=[api._call('GET',f'/payer/{p["id"]}')['data'] for p in payers]
        chosen=[p for p in payers if norm(p.get('inn'))==wanted]
    if wanted and len(chosen)!=1:missing.append('Плательщик: выберите одну из существующих карточек клиента')
    response={'ok':True,'ready':False,'missing':missing,'payers':[{'id':p['id'],'name':p.get('name','')} for p in payers], 'deal_id':str(spec['deal_id'])}
    if len(chosen)!=1:return response
    payer=api._call('GET',f'/payer/{chosen[0]["id"]}')['data'];deal['payer']=payer
    signer={**get_signatory(str(payer['id'])),**{k:details[k] for k in ('name','position','authority') if details.get(k)}}
    if details.get('date'):
        date=datetime.strptime(details['date'],'%d.%m.%Y')
        deal['Category1000068CustomFieldDataDogovora']={'contentType':'DateOnly','year':date.year,'month':date.month-1,'day':date.day}
    deal['Category1000068CustomFieldAdresObEkta']=details.get('address','')
    # Internal order instructions never become the legal subject of the contract.
    deal['Category1000068CustomFieldPredmetDogovora']=details.get('subject') or 'Поставка оборудования и материалов'
    data=contract_data(deal,{'customer_signatory':signer,'customer_signatory_payer_id':str(payer['id'])})
    rates=require_document_tax(deal,api);decorate(data,rates)
    if details.get('delivery_workdays') is not None:data['delivery_workdays']=details['delivery_workdays']
    missing.extend(data['missing']);response.update(missing=list(dict.fromkeys(missing)),data=data)
    response['ready']=not response['missing']
    return response


def fulfill(spec,api,store,send_file,fetch_invoice,upload_contracts,fresh=lambda:True):
    prepared=plan(spec,api)
    if not prepared['ready']:return prepared
    data=prepared['data'];deal_id=str(spec['deal_id']);actor=str(spec['chat_id'])
    data['payment_advance']=data['total'];data['payment_final']=0
    fingerprint=document_fingerprint(data)
    with store.connect() as db:
        issued=[dict(r) for r in db.execute("SELECT * FROM operations WHERE actor=? AND scenario=? AND status='succeeded'",(actor,'document-order:invoice'))]
    if any(json.loads(r['target']).get('deal_id')==deal_id and json.loads(r['payload'])!={'fingerprint':fingerprint} for r in issued):
        raise ValueError('Счёт этого заказа уже выпущен. Изменённые условия требуют корректировки существующих документов; повторный выпуск остановлен до изменения данных.')
    validate_confirmed_source(api,data)
    # One order is tied to the created deal; preserve its receipts across retries.
    intent='document-order:'+deal_id
    def step(name,payload,fn):
        step_intent=intent
        target={'deal_id':deal_id}
        if name == 'upload':
            with store.connect() as db:
                prior = [store.decode(r) for r in db.execute(
                    'SELECT * FROM operations WHERE actor=? AND scenario=? ORDER BY created_at',
                    (actor, 'document-order:upload'))]
            prior = [r for r in prior if r['target'].get('deal_id') == deal_id]
            unresolved = next((r for r in prior if r['status'] in ('running', 'uncertain')), None)
            if unresolved:
                raise OrderStepError(name, {'ok': False, 'requires_reconciliation': True,
                    '_operation_id': unresolved['id'],
                    'error': 'Нужна сверка загрузки договора: ' + unresolved['id']})
            failed = [r for r in prior if r['status'] == 'failed' and (r.get('receipt') or {}).get('no_effect')]
            if len(failed) >= 3:
                raise OrderStepError(name, {'ok': False, 'requires_reconciliation': True,
                    'error': 'Три попытки загрузки завершились без записи. Требуется техническая проверка.'})
            if failed:
                step_intent += ':verified-no-effect-' + str(len(failed))
        if name=='invoice':
            with store.connect() as db:
                prior_invoice=[dict(r) for r in db.execute("SELECT * FROM operations WHERE actor=? AND scenario=? AND status='succeeded'",(actor,'document-order:invoice'))]
            for old in prior_invoice:
                if json.loads(old['target']).get('deal_id')==deal_id:
                    if json.loads(old['payload'])!=payload:
                        raise RuntimeError('Счёт этого заказа уже выпущен. Условия изменились; нужна корректировка существующих документов, повторный счёт не создаётся.')
                    return json.loads(old['receipt'])
        if name.startswith('send-'):
            with store.connect() as db:
                prior=[dict(r) for r in db.execute('SELECT * FROM operations WHERE actor=? AND scenario=? ORDER BY created_at',
                       (actor,'document-order:'+name))]
            prior=[r for r in prior if json.loads(r['payload'])==payload and json.loads(r['target']).get('deal_id')==deal_id]
            successful=next((r for r in prior if r['status']=='succeeded'),None)
            if successful:return json.loads(successful['receipt'])
            if any(r['status']=='running' for r in prior):raise RuntimeError('Отправка уже выполняется')
            if len(prior)>=3:raise RuntimeError('Три попытки доставки не подтверждены. Требуется проверка Telegram; финансовые этапы сохранены.')
            step_intent+=':delivery-'+str(len(prior))
            # A requested retry is another Telegram delivery attempt, never another invoice.
            target['delivery_attempt']=str(len(prior))
        result=execute(store,actor,'document-order:'+name,step_intent,target,payload,fn,fresh=fresh)
        if not result.get('ok'):raise OrderStepError(name,result)
        return result
    fields={'contentType':'Deal','payer':{'contentType':'Payer','id':data['payer_id']},
            'Category1000068CustomFieldDataDogovora':{'contentType':'DateOnly','day':int(data['date'][:2]),'month':int(data['date'][3:5])-1,'year':int(data['date'][6:])},
            'Category1000068CustomFieldAdresObEkta':data['address'],'Category1000068CustomFieldPredmetDogovora':data['subject']}
    def update():
        api._call('POST','/deal/'+deal_id,json_body=fields)
        live=api._call('GET','/deal/'+deal_id)['data']
        if str((live.get('payer') or {}).get('id'))!=data['payer_id'] or live.get('Category1000068CustomFieldAdresObEkta')!=data['address']:
            raise ValueError('CRM fields not confirmed')
        return {'ok':True,'deal_id':deal_id}
    step('fields',fields,update)
    def render():
        data['_seller']=selected_seller(deal_id)
        docx,pdf=generate(data)
        return {'ok':True,'docx_path':str(docx),'pdf_path':str(pdf)}
    files=step('render',{'fingerprint':fingerprint},render)
    for k in ('docx_path','pdf_path'):
        if not Path(files[k]).is_file():raise ValueError('Сохранённый файл отсутствует: '+k+'. Требуется восстановить файл; финансовые этапы не повторять.')
    step('upload',{'fingerprint':fingerprint},lambda:upload_contracts(deal_id,[files['docx_path'],files['pdf_path']]))
    from contract_invoice import preview_full,create_full
    invoice_preview=preview_full({'deal_id':deal_id},api)
    invoice=step('invoice',{'fingerprint':fingerprint},lambda:create_full({'deal_id':deal_id,'expected_fingerprint':invoice_preview['fingerprint']},api))
    step('send-contract',{'fingerprint':fingerprint},lambda:send_file(actor,files['pdf_path'],f'Договор по сделке №{deal_id}'))
    step('send-word',{'fingerprint':fingerprint},lambda:send_file(actor,files['docx_path'],f'Договор по сделке №{deal_id} — Word'))
    def send_invoice():
        fetched=fetch_invoice({'invoiceId':invoice['invoice_id']})
        if not fetched.get('ok'):return fetched
        return send_file(actor,named_invoice_file(fetched),f'Счёт №{invoice.get("invoice_number") or invoice["invoice_id"]} — 100% оплаты по сделке №{deal_id}')
    delivery=step('send-invoice',{'invoice_id':invoice['invoice_id']},send_invoice)
    return {'ok':True,'ready':True,'complete':True,'deal_id':deal_id,'invoice_id':invoice['invoice_id'],'delivery':delivery}


def main():
    spec=json.load(sys.stdin);api=MegaplanAPI()
    if spec.get('action')=='plan':result=plan(spec,api)
    else:
        import bridge,closing_runtime
        result=fulfill(spec,api,Store(bridge.WORKFLOW_DB_FILE),closing_runtime.send_file,bridge.fetch_megaplan_invoice_pdf,
                       lambda deal,paths:bridge.run_deal_browser({'action':'upload_contracts','deal_id':deal,'paths':paths}),
                       fresh=lambda:bridge.ui_state_store().current(spec['chat_id']).get('_revision')==spec.get('expected_revision'))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except OrderStepError as exc:print(json.dumps(exc.result,ensure_ascii=False));sys.exit(1)
    except Exception as exc:print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));sys.exit(1)
