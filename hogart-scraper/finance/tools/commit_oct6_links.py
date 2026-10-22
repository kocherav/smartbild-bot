import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/continuation_oct6';rows=json.loads((R/'reports/ledger.json').read_text());target=R/'evidence/audit45/verified_project_links.json';links=json.loads(target.read_text());added=[]
specs=[('7720298746','ЭК00-078924','861',240000000,'cab2b192719b1643d0d8164febf88f60259539177d902023179659652d577307', 'Архив исходных документов: Подвойского5/19,1-й этаж НК, «Элевел основное оборудование». SHA256 совпал с документом реестра закупок,3047995,85 ₽. Свежая сделка861: электроснабжение1этНК, соответствующая номенклатура щита и электрики. Все4 оплаты по этому счёту,2400000 ₽, относятся к этому объекту; это частичная оплата счёта. Нераспределённая по строкам себестоимость898496,48 ₽ не означает другой объект и остаётся отдельной задачей; закупочная себестоимость не менялась.'),('4004022080','1952','858',22404000,'bbe5f185da86af59878eecce5d151be8f12fc761a7c9ffefc5fddf7c50a08671','Счёт1952 от24.06.2026 найден в исходном архиве Подвойского5/19,1-й этажНК. SHA256 совпал со счётом из kav. ИНСИС,ИНН поставщика4004022080,оплата224040 ₽ совпали. В свежей сделке858 «Вентиляция1этНК» совпадает весь состав: Zenit Heco VM350 1,5E220 EPP чёрный пульт1шт и заслонки160 с приводом2шт. Привязка подтверждена папкой исходного объекта и полным составом, не только названием поставщика.')]
for inn,number,deal,total,sha,evidence in specs:
 matched=[r for r in rows if r['inn']==inn and r['direction']=='out' and number in r['references']]
 assert sum(r['amount_cents'] for r in matched)==total
 source=next(x['source'] for x in json.loads((R/'evidence/posting/archive_catalog.json').read_text()) if x['sha256']==sha)
 assert hashlib.sha256(Path(source).read_bytes()).hexdigest()==sha
 for r in matched:
  link=dict(operation_id=r['id'],inn=inn,amount_cents=r['amount_cents'],number=number,deal_id=deal,source=source,evidence=evidence)
  if inn=='7720298746':link['cleared_flags']=['Счёт найден в реестре Мегаплана; сумма или распределение требуют сверки']
  if not any(x['operation_id']==r['id'] for x in links):links.append(link);added.append(link)
(D/'new_links.json').write_text(json.dumps(added,ensure_ascii=False,indent=2));target.write_text(json.dumps(links,ensure_ascii=False,indent=2));print('new_links',len(added),'amount',sum(x['amount_cents'] for x in added)/100)
