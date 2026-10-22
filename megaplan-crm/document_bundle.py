"""Validate actual outgoing PDFs against current CRM parties, not filenames."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path


def validate_invoice(invoice,deal_id,payer_id,recipient_id):
    expected={'deal':str(deal_id),'payer':str(payer_id),'recipient':str(recipient_id)}
    for field,value in expected.items():
        if str((invoice.get(field) or {}).get('id'))!=value:
            raise ValueError('Счёт относится к другой сделке, плательщику или нашей организации')
    amount=invoice.get('sum') or {}
    if amount.get('currency') not in (None,'RUB') or not Decimal(str(amount.get('value'))).is_finite():
        raise ValueError('Не подтверждена рублёвая сумма счёта')


def validate(spec,api):
    from contract_invoice import document_text,parse_contract,validate_contract_context
    from seller_documents import selected_seller,invoice_settings
    did=str(spec['deal_id']);fid=str(spec['contract_file_id'])
    deal=api._call('GET','/deal/'+did)['data']
    files=api._call('GET',f'/deal/{did}/allFiles',params={'limit':100}).get('data') or []
    if not any(str(f.get('id'))==fid for f in files):raise ValueError('PDF договора не найден среди файлов этой сделки')
    payer_id=str((deal.get('payer') or {}).get('id') or '')
    if not payer_id:raise ValueError('Не выбран плательщик')
    payer=api._call('GET','/payer/'+payer_id)['data']
    text=document_text(spec['contract_path']);parsed=parse_contract(text,'6.4.1')
    validate_contract_context(text,parsed,deal,selected_seller(did),payer)
    recipient_id,_=invoice_settings(did)
    invoices=[]
    for iid in spec['invoice_ids']:
        invoice=api._call('GET','/invoice/'+str(iid))['data']
        validate_invoice(invoice,did,payer_id,recipient_id)
        invoices.append({k:invoice.get(k) for k in ('id','number','invoiceDate','sum','rows','payer','recipient','deal')})
    evidence={'deal_id':did,'payer_id':payer_id,'recipient_id':recipient_id,'contract_file_id':fid,
        'contract_sha256':hashlib.sha256(Path(spec['contract_path']).read_bytes()).hexdigest(),'invoices':invoices}
    return {'ok':True,'fingerprint':hashlib.sha256(json.dumps(evidence,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest(),
            'contract_number':parsed['contract_number'],'contract_date':parsed['contract_date']}
