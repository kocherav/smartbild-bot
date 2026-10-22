import sys,json,imaplib,email,hashlib,re,os
from pathlib import Path
from email import policy
sys.path.insert(0,'/home/kocher.av/megaplan-crm');import email_payment_monitor as epm;epm.BRIDGE_ENV='/home/kocher.av/telegram-bridge/.env'
R=Path(__file__).resolve().parent;D=R/'evidence/deep_review/mail';D.mkdir(exist_ok=True,parents=True);headers=json.loads((R/'evidence/deep_review/additional_headers.json').read_text());env=epm.load_env();cfgs={'kav':json.loads(Path('/home/kocher.av/.config/innsis-finance/kav-mail.json').read_text()),'info_reconnected':{'host':env.get('IMAP_HOST') or 'imap.yandex.ru','port':int(env.get('IMAP_PORT') or 993),'username':env.get('IMAP_USERNAME') or env['SMTP_USERNAME'],'password':env.get('IMAP_PASSWORD') or env['SMTP_PASSWORD']}}
selected=headers
print('Fetching',len(selected),'known message IDs',flush=True)
for name,cfg in cfgs.items():
 targets=[x for x in selected if x['mailbox']==name]
 if not targets:continue
 with imaplib.IMAP4_SSL(cfg['host'],cfg['port'],timeout=45) as c:
  c.login(cfg['username'],cfg['password']);folder=None
  for x in targets:
   dest=D/(name+'_'+x['key']+'_'+x['uid']+'.json')
   if dest.exists():continue
   if folder!=x['folder']:assert c.select(x['folder'],readonly=True)[0]=='OK';folder=x['folder']
   typ,res=c.uid('fetch',x['uid'],'(BODY.PEEK[])');assert typ=='OK';raw=b''.join(y[1] for y in res if isinstance(y,tuple));msg=email.message_from_bytes(raw,policy=policy.default);files=[];texts=[]
   for p in msg.walk():
    if p.is_multipart():continue
    fn=p.get_filename()
    if fn:
     data=p.get_payload(decode=True)
     if data:
      sha=hashlib.sha256(data).hexdigest();fp=D/(sha+Path(fn).suffix.lower());fp.write_bytes(data);files.append({'name':fn,'path':str(fp),'sha256':sha})
    elif p.get_content_type() in ['text/plain','text/html']:
     try:texts.append(p.get_content())
     except Exception:pass
   dest.write_text(json.dumps({**x,'text':'\n'.join(texts),'files':files},ensure_ascii=False,indent=2));os.chown(dest,1001,27);print(x['uid'],x['Subject'],flush=True)
print('complete',flush=True)
