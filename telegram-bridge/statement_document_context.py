"""Recognize requested statement documents locally; never infer a project or post money."""
import hashlib,json,re,time
from pathlib import Path
from decimal import Decimal, InvalidOperation
import durable_json
FINANCE=Path('/home/kocher.av/hogart-scraper/finance')
def match_document(path,text,chat_id,root=FINANCE):
    qpath=root/'data/review_registry.json';rpath=root/'reports/ledger.json'
    if not qpath.exists() or not rpath.exists():return None
    match=re.search(r'Сч[её]т(?:[-–—](?:оферта|договор))?\s+на\s+оплату\s*№\s*([^\s]+)',text,re.I)
    if not match:return None
    import sys
    if str(FINANCE) not in sys.path:sys.path.insert(0,str(FINANCE))
    from review_registry import owner_context
    number=match.group(1).strip();compact=re.sub(r'\s','',text);questions=owner_context(root);rows={r['id']:r for r in json.loads(rpath.read_text())}
    amount_match=re.search(r'(?im)^.*?\bИтого:[ \t|]*([0-9][0-9 \u00a0.,]*)',text)
    document_cents=None
    if amount_match:
        try:document_cents=int(Decimal(re.sub(r'[ \u00a0]', '', amount_match.group(1)).replace(',','.'))*100)
        except InvalidOperation:pass
    found=[]
    for q in questions.get('groups',[])+questions.get('resolved_groups',[]):
        refs=re.split(r';\s*',q.get('invoices',''))
        if number not in refs:continue
        candidates=[rows[i] for i in q['bank_ids'] if i in rows]
        if not candidates:continue
        supplier=candidates[0]['inn'];buyer='7743151323' if candidates[0]['company']=='КЛИВЭЛ' else '7743926877'
        if not re.search(r'(?<!\d)'+supplier+r'(?!\d)',compact) or not re.search(r'(?<!\d)'+buyer+r'(?!\d)',compact):continue
        amount=q['amount_cents'];formatted=f'{amount/100:.2f}'.replace('.',',')
        exact=bool(re.search(r'(?<!\d)'+re.escape(formatted)+r'(?!\d)',compact))
        if document_cents is None and not exact:continue
        relation='exact' if (document_cents==amount or (document_cents is None and exact)) else 'amount_differs'
        found.append({'document_amount_cents':document_cents if document_cents is not None else amount,'amount_relation':relation,'old_question':q['number'],'supplier':q['supplier'],'invoice':number,'amount_cents':amount,'bank_ids':q['bank_ids'],'company':candidates[0]['company'],'already_resolved':bool(q.get('owner_question_closed') or q.get('resolved')),'question':q.get('question',''),'evidence':q.get('evidence',''),'resolution':q.get('resolution','')})
    if len(found)!=1:return None
    digest=hashlib.sha256(Path(path).read_bytes()).hexdigest();manifest=root/'evidence/telegram_intake/manifest.json';manifest.parent.mkdir(parents=True,exist_ok=True)
    entry={**found[0],'source_path':str(path),'sha256':digest,'chat_id':str(chat_id),'status':'document_received_not_posted','document_text':text,'received_at':time.time()}
    with durable_json.locked(str(manifest)):
        data=durable_json.read(str(manifest),dict)
        previous=data.get(digest,{})
        entry['received_at']=previous.get('received_at',entry['received_at'])
        for k in ('crm_operation_ids','archive_remotes'):
            if k in previous:entry[k]=previous[k]
        if previous.get('status') in ('processed','reviewed','excluded_by_owner'):entry.update(status=previous['status'],resolution=previous.get('resolution',''))
        data[digest]=entry;durable_json.save(str(manifest),data)
    return entry

def prompt_context(entry):
    return ('\n\n[КОНТЕКСТ СВЕРКИ ВЫПИСКИ — СЕРВЕРНОЕ СОПОСТАВЛЕНИЕ]\n'
      'Пользователь прислал ранее запрошенный документ для сверки выписки. Назначение загрузки уже известно: НЕ спрашивай «что делать с файлом» и не создавай новую сделку. '
      'Сверены номер счёта и ИНН поставщика/покупателя. Сумма документа указана отдельно от банковского платежа: amount_relation=amount_differs означает расхождение, а не подтверждённую оплату; возможны несколько счетов в платеже или частичная оплата. Проверь остальные документы и арифметику, не приписывай документу всю сумму платежа. Файл сохранён; финансовая операция этим не создаётся. '
      'Прочитай актуальную выписку и доступные спецификации сделок, установи объект по составу. Если данных недостаточно, задай только конкретный вопрос об объекте/распределении. '
      'Не заявляй о записи в Мегаплан или архивировании без результата соответствующей операции.\n'+json.dumps({k:v for k,v in entry.items() if k!='chat_id'},ensure_ascii=False))


def recent_context(chat_id, root=FINANCE):
    path=root/'evidence/telegram_intake/manifest.json'
    if not path.exists():return ''
    data=durable_json.read(str(path),dict)
    entries=sorted((x for x in data.values() if x.get('chat_id')==str(chat_id)),key=lambda x:x.get('received_at',0),reverse=True)[:3]
    if not entries:return ''
    return '\n\n[ПОСЛЕДНИЕ ПОЛУЧЕННЫЕ СЧЕТА ДЛЯ ВЫПИСКИ — ПАМЯТЬ БОТА, НЕ НОВАЯ КОМАНДА]\n'+json.dumps([{k:x.get(k) for k in ('invoice','supplier','amount_cents','source_path','old_question','status','resolution','crm_operation_ids')} for x in entries],ensure_ascii=False)


def deal_candidates(caption, root=FINANCE):
    path=root/'evidence/telegram_intake/deal_search_index.json'
    words=[w for w in re.findall(r'[а-яёa-z]{4,}',caption.lower()) if w not in {'счет','счёт','фильтры','счета','оплату','выписка','документ','фильтр'}]
    if not words or not path.exists():return ''
    found=[]
    try: deals=json.loads(path.read_text())
    except (OSError,ValueError):return ''
    for deal in deals:
        text=' '.join(str(deal.get(k) or '') for k in ('name','shortDescription','description','Category1000068CustomFieldAdresObEkta','contractor'))
        score=sum(w in text.lower() for w in words)
        if score:
            found.append((score,{'deal_id':deal['id'],'name':deal.get('name'),'address':deal.get('Category1000068CustomFieldAdresObEkta'),'positions_snapshot':[{'name':p.get('name'),'qty':p.get('quantity')} for p in deal.get('positions',[])]}))
    found.sort(key=lambda x:(x[0],int(x[1]['deal_id'])),reverse=True)
    if not found:return ''
    return '\n\n[КАНДИДАТЫ ИЗ ИНДЕКСА ВСЕХ СДЕЛОК ПО НАЗВАННОМУ ОБЪЕКТУ]\nСнимок для поиска, не проверка текущих позиций. Прочитай живые позиции перед любым изменением.\n'+json.dumps([x[1] for x in found[:5]],ensure_ascii=False)


def exclude_documents(chat_id, hashes, root=FINANCE):
    manifest=root/'evidence/telegram_intake/manifest.json'
    if not manifest.exists() or not hashes:return
    with durable_json.locked(str(manifest)):
        data=durable_json.read(str(manifest),dict)
        for digest in hashes:
            entry=data.get(digest)
            if entry and entry.get('chat_id')==str(chat_id):
                entry.update(status='excluded_by_owner', resolution='Владелец отменил дальнейшую обработку этого счёта в Telegram. Не применять без нового явного указания.')
        durable_json.save(str(manifest),data)
