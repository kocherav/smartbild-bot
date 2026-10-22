import sys,imaplib,email,json,re
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
from email_payment_monitor import load_env,message_text
ROOT=Path(__file__).resolve().parent/'evidence';env=load_env();headers=json.loads((ROOT/'mail_headers.json').read_text())
selected=[h for h in headers if any(w in (h['From']+' '+h['Subject']).lower() for w in ['westcall','vseinstrumenti','checkkontur','etm.ru','abb-market','nk-grup.ru','megafon.ru','sabylink.ru','no-reply@gosuslugi.ru'])]
with imaplib.IMAP4_SSL(env.get('IMAP_HOST') or 'imap.yandex.ru',int(env.get('IMAP_PORT') or 993),timeout=45) as c:
 c.login(env.get('IMAP_USERNAME') or env['SMTP_USERNAME'],env.get('IMAP_PASSWORD') or env['SMTP_PASSWORD']);c.select('INBOX',readonly=True)
 for h in selected:
  dest=ROOT/f"mail_{h['uid']}.json"
  if dest.exists() or h['size']>6_000_000:continue
  _,parts=c.uid('fetch',h['uid'],'(BODY.PEEK[])');raw=b''.join(x[1] for x in parts if isinstance(x,tuple));msg=email.message_from_bytes(raw);files=[]
  for i,p in enumerate(msg.walk()):
   if p.get_filename():
    name=p.get_filename();ext=Path(name).suffix.lower()
    if ext not in ['.pdf','.xlsx','.xls','.docx','.txt']:continue
    data=p.get_payload(decode=True)
    if data:
     target=ROOT/f"mail_{h['uid']}_{i}{ext}";target.write_bytes(data);files.append({'name':name,'path':str(target)})
  dest.write_text(json.dumps({**h,'text':message_text(msg),'files':files},ensure_ascii=False,indent=2));print(h['uid'],'saved',len(files),flush=True)
