import os,subprocess,json
from pathlib import Path
pid=subprocess.check_output(['systemctl','show','telegram-bridge','--property=MainPID','--value'],text=True).strip();env=dict(s.split('=',1) for s in Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in s)
code='''
import tempfile,json,time
from pathlib import Path
from unittest.mock import patch,Mock
import bridge,catalog_conversation as c,invoice_tasks as t
assert bridge.explicit_catalog_request('Найди самые дешевые неинверторные кондиционеры в наличии: две штуки на7кВт и одну3,5кВт')
with tempfile.TemporaryDirectory() as tmp,patch.object(t,'STORE',Path(tmp)/'tasks.json'):
 p=Path(tmp)/'invoice.pdf';p.write_bytes(b'invoice');t.register('test',p,'Счет на оплату №054832',1)
 state=c.begin('test','Найди кондиционеры Haier:7кВт2шт,3,5кВт1шт')
 assert t.active(state) is None
 assert c.is_turn('А посмотри не инверторные модели',state)
 assert '054832' not in c.prompt(state)
 assert t.read('test')['documents'][0]['status']=='pending'
print(json.dumps({'running_service_imports_new_router':True,'generic_search':True,'followup_without_brand':True,'pending_invoice_is_preserved_but_paused':True,'auth_untouched':True}))
'''
cmd=['nsenter','--target',pid,'--mount','--root','--setuid','993','--setgid','980','--wdns=/home/kocher.av/telegram-bridge','--','/usr/bin/python3','-c',code];r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=60);print(r.stdout);print(r.stderr);assert r.returncode==0
Path('/home/kocher.av/hogart-scraper/finance/evidence/catalog_routing_20261007/runtime.json').write_text(r.stdout)
