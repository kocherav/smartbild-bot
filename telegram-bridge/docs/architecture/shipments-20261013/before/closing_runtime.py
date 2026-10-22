"""Closing delivery integration. Test runs never create invoices or change CRM states."""
import json, os, sys, re, hashlib, shutil, subprocess, urllib.request, urllib.parse, ssl, smtplib, fcntl
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from closing_workflow import Registry, final_clause, cents, settled_amount, bank_closure_allowed, next_business_day, SHIP, PAYMENT, COMPLETE, HOLIDAYS_2026
from workflow_runtime import Store as WorkflowStore
from effect_runner import execute
BASE=Path(__file__).resolve().parent
CRM=BASE.parent/'megaplan-crm'
sys.path.insert(0,str(CRM))
REGISTRY=BASE/'closing_jobs.json';OUT=BASE/'closing_bundles';DB=BASE/'workflow_runtime.sqlite3'

def env():
 result={}
 for line in (BASE/'.env').read_text().splitlines():
  if line.strip() and not line.lstrip().startswith('#') and '=' in line:
   k,v=line.split('=',1);result[k.strip()]=v.strip()
 return result

def recipient(config):
 p=BASE/'edo_recipient_chat_id.txt'
 return p.read_text().strip() if p.exists() else str(config.get('EDO_NOTIFY_TELEGRAM_CHAT_ID') or '')

def now():return datetime.now(ZoneInfo('Europe/Moscow'))
def registry():return Registry(REGISTRY)
def api():
 from megaplan_api import MegaplanAPI
 return MegaplanAPI()
def effect(job,name,action):
 result=execute(WorkflowStore(DB),'closing',name,job['id']+':'+name,{'deal':job['deal_id'],'mode':job['mode']},{'fingerprint':job.get('fingerprint','')},action)
 def record(data):
  data['jobs'][job['id']].setdefault('receipts',{})[name]=result
 registry().change(record)
 if not result.get('ok'):raise ValueError(name+': '+str(result.get('error','Нет подтверждения')))
 return result

def tg(method,data):
 config=env();request=urllib.request.Request('https://api.telegram.org/bot'+config['TELEGRAM_BOT_TOKEN']+'/'+method,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=30) as response:r=json.load(response)
 if not r.get('ok'):raise ValueError('Telegram не подтвердил '+method)
 result=r.get('result')
 # answerCallbackQuery returns True; sendMessage returns a Message object.
 return {'ok':True,'message_id':result.get('message_id') if isinstance(result,dict) else None}
def send_file(chat,path,caption):
 config=env();r=subprocess.run(['curl','-sS','--max-time','60','https://api.telegram.org/bot'+config['TELEGRAM_BOT_TOKEN']+'/sendDocument','-F','chat_id='+str(chat),'-F','document=@'+str(path),'-F','caption='+caption],capture_output=True,text=True,timeout=65)
 result=json.loads(r.stdout)
 if not result.get('ok'):raise ValueError('Telegram не подтвердил файл')
 return {'ok':True,'message_id':result['result']['message_id']}

def sources(deal_id):
 path=CRM/'bank_statement_registry.json';bank=json.loads(path.read_text())
 return bank.get('transactions',[])

def deadline(text,txs):
 spec=text[text.upper().rfind('СПЕЦИФИКАЦИЯ'):]
 terms=re.findall(r'(\d+)\s*\([^)]*\)\s*(рабочих|календарных)\s+дней',spec)
 if len(terms)!=1:raise ValueError('Не определён однозначный срок из спецификации')
 advances=[x for x in txs if x.get('direction')=='income' and re.search(r'6\.4\.1',x.get('purpose',''))]
 if not advances:raise ValueError('Не найдена дата аванса для расчёта договорного срока')
 day=max(datetime.strptime(x['date'],'%d.%m.%Y').date() for x in advances)
 count,kind=terms[0]
 for _ in range(int(count)):
  day+=timedelta(days=1)
  if kind=='рабочих':
   while True:
    if day.year!=2026:raise ValueError('Не настроен производственный календарь '+str(day.year))
    if day.weekday()<5 and day not in HOLIDAYS_2026:break
    day+=timedelta(days=1)
 return day.strftime('%d.%m.%Y')

def onedrive_url(remote):
 # Read-only webUrl of an existing item; never create anonymous/public sharing links.
 result=subprocess.run(['rclone','lsjson',remote,'--stat'],capture_output=True,text=True,timeout=40)
 if result.returncode:raise ValueError('Не найден документ OneDrive: '+remote.split('/')[-1])
 item=json.loads(result.stdout)
 config=json.loads(subprocess.run(['rclone','config','dump'],capture_output=True,text=True,timeout=10,check=True).stdout)['onedrive']
 token=json.loads(config['token'])['access_token'];drive=config['drive_id'];iid=str(item['ID']).split('#')[-1]
 url='https://graph.microsoft.com/v1.0/drives/'+urllib.parse.quote(drive,safe='')+'/items/'+urllib.parse.quote(iid,safe='')+'?$select=webUrl'
 request=urllib.request.Request(url,headers={'Authorization':'Bearer '+token})
 with urllib.request.urlopen(request,timeout=25) as response:info=json.load(response)
 if not info.get('webUrl'):raise ValueError('OneDrive не вернул ссылку на оригинал')
 return info['webUrl']

def procurement_links(deal_id,crm):
 archive=json.loads((CRM/'financial_archive.json').read_text()).get('documents',[])
 files=[];params={'limit':100};page_ids=set()
 while True:
  response=crm._call('GET',f'/deal/{deal_id}/allFiles',params=params);page=response.get('data') or []
  files.extend(page)
  if not response.get('meta',{}).get('pagination',{}).get('hasMoreNext'):break
  if not page or page[-1]['id'] in page_ids:raise ValueError('Мегаплан не вернул следующую страницу закупочных документов')
  page_ids.add(page[-1]['id']);params={'limit':100,'pageAfter':{'contentType':'File','id':page[-1]['id']}}
 docs=[];seen=set()
 for entry in archive:
  if entry.get('status','uploaded')!='uploaded':continue
  if str(entry.get('deal_id'))!=str(deal_id) or entry.get('category') not in ('supplier_invoice','supplier_closing'):continue
  identity=entry.get('sha256') or entry.get('onedrive_remote')
  if identity in seen:continue
  seen.add(identity);url=onedrive_url(entry['onedrive_remote']);docs.append({'name':entry['filename'],'url':url,'category':entry['category'],'number':entry.get('document_number','')})
 for f in files:
  name=f.get('name','')
  if re.search(r'счет|счёт|упд|накладн|поставщик',name,re.I) and not re.search('клиент|окончательн',name,re.I):
   if any(d.get('number') and d['number'] in name for d in docs):continue
   if f.get('path'):docs.append({'name':name,'url':f['path'] if f['path'].startswith('http') else 'https://'+crm.domain+f['path'],'category':'crm_document'})
 return docs

def validate_current(job,crm,deal=None):
 from contract_invoice import preview
 from generate_contract import contract_data
 deal=deal or crm._call('GET',f"/deal/{job['deal_id']}")['data']
 if str((deal.get('payer') or {}).get('id'))!=str(job['data']['payer_id']) or cents(deal['price'])!=job['total_cents']:raise ValueError('Плательщик или сумма изменились после подготовки комплекта')
 current=contract_data(deal,{})
 def rows(items):return [(p['id'],p['name'],Decimal(str(p['quantity'])),cents(p['total']),p['kind']) for p in items]
 if rows(current['positions'])!=rows(job['data']['positions']):raise ValueError('Позиции изменились после подготовки комплекта')
 for field in ('address','number','date'):
  if current[field]!=job['data'][field]:raise ValueError('Реквизиты договора изменились после подготовки комплекта')
 pay=preview({'deal_id':job['deal_id'],'clause':job['data']['payment']['clause']},crm)
 if pay['fingerprint']!=job['data']['payment']['fingerprint']:raise ValueError('Договор или реквизиты счёта изменились после подготовки комплекта')
 return deal

def prepare(job):
 from generate_contract import contract_data
 from payer_signatory_store import get_signatory
 from seller_documents import selected_seller
 from document_tax_policy import require_document_tax, decorate, contract_positions, approved_deal
 from contract_invoice import latest_contract,document_text,preview
 from closing_documents import validate_contract_rows,generate_act,test_invoice,money
 from procurement_workflow import supplier_invoices_for_deal,accounting_hints
 crm=api();deal=crm._call('GET',f"/deal/{job['deal_id']}")['data']
 if job['mode']=='live' and str(deal['state']['id'])!=SHIP:raise ValueError('Комплект формируется только в Отгрузке')
 payer_id=str((deal.get('payer')or{}).get('id') or '')
 if not payer_id:raise ValueError('Не указан плательщик')
 deal['payer']=crm._call('GET',f'/payer/{payer_id}')['data'];require_document_tax(deal,crm)
 data=contract_data(deal,{'customer_signatory':get_signatory(payer_id),'customer_signatory_payer_id':payer_id})
 if data['missing']:raise ValueError('Не заполнено: '+', '.join(data['missing']))
 seller=selected_seller(job['deal_id'])
 if seller['id']!='cliwell':raise ValueError('Для выбранного продавца не утверждён акт и комплект закрытия')
 selected,path=latest_contract(crm,job['deal_id']);text=document_text(path);clause=final_clause(text)
 payment=preview({'deal_id':job['deal_id'],'clause':clause},crm)
 checked=validate_contract_rows(text,contract_positions(data['positions'],job['deal_id']))
 data['positions']=[{**original,'unit':verified['unit']} for original,verified in zip(data['positions'],checked)]
 decorate(data,require_document_tax(deal,crm))
 data['transfer_dates']=approved_deal(job['deal_id']).get('transfer_dates',{})
 bank=sources(job['deal_id']);paid,proof=settled_amount(bank,job['deal_id'],deal['payer']['inn'],seller['accounts'])
 txs=[t for t in bank if t.get('source')!='email' and not str(t.get('id','')).startswith('email:') and str(t.get('deal_id'))==job['deal_id'] and t.get('status')=='assigned' and t.get('account') in seller['accounts'] and t.get('counterparty_inn')==deal['payer']['inn']]
 data.update(payment=payment,seller=seller,deadline=deadline(text,txs),act_date=now().strftime('%d.%m.%Y'))
 for fact in ['40702810902570001580','044525593','30101810200000000593']:
  if fact not in text:raise ValueError('Реквизиты расчётного счёта в договоре требуют проверки')
 fingerprint=hashlib.sha256(json.dumps({'contract':selected['id'],'positions':data['positions'],'payer':deal['payer']['inn'],'payment':payment['fingerprint']},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 folder=OUT/job['id'];folder.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,folder/('Договор'+Path(path).suffix));Path(path).unlink()
 from hogart_closing import sync as sync_hogart
 supplier_checks=sync_hogart(job['deal_id'],folder/'supplier-originals',crm,lambda name,action:effect(job,name,action),publish=job['mode']=='live')
 registry().patch(job['id'],supplier_checks=supplier_checks)
 from procurement_attachments import build as build_attachments
 procurement=build_attachments(job['deal_id'],folder/'procurement-attachments',CRM/'financial_archive.json',supplier_invoices_for_deal(job['deal_id']))
 docs=[{'name':x['name'],'category':x['category'],'number':x['number']} for x in procurement['files']]
 registry().patch(job['id'],procurement_attachments=procurement['attachments'])
 act=generate_act(data,folder,job['mode']=='test');inv=test_invoice(data,folder) if job['mode']=='test' else None
 updated=registry().patch(job['id'],fingerprint=fingerprint,payer_inn=deal['payer']['inn'],seller_accounts=seller['accounts'],total_cents=cents(data['total']),data=data,links=docs,contract_file_id=selected['id'],folder=str(folder),act=act)
 if job['mode']=='live':inv=ensure_invoice(updated,crm)
 note=['ТЕСТ — НЕ ОТПРАВЛЯТЬ КЛИЕНТУ И НЕ ПРОВОДИТЬ В 1С' if job['mode']=='test' else 'Подсказка бухгалтеру — внутренний документ',f"Сделка №{job['deal_id']}. Плательщик: {data['payer_name']}, ИНН {deal['payer']['inn']}.",f"Договор №{data['number']} от {data['date']}. Объект: {data['address']}.",f"Полный объём закрытия: {money(data['total'])} ₽. {data['tax_text']}.",f"Товары: {money(sum(Decimal(str(x['total'])) for x in data['positions'] if x['kind']!='work'))} ₽. Работы: {money(sum(Decimal(str(x['total'])) for x in data['positions'] if x['kind']=='work'))} ₽.",f"Подтверждённые оплаты по выписке: {money(Decimal(paid)/100)} ₽. Остаток по всей сделке: {money(Decimal(cents(data['total'])-paid)/100)} ₽.",f"Счёт окончательного расчёта по п. {clause}: {money(payment['amount'])} ₽. Условия — в договоре.", 'Задание: отправить наш акт, подготовить в 1С УПД на товары и работы и отправить УПД и счёт через ЭДО. Затем подтвердить отправку всего комплекта в боте и указать реквизиты акта, всех УПД и счёта.']
 difference=cents(data['total'])-paid-cents(payment['amount'])
 if difference:note.append('ВНИМАНИЕ: остаток по всей сделке отличается от суммы окончательного счёта на '+money(Decimal(difference)/100)+' ₽. Эта разница не списывается автоматически.')
 note+=['','Проверка личного кабинета Хогарт:']+supplier_checks if supplier_checks else []
 if data.get('transfer_dates'):
  note+=['Даты передачи по указанию руководителя: товары — '+data['transfer_dates']['goods']+' без НДС; работы — '+data['transfer_dates']['work']+' с НДС 5%. Дата составления акта — '+data['act_date']+'.',
   'В 1С разделить передачу товаров и работ по датам хозяйственных операций. Оплата аванса сама по себе не определяет режим НДС отгрузки. Не задваивать сентябрьскую передачу товаров октябрьским документом.',
   'Стоимость работ увеличена на НДС 5% сверху по указанию руководителя. Согласовать изменение цены с заказчиком; первоначальный договор сохраняется без перезаписи.']
 note+=['','Закупки и оплаченные счета поставщиков:']
 suppliers=supplier_invoices_for_deal(job['deal_id'])
 for supplier in suppliers:
  note.append(f"• {supplier.get('supplier')}, счёт №{supplier.get('number')} от {supplier.get('date')}; сумма {money(supplier.get('total',0))} ₽, оплачено {money(supplier.get('paid_total',0))} ₽; покупатель {supplier.get('buyer') or 'не указан'}.")
  for closing in supplier.get('closing_documents',[]):note.append('  Получен закрывающий документ: '+closing.get('filename','УПД')+'.')
  if not supplier.get('closing_documents'):note.append('  ВНИМАНИЕ: закрывающий документ поставщика не зарегистрирован. Перечень приобретённого товара сейчас можно посмотреть по счёту поставщика; необходимо получить закрывающий документ.')
 for hint in accounting_hints(job['deal_id']).get('hints',[]):note.append('• '+hint['text'])
 note+=['','Закупочные оригиналы приложены ZIP-архивом; вход в OneDrive не требуется.',procurement['register']]
 note+=['','Акт и УПД относятся к одному объёму передачи: не дублировать реализацию при отражении в 1С.','Тестовые документы не регистрировались как реализация и не изменяют стадию сделки.' if job['mode']=='test' else 'Даты фактической передачи указаны выше; даты подписания стороны заполняют при подписании.' if data.get('transfer_dates') else 'Дата фактической передачи заполняется при подписании; дата акта — дата формирования.']
 if job.get('replaces_job'):note.insert(1,'ИСПРАВЛЕННЫЙ КОМПЛЕКТ: заменяет ранее отправленные акт, счёт №10497 и подсказку. Счёт обновлён под прежним номером; это не второй счёт к оплате. До отправки согласовать с заказчиком приложенный проект допсоглашения. Если прежние документы уже отправлены в ЭДО, сообщить руководителю и оформить исправления; повторную реализацию не проводить.')
 note_text='\n'.join(note);(folder/'Подсказка бухгалтеру.txt').write_text(note_text)
 from weasyprint import HTML
 import html
 hintpdf=folder/'Подсказка бухгалтеру.pdf';HTML(string='<meta charset="utf-8"><style>@page{size:A4;margin:16mm}body{font:10pt Arial}p{white-space:pre-wrap;overflow-wrap:anywhere}</style><p>'+html.escape(note_text)+'</p>').write_pdf(hintpdf)
 from closing_documents import price_addendum
 addendum=price_addendum(data,folder)
 registry().patch(job['id'],additional_documents=[addendum] if addendum else [])
 manifest={'additional_documents':[addendum] if addendum else [],'data':data,'links':docs,'paid_cents':paid,'payment_proof':proof,'documents':[act,inv,str(hintpdf)],'note':note_text,'fingerprint':fingerprint}
 (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 return registry().patch(job['id'],documents=manifest['documents'],note=note_text,status='ready',last_error=None)

from decimal import Decimal

def ensure_invoice(job,crm):
 from contract_invoice import list_invoices,create
 payment=job['data']['payment'];existing=[x for x in list_invoices({'deal_id':job['deal_id']},crm)['invoices'] if x.get('line')==payment['line'] and cents(x['sum'])==cents(payment['amount'])]
 if len(existing)>1:raise ValueError('Найдено несколько счетов окончательного расчёта; нужна сверка')
 if existing:
  inv=crm._call('GET',f"/invoice/{existing[0]['id']}",params={'fields':['rows']})['data']
  if str((inv.get('payer') or {}).get('id'))!=str(job['data']['payer_id']) or str((inv.get('recipient') or {}).get('id'))!=str(payment['recipient_id']):raise ValueError('У найденного окончательного счёта другие стороны')
 def make():
  result=create({'deal_id':job['deal_id'],'clause':payment['clause'],'expected_fingerprint':payment['fingerprint']},crm)
  if not result.get('ok'):return result
  return {'ok':True,'invoice_id':result['invoice_id'],'number':result['invoice_number']}
 invoice={'invoice_id':existing[0]['id'],'number':existing[0]['number']} if existing else effect(job,'create-final-invoice',make)
 registry().patch(job['id'],invoice=invoice)
 # Use the already tested fetch command without triggering invoice creation.
 result=subprocess.run([sys.executable,str(CRM/'megaplan_webhook.py'),'fetch-invoice-pdf'],input=json.dumps({'invoiceId':invoice['invoice_id']}),capture_output=True,text=True,timeout=90)
 fetched=json.loads(result.stdout.strip().splitlines()[-1])
 if not fetched.get('ok'):raise ValueError('Не получен PDF окончательного счёта')
 path=Path(job['folder'])/('Счёт '+str(invoice['number'])+'.pdf');shutil.copyfile(fetched['path'],path);return str(path)

def publish(job):
 if job['mode']=='test':return
 crm=api();current=validate_current(job,crm)
 if str(current['state']['id'])!=SHIP:raise ValueError('Сделка вышла из Отгрузки до публикации комплекта')
 from financial_archive import archive_document
 for i,path in enumerate(job['documents']+job.get('additional_documents',[])):
  def attach(path=path):
   f=crm.upload_file(path);c=crm._call('POST',f"/deal/{job['deal_id']}/comments",json_body={'contentType':'Comment','subject':{'contentType':'Deal','id':job['deal_id']},'content':'Комплект закрытия '+job['id']+': '+Path(path).name,'attaches':[{'contentType':'File','id':f['id']}]}).get('data') or {}
   if not c.get('id'):raise ValueError('Не подтверждено вложение в сделку')
   return {'ok':True,'file_id':f['id'],'comment_id':c['id']}
  effect(job,'crm-'+str(i),attach)
  effect(job,'archive-'+str(i),lambda path=path,i=i:archive_document(job['deal_id'],path,'client_closing' if i==0 or i>=3 else 'invoice_client' if i==1 else 'accounting_register',api=crm))

def send_email(message):
 config=env();port=int(config['SMTP_PORT'])
 connection=smtplib.SMTP(config['SMTP_HOST'],port,timeout=40) if port==587 else smtplib.SMTP_SSL(config['SMTP_HOST'],port,timeout=40,context=ssl.create_default_context())
 with connection as smtp:
  if port==587:smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
  smtp.login(config['SMTP_USERNAME'],config['SMTP_PASSWORD']);refused=smtp.send_message(message)
  if refused:raise ValueError('SMTP отклонил получателя')
 return {'ok':True,'message_id':str(message['Message-ID']),'recipient':str(message['To']),'status':'accepted_by_smtp'}

def delivery(job):
 config=env();tanya=recipient(config);owner=config['TELEGRAM_CHAT_ID']
 if not tanya:raise ValueError('Не зарегистрирован Telegram Татьяны')
 test=job['mode']=='test';prefix='ТЕСТ — НЕ ОТПРАВЛЯТЬ КЛИЕНТУ. ' if test else ''
 if job.get('replaces_job'):prefix+='ИСПРАВЛЕННЫЙ КОМПЛЕКТ — НДС 5%. '
 title=prefix+f"Закрывающие документы — {job['data']['payer_name']} — договор {job['data']['number']}"
 text=prefix+'\nТатьяна, добрый день!\n'+('Просьба проверить полный комплект. В 1С не проводить и клиенту через ЭДО пока не отправлять. Боевой комплект придёт отдельно после перевода сделки владельцем в «Отгрузку».\n' if test else 'Просьба отправить клиенту наш акт, подготовить в 1С УПД и отправить его вместе со счётом окончательного расчёта через ЭДО. После отправки всех документов нажмите кнопку в боте и укажите их реквизиты.\n')+'\n'+job['note']
 from procurement_attachments import email_messages
 attachments=job['documents']+job.get('additional_documents',[])+job.get('procurement_attachments',[])
 messages=email_messages(config.get('SMTP_FROM') or config['SMTP_USERNAME'],config['EDO_NOTIFY_EMAIL'],title,text,attachments,'closing-'+job['id'])
 errors=[]
 steps=[('email' if len(messages)==1 else 'email-part-'+str(i),lambda m=m:send_email(m)) for i,m in enumerate(messages,1)]
 for chat in dict.fromkeys([owner,tanya]):
  summary=prefix+f"Сделка №{job['deal_id']} · {job['data']['payer_name']}\nАкт + счёт по п. {job['data']['payment']['clause']} + подсказка бухгалтеру.\n"+('Проверить комплект; клиенту не отправлять.' if test else 'Отправить акт, УПД из 1С и счёт через ЭДО.')+'\n\nЗакупочные документы приложены архивом с реестром:\n'+'\n'.join(x['name'] for x in job['links'])
  steps.append(('tg-message-'+chat,lambda chat=chat,summary=summary:tg('sendMessage',{'chat_id':chat,'text':summary})))
  for i,path in enumerate(attachments):steps.append(('tg-file-'+chat+'-'+str(i),lambda chat=chat,path=path:send_file(chat,path,prefix+Path(path).name)))
 controls={'inline_keyboard':[[{'text':'Тест проверен' if test else 'Отправлено в ЭДО','callback_data':'closing:'+job['id']+':'+('review' if test else 'sent')}],[{'text':'Нужны уточнения','callback_data':'closing:'+job['id']+':help'}]]}
 steps.append(('tg-controls',lambda:tg('sendMessage',{'chat_id':tanya,'text':prefix+'Результат по комплекту №'+job['deal_id'],'reply_markup':controls})))
 for name,fn in steps:
  try:effect(job,name,fn)
  except Exception as exc:errors.append(str(exc))
 if errors:raise ValueError('; '.join(errors))
 return registry().patch(job['id'],status='awaiting_test_review' if test else 'awaiting_edo',delivered_at=now().isoformat(),remind_at=next_business_day(now()).isoformat(),last_error=None)

def transition(job,target):
 crm=api();d=crm._call('GET',f"/deal/{job['deal_id']}")['data'];state=str(d['state']['id'])
 if state==target:return {'ok':True,'already':True}
 expected=SHIP if target==PAYMENT else PAYMENT
 if job['mode']!='live' or state!=expected:raise ValueError('Стадия изменилась; переход требует проверки')
 if target==PAYMENT:
  if not job.get('edo_confirmation'):raise ValueError('Нет подтверждения отправки документов через ЭДО')
  validate_current(job,crm,d)
 if target==COMPLETE:
  allowed,proof=bank_closure_allowed(job,d,sources(job['deal_id']))
  if not allowed:raise ValueError('Полная оплата не подтверждена')
  registry().patch(job['id'],settlement=proof)
 choices=[t for t in d.get('possibleTransitions',[]) if str((t.get('to')or{}).get('id'))==target and t.get('enabled',True)]
 if len(choices)!=1:raise ValueError('В схеме сделки отсутствует однозначный переход в '+target)
 crm._call('POST',f"/deal/{job['deal_id']}/applyTransition",json_body={'contentType':'ProgramTransition','id':choices[0]['id']})
 actual=crm._call('GET',f"/deal/{job['deal_id']}")['data']
 if str(actual['state']['id'])!=target:raise ValueError('Мегаплан не подтвердил стадию')
 from deal_browser import update_cached_deal
 update_cached_deal(actual)
 return {'ok':True,'state':target}

def process(job_id):
 # Whole-job lock prevents simultaneous preparation/delivery workers.
 BASE.mkdir(exist_ok=True)
 with open(BASE/('closing-'+job_id+'.lock'),'a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  job=registry().get(job_id)
  if job.get('manual_release_required'):return
  try:
   if job['status']=='preparing':job=prepare(job)
   if job['status']=='ready':publish(job);job=delivery(job)
   if job['status']=='edo_evidence_pending':job=preserve_edo_evidence(job)
   if job['status']=='edo_confirmed':
    # Re-read CRM after an uncertain transition before ever repeating it.
    actual=api()._call('GET',f"/deal/{job['deal_id']}")['data']
    if str(actual['state']['id'])==PAYMENT:validate_current(job,api(),actual)
    else:effect(job,'to-payment',lambda:transition(job,PAYMENT))
    job=registry().patch(job_id,status='awaiting_payment',last_error=None)
   if job['status']=='awaiting_payment':
    bank=sources(job['deal_id']);relevant=[t for t in bank if str(t.get('deal_id'))==job['deal_id']]
    cache=CRM/'deal_browser_cache.json';cards=json.loads(cache.read_text()) if cache.exists() else []
    card=next((d for d in cards if str(d.get('id'))==job['deal_id']),{})
    bank_digest=hashlib.sha256(json.dumps([relevant,card.get('state'),card.get('price'),card.get('payer')],sort_keys=True).encode()).hexdigest()
    if bank_digest==job.get('checked_bank_digest'):return
    deal=api()._call('GET',f"/deal/{job['deal_id']}")['data']
    already_complete=str((deal.get('state') or {}).get('id'))==COMPLETE
    checked={**deal,'state':{'id':PAYMENT}} if already_complete else deal
    allowed,proof=bank_closure_allowed(job,checked,bank)
    if allowed:
     if not already_complete:effect(job,'to-completed',lambda:transition(job,COMPLETE))
     registry().patch(job_id,status='completed',settlement=proof,last_error=None)
     effect(job,'completed-notice',lambda:tg('sendMessage',{'chat_id':env()['TELEGRAM_CHAT_ID'],'text':f"Сделка №{job['deal_id']}: полная оплата подтверждена выпиской, статус «Завершена»."}))
    registry().patch(job_id,checked_bank_digest=bank_digest)
   elif job['status'] in ('awaiting_edo','needs_info') and now()>=datetime.fromisoformat(job['remind_at']):
    due=job['remind_at'];cfg=env()
    for chat in dict.fromkeys([recipient(cfg),cfg['TELEGRAM_CHAT_ID']]):effect(job,'remind-'+due+'-'+chat,lambda chat=chat:tg('sendMessage',{'chat_id':chat,'text':f"Напоминание: по сделке №{job['deal_id']} ещё не подтверждена отправка акта, УПД и счёта через ЭДО. Если нужны уточнения, укажите их в боте."}))
    registry().patch(job_id,remind_at=next_business_day(now()).isoformat())
  except Exception as exc:
   # Never include tokens, credentials or signed transport URLs in notifications.
   message=('Не установлена библиотека формирования документов: '+str(exc.name)) if isinstance(exc,ModuleNotFoundError) else str(exc) if isinstance(exc,ValueError) else type(exc).__name__
   registry().patch(job_id,last_error=message)
   if message!=job.get('last_error'):
    tg('sendMessage',{'chat_id':env()['TELEGRAM_CHAT_ID'],'text':f"Комплект закрытия №{job['deal_id']}: {message}. Успешные этапы повторно не выполняются."})

def watch_cached():
 # Existing CRM cache refresh remains the only full-list network reader.
 cache=CRM/'deal_browser_cache.json'
 if not cache.exists():return
 content=cache.read_bytes();digest=hashlib.sha256(content).hexdigest()
 if registry().read().get('cache_digest')==digest:return
 states=[(d['id'],d['state']['id']) for d in json.loads(content) if str((d.get('program') or {}).get('id'))=='16' and (d.get('state') or {}).get('id')]
 registry().observe_many(states)
 registry().change(lambda data:data.update(cache_digest=digest))

def poll_in_document_environment():
 # The Telegram daemon uses system Python; document dependencies live in report-venv.
 python=Path(__file__).resolve().parent.parent/'.report-venv/bin/python'
 subprocess.run([str(python),str(Path(__file__).resolve()),'--poll'],check=True,timeout=900)

def poll():
 watch_cached()
 # Local minute tick does not reimport statements or rescan CRM.
 for job in list(registry().read()['jobs'].values()):
  if job['status'] not in ('completed','test_reviewed','cancelled'):process(job['id'])

def callback(query):
 cfg=env();actor=str(query.get('from',{}).get('id'));chat=str(query.get('message',{}).get('chat',{}).get('id'));tanya=recipient(cfg)
 if actor!=chat or actor!=tanya:return tg('answerCallbackQuery',{'callback_query_id':query['id'],'text':'Подтверждение доступно только Татьяне'})
 _,key,action=query['data'].split(':',2);job=registry().get(key)
 tg('answerCallbackQuery',{'callback_query_id':query['id'],'text':'Принято'})
 if action=='review' and job['mode']=='test' and job['status']=='awaiting_test_review':
  registry().patch(key,status='test_reviewed');return tg('sendMessage',{'chat_id':cfg['TELEGRAM_CHAT_ID'],'text':f"Татьяна проверила тестовый комплект №{job['deal_id']}. Боевые стадии и документы не менялись."})
 if action=='sent' and job['mode']=='live' and job['status'] in ('awaiting_edo','needs_info'):
  registry().patch(key,pending_actor=actor,pending_action='screenshot')
  result=tg('sendMessage',{'chat_id':chat,'text':f"Пришлите скриншот экрана отправки через ЭДО по сделке №{job['deal_id']}. На нём должны быть видны получатель, отправленные акт, УПД и счёт, дата и статус отправки. Ответьте фотографией или файлом PNG/JPEG на это сообщение. Отправляя скриншот, вы подтверждаете отправку всего комплекта. После сохранения скриншота в сделке и архиве бот переведёт сделку в «Оплату».",'reply_markup':{'force_reply':True,'selective':True}})
  registry().patch(key,screenshot_prompt_id=result['message_id'])
  return result
 if action=='help' and job['status'] in ('awaiting_edo','needs_info','awaiting_test_review'):
  registry().patch(key,pending_actor=actor,pending_action='help')
  return tg('sendMessage',{'chat_id':chat,'text':f"Напишите: Вопрос {key} и что нужно уточнить по сделке №{job['deal_id']}. Сообщение получит руководитель."})
 return tg('sendMessage',{'chat_id':chat,'text':'Действие недоступно для текущего состояния комплекта.'})

def screenshot(msg,download):
 chat=str((msg.get('chat') or {}).get('id'));actor=str((msg.get('from') or {}).get('id'))
 if chat!=recipient(env()) or actor!=chat:return False
 if not (msg.get('photo') or msg.get('document')):return False
 jobs=list(registry().read()['jobs'].values())
 if any(j.get('edo_evidence',{}).get('message_id')==msg.get('message_id') and j.get('edo_evidence',{}).get('actor')==actor for j in jobs):return True
 pending=[j for j in jobs if j['mode']=='live' and j['status'] in ('awaiting_edo','needs_info') and j.get('pending_actor')==actor and j.get('pending_action')=='screenshot']
 reply=(msg.get('reply_to_message') or {}).get('message_id')
 if reply is not None:pending=[j for j in pending if j.get('screenshot_prompt_id')==reply]
 if len(pending)!=1:
  raise ValueError('Ответьте скриншотом именно на запрос нужной сделки после кнопки «Отправлено в ЭДО».')
 job=pending[0];doc=msg.get('document') or {}
 if doc and str(doc.get('mime_type')) not in ('image/png','image/jpeg'):raise ValueError('Нужен скриншот PNG/JPEG или фотография, отправленная через Telegram.')
 path,error=download(msg)
 if error or not path:raise ValueError(error or 'Не удалось скачать скриншот; пришлите его повторно.')
 content=Path(path).read_bytes()
 if len(content)>20*1024*1024 or not (content.startswith(b'\x89PNG\r\n\x1a\n') or content.startswith(b'\xff\xd8\xff')):raise ValueError('Файл не является скриншотом PNG/JPEG.')
 folder=OUT/job['id'];folder.mkdir(parents=True,exist_ok=True)
 target=folder/('ЭДО — подтверждение отправки'+('.png' if content.startswith(b'\x89PNG') else '.jpg'));target.write_bytes(content)
 evidence={'actor':actor,'message_id':msg['message_id'],'path':str(target),'sha256':hashlib.sha256(content).hexdigest(),'at':now().isoformat(),'caption':msg.get('caption','')}
 registry().patch(job['id'],edo_evidence=evidence,status='edo_evidence_pending',pending_actor=None,pending_action=None)
 tg('sendMessage',{'chat_id':chat,'text':f"Скриншот по сделке №{job['deal_id']} получен. Сохраняю его в Мегаплане и архиве; затем проверю переход в «Оплату»."})
 return True

def preserve_edo_evidence(job):
 evidence=job['edo_evidence'];path=evidence['path']
 if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=evidence['sha256']:raise ValueError('Контрольная сумма скриншота изменилась')
 crm=api();validate_current(job,crm)
 def attach():
  f=crm.upload_file(path);result=crm._call('POST',f"/deal/{job['deal_id']}/comments",json_body={'contentType':'Comment','subject':{'contentType':'Deal','id':job['deal_id']},'content':'Татьяна подтвердила отправку комплекта через ЭДО. Приложен предоставленный ею скриншот.','attaches':[{'contentType':'File','id':f['id']}]}).get('data') or {}
  if not result.get('id'):raise ValueError('Не подтверждено сохранение скриншота в сделке')
  return {'ok':True,'file_id':f['id'],'comment_id':result['id']}
 effect(job,'edo-screenshot-crm',attach)
 from financial_archive import archive_document
 effect(job,'edo-screenshot-archive',lambda:archive_document(job['deal_id'],path,'accounting_register',api=crm))
 return registry().patch(job['id'],status='edo_confirmed',edo_confirmation={'actor':evidence['actor'],'at':evidence['at'],'kind':'user_attestation_with_screenshot','evidence':evidence})

def message(chat,text):
 cfg=env()
 if str(chat)!=recipient(cfg):return False
 m=re.match(r'(?is)^(ЭДО|Вопрос)\s+([0-9a-f]{16})\s*(.*)',text.strip())
 if not m:return False
 key=m[2];job=registry().get(key)
 if job.get('pending_actor')!=str(chat):raise ValueError('Сначала выберите действие у соответствующего комплекта')
 if m[1].casefold()=='вопрос':
  if job.get('pending_action')!='help':raise ValueError('Выберите «Нужны уточнения» у этого комплекта')
  if not m[3].strip():raise ValueError('Укажите текст вопроса')
  registry().patch(key,status='needs_info' if job['mode']=='live' else 'awaiting_test_review',question=m[3],remind_at=next_business_day(now()).isoformat(),pending_actor=None)
  tg('sendMessage',{'chat_id':cfg['TELEGRAM_CHAT_ID'],'text':f"Татьяна: уточнение по сделке №{job['deal_id']}:\n{m[3]}"})
 else:
  if job.get('pending_action')!='sent':raise ValueError('Выберите «Отправлено в ЭДО» у этого комплекта')
  refs={}
  for label,k in [('Акт','act'),('УПД','upd'),('Сч[её]т','invoice')]:
   value=re.search(r'(?im)^'+label+r'\s*:\s*(.+)$',m[3]);refs[k]=value[1].strip() if value else ''
  registry().confirm(key,chat,recipient(cfg),refs,now())
  tg('sendMessage',{'chat_id':chat,'text':'Подтверждение отправки акта, УПД и счёта сохранено. Переход в «Оплату» будет проверен в течение минуты; при ошибке руководитель получит уведомление.'})
 return True

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--test');p.add_argument('--poll',action='store_true');args=p.parse_args()
 if args.test:process(registry().enqueue(args.test,'test')['id'])
 elif args.poll:poll()
