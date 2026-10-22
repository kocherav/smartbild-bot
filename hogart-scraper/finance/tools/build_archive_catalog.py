import sys,json,hashlib,re
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));from document_review import KNOWN,refs
rows=json.loads((R/'reports/ledger.json').read_text());items=[]
for name in ['evidence/kav/reviewed.json','evidence/uploaded_invoices/manifest.json']:
 for d in json.loads((R/name).read_text()):items.append({**d,'note':d.get('note','Присланный счёт; объект проверяется.')})
proc=json.loads(Path('/home/kocher.av/megaplan-crm/procurement_registry.json').read_text())['invoices']
for d in proc:
 source=d.get('source_path')
 if not source:
  for p in Path('/home/kocher.av/hogart-scraper/incoming').glob('*'):
   if d['number'] in p.name and p.suffix.lower() in ['.pdf','.xls','.xlsx']:source=str(p);break
 if source:items.append({'source':source,'number':d['number'],'supplier_inn':d['supplier_inn'],'buyer_inn':d.get('buyer_inn',''),'amount_cents':round(d['total']*100),'deal_ids':sorted({str(a['deal_id']) for a in d.get('allocations',[])}),'note':'Счёт из действующего реестра закупок; распределения и себестоимость сохранены без изменений.'})
# Preserve other versions of invoices already identified during reconciliation.
for d in json.loads((R/'evidence/kav/documents.json').read_text()):
 t=d['text'].replace('\xa0',' ')
 for (inn,num),note in KNOWN.items():
  if inn not in t or not ('7743926877' in t or '7743151323' in t):continue
  pat=r'сч[её]т[^\n]{0,55}?№\s*'+re.escape(num)+r'(?![\w/-])'
  if not re.search(pat,t,re.I):continue
  items.append({'source':d['path'],'number':num,'supplier_inn':inn,'buyer_inn':'7743926877' if '7743926877' in t else '7743151323','note':'Версия найденного счёта. Не считать самостоятельной закупкой; актуальность суммы указана в реестре сверки.'})
for number,inn,name in [('212/099912362','7842224734','mail_13689_4.pdf'),('2606-413221-03944','7722753969','mail_13490_2.pdf'),('2607-466489-69135','7722753969','mail_13544_2.pdf')]:
 p=R/'evidence'/name
 if p.exists():items.append({'source':str(p),'number':number,'supplier_inn':inn,'buyer_inn':'7743926877','note':KNOWN.get((inn,number),'')})
# Include verified supplier portal invoice/UPD sources; never turn an UPD into a new invoice.
portal=R/'evidence/trio_portal'
for p in portal.glob('*.pdf'):
 if p.stem in ['44245','TR0000013459','TR0000017445']:items.append({'source':str(p),'number':p.stem,'supplier_inn':'7717632694','buyer_inn':'7743926877','category':'supplier_closing' if p.stem.startswith('TR') else 'supplier_invoice','note':'Источник: кабинет поставщика. Связь с платежом проверяется отдельно.'})
for d in json.loads((R/'evidence/audit45/cloud/manifest.json').read_text()):
 if '208098' in d['source']:
  items.append({'source':d['local'],'number':'208098','supplier_inn':'9728104795','buyer_inn':'7743926877','amount_cents':7483570,'note':'Версия на74835,70 подтверждает первый платёж; доплата12806,65 отдельно не подтверждена.'})
unique={}
for d in items:
 p=Path(d['source'])
 if not p.exists():continue
 sha=hashlib.sha256(p.read_bytes()).hexdigest();deals=set(d.get('deal_ids',[]))
 if (d['supplier_inn'],d['number'])==('7743949955','1794'):deals.update(['862','864']);d['note']='Общий счёт: Примавера344040, Слава306240. Две архивные копии одного документа; сумма закупки650280, не удваивать.'
 for r in rows:
  if r['inn']==d['supplier_inn'] and d['number'] in refs(r) and not r['flags']:
   deal=r.get('verified_deal_id');deals.update([deal] if deal else re.findall(r'Мегаплан №(\d+)',r['project']))
 if sha in unique:
  unique[sha]['deal_ids']=sorted(set(unique[sha]['deal_ids'])|deals);continue
 name=next((r['counterparty'] for r in rows if r['inn']==d['supplier_inn']),d['supplier_inn'])
 unique[sha]={**d,'source':str(p.resolve()),'sha256':sha,'deal_ids':sorted(deals),'supplier':name,'category':d.get('category','supplier_invoice')}
out=list(unique.values());(R/'evidence/posting/archive_catalog.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('unique_files',len(out),'assigned_files',sum(bool(x['deal_ids']) for x in out),'unassigned_files',sum(not x['deal_ids'] for x in out))
