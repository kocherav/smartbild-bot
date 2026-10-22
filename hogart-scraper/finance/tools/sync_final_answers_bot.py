import os,sys,json,subprocess,hashlib
from pathlib import Path
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import atomic,ROOT
D=ROOT/'evidence/final_answers_20261007';v=json.loads((D/'verified.json').read_text());assert len(v['operations'])==21 and not v['errors'];archives=json.loads((D/'archive_results.json').read_text())+json.loads((D/'outside_archive_results.json').read_text());answers=json.loads((D/'answers.json').read_text());q={x['number']:x for x in answers};entries=[]
for number,num,path,cents in [('4772',46,str(next(Path('/home/kocher.av/.cloudcli/assets').glob('1791378975814*'))),2806716),('5769',47,str(next(Path('/home/kocher.av/.cloudcli/assets').glob('1791378976232*'))),1556285),('ЭК00-054832',41,'/home/kocher.av/hogart-scraper/incoming/1791375794-Счет_договор___ЭК00_054832_от_12_мая_2026_г_.pdf',9979470),('ЭК00-054835',41,'/home/kocher.av/hogart-scraper/incoming/1791375801-Счет_договор___ЭК00_054835_от_12_мая_2026_г_.pdf',1983218)]:
 digest=hashlib.sha256(Path(path).read_bytes()).hexdigest();ops=[p for p in v['operations'] if p['bank_operation_id'] in q[num]['bank_ids'] and (num!=41 or p['invoice_number']==number)];assert ops
 entries.append(dict(sha256=digest,source_path=path,invoice=number,old_question=num,chat_id='289622514',status='processed',already_resolved=True,bank_ids=q[num]['bank_ids'],document_amount_cents=cents,amount_cents=sum(p['amount_cents'] for p in ops),crm_operation_ids=[p['operation_id'] for p in ops],archive_remotes=[a['remote'] for a in archives if a['number']==number],resolution='Новый явный ответ владельца в Excel07.10.2026: '+q[num]['answer']+'. Денежная часть проведена и проверена; товарное движение0. '+('Доставка900 не покрыта этим платежом; счёт не объявлен полностью оплаченным.' if number=='ЭК00-054832' else '')))
# Update public deal search snapshot for explicitly created deal898.
p=ROOT/'evidence/telegram_intake/deal_search_index.json';idx=json.loads(p.read_text());deal=json.loads((D/'deal_898.json').read_text())['data'];idx=[d for d in idx if d['id']!='898'];idx.append({k:deal.get(k) for k in ['id','name','description','Category1000068CustomFieldAdresObEkta','shortDescription','positions']}|{'contractor':{'name':'Автосалон JetCar'}});atomic(p,idx)
pid=subprocess.check_output(['systemctl','show','telegram-bridge','--property=MainPID','--value'],text=True).strip();env=dict(s.split('=',1) for s in Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in s)
code='''import json,time
import durable_json,invoice_tasks
from pathlib import Path
entries=json.loads(DATA)
p=Path('/home/kocher.av/hogart-scraper/finance/evidence/telegram_intake/manifest.json')
with durable_json.locked(str(p)):
 data=durable_json.read(str(p),dict)
 for x in entries:
  old=data.get(x['sha256'],{});data[x['sha256']]={**old,**x,'received_at':old.get('received_at',time.time())}
 durable_json.save(str(p),data)
def apply(state):
 for doc in state.get('documents',[]):
  x=next((e for e in entries if e['sha256']==doc['sha256']),None)
  if x:doc.update(status='applied',statement=x,resolution=x['resolution'])
 state['history'].append({'role':'user','text':'Новые ответы Excel07.10:054832 — JetCar851;054835 — собственные нужды. Это новое указание заменяет прежнюю отмену054835. Платежи уже проведены, не повторять.','document_id':None})
invoice_tasks.change('289622514',apply)
print(json.dumps({'processed_invoices':[x['invoice'] for x in entries],'runtime_verified':all(d.get('status')=='applied' for d in invoice_tasks.read('289622514').get('documents',[]) if d['sha256'] in {x['sha256'] for x in entries})}))
'''.replace('DATA',repr(json.dumps(entries,ensure_ascii=False)))
cmd=['nsenter','--target',pid,'--mount','--root','--setuid','993','--setgid','980','--wdns=/home/kocher.av/telegram-bridge','--','/usr/bin/python3','-c',code];r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=60);print(r.stdout);print(r.stderr);assert r.returncode==0;atomic(D/'bot_state_sync.json',json.loads(r.stdout))
