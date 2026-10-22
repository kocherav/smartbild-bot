"""Read-only, replay-safe intake of 1C bank ZIPs; unknown senders await review."""
import datetime as dt,email,email.policy,hashlib,imaplib,io,json,os,re,zipfile
from email.utils import getaddresses
from zoneinfo import ZoneInfo
from pathlib import Path
from ledger import ROOT,parse

def inspect_archive(payload,accounts):
 with zipfile.ZipFile(io.BytesIO(payload)) as z:
  entries=[x for x in z.infolist() if not x.is_dir()]
  if not entries or len(entries)>100 or sum(x.file_size for x in entries)>30_000_000:raise ValueError('Archive size limit')
  if not all(x.filename.lower().endswith('.txt') for x in entries):return False
  raw=[z.read(x) for x in entries]
  if not all(x.startswith(b'1CClientBankExchange') for x in raw):return False
  for x in raw:
   d=parse(x)
   if d['balance']['РасчСчет'] not in accounts:raise ValueError('Unknown company account')
 return True

def _retrieve_once():
 import sys
 sys.path.insert(0,'/home/kocher.av/megaplan-crm');from email_payment_monitor import load_env
 e=load_env();allowed={x.strip().lower() for x in os.environ.get('STATEMENT_SENDERS','payment@alfa-bank.info').split(',') if x.strip()}
 state_path=ROOT/'data/mail_intake.json';state=json.loads(state_path.read_text()) if state_path.exists() else {'seen':{},'pending':[]};notices=[]
 accounts=json.loads((ROOT/'accounts.json').read_text());today=dt.datetime.now(ZoneInfo('Europe/Moscow')).date();since=(today-dt.timedelta(days=14)).strftime('%d-%b-%Y')
 with imaplib.IMAP4_SSL(e.get('IMAP_HOST') or 'imap.yandex.ru',int(e.get('IMAP_PORT') or 993),timeout=45) as c:
  c.login(e.get('IMAP_USERNAME') or e['SMTP_USERNAME'],e.get('IMAP_PASSWORD') or e['SMTP_PASSWORD']);folder='INBOX'
  if c.select(folder,readonly=True)[0]!='OK':raise RuntimeError('Cannot read INBOX')
  validity=str(c.response('UIDVALIDITY')[1]);status,data=c.uid('search',None,'SINCE',since)
  if status!='OK':raise RuntimeError('Date search failed')
  for uid in data[0].split():
   identity=hashlib.sha256((folder+validity+uid.decode()).encode()).hexdigest()
   if identity in state['seen']:continue
   status,parts=c.uid('fetch',uid,'(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])')
   if status!='OK':raise RuntimeError('Metadata fetch failed')
   raw=b''.join(x[1] for x in parts if isinstance(x,tuple));h=email.message_from_bytes(raw,policy=email.policy.default);senders={a.lower() for _,a in getaddresses(h.get_all('From',[]))}
   sizes=re.findall(rb'RFC822.SIZE (\d+)',b' '.join(x[0] if isinstance(x,tuple) else x for x in parts if x))
   if not sizes or int(sizes[0])>40_000_000:
    notices.append({'uid':uid.decode(),'reason':'oversize_message'});continue
   status,parts=c.uid('fetch',uid,'(BODY.PEEK[])')
   if status!='OK':raise RuntimeError('Message fetch failed')
   full=email.message_from_bytes(b''.join(x[1] for x in parts if isinstance(x,tuple)),policy=email.policy.default)
   for part in full.walk():
    filename=part.get_filename() or ''
    if not filename.lower().endswith('.zip'):continue
    payload=part.get_payload(decode=True)
    if not payload:continue
    sha=hashlib.sha256(payload).hexdigest()
    if any((ROOT/sub/(sha+'.zip')).exists() for sub in ['archive','inbox','quarantine','pending_sender']):continue
    try:valid=inspect_archive(payload,accounts)
    except Exception as exc:
     if re.search('выписк|statement',filename+' '+str(full.get('Subject','')),re.I):
      target=ROOT/'quarantine';target.mkdir(exist_ok=True);(target/(sha+'.zip')).write_bytes(payload);notices.append({'archive':sha,'reason':'invalid_statement','error':type(exc).__name__})
     continue
    if not valid:continue
    trusted=bool(senders&allowed);dest=ROOT/('inbox' if trusted else 'pending_sender');dest.mkdir(exist_ok=True)
    (dest/(sha+'.zip')).write_bytes(payload)
    meta={'uid':uid.decode(),'message_id':str(full.get('Message-ID','')),'sender':sorted(senders),'filename':filename,'received_header':str(full.get('Date','')),'saved_at':dt.datetime.now(dt.timezone.utc).isoformat(),'trusted_sender':trusted}
    (dest/(sha+'.json')).write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    if not trusted:state['pending'].append(meta);notices.append({'archive':sha,'reason':'new_statement_sender','sender':sorted(senders)})
   state['seen'][identity]={'uid':uid.decode(),'date':today.isoformat()}
   tmp=state_path.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False));tmp.replace(state_path)
 # Keep unresolved archives visible in every status, not only when first fetched.
 for meta_path in (ROOT/'pending_sender').glob('*.json'):
  if not any(x.get('archive')==meta_path.stem for x in notices):
   meta=json.loads(meta_path.read_text());notices.append({'archive':meta_path.stem,'reason':'new_statement_sender','sender':meta.get('sender',[])})
 return notices


def retrieve():
 # A reconnect replays safely: each imported archive and processed UID has a durable identity.
 import time
 for attempt in range(3):
  try:return _retrieve_once()
  except (imaplib.IMAP4.abort,OSError):
   if attempt==2:raise
   time.sleep(2*(attempt+1))
