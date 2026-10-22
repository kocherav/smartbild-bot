import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,'/home/kocher.av/telegram-bridge')
import closing_runtime as c
from financial_archive import archive_document
root=Path(__file__).resolve().parent;file=next(root.glob('Договор*.pdf'));receipt=root/'contract-receipt.json';r=json.loads(receipt.read_text()) if receipt.exists() else {};api=c.api()
def save():receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2))
if not r.get('file_id'):
 f=api.upload_file(str(file));r['file_id']=str(f['id']);r['sha256']=hashlib.sha256(file.read_bytes()).hexdigest();save()
if not r.get('comment_id'):
 result=api._call('POST','/deal/861/comments',json_body={'contentType':'Comment','subject':{'contentType':'Deal','id':'861'},'content':'Договор №1.861-1606/2026 от 30.06.2026, предоставленный владельцем 13.10.2026 как действующая редакция. Сумма договора 6 150 000 руб.; дополнительно согласованы монтажные работы 1 500 000 руб. с оплатой наличными. Общая сумма сделки 7 650 000 руб. Владелец подтвердил наличный аванс 1 000 000 руб. от 01.07.2026. Оригинал сохранён без изменения.','attaches':[{'contentType':'File','id':r['file_id']}]})['data'];r['comment_id']=str(result['id']);save()
files=api._call('GET','/deal/861/allFiles',params={'limit':100})['data'];assert any(str(f['id'])==r['file_id'] for f in files);r['crm_verified']=True;save()
if not r.get('archive'):
 r['archive']=archive_document('861',str(file),'contract_client',document_number='1.861-1606/2026',display_name=file.name,api=api);save()
print(json.dumps(r,ensure_ascii=False))
