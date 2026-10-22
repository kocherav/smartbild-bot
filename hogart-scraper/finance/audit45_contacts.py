import imaplib,email,json,re,hashlib,sys
from email import policy
from pathlib import Path
root=Path(__file__).resolve().parent/'evidence/kav';cfg=json.loads(Path('/home/kocher.av/.config/innsis-finance/kav-mail.json').read_text())
headers=json.loads((root/'headers.json').read_text())
# Read supplier correspondence and outgoing threads, not bulk commercial mail.
selected=[h for h in headers if re.search(r'шиша|вовчен|пономар|головин|беккер|андрос|борисик|русад|prv-70|d-shishaev',h.get('From','')+' '+h.get('To','')+' '+h.get('Subject',''),re.I)]
print('selected',len(selected),flush=True)
with imaplib.IMAP4_SSL(cfg['host'],cfg['port'],timeout=45) as c:
 c.login(cfg['username'],cfg['password']);folder=None
 for h in selected:
  dest=root/(h['key']+'_'+h['uid']+'.json')
  if dest.exists():continue
  if h['size']>25_000_000:print('oversize',h['uid'],flush=True);continue
  if folder!=h['folder']:
   folder=h['folder'];c.select(folder,readonly=True)
  status,parts=c.uid('fetch',h['uid'],'(BODY.PEEK[])')
  if status!='OK':continue
  raw=b''.join(x[1] for x in parts if isinstance(x,tuple));msg=email.message_from_bytes(raw,policy=policy.default);files=[];texts=[]
  for i,p in enumerate(msg.walk()):
   if p.is_multipart():continue
   name=p.get_filename()
   if name:
    ext=Path(name).suffix.lower()
    if ext in ['.pdf','.xlsx','.xls','.docx','.txt','.zip','.jpg','.png']:
     data=p.get_payload(decode=True)
     if data:
      sha=hashlib.sha256(data).hexdigest();target=root/(sha+ext)
      if not target.exists():target.write_bytes(data)
      files.append({'name':name,'path':str(target),'sha256':sha})
   elif p.get_content_type() in ['text/plain','text/html']:
    try:texts.append(p.get_content())
    except Exception:pass
  dest.write_text(json.dumps({**h,'text':'\n'.join(texts),'files':files},ensure_ascii=False,indent=2))
  print(h['uid'],'attachments',len(files),flush=True)
