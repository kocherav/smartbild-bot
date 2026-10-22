import json,sys,copy
from pathlib import Path
from decimal import Decimal
P=Path(__file__).resolve().parent
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
from position_types import classify_position,FIELD
from closing_documents import generate_act
from pypdf import PdfReader
all_deals=json.load(open(P/'all-deals-after.json'));deal=next(d for d in all_deals if d['id']=='861')
kinds={str(r['id']):classify_position(r) for r in deal['positions']}
source=json.load(open(P/'act-861-source.json'));data=copy.deepcopy(source);changes=[]
for r in data['positions']:
 new=kinds[str(r.get('source_id')or r['id'])]
 if new!=r['kind']:changes.append({'id':r['id'],'name':r['name'],'before':r['kind'],'after':new,'total':r['total']})
 r['kind']=new
assert sum(Decimal(str(r['total'])) for r in data['positions'])==Decimal(str(source['total']))
assert not any(r['kind']=='work' for r in data['positions'])
assert sum(Decimal(str(r['total'])) for r in changes if r['before']=='work')==Decimal('56970')
pdf=generate_act(data,P/'act-861-check',test=True)
text='\n'.join(p.extract_text() for p in PdfReader(pdf).pages)
assert '02 / Выполненные работы и оказанные услуги' not in text
assert 'Монтажная плата' in text and 'НШП-50' in text
json.dump({'total':source['total'],'changed_rows':changes,'work_amount_removed':'56970.00','pdf':pdf,'pages':len(PdfReader(pdf).pages),'external_writes':False,'test_document':True},open(P/'act-check-result.json','w'),ensure_ascii=False,indent=2)
print(json.dumps({'ok':True,'total':source['total'],'changed_rows':len(changes),'pdf':pdf},ensure_ascii=False))
