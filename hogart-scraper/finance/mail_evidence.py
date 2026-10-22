import sys,imaplib,email,json,re,time
from pathlib import Path
from email.header import decode_header,make_header
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
from email_payment_monitor import load_env,message_text
ROOT=Path(__file__).resolve().parent/'evidence';env=load_env()
def decode(v):
 try:return str(make_header(decode_header(v or '')))
 except Exception:return str(v)
with imaplib.IMAP4_SSL(env.get('IMAP_HOST') or 'imap.yandex.ru',int(env.get('IMAP_PORT') or 993),timeout=45) as c:
 c.login(env.get('IMAP_USERNAME') or env['SMTP_USERNAME'],env.get('IMAP_PASSWORD') or env['SMTP_PASSWORD']);c.select('INBOX',readonly=True)
 _,data=c.uid('search',None,'SINCE','01-May-2026','BEFORE','07-Oct-2026');ids=data[0].split();print('headers_to_read',len(ids),flush=True);headers=[]
 for i in range(0,len(ids),100):
  _,parts=c.uid('fetch',b','.join(ids[i:i+100]),'(UID RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])')
  for part in parts:
   if not isinstance(part,tuple):continue
   meta,raw=part;m=email.message_from_bytes(raw);uid=re.search(rb'UID (\d+)',meta);size=re.search(rb'RFC822.SIZE (\d+)',meta)
   if uid:headers.append({'uid':uid.group(1).decode(),'size':int(size.group(1)) if size else 0,**{k:decode(m.get(k,'')) for k in ['From','Subject','Date','Message-ID']}})
 (ROOT/'mail_headers.json').write_text(json.dumps(headers,ensure_ascii=False,indent=2))
 print('headers_saved',len(headers),flush=True)
