import sys,json,hashlib
from pathlib import Path
sys.path[:0]=['/home/kocher.av/telegram-bridge','/home/kocher.av/megaplan-crm']
import closing_runtime as c
from financial_archive import archive_document
from procurement_attachments import email_messages
P=Path(__file__).parent; prepared=json.loads((P/'prepared.json').read_text());before=json.loads((P/'job-before.json').read_text());key=before['id'];crm=c.api();statepath=P/'receipts.json';state=json.loads(statepath.read_text()) if statepath.exists() else {}
def save():
 t=statepath.with_suffix('.tmp');t.write_text(json.dumps(state,ensure_ascii=False,indent=2));t.replace(statepath)
def step(k,fn):
 if k in state:
  if state[k].get('ok'):return state[k]
  raise ValueError('Нужна сверка неопределённого результата '+k)
 state[k]={'status':'started'};save();result=fn();assert result.get('ok');state[k]=result;save();return result
for i,path in enumerate(prepared['documents']):
 f=step('upload'+str(i),lambda path=path:{'ok':True,**crm.upload_file(path)})
 def comment(f=f):
  r=crm._call('POST','/deal/861/comments',json_body={'contentType':'Comment','subject':{'contentType':'Deal','id':'861'},'content':'Исправленная группировка акта 861-АПП/01: заменяет ранее отправленный файл. Все позиции — товары; сумма 4 799 480,20 ₽ прежняя. Финоперацию №3248 повторно не создавать. '+Path(path).name,'attaches':[{'contentType':'File','id':f['id']}]})['data'];return {'ok':bool(r.get('id')),'id':r.get('id')}
 step('comment'+str(i),comment)
 step('archive'+str(i),lambda path=path,i=i:archive_document('861',path,'client_closing' if i==0 else 'accounting_register',document_number='861-АПП/01',api=crm))
files=crm._call('GET','/deal/861/allFiles',params={'limit':100})['data'];assert all(any(str(f['id'])==str(state['upload'+str(i)]['id']) for f in files) for i in range(2))
current=c.registry().get(key);assert current.get('shipment_finance')==before.get('shipment_finance')
c.registry().patch(key,documents=prepared['documents'],note=prepared['note'],document_revision={'date':'2026-10-14','reason':'goods/service classification correction','previous_documents':before['documents'],'corrected_data':prepared['data'],'receipts':state.copy()})
cfg=c.env();subject='ИСПРАВЛЕННЫЙ АКТ №861-АПП/01 — только товары, сумма без изменений'
text='Татьяна, добрый день!\n\n'+prepared['note'].split('\n\n')[0]+'\n\nВо вложении исправленный акт с нашей подписью и печатью и исправленная подсказка бухгалтеру. Используйте эти файлы вместо ранее присланных. Закупочные документы прежние. Подтверждение отправки в ЭДО — по существующей кнопке этой отгрузки в боте.'
messages=email_messages(cfg.get('SMTP_FROM') or cfg['SMTP_USERNAME'],cfg['EDO_NOTIFY_EMAIL'],subject,text,prepared['documents'],'act861-classification-correction-20261014')
for i,m in enumerate(messages):step('email'+str(i),lambda m=m:c.send_email(m))
for who,chat in [('owner',cfg['TELEGRAM_CHAT_ID']),('tanya',c.recipient(cfg))]:
 step(who+'notice',lambda chat=chat:c.tg('sendMessage',{'chat_id':chat,'text':subject+'\nПять позиций на 56 970 ₽ перенесены из работ в товары. Итого по акту: 4 799 480,20 ₽. Замените прежний акт и подсказку файлами ниже. Татьяне отправлено также по почте. Повторную отгрузку/реализацию не создавать; операция №3248 остаётся прежней. Если старый акт уже отправлен в ЭДО — сообщите руководителю.'}))
 for i,path in enumerate(prepared['documents']):step(who+'file'+str(i),lambda chat=chat,path=path:c.send_file(chat,path,subject))
assert c.registry().get(key)['shipment_finance']==before['shipment_finance']
print(json.dumps(state,ensure_ascii=False))
