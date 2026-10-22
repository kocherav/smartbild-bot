#!/usr/bin/env python3
"""Create confirmed, idempotent Megaplan expense operations from bank email candidates."""
import json, os, sys, hashlib, math, re
from registry_transaction import transaction
from datetime import datetime
from megaplan_api import MegaplanAPI
from contract_invoice import v1_auth, v1_call

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
REGISTRY=os.path.join(BASE_DIR,"megaplan_finance_registry.json")
PROCUREMENT=os.path.join(BASE_DIR,"procurement_registry.json")
ACCOUNT_BY_BUYER_INN={"7743926877":"20","7743151323":"22"}
PURCHASE_OPERATION_TYPE="23"

def load(path,default):
    try:return json.load(open(path,encoding="utf-8"))
    except FileNotFoundError:return default
def save(path,value):
    tmp=path+'.tmp'; json.dump(value,open(tmp,'w',encoding='utf-8'),ensure_ascii=False,indent=2,allow_nan=False); os.replace(tmp,path)

def operation_form(candidate, invoice, account_id):
    contractor_id=invoice.get("supplier_contractor_id")
    if not contractor_id:
        supplier_map=load("/home/kocher.av/hogart-scraper/finance/evidence/payment_correction/supplier_mapping.json",{})
        contractor_id=supplier_map.get(str(invoice.get("supplier_inn") or ""),{}).get("contractor_id")
    if not contractor_id:raise ValueError("Для денежной операции без получения товара нужен проверенный ID поставщика в Мегаплане")
    return {"Model[OperationType]":PURCHASE_OPERATION_TYPE,"Model[Kind]":"expense",
            "Model[Sum][Value]":f"{float(invoice['total']):.2f}","Model[Sum][Currency]":"1",
            "Model[SecondarySum][Value]":"0.00","Model[SecondarySum][Currency]":"1",
            "Model[ControlDate]":datetime.now().strftime("%Y-%m-%d"),
            "Model[Contractor]":str(contractor_id),
            "Model[RealAccount]":str(account_id),
            "Model[Date]":datetime.strptime(candidate["date"],"%d.%m.%Y").strftime("%Y-%m-%d 12:00:00"),
            "Model[DocumentNumber]":str(candidate.get("payment_number") or ""),
            "Model[Description]":f"Оплата поставщику по счёту №{invoice['number']}. {candidate.get('purpose','')}"[:255]}

def megaplan_operations(api, auth):
    """Read enough finance history to make retries safe after a worker restart."""
    result=[]
    for offset in range(0,2000,100):
        response=v1_call(api,'/BumsFinApiV01/Operation/list.api',{"Limit":100,"Offset":offset},auth)
        items=(response.get('data') or {}).get('items') or []
        result.extend(items)
        if len(items)<100: return result
    raise ValueError('История финансовых операций получена не полностью; безопасный поиск повторов не завершён')

def existing_operation(items, candidate, invoice, account_id):
    invoice_marker=f"счёту №{invoice['number']}".casefold()
    expected_date=datetime.strptime(candidate["date"],"%d.%m.%Y").strftime("%Y-%m-%d")
    found=[]
    for item in items:
        amount=float(((item.get('Sum') or {}).get('Value') or 0))
        real_account=str((item.get('RealAccount') or {}).get('Id') or '')
        if (item.get('Kind')=='expense'
                and str(item.get('DocumentNumber') or '')==str(candidate.get('payment_number') or '')
                and str(item.get('Date') or '').startswith(expected_date)
                and real_account==str(account_id)
                and abs(amount-float(invoice['total']))<0.01
                and re.search(re.escape(invoice_marker)+r'(?![\w/-])',str(item.get('Description') or '').casefold())):
            found.append(item)
    if len(found)>1: raise ValueError('Найдено несколько финансовых операций с одинаковыми реквизитами; нужна сверка')
    return found[0] if found else None

@transaction(lambda:PROCUREMENT)
def record_procurement_payments(candidate, operations):
    data=load(PROCUREMENT,{"invoices":[]})
    for op in operations:
        source=[x for x in candidate.get('invoices') or [] if str(x.get('number'))==str(op['invoice_number'])]
        if len(source)!=1 or not source[0].get('id'): raise ValueError('Не подтверждён ID счёта поставщика')
        matches=[x for x in data.get('invoices') or [] if str(x.get('id'))==str(source[0]['id'])]
        if len(matches)!=1: raise ValueError('Исходный счёт поставщика не найден однозначно по ID')
        invoice=matches[0]
        txid=f"email:{candidate['id']}:{op['invoice_number']}"
        payments=invoice.setdefault('payments',[])
        if not any(x.get('transaction_id')==txid for x in payments):
            payments.append({"transaction_id":txid,"date":candidate['date'],"amount":op['amount'],
                             "megaplan_operation_id":op['operation_id'],"source":"email"})
        invoice['paid_total']=round(sum(float(x.get('amount') or 0) for x in payments),2)
        invoice['status']='оплачен' if invoice['paid_total']+0.01>=float(invoice.get('total') or 0) else 'частично оплачен'
    save(PROCUREMENT,data)

@transaction(lambda:REGISTRY)
def create(candidate, api=None):
    if os.path.exists("/home/kocher.av/hogart-scraper/finance/data/posting_paused.json"):raise ValueError("Автопроведение приостановлено на время проверки оплаты и отгрузки")
    if not candidate.get('exact'): raise ValueError('платёж не имеет однозначного соответствия')
    invoices=candidate.get('invoices') or []
    amounts=[float(x.get('total') or 0) for x in invoices]
    payment_amount=float(candidate.get('amount') or 0)
    if not invoices or not math.isfinite(payment_amount) or any(not math.isfinite(x) or x<=0 for x in amounts) or abs(sum(amounts)-payment_amount)>.01:
        raise ValueError('Суммы счетов не совпадают с банковским платежом')
    if len({str(x.get('number')) for x in invoices}) != len(invoices) or any(not x.get('id') for x in invoices):
        raise ValueError('Неоднозначные номера или отсутствуют ID счетов поставщика')
    registry=load(REGISTRY,{"operations":[]})
    prior=[x for x in registry['operations'] if x.get('candidate_id')==candidate['id']]
    by_invoice={str(x.get('invoice_number')):x for x in prior}
    api=api or MegaplanAPI(); auth=v1_auth(api); created=[]; recovered=[]
    remote_items=megaplan_operations(api,auth)
    for invoice in candidate.get('invoices') or []:
        invoice_number=str(invoice['number'])
        if invoice_number in by_invoice:
            continue
        account=ACCOUNT_BY_BUYER_INN.get(str(invoice.get('buyer_inn') or ''))
        if not account: raise ValueError(f"не определён расчётный счёт для ИНН {invoice.get('buyer_inn')}")
        existing=existing_operation(remote_items,candidate,invoice,account)
        if existing:
            operation_id=str(existing['Id']); recovered_flag=True
        else:
            response=v1_call(api,'/BumsFinApiV01/Operation/save.api',operation_form(candidate,invoice,account),auth)
            item=(response.get('data') or {}).get('item') or (response.get('data') or {}).get('Operation') or response.get('data') or {}
            operation_id=str(item.get('Id') or item.get('id') or '')
            if not operation_id: raise ValueError('Мегаплан не вернул ID финансовой операции')
            verified=(v1_call(api,'/BumsFinApiV01/Operation/card.api',{'Id':operation_id},auth).get('data') or {}).get('item') or {}
            if float((verified.get('SecondarySum') or {}).get('Value',-1))!=0 or abs(float((verified.get('Sum') or {}).get('Value',0))-float(invoice['total']))>.01:
                raise ValueError('Проверка денежной операции не пройдена: сумма оплаты или товарное движение отличаются')
            recovered_flag=False
        row={"id":hashlib.sha256(f"{candidate['id']}|{invoice['number']}".encode()).hexdigest()[:20],
             "candidate_id":candidate['id'],"operation_id":operation_id,"invoice_number":invoice['number'],
             "amount":float(invoice['total']),"deal_ids":candidate.get('deal_ids') or [],"created_at":datetime.now().isoformat(),
             "recovered":recovered_flag}
        registry['operations'].append(row); save(REGISTRY,registry)
        (recovered if recovered_flag else created).append(row)
        for deal_id in candidate.get('deal_ids') or []:
            api._call('POST',f"/deal/{deal_id}/comments",json_body={"contentType":"Comment",
                "subject":{"contentType":"Deal","id":str(deal_id)},
                "content":f"{'Найдена ранее созданная' if recovered_flag else 'Создана'} расходная операция №{operation_id}: {row['amount']:.2f} руб. по счёту поставщика №{invoice['number']}; платёж №{candidate.get('payment_number')} от {candidate.get('date')}."})
    operations=[x for x in registry['operations'] if x.get('candidate_id')==candidate['id']]
    record_procurement_payments(candidate,operations)
    return {"ok":True,"duplicate":not created,"operations":operations,"created":created,"recovered":recovered}

def main():
    req=json.load(sys.stdin)
    if req.get('action')=='create': result=create(req['candidate'])
    else: result={"ok":False,"error":"неизвестное действие"}
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception as exc:print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False));raise SystemExit(1)
