import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/owner_workbook_20261007'
for id in ['1003020','1002765','1002904','1002845','1002523','1001260','1002334','1003018']:
 x=wait_budget(a._call,'GET','/contractor/'+id);atomic(D/('party_'+id+'.json'),x);d=x['data'];print(id,d.get('contentType'),d.get('name'),d.get('firstName'),d.get('lastName'),d.get('description'),flush=True)
 kind='contractorHuman' if d['contentType']=='ContractorHuman' else 'contractorCompany'
 y=wait_budget(a._call,'GET','/'+kind+'/'+id+'/payers');atomic(D/('payers_'+id+'.json'),y);print('payers',[(v.get('inn'),v.get('name')) for v in y['data']],flush=True)
