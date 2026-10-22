"""Durable document queue and deterministic cancellation, independent of model history.

The model may read a document and propose a mapping. It does not own task identity,
select the execution route, cancel documents, or authorize a financial write.
"""
import copy,json,re,time
from pathlib import Path
import durable_json
import invoice_continuation
STORE=Path(__file__).with_name('invoice_tasks.json')
TITLE=re.compile(r'Сч[её]т(?:[-–—](?:оферта|договор))?\s*(?:на\s+оплату\s*)?№\s*([^\s]+)',re.I)
CANCEL=re.compile(r'(?i)\b(?:не\s+обрабатыва[йть]+|не\s+разнос[иить]+|исключи|отмени)\b')

def normal(number):
 return re.sub(r'[^0-9a-zа-я]','',str(number).casefold().replace('ё','е'))

def same_number(a,b):
 tail=re.search(r'(\d+)$',str(a).strip())
 a,b=normal(a),normal(b)
 return a==b or (b.isdigit() and tail is not None and tail.group(1)==b)

def read(chat):return copy.deepcopy(durable_json.read(str(STORE),dict).get(str(chat),{}))

def change(chat,fn):
 with durable_json.locked(str(STORE)):
  data=durable_json.read(str(STORE),dict);state=data.setdefault(str(chat),{'documents':[],'history':[],'revision':0})
  result=fn(state);state['revision']=state.get('revision',0)+1;durable_json.save(str(STORE),data)
  return copy.deepcopy(state),result

def active(state):
 if state.get('paused'):return None
 return next((d for d in sorted(state.get('documents',[]),key=lambda d:d.get('message_id',0)) if d.get('status') in ('pending','draft') and time.time()-d['received_at']<86400),None)

def register(chat,path,text,message_id,statement=None):
 title=TITLE.search(text)
 if not title:return None
 doc=invoice_continuation.remember(path,text,chat);doc.update(number=title.group(1),message_id=int(message_id),status='pending',statement=statement)
 if statement and statement.get('status')=='excluded_by_owner':doc['status']='cancelled'
 if statement and statement.get('status')=='processed':doc['status']='applied'
 def add(state):
  state['paused']=False
  state['foreground']='invoice'
  old=next((d for d in state['documents'] if d['sha256']==doc['sha256']),None)
  if old:return old
  for tomb in state.get('cancellations',[]):
   if int(message_id)<=tomb['message_id'] and same_number(doc['number'],tomb['number']):doc['status']='cancelled'
  state['documents'].append(doc);return doc
 state,doc=change(chat,add);return state,doc

def cancellation_number(text):
 if not CANCEL.search(text):return None
 # A number is mandatory: a bare refusal must never cancel all pending invoices.
 m=re.search(r'(?i)(?:сч[её]т(?:а)?\s*|№\s*)([a-zа-я]*\d[\w/\-]*)',text)
 if not m:m=re.search(r'(?<!\w)(\d{3,})(?!\w)',text)
 return m.group(1) if m else None

def cancel(chat,text,message_id):
 number=cancellation_number(text)
 if not number:return None
 def stop(state):
  found=[d for d in state['documents'] if same_number(d['number'],number) and d['status']!='applied']
  if len({normal(d['number']) for d in found})>1:return {'ambiguous':True,'number':number}
  for d in found:d['status']='cancelled'
  state.setdefault('cancellations',[]).append({'number':number,'message_id':int(message_id)})
  return {'number':number,'cancelled':[d['sha256'] for d in found],'registered':bool(found)}
 state,result=change(chat,stop);return state,result

def cancelled(chat,path):
 return any(d['path']==path and d['status']=='cancelled' for d in read(chat).get('documents',[]))

def history(chat,role,text,document_id=None):
 def add(state):
  if document_id and not any(d['sha256']==document_id and d['status']!='cancelled' for d in state['documents']):return
  state['history'].append({'role':role,'text':text[:16000],'document_id':document_id});state['history']=state['history'][-12:]
 return change(chat,add)[0]

def pause(chat):return change(chat,lambda s:s.update(paused=True))[0]

def complete(chat,path):
 if not path or not any(d['path']==path for d in read(chat).get('documents',[])):return read(chat)
 def done(state):
  for d in state['documents']:
   if d['path']==path and d['status']!='cancelled':d['status']='applied'
 return change(chat,done)[0]

def question(doc):return f"К какому объекту или сделке относится счёт №{doc['number']}? Достаточно названия — номер сделки искать вручную не нужно."

def prompt(state):
 doc=active(state)
 if not doc:return ''
 history=[h for h in state.get('history',[]) if h.get('document_id') in (None,doc['sha256'])]
 return ('[ИЗОЛИРОВАННАЯ ЗАДАЧА: РАЗОБРАТЬ СОХРАНЁННЫЙ СЧЁТ]\n'
 'Это продолжение одной задачи, а не поиск товаров. Используй только активный документ. '
 'Нельзя вызывать каталоги, готовить КП, договоры, менять другие сделки или создавать новую без прямого указания. '
 'Назначение загрузки: сверка оплаты/счёта с существующей сделкой. Не спрашивай, что делать с документом. '
 'Если объект ещё неизвестен, спроси только название объекта. Если назван — найди его среди всех сделок; '
 'не ограничивайся последними пятью. Прочитай живую спецификацию через DEAL_LEDGER_REQUEST. '
 'Не предлагай менять клиентские позиции или запрашивать наценку для простого разнесения оплаты. '
 'Отмена и очередь уже исполнены сервером; отменённые документы не возобновлять. '
 'Разрешены только DEAL_LEDGER_REQUEST, RECENT_DEALS_REQUEST, SUPPLIER_INVOICE_APPLY_BEGIN/END. '
 'SUPPLIER_INVOICE_APPLY — только проект для подтверждения; не обещай запись до результата.\n'
 +json.dumps({'active_document':doc,'other_pending_numbers':[d['number'] for d in state['documents'] if d['status']=='pending' and d['sha256']!=doc['sha256']],'history':history},ensure_ascii=False))

def guard_reply(reply,doc):
 # Even a confused model cannot execute unrelated tool protocols in invoice mode.
 markers=re.findall(r'(?m)^\s*([A-Z][A-Z_]+)(?::|\s|$)',reply)
 allowed={'SUPPLIER_INVOICE_APPLY_BEGIN','SUPPLIER_INVOICE_APPLY_END','DEAL_LEDGER_REQUEST','RECENT_DEALS_REQUEST'}
 if any(m not in allowed for m in markers):return question(doc)
 return reply


def accepts_upload(ui_state):
 # Merely being on a menu does not make an unsolicited file belong to its last deal.
 return ui_state.get('pending') in (None, '', 'procurement_menu', 'deal_menu', 'deal_card') and not ui_state.get('deal_creation_active')
