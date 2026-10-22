import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/final_answers_20261007'
x=wait_budget(a._call,'GET','/contractor/1002188');atomic(D/'inttexno_contact.json',x);d=x['data'];print('inttexno',d.get('contentType'),d.get('name'),d.get('company'),d.get('description'),flush=True)
kind=d['contentType'][0].lower()+d['contentType'][1:];p=wait_budget(a._call,'GET','/'+kind+'/1002188/payers');atomic(D/'inttexno_payers.json',p);print('payers',[(v['id'],v.get('inn'),v.get('contractor')) for v in p['data']],flush=True)
state=D/'new_deal_state.json'
if not state.exists():
 payload={'contentType':'Deal','program':{'contentType':'Program','id':'16'},'state':{'contentType':'ProgramState','id':'129'},'contractor':{'contentType':'ContractorCompany','id':'1002845'},'description':'JetCar — закупки Элевел 061898 и 065961. Новая отдельная сделка по прямому ответу владельца в Excel07.10.2026, пункт42 вместе с пунктом43. Оплаты:2354,98 ₽ и762,28 ₽. Детальные счета и клиентская продажная цена не установлены.','positions':[]}
 atomic(state,{'state':'creating','payload':payload});x=wait_budget(a._call,'POST','/deal',json_body=payload);atomic(D/'new_deal_created.json',x);ident=x['data']['id'];live=wait_budget(a._call,'GET','/deal/'+ident);assert live['data']['contractor']['id']=='1002845';atomic(D/('deal_'+ident+'.json'),live);atomic(state,{'state':'verified','deal_id':ident});print('created',ident,flush=True)
else:assert json.loads(state.read_text())['state']=='verified'
