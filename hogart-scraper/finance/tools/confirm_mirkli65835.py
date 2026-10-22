import sys,json,hashlib
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
D=ROOT/'evidence/mirkli65835';D.mkdir(exist_ok=True);a=MegaplanAPI()
payer=wait_budget(a._call,'GET','/payer/1003018');atomic(D/'payer.json',payer);assert payer['data']['inn']=='7743250099' and payer['data']['contractor']['id']=='1000608'
deal=wait_budget(a._call,'GET','/deal/862');atomic(D/'deal_862.json',deal);assert 'Примавера' in deal['data']['description']
mp=ROOT/'evidence/payment_correction/supplier_mapping.json';m=json.loads(mp.read_text());m['7743250099']={'contractor_id':'1000608','state':'existing','basis':'Точный ИНН в актуальной карточке плательщика1003018'};atomic(mp,m)
r=next(x for x in json.loads((ROOT/'reports/ledger.json').read_text()) if x['inn']=='7743250099' and x['date']=='2026-09-09' and x['number']=='132');assert r['amount_cents']==4460000 and r['account'].endswith('1572')
d=next(x for x in json.loads((ROOT/'evidence/kav/reviewed.json').read_text()) if x['supplier_inn']=='7743250099' and x['number']=='У65 835');assert d['amount_cents']==4460000 and d['buyer_inn']=='7743926877'
evidence='Пользователь прямо подтвердил по вопросу12: МИРКЛИ, счёт У65 835, оплата44600 ₽ — Примавера, сделка862. Только оплата, товарная приёмка не подтверждается.'
x=dict(operation_id=r['id'],inn=r['inn'],amount_cents=r['amount_cents'],number=d['number'],deal_id='862',source=d['source'],sha256=hashlib.sha256(Path(d['source']).read_bytes()).hexdigest(),evidence=evidence,confirmed_by='user')
p=ROOT/'evidence/audit45/verified_project_links.json';links=json.loads(p.read_text());old=[v for v in links if v['operation_id']==r['id']];assert not old or old[0]['deal_id']=='862'
if not old:links.append(x)
atomic(p,links);atomic(D/'new_links.json',[x]);u=ROOT/'user_rules.json';rules=json.loads(u.read_text());rules.setdefault('supplier_project_corrections',{})['7743250099:У65 835']=dict(confirmed=True,deal_id='862',project='ЖК Примавера',amount_cents=4460000,source=evidence);atomic(u,rules);print('Confirmed invoice and existing contractor')
