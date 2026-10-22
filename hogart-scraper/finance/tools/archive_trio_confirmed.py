import json,sys,re,subprocess
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/megaplan-crm')
import financial_archive as a
R=Path(__file__).resolve().parents[1];D=R/'evidence/trio_confirmed_oct6'
folders={}
for line in (R/'evidence/posting/onedrive_folders.txt').read_text().splitlines():
 m=re.match(r'Сделка №(\d+) - ',line)
 if m:folders[m[1]]=line.rstrip('/')
original=a.deal_folder_name
a.deal_folder_name=lambda deal:folders.get(str(deal['id'])) or original(deal)
class Cached:
 def _call(self,method,path):return json.loads((D/('deal_'+path.split('/')[-1]+'.json')).read_text())
def copy(p,remote):subprocess.run(['rclone','copyto',p,remote,'--immutable'],check=True,capture_output=True,timeout=120)
results=[];seen=set()
for x in json.loads((D/'new_links.json').read_text()):
 key=(x['deal_id'],x['source'])
 if key in seen:continue
 seen.add(key);res=a.archive_document(x['deal_id'],x['source'],'supplier_invoice',x['number'],'Счёт '+x['number'],api=Cached(),copier=copy)
 verify=json.loads(subprocess.check_output(['rclone','lsjson',res['onedrive_remote'],'--stat'],text=True));assert verify['Size']==Path(x['source']).stat().st_size
 results.append({'number':x['number'],'deal_id':x['deal_id'],'remote':res['onedrive_remote'],'sha256':a.sha256(x['source']),'verified':True,'duplicate':res['duplicate']});print(x['number'],x['deal_id'],'verified',flush=True)
(D/'archive_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
