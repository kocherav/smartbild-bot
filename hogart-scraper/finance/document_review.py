"""Reconciled supplier documents and a concise request list; no guessed allocations."""
import json,re,collections
from pathlib import Path
from ledger import ROOT,connect,records,invoice_refs

# Documents inspected against their buyer, supplier, number and amount.
KNOWN={
 ('7733272640','61810'):'Счёт 61810 от 16.06.2026, 22924 руб.; реестр закупок, полное распределение на сделку 861.',
 ('7720298746','ЭК00-078924'):'Счёт 3047995,85; оплачено 2400000. На сделку 861 распределена часть закупки. Нужна разбивка оставшихся позиций, повторно счёт не нужен.',
 ('7720298746','ЭК00-119581'):'Счёт 89036,80; платёж 83129,92. Частичная оплата либо другая версия; распределение закупки частичное.',
 ('7842224734','212/099912362'):'Счёт из письма mail_13689_4.pdf: 490264,93. Совпадает с платежом. Более ранний счёт 212/09993767866-2 — отдельная версия/предложение; распределение не переносилось.',
 ('7722753969','2606-413221-03944'):'Счёт mail_13490_2.pdf, 11239 руб.; требуется определить объект.',
 ('7722753969','2607-466489-69135'):'Счёт mail_13544_2.pdf, 3760 руб.; правильный НДС 678,03. Требуется объект.',
 ('7743795913','ПКБ-00002943'):'Счёт 114370,90, платёж 107230,90. Разница 7140 равна строке воздуховодов. Нужна оплаченная версия или подтверждение исключённой строки; в имени файла два объекта.',
 ('7743795913','ПКБ-00003477'):'Исправленный счёт 87255,35 = 82502,15 + 4753,20. Платёж 13505,65 от 25.08 содержит этот номер, но найден отдельный счёт ПКБ-00003617 от 24.08 на 13505,65. Нужна проверка номера и объектов; оба файла уже есть.'
}
UPLOADS=ROOT/'evidence/uploaded_invoices/manifest.json'
if UPLOADS.exists():
 for doc in json.loads(UPLOADS.read_text()):
  KNOWN[(doc['supplier_inn'],doc['number'])]=f"Получен от пользователя: {doc['number']}, {doc['amount_cents']/100:.2f} руб., покупатель ИНСИС. Документ сохранён с SHA256. Объект ещё требуется подтвердить."

MAIL_REVIEW=ROOT/'evidence/kav/reviewed.json'
MAIL_DOCS=json.loads(MAIL_REVIEW.read_text()) if MAIL_REVIEW.exists() else []
for doc in MAIL_DOCS:KNOWN[(doc['supplier_inn'],doc['number'])]=doc['note']
CORRECTIONS=json.loads((ROOT/'user_rules.json').read_text()).get('supplier_project_corrections',{})
if '7743949955:1794' in CORRECTIONS:
 KNOWN[('7743949955','1794')]='Счёт №1794 найден: 650280 руб. Пользователь исправил объект: ЖК «Слава» и ЖК «Примавера», по одной установке. Установки стоят 254400 и 292200; два пульта — 55200; четыре клапана — 48480. Распределение конкретных моделей и комплектующих пока не подтверждено. Тема письма только про Славу не определяет весь состав счёта.'


if CORRECTIONS.get('7743949955:1794',{}).get('confirmed'):
 KNOWN[('7743949955','1794')]='Счёт №1794, 650280 руб. Подтверждено пользователем: Примавера — установка 4.0 (292200), пульт (27600), два клапана (24240), всего 344040; Слава — установка 2.5 (254400), пульт (27600), два клапана (24240), всего 306240. Денежные операции проверены в Мегаплане, отгрузка учитывается отдельно.'

def refs(r):
 restored={('7811504932','2026-07-06','75',7043937):'51728',('7705449060','2026-09-08','130',6988600):'138000152939'}
 key=(r['inn'],r['date'],r['number'],r['amount_cents'])
 if r['account']=='40702810402570001572' and key in restored and (r['inn'],restored[key]) in KNOWN:return [restored[key]]
 if r['inn']=='7736192449' and r['date']=='2026-09-24' and r['amount_cents']==6037475 and ('7736192449','22427744/SA') in KNOWN:return ['22427744/SA']
 if r['inn']=='7743250099' and r['date']=='2026-09-09' and r['amount_cents']==4460000 and ('7743250099','У65 835') in KNOWN:return ['У65 835']
 result=invoice_refs(re.split(r'на сумму',r['purpose'],flags=re.I)[0])
 if not result:
  m=re.search(r'заказ(?:у клиента|у)?\s*№?\s*([A-ZА-Я0-9][A-ZА-Я0-9/-]*\d)',r['purpose'],re.I)
  if m:result=[m.group(1)]
 if not result:
  m=re.search(r'(?:договору|заказ наряду|оферты)\s*№\s*([A-ZА-Я0-9/-]+)',r['purpose'],re.I)
  if m:result=['Договор/заказ-наряд '+m.group(1)]
 return result

def apply(rows):
 archive_links_path=ROOT/'evidence/audit45/verified_project_links.json'
 archive_links=json.loads(archive_links_path.read_text()) if archive_links_path.exists() else []
 reviewed_path=ROOT/'evidence/deep_review/reviewed_allocations.json'
 reviewed=json.loads(reviewed_path.read_text()) if reviewed_path.exists() else {}
 for r in rows:
  if r['direction']!='out' or r['group']!='Внешняя':continue
  rr=refs(r)
  splits=json.loads((ROOT/'user_rules.json').read_text()).get('confirmed_payment_allocations',{})
  split=splits.get(r['id'])
  if not split:split=reviewed.get(r['id'])
  if split and split.get('confirmed'):
   assert split['inn']==r['inn'] and split['amount_cents']==r['amount_cents'] and split['number'] in rr
   assert sum(x['amount_cents'] for x in split['allocations'])==r['amount_cents']
   r['confirmed_payment_allocations']=split['allocations'];r['document_numbers']=split['number']
   if split.get('category'):r['category']=split['category']
   r['project']='; '.join(x['project']+': '+format(x['amount_cents']/100,'.2f')+' руб.' for x in split['allocations'])
   r['crm_evidence']=split['source'];r['decision_note']=split['source']
   r['flags']=[f for f in r['flags'] if f not in ('Нет подтверждённой привязки к объекту/заказу','Возможна оплата нескольких счетов — нужна разбивка')]
   r['review_owner']='Не требуется';r['status']='Сверено по совокупности документов' if split.get('reviewed_by')=='assistant' else 'Подтверждено пользователем'
   r['flags']=[f for f in r['flags'] if f not in split.get('cleared_flags',[])]
  for link in archive_links:
   if r['id']==link['operation_id'] and r['inn']==link['inn'] and r['amount_cents']==link['amount_cents']:
    r['verified_deal_id']=link['deal_id'];r['project']='Мегаплан №'+link['deal_id']
    if link['number']=='П008-07-26':
     r['category']='Оборудование и материалы';r['flags']=[f for f in r['flags'] if f!='Подтвердить статью']
    r['flags']=[f for f in r['flags'] if f not in ('Нет подтверждённой привязки к объекту/заказу','Пропущен номер счёта')]
    r['flags']=[f for f in r['flags'] if f not in link.get('cleared_flags',[])]
    r['status']='Требует уточнения' if r['flags'] else 'Сверено с реестром Мегаплана'
    r['review_owner']='Ассистент: оставшиеся замечания' if r['flags'] else 'Не требуется'
    r['crm_evidence']=link['evidence'];r['document_numbers']=link['number']
  if r['inn']=='615518680653' and rr==['45'] and r['account']=='40702810902570001580' and r['date']=='2026-09-30' and r['number']=='72' and r['amount_cents']==3500000 and ('615518680653','45') in KNOWN:
   r['verified_deal_id']='862';r['project']='Мегаплан №862 — Примавера, Покровская набережная, 16'
   r['flags']=[f for f in r['flags'] if f!='Нет подтверждённой привязки к объекту/заказу']
   r['status']='Требует уточнения' if r['flags'] else 'Сверено с реестром Мегаплана'
   r['review_owner']='Ассистент: оставшиеся замечания' if r['flags'] else 'Не требуется'
   r['crm_evidence']='Счёт №45, договор и акт из kav UID67443: алмазное бурение, Покровская наб.,16. В реестре сделок адрес однозначно соответствует №862; сумма, покупатель, поставщик и номер совпали с платежом.'
  if r['inn']=='6623097295' and rr==['793'] and r['amount_cents']==175500 and r['date']=='2026-09-02' and r['account'].endswith('1572') and ('6623097295','793') in KNOWN:
   r['verified_deal_id']='861';r['project']='Мегаплан №861';r['category']='Доставка оборудования'
   r['flags']=[f for f in r['flags'] if f not in ('Подтвердить статью','Нет подтверждённой привязки к объекту/заказу')]
   r['status']='Требует уточнения' if r['flags'] else 'Сверено с реестром Мегаплана'
   r['crm_evidence']='Счёт 793 и письмо kav INBOX UID67188: доставка оборудования по счетам 668 и 646, полностью распределённым на сделку 861 в реестре закупок.'
  if r['inn']=='7733272640' and r['amount_cents']==2292400 and r['date']=='2026-07-06' and r['account'].endswith('1572'):
   rr=['61810'];r['verified_deal_id']='861';r['project']='Мегаплан №861';r['flags']=[f for f in r['flags'] if f not in ('Пропущен номер счёта','Нет подтверждённой привязки к объекту/заказу')];r['status']='Сверено с реестром Мегаплана' if not r['flags'] else 'Требует уточнения'
  if r['inn']=='7743949955' and rr==['1794'] and ('7743949955','1794') in KNOWN:
   correction=json.loads((ROOT/'user_rules.json').read_text()).get('supplier_project_corrections',{}).get('7743949955:1794')
   r['flags']=[f for f in r['flags'] if f!='Нет подтверждённой привязки к объекту/заказу']
   if correction:
    if correction.get('confirmed') and r['account']=='40702810402570001572' and r['date']=='2026-07-16' and r['number']=='92' and r['amount_cents']==65028000:
     allocations=correction['allocations']
     assert sum(a['amount_cents'] for a in allocations)==r['amount_cents']
     r['project_allocations']=allocations
     r['project']='; '.join(a['project']+': '+format(a['amount_cents']/100,'.2f')+' руб.' for a in allocations)
     r['decision_note']=correction['source']
     r['status']='Требует уточнения' if r['flags'] else 'Подтверждено пользователем'
     r['review_owner']='Не требуется' if not r['flags'] else 'Ассистент: оставшиеся замечания'
     r['crm_posting_status']='Распределение по объектам подтверждено; финансовые операции в Мегаплане не созданы'
    else:
     r['project']='ЖК «Слава» + ЖК «Примавера»: по одной установке'
     r['decision_note']=correction['source']+' Суммы по объектам пока не распределены.'
     r['flags'].append(correction['allocation_status'])
     r['review_owner']='Пользователь: модели установок и комплектующие по двум объектам'
   else:
    r['project']='ЖК Слава, Ленинградский проспект, вл.8 (письмо UID66512)'
    r['flags'].append('Объект установлен; конкретная сделка Мегаплана ещё не подтверждена')
  if r['inn'] in ('7743250099','7736192449','7811504932','7705449060') and rr and (r['inn'],rr[0]) in KNOWN:
   r['flags']=[f for f in r['flags'] if f!='Пропущен номер счёта']
  notes=[KNOWN[(r['inn'],ref)] for ref in rr if (r['inn'],ref) in KNOWN]
  if notes:
   r['document_review']='; '.join(notes);r['document_numbers']='; '.join(ref for ref in rr if (r['inn'],ref) in KNOWN)
   r['crm_evidence']='; '.join(filter(None,[r.get('crm_evidence'),r['document_review']]))

def main():
 # Keep the old command as an alias; it must not create another work register.
 from report import main as rebuild_report
 rebuild_report()
if __name__=='__main__':main()
