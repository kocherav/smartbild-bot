"""Read projection combining direct invoice rows and later stock allocations once."""
import copy

def effective_registry(data):
 result=copy.deepcopy(data)
 for inv in result.get('invoices',[]):
  for allocation in inv.get('allocations',[]):
   for line in allocation.get('source_lines',[]):
    if line.get('offer_row_id'):continue
    key=str(line.get('key') or line.get('source_sku') or '').casefold()
    updates=[u for u in allocation.get('updates',[]) if key and key in {str(u.get('source_line_key') or '').casefold(),str(u.get('source_sku') or '').casefold()}]
    if len(updates)==1:
     line['offer_row_id']=updates[0].get('offer_row_id');line['offer_id']=updates[0].get('offer_id')
  originals={str(l.get('key') or '').casefold():l for a in inv.get('allocations',[]) for l in a.get('source_lines',[])}
  for stock in data.get('unallocated_stock',[]):
   if stock.get('document_key')!=inv.get('document_key'):continue
   source=originals.get(str(stock.get('source_line_key') or '').casefold(),{})
   for part in stock.get('allocations',[]):
    line={'key':stock.get('source_line_key'),'offer_row_id':part.get('offer_row_id'),'offer_id':part.get('offer_id'),
          'source_name':stock.get('name'),'source_sku':stock.get('sku'),'source_qty':source.get('source_qty',stock.get('initial_qty')),
          'qty_used':part.get('covered_qty',part.get('qty')),'source_qty_used':part.get('qty'),'identity_confirmed':part.get('identity_confirmed',False),'identity_reason':part.get('reason',''),'source_unit':stock.get('unit',''),'amount_used':part.get('amount')}
    allocation={'id':'stock:'+part['id'],'deal_id':part['deal_id'],'amount':part['amount'],'source_lines':[line],'updates':[], 'stock_allocation':True}
    if part.get('cost_kind')=='expense':allocation['additional_expenses']=[{'source_name':stock.get('name'),'qty':part['qty'],'amount':part['amount']}]
    inv.setdefault('allocations',[]).append(allocation)
 return result


from decimal import Decimal

def confirmed_totals(registry):
 out={}
 for inv in effective_registry(registry).get('invoices',[]):
  for alloc in inv.get('allocations',[]):
   for line in alloc.get('source_lines') or alloc.get('updates') or []:
    if not line.get('offer_row_id'):continue
    key=(str(alloc['deal_id']),str(line['offer_row_id']));v=out.setdefault(key,{'qty':Decimal(0),'cost':Decimal(0)})
    v['qty']+=Decimal(str(line.get('qty_used') or 0));v['cost']+=Decimal(str(line.get('amount_used',line.get('material_cost_used',0)) or 0))
 return out
