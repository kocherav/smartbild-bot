import os,subprocess,json
from pathlib import Path
pid=subprocess.check_output(['systemctl','show','telegram-bridge','--property=MainPID','--value'],text=True).strip()
env=dict(s.split('=',1) for s in Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in s)
code='''
import json
import bridge,statement_document_context as s,invoice_continuation as c
p='/home/kocher.av/hogart-scraper/incoming/1791365968-Счет_оферта_на_оплату___1624_от_22_июня_2026_г.xlsx'
t=bridge.extract_document_text_for_model(p);assert '27600' in t
found=s.deal_candidates('Отнести этот счет в сделке Павелецкая Сити Наталья');assert '"807"' in found
print('Full-index search finds 807',flush=True)
a=c.remember(p,t,'289622514');spec={'deal_id':'807','invoice':{'number':'1624','supplier_inn':'7743949955','buyer_inn':'7743926877'}}
assert c.bind(spec,a,'289622514')['invoice']['source_path']==p
print('Original XLSX and later reply can prepare a bound draft',flush=True)
rows=bridge.fetch_deal_ledger('807');assert rows is not None and len(rows)==25
p=next(x for x in rows if x['name']=='Пульт управления C1G');assert p['qty']==1 and p['sell_price']==43000 and p['cost_material']==27600
print('Live CRM: 25 positions, C1G qty1 sale43000 cost27600',flush=True)
'''
cmd=['nsenter','--target',pid,'--mount','--root','--setuid','993','--setgid','980','--wdns=/home/kocher.av/telegram-bridge','--','/usr/bin/python3','-c',code]
r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=85);print(r.stdout);print(r.stderr);raise SystemExit(r.returncode)
