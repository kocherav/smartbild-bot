"""Freeze sale rows from an explicitly approved contract total; never reprice by today's FX."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
import copy

def dec(x):
 d=Decimal(str(x))
 if not d.is_finite():raise ValueError('Некорректная сумма')
 return d

def cents(x):return int((dec(x)*100).quantize(Decimal(1),rounding=ROUND_HALF_UP))
def signature(row):
 return {'quantity':str(row['quantity']),'offer_id':str(row['offer']['id']),'price':copy.deepcopy(row['price']),'discount':copy.deepcopy(row.get('discount')),'sum':copy.deepcopy(row['sum'])}

def plan(deal,contract_total,contract_net,source_sha256,source_date):
 """contract_net maps every row ID to its approved net sum in that row's currency."""
 rows=deal['positions'];ids={str(r['id']) for r in rows}
 if set(contract_net)!=ids:raise ValueError('Договор должен объяснять каждую строку сделки')
 currencies={r['sum'].get('currency','RUB') for r in rows}-{'RUB'}
 if len(currencies)!=1:raise ValueError('Нужна одна валютная часть для однозначного расчёта курса')
 rub=sum(dec(contract_net[str(r['id'])]) for r in rows if r['sum'].get('currency','RUB')=='RUB')
 foreign=[r for r in rows if r['sum'].get('currency','RUB')!='RUB'];mass=sum(dec(contract_net[str(r['id'])]) for r in foreign)
 remainder=dec(contract_total)-rub
 if mass<=0 or remainder<=0:raise ValueError('Некорректный валютный остаток')
 for r in rows:
  if r['sum'].get('currency','RUB')=='RUB' and cents(r['sum']['value'])!=cents(contract_net[str(r['id'])]):raise ValueError('Рублёвая строка расходится с договором')
 exact={str(r['id']):dec(contract_net[str(r['id'])])*dec(cents(remainder))/mass for r in foreign}
 amounts={k:int(v.quantize(Decimal(1),rounding=ROUND_DOWN)) for k,v in exact.items()}
 for key in sorted(exact,key=lambda k:(-(exact[k]-amounts[k]),k))[:cents(remainder)-sum(amounts.values())]:amounts[key]+=1
 targets=[]
 for r in foreign:
  rid=str(r['id']);qty=dec(r['quantity']);discount=r.get('discount') or {};kind=discount.get('type','absolute');value=dec(discount.get('value',discount.get('valueInMain',0)))
  if kind=='percent':factor=1-value/100
  elif kind=='absolute' and value==0:factor=Decimal(1)
  else:raise ValueError('Для ненулевой абсолютной скидки требуется явный рублёвый план скидки')
  if qty<=0 or factor<=0:raise ValueError('Некорректное количество или скидка')
  target=dec(amounts[rid])/100;unit=(target/qty/factor).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP)
  if cents(unit*qty*factor)!=amounts[rid]:raise ValueError('Точность цены CRM не позволяет сохранить копейки строки')
  targets.append({'row_id':rid,'original':signature(r),'contract_net':str(contract_net[rid]),'unit_rub':str(unit),'total_cents':amounts[rid]})
 return {'deal_id':str(deal['id']),'source_sha256':source_sha256,'source_date':source_date,'source_currency':next(iter(currencies)),'contract_total_cents':cents(contract_total),'rub_part':str(rub),'foreign_mass':str(mass),'foreign_rub':str(remainder),'derived_rate':str(remainder/mass),'targets':targets,'original_rows':{str(r['id']):signature(r) for r in rows}}

def target_matches(row,target):
 return row['price'].get('currency')=='RUB' and row['sum'].get('currency')=='RUB' and dec(row['price']['value'])==dec(target['unit_rub']) and cents(row['sum']['value'])==target['total_cents'] and dec(row['quantity'])==dec(target['original']['quantity']) and str(row['offer']['id'])==target['original']['offer_id'] and row.get('discount')==target['original']['discount']

def apply(api,fixation,progress,save):
 did=fixation['deal_id'];current=api._call('GET','/deal/'+did)['data'];by={str(r['id']):r for r in current['positions']};targets={t['row_id']:t for t in fixation['targets']}
 if set(by)!=set(fixation['original_rows']):raise ValueError('Состав сделки изменён после плана фиксации')
 for rid,row in by.items():
  if rid in targets and target_matches(row,targets[rid]):continue
  if signature(row)!=fixation['original_rows'][rid]:raise ValueError('Строка изменена после плана фиксации: '+rid)
 for target in fixation['targets']:
  rid=target['row_id']
  if not target_matches(by[rid],target):
   api.update_offer_row_price(rid,float(target['unit_rub']))
   verified=next(r for r in api._call('GET','/deal/'+did)['data']['positions'] if str(r['id'])==rid)
   if not target_matches(verified,target):raise ValueError('CRM не подтвердила рублёвую строку '+rid)
  progress[rid]={'verified':True,'total_cents':target['total_cents']};save()
 final=api._call('GET','/deal/'+did)['data'];rows={str(r['id']):r for r in final['positions']}
 if any(not target_matches(rows[t['row_id']],t) for t in fixation['targets']):raise ValueError('После фиксации цены строк изменились')
 if cents(final['price']['value'])!=fixation['contract_total_cents'] or final['price'].get('currency')!='RUB':raise ValueError('Итог CRM не совпал с договором')
 if sum(cents(r['sum']['value']) for r in rows.values())!=fixation['contract_total_cents']:raise ValueError('Строки не сходятся с договором')
 return final
