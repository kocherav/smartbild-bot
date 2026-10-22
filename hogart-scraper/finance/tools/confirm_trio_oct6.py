import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/trio_confirmed_oct6';D.mkdir(exist_ok=True)
rows=json.loads((R/'reports/ledger.json').read_text());docs=json.loads((R/'evidence/uploaded_invoices/manifest.json').read_text());p=R/'evidence/audit45/verified_project_links.json';links=json.loads(p.read_text());u=R/'user_rules.json';rules=json.loads(u.read_text());batch=[]
for num,deal,amount,name in [('62105','862',33609492,'ЖК Примавера'),('58813','867',9349020,'Квартира44м²')]:
 d=next(x for x in docs if x['number']==num);assert d['amount_cents']==amount;assert hashlib.sha256(Path(d['source']).read_bytes()).hexdigest()==d['sha256']
 rr=[r for r in rows if r['inn']=='7717632694' and r['references']==num and r['amount_cents']==amount and r['direction']=='out'];assert len(rr)==1
 evidence='Пользователь06.10.2026 прямо подтвердил: «62105 — Примавера, 58813 — квартира44м², да верно». Объект подтверждён несмотря на различие3FA/9FA. Это привязка оплаты; не подтверждение отгрузки/приёмки или изменение комплектации договора.'
 x=dict(operation_id=rr[0]['id'],inn=d['supplier_inn'],amount_cents=amount,number=num,deal_id=deal,source=d['source'],sha256=d['sha256'],evidence=evidence,confirmed_by='user')
 old=[a for a in links if a['operation_id']==x['operation_id']];assert not old or old[0]['deal_id']==deal
 if not old:links.append(x)
 batch.append(x);rules.setdefault('supplier_project_corrections',{})['7717632694:'+num]=dict(confirmed=True,deal_id=deal,project=name,amount_cents=amount,source=evidence)
u.write_text(json.dumps(rules,ensure_ascii=False,indent=2));p.write_text(json.dumps(links,ensure_ascii=False,indent=2));(D/'new_links.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2));print('confirmed',len(batch),sum(x['amount_cents'] for x in batch)/100)
