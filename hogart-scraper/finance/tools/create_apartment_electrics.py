import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/owner_workbook_20261007';state=D/'new_deal_state.json'
if state.exists():
 x=json.loads(state.read_text());assert x.get('state')=='verified','Creation already attempted: read CRM first';print(x);raise SystemExit
base=json.loads((D/'deal_867.json').read_text())['data'];assert base['contractor']['id']=='1002845' and '44' in base['description']
payload={'contentType':'Deal','program':{'contentType':'Program','id':'16'},'state':{'contentType':'ProgramState','id':'129'},'contractor':{'contentType':'ContractorCompany','id':'1002845'},'description':'Квартира 44 м² — электрика. Отдельный раздел того же объекта, что сделка №867 (кондиционирование). Создано по прямому указанию владельца в ответе №4 от 07.10.2026. Закупка: счёт ИП Панькина №1695, оплачено 42 360 ₽. Цена продажи и клиентская спецификация пока не установлены.','positions':[]}
atomic(state,{'state':'creating','payload':payload});x=wait_budget(a._call,'POST','/deal',json_body=payload);atomic(D/'new_deal_created.json',x)
id=x['data']['id'];live=wait_budget(a._call,'GET','/deal/'+id);assert live['data']['contractor']['id']=='1002845';atomic(D/('deal_'+id+'.json'),live);atomic(state,{'state':'verified','deal_id':id,'url':a.deal_url(id),'description':live['data']['description']});print('created',id,flush=True)
