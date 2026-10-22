"""Find new invoice-to-deal links, before any offer_row_id exists on the invoice."""
import re,sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'dashboard'))
import matching_store
from product_matching import compare,canonical
import allocation_workspace as aw

def unit(value):
 s=re.sub(r'[\s.]','',str(value or '').lower())
 return {'штук':'шт','штука':'шт','метр':'м','метры':'м','мп':'м','комплект':'компл','компл':'компл','м2':'м²','м3':'м³'}.get(s,s)

def candidates(registry,ledgers):
 from procurement_usage import totals
 usage=totals(registry)
 inputs={};links={};stocks=registry.get('unallocated_stock',[])
 for inv in registry.get('invoices',[]):
  if inv.get('intake',{}).get('state') not in ('ready',None):continue
  scope=set(map(str,inv.get('candidate_deal_ids',[])))|{str(a['deal_id']) for a in inv.get('allocations',[])}
  for stock in stocks:
   if stock.get('document_key')!=inv['document_key'] or aw.number(stock.get('available_qty',0))<=0:continue
   scores=[]
   for did in scope:
    for e in ledgers.get(did,[]):
     if e.get('position_type')=='service':continue
     remaining=aw.number(e.get('qty',0))-max(aw.number(e.get('consumed_qty',0)),usage.get((did,str(e.get('offer_row_id'))),{}).get('qty',Decimal(0)))
     if remaining<=0 or not e.get('offer_row_id'):continue
     rule=compare(stock['name'],e['name'])
     a=set(re.findall(r'[\w]+',canonical(stock['name'])));b=set(re.findall(r'[\w]+',canonical(e['name'])))
     score=len(a&b)/max(1,len(a|b))
     if rule['same'] or score>=.08:scores.append((2 if rule['same'] else score,did,e,remaining,rule))
   scores.sort(key=lambda x:-x[0])
   # Candidate retrieval is NOT a match decision; semantic approval is separate.
   selected=[x for x in scores if x[4]['same']] or scores[:4]
   for _,did,e,remaining,rule in selected:
    row={'id':str(e['offer_row_id']),'name':e['name'],'quantity':e['qty'],'unit':e.get('unit','')}
    line={'key':stock['source_line_key'],'source_name':stock['name'],'source_sku':stock.get('sku',''),'source_qty':stock.get('initial_qty'),'qty_used':str(min(remaining,aw.number(stock['available_qty']))),'source_unit':stock.get('unit',''),'stock_id':stock['id']}
    key,payload=matching_store.candidate(did,row,line,inv);payload['allocation_stock_id']=stock['id']
    inputs[key]=payload;links[key]={'id':key,'line_id':stock['id'],'deal_id':did,'offer_row_id':str(e['offer_row_id']),'name':e['name'],'remaining':str(remaining),'unit':e.get('unit',''),'unit_compatible':bool(unit(stock.get('unit')) and unit(stock.get('unit'))==unit(e.get('unit')) and not (unit(stock.get('unit'))=='шт' and re.search(r'\b\d+(?:[.,]\d+)?\s*м\b',stock['name'],re.I))),'rule':rule}
 return inputs,links

def suggestions(registry,ledgers,path=None):
 inputs,links=candidates(registry,ledgers);decisions=matching_store.project(inputs,path)
 result=[]
 for key,link in links.items():
  decision=decisions.get(key,{})
  approved=link['rule']['same'] or decision.get('state') in ('auto','accepted')
  result.append({**link,**decision,'approved':approved and not link['rule']['conflicts'],'state':'rule' if link['rule']['same'] else decision.get('state','queued'),'reason':link['rule']['basis'] if link['rule']['same'] else decision.get('reason','Проверяет ИИ'),'conflicts':link['rule']['conflicts']})
 return result

def auto_parts(document,options):
 result=[];budget={}
 for line in document['lines']:
  choices=[o for o in options if o['line_id']==line['id'] and o['approved'] and o['unit_compatible']]
  if len(choices)!=1:continue
  c=choices[0];key=(c['deal_id'],c['offer_row_id']);budget.setdefault(key,aw.number(c['remaining']));qty=min(aw.number(line['qty']),budget[key])
  if qty<=0:continue
  budget[key]-=qty
  result.append({'line_id':line['id'],'deal_id':c['deal_id'],'offer_row_id':c['offer_row_id'],'qty':str(qty),'covered_qty':str(qty),'match_id':c['id'],'identity_confirmed':True,'reason':c['reason']})
 return result
