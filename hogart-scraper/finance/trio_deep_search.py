import imaplib,json,email,re,hashlib
from pathlib import Path
from email import policy
root=Path(__file__).resolve().parent/'evidence/kav';cfg=json.loads(Path('/home/kocher.av/.config/innsis-finance/kav-mail.json').read_text());found=[]
with imaplib.IMAP4_SSL(cfg['host'],cfg['port'],timeout=45) as c:
 c.login(cfg['username'],cfg['password']);_,folders=c.list()
 for f in folders:
  m=re.match(rb'\((.*?)\) "[^"]*" (.*)',f)
  if not m or b'\\Noselect' in m[1]:continue
  folder=m[2].decode()
  if c.select(folder,readonly=True)[0]!='OK':continue
  # Server-side full-text search across all dates, including previously missed threads.
  query='(OR TEXT "44472" (OR TEXT "45575" (OR TEXT "50605" TEXT "55512")))'
  status,data=c.uid('search',None,query)
  if status!='OK':continue
  ids=data[0].split();print(folder,len(ids),flush=True)
  for uid in ids:
   _,parts=c.uid('fetch',uid,'(BODY.PEEK[])');raw=b''.join(x[1] for x in parts if isinstance(x,tuple));msg=email.message_from_bytes(raw,policy=policy.default);files=[];texts=[]
   for i,p in enumerate(msg.walk()):
    if p.is_multipart():continue
    name=p.get_filename()
    if name and Path(name).suffix.lower() in ['.pdf','.xls','.xlsx','.docx','.zip']:
     data=p.get_payload(decode=True)
     if data:
      sha=hashlib.sha256(data).hexdigest();dest=root/(sha+Path(name).suffix.lower());dest.write_bytes(data);files.append({'name':name,'path':str(dest),'sha256':sha})
    elif p.get_content_type() in ['text/plain','text/html']:
     try:texts.append(p.get_content())
     except Exception:pass
   key=hashlib.sha256(folder.encode()).hexdigest()[:12];d={'folder':folder,'key':key,'uid':uid.decode(),'From':str(msg.get('From','')),'Subject':str(msg.get('Subject','')),'Date':str(msg.get('Date','')),'files':files,'text':'\n'.join(texts)}
   (root/(key+'_'+uid.decode()+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2));found.append({'folder':folder,'uid':uid.decode(),'subject':d['Subject'],'attachments':[f['name'] for f in files]})
(root/'trio_deep_search.json').write_text(json.dumps(found,ensure_ascii=False,indent=2));print('matched',len(found),flush=True)
