import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/payment_correction'
for ident in ['1002381','1000710','1002337']:
 p=D/('contact_'+ident+'.json')
 if not p.exists():atomic(p,wait_budget(a._call,'GET','/contractor/'+ident))
 d=json.loads(p.read_text())['data'];print(ident,d.get('contentType'),d.get('name'),d.get('firstName'),d.get('lastName'),d.get('company'),d.get('description'),flush=True)
atomic(D/'contractor_types.json',wait_budget(a._call,'GET','/contractorType'))
