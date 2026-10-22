import sys,json,re
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();auth=wait_budget(v1_auth,a);D=ROOT/'evidence/payment_correction'
for label,form in [('invoice05487',{'FilterFields[Number]':'05487','Limit':100}),('invoices851',{'FilterFields[Trade]':'851','Limit':100})]:
 d=v1_call(a,'/BumsInvoiceApiV01/Invoice/list.api',form,auth);atomic(D/(label+'.json'),d);print(label,json.dumps(d,ensure_ascii=False),flush=True)
ids=sorted({re.search(r'invoice_(\d+)\.json',x['evidence']).group(1) for x in json.loads(JOURNAL.read_text())['operations'].values() if x['kind']=='income' and re.search(r'invoice_(\d+)\.json',x['evidence'])})
for ident in ids:
 d=wait_budget(a._call,'GET','/invoice/'+ident);atomic(D/('invoice_live_'+ident+'.json'),d);q=d['data'];print(ident,q['number'],q['status'],q['sum']['value'],q['payer'].get('inn'),q['payer'].get('contractor',{}).get('id'),flush=True)
