"""Durable, user-visible model failures; no credentials or automatic side-effect replay."""
import hashlib,json,time
import durable_json

COMPLETED_HISTORY_LIMIT = 20

def compact(data):
    """Keep every recoverable request and only a small diagnostic success tail."""
    pending={key:value for key,value in data.items() if value.get('status') != 'model_answered'}
    answered=sorted(
        ((key,value) for key,value in data.items() if value.get('status') == 'model_answered'),
        key=lambda item:item[1].get('updated_at',0), reverse=True,
    )[:COMPLETED_HISTORY_LIMIT]
    return {**pending, **dict(answered)}

class ModelUnavailable(str):
    def __new__(cls,text,kind,request_id=''):
        obj=super().__new__(cls,text);obj.kind=kind;obj.request_id=request_id;return obj

def failure_kind(result):
    errors=[]
    for line in (result.stdout or '').splitlines():
        try:event=json.loads(line)
        except (ValueError,TypeError):continue
        if event.get('type') in ('error','turn.failed'):errors.append(str(event.get('message') or event.get('error') or ''))
    detail=(' '.join(errors)+' '+(result.stderr or '')).lower()
    if any(x in detail for x in ('refresh token','refresh_token','401 unauthorized','not logged in','authentication failed')):return 'auth'
    if any(x in detail for x in ('no rollout found','thread/resume failed','session not found')):return 'missing_thread'
    if result.returncode or errors:return 'provider'
    return ''

def key(chat_id,prompt,mode):return hashlib.sha256((str(chat_id)+'\0'+mode+'\0'+prompt).encode()).hexdigest()[:24]

def save_failure(path,chat_id,prompt,mode,kind):
    ident=key(chat_id,prompt,mode)
    with durable_json.locked(path):
        data=durable_json.read(path,dict);old=data.get(ident,{})
        data[ident]={'id':ident,'chat_id':str(chat_id),'prompt':prompt,'mode':mode,'kind':kind,'status':'needs_retry','created_at':old.get('created_at',time.time()),'updated_at':time.time(),'attempts':old.get('attempts',0)+(0 if old.get('status')=='processing' else 1)}
        durable_json.save(path,compact(data))
    return ident

def begin_request(path,chat_id,prompt,mode):
    ident=key(chat_id,prompt,mode)
    with durable_json.locked(path):
        data=durable_json.read(path,dict);old=data.get(ident,{})
        data[ident]={'id':ident,'chat_id':str(chat_id),'prompt':prompt,'mode':mode,'status':'processing','created_at':old.get('created_at',time.time()),'updated_at':time.time(),'attempts':old.get('attempts',0)+1}
        durable_json.save(path,compact(data))
    return ident


def mark_answered(path,chat_id,prompt,mode):
    ident=key(chat_id,prompt,mode)
    with durable_json.locked(path):
        data=durable_json.read(path,dict)
        if ident in data:
            data[ident].update(status='model_answered',updated_at=time.time());durable_json.save(path,compact(data))

def latest(path,chat_id):
    data=durable_json.read(path,dict)
    pending=[x for x in data.values() if x['chat_id']==str(chat_id) and (x['status']=='needs_retry' or (x['status']=='processing' and time.time()-x['updated_at']>360)) and x['mode']=='chat']
    return max(pending,key=lambda x:x['updated_at']) if pending else None

def failure_message(kind,mode):
    reason={'auth':'Сейчас не работает подключение к ИИ: требуется восстановить вход. Это технический сбой, а не проблема вашего файла.', 'timeout':'ИИ не успел закончить обработку.', 'provider':'Сервис ИИ временно не вернул ответ.'}.get(kind,'Не удалось получить ответ ИИ.')
    retry='После восстановления можно нажать «🔄 Повторить последний счёт».' if mode=='document' else 'Для повторной обработки сохранённого запроса напишите /повторить.'
    return reason+'\n\nЗапрос сохранён; приложенный файл повторно отправлять не нужно. '+retry
