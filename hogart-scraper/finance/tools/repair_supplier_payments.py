import sys,json,sqlite3,collections
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/payment_correction'
addresses={
'6623097295':'622036, Свердловская область, г. Нижний Тагил, ул. Серова, зд.14',
'6673199711':'622036, Свердловская область, г. Нижний Тагил, ул. Серова, зд.14',
'775114176346':'117535, г. Москва, 3-й Дорожный проезд, д.4, к.1, кв.151',
'9701027624':'123290, Россия, г. Москва, 1-й Магистральный тупик, 5А, 38/1',
'9701037968':'105005, г. Москва, ул. Бауманская, д.58, стр.16, оф.10А',
'7733272640':'141407, Московская область, г. Химки, ул. Бабакина, стр.5А, пом.316',
'7722805624':'127247, г. Москва, Дмитровское шоссе, д.100, стр.2, этаж02, пом.3243 А+Б',
'7811504932':'192029, г. Санкт-Петербург, наб. Обводного канала, д.14, лит.С, оф.350',
'9728104795':'115432, г. Москва, проезд Проектируемый 4062-й, д.6, стр.1, пом.2Б/5',
'7842224734':'191144, г. Санкт-Петербург, ул.7-я Советская, д.44, лит.Б, пом.6-Н',
'7717632694':'127521, г. Москва, 12-й проезд Марьиной Рощи, д.9, стр.1, этаж3',
'5038179677':'141204, Московская область, г. Пушкино, ул. Тургенева, д.1, пом.2, комн.3Е'}
payers=json.loads((D/'all_payers.json').read_text());assert len(payers)==3035
old=json.loads((D/'all_before.json').read_text());uses=collections.Counter(str(o.get('Contractor',{}).get('Id')) for o in old)
rows={r['id']:r for r in json.loads((ROOT/'reports/ledger.json').read_text())};j=json.loads(JOURNAL.read_text());parts=[p for p in j['operations'].values() if p['kind']=='expense']
map_path=D/'supplier_mapping.json';mapping=json.loads(map_path.read_text()) if map_path.exists() else {}
for inn in sorted({p['counterparty_inn'] for p in parts}):
 if mapping.get(inn,{}).get('contractor_id'):continue
 if mapping.get(inn,{}).get('state')=='creating':raise ValueError('Uncertain supplier creation; inspect before retry')
 candidates={p['contractor']['id']:p for p in payers if p.get('inn')==inn and p.get('contractor',{}).get('id') and not p.get('isDropped')}
 if candidates:
  cid=sorted(candidates,key=lambda c:(-uses[c],int(c)))[0]
  mapping[inn]={'contractor_id':cid,'state':'existing','basis':'Exact INN in full payer registry; prefer existing financial history, otherwise earliest card; no merge or deletion'}
 else:
  p=next(p for p in parts if p['counterparty_inn']==inn);name=rows[p['bank_operation_id']]['counterparty'];assert addresses.get(inn)
  payload={'contentType':'ContractorCompany','name':name,'type':{'contentType':'ContractorType','id':'5'},'description':'ИНН '+inn,'contactInfo':[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':addresses[inn]}]}
  mapping[inn]={'state':'creating','payload':payload};atomic(map_path,mapping)
  response=wait_budget(a._call,'POST','/contractorCompany',json_body=payload);atomic(D/('new_supplier_'+inn+'.json'),response);cid=response['data']['id']
  mapping[inn].update(contractor_id=cid,state='created',basis='Bank recipient legal name and INN; address from supplier invoice. Existing payer INNs and name search checked first.')
 atomic(map_path,mapping);print('supplier',inn,cid,mapping[inn]['state'],flush=True)
with locked(REG):
 for p in parts:
  ident=p['operation_id'];cid=mapping[p['counterparty_inn']]['contractor_id'];p['contractor_id']=cid
  before=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':ident},auth)['data']['item'];assert money_match(before,p)
  path=D/('expense_before_'+ident+'.json')
  if not path.exists():atomic(path,before)
  if not (cents(before['SecondarySum']['Value'])==0 and str(before.get('Contractor',{}).get('Id'))==cid):
   form=cash_form(p,'2026-10-06');form['Id']=ident
   atomic(D/('expense_save_'+ident+'.json'),v1_call(a,'/BumsFinApiV01/Operation/save.api',form,auth))
  after=v1_call(a,'/BumsFinApiV01/Operation/card.api',{'Id':ident},auth)['data']['item'];atomic(D/('expense_after_'+ident+'.json'),after);verify_cash_operation(after,p)
  assert str(after.get('Contractor',{}).get('Id'))==cid and after.get('Deal',{}).get('Id')==int(p['deal_id']);assert after['DocumentNumber']==p['document_number']
  p.update(secondary_cents=0,payment_semantics='cash_only',control_date='2026-10-06',control_date_basis='Internal audit review date; not promised delivery date');j['operations'][p['key']]=p;atomic(JOURNAL,j);print('expense corrected',ident,p['amount_cents']/100,cid,flush=True)
print('DONE',len(parts),flush=True)
