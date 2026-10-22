import json,sys,re,subprocess,urllib.request,hashlib
from pathlib import Path
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/megaplan-crm']
import financial_archive as a
import megaplan_transport
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from post_confirmed import wait_budget
R=Path(__file__).resolve().parents[1];D=R/'evidence/final111';folders={}
for line in (R/'evidence/posting/onedrive_folders.txt').read_text().splitlines():
 m=re.match(r'Сделка №(\d+) - ',line)
 if m:folders[m[1]]=line.rstrip('/')
original=a.deal_folder_name;a.deal_folder_name=lambda deal:folders.get(str(deal['id'])) or original(deal)
class Cached:
 def _call(self,method,path):return json.loads((R/'evidence'/('deal_'+path.split('/')[-1]+'.json')).read_text())
def copy(p,remote):subprocess.run(['rclone','--config','/home/kocher.av/.config/rclone/rclone.conf','copyto',str(p),remote,'--immutable'],check=True,capture_output=True,timeout=120)
def download(url):
 with megaplan_transport.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=60) as response:return response.read(20000001)
j=list(json.loads((R/'data/posting_journal.json').read_text())['operations'].values());results=[]
for iid in sorted({p['crm_invoice_id'] for p in j if p.get('crm_invoice_id')}):
 inv=json.loads((R/'evidence/payment_correction'/('verified_invoice_'+iid+'.json')).read_text());did=next(p['deal_id'] for p in j if p.get('crm_invoice_id')==iid);dest=D/('invoice_'+iid+'.pdf')
 if not dest.exists():
  data=wait_budget(download,inv['publicDownloadLink'])
  assert len(data)<=20000000 and data.startswith(b'%PDF');dest.write_bytes(data)
 assert dest.read_bytes().startswith(b'%PDF')
 text=subprocess.check_output(['pdftotext',str(dest),'-'],text=True);assert inv['number'] in text
 res=a.archive_document(did,str(dest),'invoice_client',inv['number'],'Счёт клиенту '+inv['number'],api=Cached(),copier=copy)
 stat=json.loads(subprocess.check_output(['rclone','--config','/home/kocher.av/.config/rclone/rclone.conf','lsjson',res['onedrive_remote'],'--stat'],text=True));assert stat['Size']==dest.stat().st_size
 results.append({'invoice_id':iid,'number':inv['number'],'deal_id':did,'source':str(dest),'sha256':a.sha256(str(dest)),'remote':res['onedrive_remote'],'verified':True});(D/'client_archive.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print('archived',iid,inv['number'],flush=True)
