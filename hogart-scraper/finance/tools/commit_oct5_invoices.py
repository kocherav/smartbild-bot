import json
from pathlib import Path
R=Path(__file__).resolve().parents[1];root=R/'evidence/uploaded_oct5'
docs=json.loads((root/'manifest.json').read_text());rows=json.loads((R/'reports/ledger.json').read_text());review_path=R/'evidence/kav/reviewed.json';review=json.loads(review_path.read_text());lp=R/'evidence/audit45/verified_project_links.json';links=json.loads(lp.read_text())
spec=[('86490d44','9701027624','557',125201287,'865'),('2994bba4','9701037968','307',35140000,'865'),('016447e0','7743795913','ПКБ-00002943',16446055,'862'),('5f18c478','7743795913','ПКБ-00003053',1565675,'862'),('67bc775d','7743795913','ПКБ-00003937',335580,None),('53bd57c0','7743795913','ПКБ-00003931',2082755,None),('e5b1108e','5038179677','П008-07-26',17108000,'867')]
for prefix,inn,num,cents,deal in spec:
 d=next(x for x in docs if x['sha256'].startswith(prefix));note=f'Получен от пользователя: счёт {num}, {cents/100:.2f} руб.; покупатель ИНСИС. '
 if num=='307':
  d['text']='Визуально прочитан скан: счёт307 от07.09.2026, АЕРГРУПП ИНН9701037968, ИНСИС ИНН7743926877. FCZ300PO 3шт; FCZ400PO 1шт; VCZ42 4шт. Итого351400.00, НДС63367.22.';Path(d['local']).with_suffix('.txt').write_text(d['text'])
 if deal:note+=f'Объект соответствует сделке №{deal}. '
 if num=='557':note+='ЖК Реномэ: центральный модуль Liechty CL12 White Energy Multi и комплектующие совпадают со спецификацией сделки; закупленные74м трубы не заменяют план85м.'
 if num=='307':note+='ЖК Реномэ: совпали модели и количества всех фанкойлов и клапанов.'
 if num=='ПКБ-00002943':note+='Новая версия164460,55 отличается от платежа107230,90 и ранее найденной114370,90. Название присланного файла — Примавера. Версии сохранены, распределение платежа не подтверждено.'
 if num=='ПКБ-00003053':note+='Примавера подтверждена именем присланного файла; сумма15656,75 совпадает с платежом24.07 №100.'
 if num=='ПКБ-00003937':note+='Платёж по этому номеру или на3355,80 в данной выписке не найден; оплаченный статус не присваивался.'
 if num=='ПКБ-00003931':note+='Оплата20827,55 совпадает. Объект по типовой номенклатуре воздуховодов не установлен.'
 if num=='П008-07-26':note+='Сделка867: совпали модели диффузоров40/50 и количество2+2; у КСД отличается обозначениеE125/D125, требуется техническая сверка. В выписке предоплата130000,00, не полная оплата171080,00; бухгалтерское начисление полной стоимости не создаётся.'
 review=[x for x in review if (x['supplier_inn'],x['number'])!=(inn,num)]
 entry=dict(supplier_inn=inn,buyer_inn='7743926877',number=num,amount_cents=cents,source=str(Path(d['local']).resolve()),messages=[],note=note,deal_ids=[deal] if deal else [],sha256=d['sha256'])
 review.append(entry);d.update(entry)
 if deal and num!='ПКБ-00002943':
  pay=13000000 if num=='П008-07-26' else cents
  hits=[r for r in rows if r['inn']==inn and r['amount_cents']==pay and num in r['purpose']];assert len(hits)==1,(num,len(hits));r=hits[0]
  links=[x for x in links if x['operation_id']!=r['id']]
  links.append(dict(operation_id=r['id'],inn=inn,amount_cents=pay,number=num,deal_id=deal,source=entry['source'],evidence=note))
review_path.write_text(json.dumps(review,ensure_ascii=False,indent=2));lp.write_text(json.dumps(links,ensure_ascii=False,indent=2));(root/'manifest.json').write_text(json.dumps(docs,ensure_ascii=False,indent=2))
