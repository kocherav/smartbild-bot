import sys,json,imaplib,re,email,hashlib
from pathlib import Path
from email import policy
sys.path.insert(0,'/home/kocher.av/megaplan-crm');from email_payment_monitor import load_env
root=Path(__file__).resolve().parents[1]/'evidence/final_answers_20261007/mail';root.mkdir(exist_ok=True,parents=True)
terms={'085379','30621746','31421282','34023676','099912439','AS20HQJ','42965','44245'}
cfg=json.loads(Path('/home/kocher.av/.config/innsis-finance/kav-mail.json').read_text());import email_payment_monitor as epm;epm.BRIDGE_ENV='/home/kocher.av/telegram-bridge/.env';env=epm.load_env()
configs=[cfg,{'host':env.get('IMAP_HOST') or 'imap.yandex.ru','port':int(env.get('IMAP_PORT') or 993),'username':env.get('IMAP_USERNAME') or env['SMTP_USERNAME'],'password':env.get('IMAP_PASSWORD') or env['SMTP_PASSWORD']}]
audit=[]
for cfg in configs:
 with imaplib.IMAP4_SSL(cfg['host'],cfg['port'],timeout=45) as c:
  try:c.login(cfg['username'],cfg['password'])
  except imaplib.IMAP4.error:
   audit.append({'mailbox':cfg['username'],'status':'authentication_failed'});continue
  _,folders=c.list()
  for f in folders:
   m=re.match(rb'\((.*?)\) "[^"]*" (.*)',f)
   if not m or b'\\Noselect' in m[1]:continue
   folder=m[2].decode()
   if folder.strip(chr(34)) not in ('INBOX','Sent'):continue
   if c.select(folder,readonly=True)[0]!='OK':continue
   status,count=c.select(folder,readonly=True)
   if status!='OK' or not int(count[0] or 0):continue
   ids=set();failures=[]
   for term in sorted(terms):
    status,data=c.uid('search',None,'TEXT', '"'+term+'"')
    if status=='OK':ids.update(data[0].split())
    else:failures.append(term)
   ids=sorted(ids,key=int);print(cfg['username'],folder,len(ids),'failed',len(failures),flush=True)
   audit.append({'mailbox':cfg['username'],'folder':folder,'count':len(ids),'status':'searched_all_dates' if not failures else 'partial','failed_terms':failures})
   key=hashlib.sha256((cfg['username']+folder).encode()).hexdigest()[:16]
   for uid in ids:
    dest=root/(key+'_'+uid.decode()+'.json')
    if dest.exists():continue
    if False:
     previous=root.parent/'kav'/(hashlib.sha256(folder.encode()).hexdigest()[:12]+'_'+uid.decode()+'.json')
     if previous.exists():
      old=json.loads(previous.read_text());old['mailbox']=cfg['username'];old['subject']=old.get('Subject','');old['from']=old.get('From','');old['date']=old.get('Date','');dest.write_text(json.dumps(old,ensure_ascii=False));continue
    _,parts=c.uid('fetch',uid,'(BODY.PEEK[])');raw=b''.join(x[1] for x in parts if isinstance(x,tuple));msg=email.message_from_bytes(raw,policy=policy.default);files=[];texts=[]
    for p in msg.walk():
     if p.is_multipart():continue
     name=p.get_filename()
     if name and Path(name).suffix.lower() in ['.pdf','.xls','.xlsx','.docx','.zip','.jpg','.png']:
      data=p.get_payload(decode=True)
      if data:
       sha=hashlib.sha256(data).hexdigest();fp=root/(sha+Path(name).suffix.lower());fp.write_bytes(data);files.append({'name':name,'path':str(fp),'sha256':sha})
     elif p.get_content_type() in ['text/plain','text/html']:
      try:texts.append(p.get_content())
      except Exception:pass
    dest.write_text(json.dumps({'mailbox':cfg['username'],'folder':folder,'uid':uid.decode(),'subject':str(msg.get('Subject','')),'date':str(msg.get('Date','')),'from':str(msg.get('From','')),'text':'\n'.join(texts),'files':files},ensure_ascii=False,indent=2))
   (root/'primary_mail_search_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
(root/'primary_mail_search_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
print('complete',flush=True)
