"""Copy reconciled originals to OneDrive, retaining versions and unresolved documents."""
import sys,json,hashlib,subprocess,re,os
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
import financial_archive as archive
R=Path(__file__).resolve().parent;E=R/'evidence/posting'
config='/home/kocher.av/.config/rclone/rclone.conf'
def copy(path,remote):
 r=subprocess.run(['rclone','--config',config,'copyto',str(path),remote,'--immutable','--retries','3'],capture_output=True,text=True,timeout=120)
 if r.returncode:raise RuntimeError('OneDrive copy failed: '+r.stderr[-300:])
class CachedAPI:
 def _call(self,method,path):
  assert method=='GET' and re.fullmatch(r'/deal/\d+',path)
  return json.loads((R/'evidence'/('deal_'+path.rsplit('/',1)[1]+'.json')).read_text())
existing={}
for line in (E/'onedrive_folders.txt').read_text().splitlines():
 m=re.match(r'Сделка №(\d+) - ',line)
 if m:existing[m[1]]=line.rstrip('/')
def folder(deal):
 did=str(deal['id'])
 if did in existing:return existing[did]
 description=re.sub('<[^>]+>','',deal.get('description') or deal.get('Category1000068CustomFieldPredmetDogovora') or deal['name'])
 return archive.safe('Сделка №'+did+' - '+deal.get('contractor',{}).get('name','Клиент')+' - '+description)
archive.deal_folder_name=folder
catalog=json.loads((E/'archive_catalog.json').read_text());results=[]
for d in catalog:
 title=archive.safe(f"Счёт {d['number']} — {d['supplier']} — {d['sha256'][:10]}")+Path(d['source']).suffix
 if d['category']=='supplier_closing':title=title.replace('Счёт ','УПД ',1)
 if d['deal_ids']:
  for did in d['deal_ids']:
   ans=archive.archive_document(did,d['source'],d['category'],d['number'],title,api=CachedAPI(),copier=copy)
   results.append({**d,'deal_id':did,'remote':ans['onedrive_remote'],'duplicate':ans['duplicate']})
 else:
  company='ИНСИС' if d['buyer_inn']=='7743926877' else 'КЛИВЭЛ'
  remote='onedrive:SmartBild/Сделки/00_Неразнесенные_счета/'+company+'/'+archive.safe(d['supplier'])+'/'+title
  copy(d['source'],remote);results.append({**d,'deal_id':None,'remote':remote,'duplicate':False})
 (E/'archive_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 print(d['number'],d['deal_ids'] or ['очередь'],flush=True)
# Verify against OneDrive's returned listing, not only the local mount cache.
r=subprocess.run(['rclone','--config',config,'lsjson','onedrive:SmartBild/Сделки','--recursive','--files-only'],capture_output=True,text=True,check=True,timeout=120)
listing=json.loads(r.stdout);sizes={x['Path']:x['Size'] for x in listing}
for d in results:
 relative=d['remote'].split('onedrive:SmartBild/Сделки/',1)[1]
 if sizes.get(relative)!=Path(d['source']).stat().st_size:raise RuntimeError('Remote verification failed: '+d['number'])
print(json.dumps({'unique_files':len(catalog),'copies':len(results),'deal_copies':sum(bool(x['deal_id']) for x in results),'queue_copies':sum(not x['deal_id'] for x in results),'remote_sizes_verified':True}),flush=True)
(E/'archive_verified.json').write_text(json.dumps({'unique_files':len(catalog),'copies':len(results),'remote_sizes_verified':True},ensure_ascii=False))
