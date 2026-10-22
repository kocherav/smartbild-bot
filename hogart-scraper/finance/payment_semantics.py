"""Trade payments never imply delivery; explicitly identified bank services/income settle without goods."""
from decimal import Decimal

def cents(value):return int((Decimal(str(value))*100).quantize(Decimal('1')))

# Narrow, identity-checked company payments. A cash advance does not recognize service delivery.
COMPANY_CASH = {
 ('Единый налоговый платёж','7727406020'): '25',
 ('Страховые взносы','7703363868'): '25',
 ('Связь','7812014560'): '25', ('Связь','7702388235'): '25', ('Связь','7709501144'): '25',
 ('ИТ и подписки','7714415613'): '25', ('ИТ и подписки','7810945525'): '25',
 ('Членские взносы','7734268607'): '25',
 ('Заработная плата','690501575701'): '25',
 ('Выдача под отчёт','690501575701'): '25',
 ('Взыскание','7727406020'): '25',
 ('ИТ и подписки','4345115602'): '25',
 ('Страхование','7710045520'): '25',
 ('Штрафы','7714887870'): '25',
 # Explicit owner answers in workbook 07.10.2026; verified payer INNs.
 ('Внепроектные закупки и услуги','7722753969'): '25',
 ('Внепроектные закупки и услуги','7743795913'): '25',
 ('Внепроектные закупки и услуги','770504195313'): '25',
 ('Внепроектные закупки и услуги','502805650665'): '25',
 ('Внепроектные закупки и услуги','9703149995'): '25',

 ('Внепроектные закупки и услуги','7717632694'): '25',
 ('Внепроектные закупки и услуги','7720298746'): '25',
 ('Внепроектные закупки и услуги','9704254424'): '25',
 ('Внепроектные закупки и услуги','782704631045'): '25',
 ('Внепроектные закупки и услуги','9726067241'): '25',
 ('Внепроектные закупки и услуги','183513773502'): '25',
 ('Внепроектные закупки и услуги','332912396061'): '25',
 ('Внепроектные закупки и услуги','770406087486'): '25',
 ('Закупки для Деревянко','7717632694'): '23',
 ('Внепроектные закупки и услуги','332904300538'): '25',
}
def verified_company_operation(payment):
    if payment.get('allocation_scope')!='company' or payment.get('deal_id'):return False
    cat=payment.get('category');inn=payment.get('counterparty_inn');kind=payment.get('kind');typ=payment.get('operation_type')
    if cat=='Возвращённый аванс СТК' and inn=='7704845920' and payment.get('refund_pair_id') and payment.get('contractor_id')=='1002588' and ((kind=='expense' and typ=='23') or (kind=='income' and typ=='30')):return True
    if cat=='ИТ и подписки' and inn=='7728168971' and kind=='expense' and typ=='25' and payment.get('receipt_supplier_inn')=='9704259180' and payment.get('receipt_verified') and payment.get('card_last4')=='2624':return True
    if inn=='7728168971' and (cat,kind,typ) in {('Банковские комиссии','expense','25'),('Проценты по депозиту','income','32')}:return True
    if cat=='Расчёты между компаниями группы' and inn in {'7743926877','7743151323'} and payment.get('intercompany_pair_id') and ((kind=='income' and typ=='31') or (kind=='expense' and typ=='23')):return True
    if inn in {'7743926877','7743151323'} and payment.get('deposit_contract') and payment.get('contractor_id')=='1000609' and (cat,kind,typ) in {('Размещение депозита','expense','22'),('Возврат депозита','income','30')}:return True
    if inn=='7807391482' and cat in {'Проценты по займу','Пени по займу'} and kind=='income' and typ=='32':return True
    return kind=='expense' and COMPANY_CASH.get((cat,inn))==typ

def company_settled(payment):
    return verified_company_operation(payment) and (payment['operation_type']=='32' or payment.get('category')=='Банковские комиссии')

def expected_secondary_cents(payment):
    return payment['amount_cents'] if company_settled(payment) else 0

def semantics_label(payment):
    if not company_settled(payment):return 'cash_only'
    return 'nontrade_income' if payment['kind']=='income' else 'bank_service_settled'

def cash_form(payment, review_date):
    form={'Model[OperationType]':payment['operation_type'],'Model[Kind]':payment['kind'],
          'Model[Sum][Value]':f"{payment['amount_cents']/100:.2f}",'Model[Sum][Currency]':'1',
          'Model[SecondarySum][Value]':f"{expected_secondary_cents(payment)/100:.2f}",'Model[SecondarySum][Currency]':'1',
          'Model[ControlDate]':review_date,'Model[RealAccount]':payment['account_id'],
          'Model[Date]':payment['date']+' 12:00:00','Model[DocumentNumber]':payment['document_number'],
          'Model[Description]':payment['description']}
    if not payment.get('contractor_id'):raise ValueError('Cash-only payment requires a verified contractor; otherwise CRM ignores zero goods')
    if payment['kind']=='income' and not verified_company_operation(payment) and not (payment.get('crm_invoice_id') and payment.get('contractor_id')):
        raise ValueError('Incoming payment needs a verified invoice and contractor')
    if payment.get('crm_invoice_id'):form['Model[Invoice]']=payment['crm_invoice_id']
    if payment.get('contractor_id'):form['Model[Contractor]']=payment['contractor_id']
    return form

def invoice_cash_status(invoice):
    operations=invoice.get('financeOperations',[])
    if int(invoice.get('financeOperationsCount',len(operations)))!=len(operations):
        raise ValueError('Invoice payment collection is incomplete')
    if len({str(o['id']) for o in operations})!=len(operations):raise ValueError('Duplicate invoice operations')
    amount=0
    for operation in operations:
        if operation['kind']!='income':raise ValueError('Invoice has a non-income operation; review required')
        money=operation.get('incomeSum')
        if money is None or money.get('currency')!='RUB':raise ValueError('Invoice cash amount is not verified')
        amount+=cents(money['value'])
    if invoice['sum'].get('currency')!='RUB':raise ValueError('Invoice currency is not RUB')
    total=cents(invoice['sum']['value'])
    if amount>total:raise ValueError('Invoice overpayment needs review')
    return ('paid' if amount==total and total>0 else 'drawn'),amount

def verify_cash_operation(operation,payment):
    if cents(operation['Sum']['Value'])!=payment['amount_cents']:raise ValueError('Cash changed')
    if cents(operation['SecondarySum']['Value'])!=expected_secondary_cents(payment):raise ValueError('Unexpected goods/secondary amount for operation type')
    if verified_company_operation(payment) and str((operation.get('OperationType') or {}).get('Id'))!=payment['operation_type']:raise ValueError('Wrong company operation type')
    if company_settled(payment) and operation.get('Status')!='closed':raise ValueError('Bank service/income should not create an open obligation')
    if str(operation['RealAccount']['Id'])!=payment['account_id'] or operation['Kind']!=payment['kind']:
        raise ValueError('Wrong cash direction/account')
