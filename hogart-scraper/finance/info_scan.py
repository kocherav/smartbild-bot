import imaplib,json,re,email,hashlib
from email.header import decode_header,make_header
from pathlib import Path
root=Path(__file__).resolve().parent/'evidence/info_reconnected';root.mkdir(exist_ok=True)
import sys
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
from email_payment_monitor import load_env
e=load_env();cfg={'host':e.get('IMAP_HOST') or 'imap.yandex.ru','port':int(e.get('IMAP_PORT') or 993),'username':e.get('IMAP_USERNAME') or e['SMTP_USERNAME'],'password':e.get('IMAP_PASSWORD') or e['SMTP_PASSWORD']}
def dec(v):
 try:return str(make_header(decode_header(v or '')))
 except Exception:return str(v)
with imaplib.IMAP4_SSL(cfg['host'],cfg['port'],timeout=45) as c:
 c.login(cfg['username'],cfg['password']);print('login OK',flush=True)
 _,folders=c.list();allheaders=[]
 for folder in folders:
  m=re.match(rb'\((.*?)\) "[^"]*" (.*)',folder)
  if not m or b'\\Noselect' in m[1]:continue
  name=m[2].decode();key=hashlib.sha256(name.encode()).hexdigest()[:12]
  status,_=c.select(name,readonly=True)
  if status!='OK':continue
  status,d=c.uid('search',None,'SINCE','01-Dec-2025','BEFORE','07-Oct-2026');
  if status!='OK':raise RuntimeError('Date search failed')
  ids=d[0].split();print('folder',name,'messages',len(ids),flush=True)
  for i in range(0,len(ids),150):
   status,parts=c.uid('fetch',b','.join(ids[i:i+150]),'(UID RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)])')
   for part in parts:
    if not isinstance(part,tuple):continue
    meta,raw=part;msg=email.message_from_bytes(raw);u=re.search(rb'UID (\d+)',meta);size=re.search(rb'RFC822.SIZE (\d+)',meta)
    if u:allheaders.append({'folder':name,'key':key,'uid':u[1].decode(),'size':int(size[1]) if size else 0,**{h:dec(msg.get(h)) for h in ['From','To','Subject','Date','Message-ID']}})
  (root/'headers.json').write_text(json.dumps(allheaders,ensure_ascii=False,indent=2))
 print('headers',len(allheaders),flush=True)
