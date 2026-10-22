import sys,json,time
from pathlib import Path
sys.path[:0]=['/home/kocher.av/telegram-bridge','/home/kocher.av/megaplan-crm','/home/kocher.av/hogart-scraper/dashboard']
from megaplan_api import MegaplanAPI
from megaplan_transport import ProtectionPause
from partial_shipments import snapshot
import shipment_workspace as w
api=MegaplanAPI()
for did in ('861','887','890','894'):
 for attempt in range(8):
  try:
   data=snapshot(did,api);w.save_book(did,data);break
  except ProtectionPause:
   if attempt==7:raise
   time.sleep(15)
 print(json.dumps({'deal':did,'state':w.book(did)['state'],'rows':len(data['positions']),'blocking_errors':data.get('blocking_errors')},ensure_ascii=False),flush=True)
