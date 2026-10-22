"""Deliver the requested workbook to the owner's existing bot chat."""
import json,uuid,urllib.request,sys
from pathlib import Path
p=Path('/home/kocher.av/telegram-bridge/.env');env={}
for line in p.read_text().splitlines():
 if '=' in line and not line.lstrip().startswith('#'):
  k,v=line.split('=',1);env[k.strip()]=v.strip().strip('\"').strip("'")
file=Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).parent/'reports/Разнесение_выписок.xlsx'
boundary=uuid.uuid4().hex
parts=[]
for k,v in {'chat_id':env['TELEGRAM_CHAT_ID'],'caption':(sys.argv[1] if len(sys.argv)>1 else 'Разнесение банковских выписок — актуальный отчёт.')}.items():
 parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{file.name}"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n'.encode()+file.read_bytes()+b'\r\n')
parts.append(f'--{boundary}--\r\n'.encode())
req=urllib.request.Request('https://api.telegram.org/bot'+env['TELEGRAM_BOT_TOKEN']+'/sendDocument',data=b''.join(parts),headers={'Content-Type':'multipart/form-data; boundary='+boundary})
with urllib.request.urlopen(req,timeout=45) as response:result=json.load(response)
print(json.dumps({'sent':result.get('ok'),'message_id':result.get('result',{}).get('message_id')}))
