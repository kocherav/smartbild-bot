import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/continuation_oct6b'
rows=json.loads((R/'reports/ledger.json').read_text());docs=json.loads((R/'evidence/kav/reviewed.json').read_text());target=R/'evidence/audit45/verified_project_links.json';links=json.loads(target.read_text());batch=[]
specs=[('7703675923','DAER-014914','851',3036400,'Счёт ДАИЧИ DAER-014914: четыре пульта DC60W. В актуальной сделке851 «БП и пульты на замену» ровно4 DC60W; среди48 сделок2026 это единственное совпадение. Заказ владельца в kav INBOX65458 от05.05.2026 прямо просит4 DC60W; дата заказа/оплаты соответствует договору1.851-0505/2026. ИНН покупателя/поставщика и сумма совпали.'),('7728336506','208096','858',1540991,'Счёт208096: BlauFast RL63 64шт и RM63 10шт полностью совпадают с уникальным составом сделки858 «Вентиляция1этНК». Другие позиции: заглушка того же коллектора и доставка. Общая переписка kav66128/66130 по208096 и208098; последующая цепочка66734 подтверждает доставку системы63мм на Подвойского5/19. Сопоставлены состав, количества, адрес, получатель и сумма.'),('7728336506','208164','858',426450,'Дополнительный счёт208164: BlauFast RM63 10шт и доставка. Приложен к kav INBOX66734 от30.07.2026 в цепочке заказа208098 системы воздуховодов63мм: Подвойского5/19. Тот же контур снабжения, что208096, уникальная системаBlauFast63мм в сделке858. Сумма и ИНН совпали. Это отдельный банковский платёж; получение товаров и начисление себестоимости не создаются.')]
for inn,num,deal,cents,evidence in specs:
 matches=[r for r in rows if r['inn']==inn and r['direction']=='out' and num in r['references'] and r['amount_cents']==cents];assert len(matches)==1
 doc=next(d for d in docs if d['supplier_inn']==inn and d['number']==num);assert doc['amount_cents']==cents and doc['buyer_inn']=='7743926877'
 link=dict(operation_id=matches[0]['id'],inn=inn,amount_cents=cents,number=num,deal_id=deal,source=doc['source'],evidence=evidence,sha256=hashlib.sha256(Path(doc['source']).read_bytes()).hexdigest())
 old=[x for x in links if x['operation_id']==link['operation_id']];assert not old or old[0]['deal_id']==deal
 if not old:links.append(link)
 batch.append(link)
(D/'new_links.json').write_text(json.dumps(batch,ensure_ascii=False,indent=2));target.write_text(json.dumps(links,ensure_ascii=False,indent=2));print('verified',len(batch),sum(x['amount_cents'] for x in batch)/100)
