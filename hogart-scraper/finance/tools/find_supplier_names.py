import sys,json
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance']
from post_confirmed import *
a=MegaplanAPI();D=ROOT/'evidence/payment_correction'
queries={'7703675923':'ДАИЧИ','5038179677':'ФЛОУ','615518680653':'Пономарев','6623097295':'БОНГО','6673199711':'ИРИДИУМ','7705449060':'ЭЛИТАСВЕТ','7717632694':'ТРИО','7720298746':'ЭЛЕВЕЛ','7722805624':'УНИСТРОЙ','7733272640':'ЭЛРУС','7743795913':'ВЕНТРЕШЕНИЕ','7743949955':'КОМФОРТНАЯ','775114176346':'Панькин','7811504932':'КЕМИКС','7842224734':'ЭЛЕКТРОТЕХМОНТАЖ','9701027624':'БЮЛЕР','9701037968':'АЕР','9728104795':'ОЗОН'}
for inn,q in queries.items():
 f=D/('supplier_name_'+inn+'.json')
 if f.exists():continue
 data=wait_budget(a._call,'GET','/contractorCompany/search',params={'q':q,'limit':100})
 if len(inn)==12:
  data['data']+=wait_budget(a._call,'GET','/contractorHuman/search',params={'q':q,'limit':100}).get('data',[])
 atomic(f,data);print(inn,[(x.get('id'),x.get('name')) for x in data.get('data',[])],flush=True)
