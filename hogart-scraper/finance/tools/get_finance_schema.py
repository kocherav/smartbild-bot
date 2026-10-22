import sys,urllib.request
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
import megaplan_transport
a=MegaplanAPI()
def get():
 req=urllib.request.Request(a.base,headers={'Authorization':'Bearer '+a.token})
 with megaplan_transport.urlopen(req,timeout=60) as r:return r.read()
data=wait_budget(get);p=ROOT/'evidence/finish_all/api_schema.txt';p.write_bytes(data);os.chmod(p,0o600);print(len(data),data[:50])
