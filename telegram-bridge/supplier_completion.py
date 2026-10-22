"""Keep committed procurement separate from completion of files and archives."""
import hashlib
import json
import sys
from pathlib import Path
FINANCE=Path(__file__).resolve().parent.parent/'hogart-scraper/finance'

def pending_steps(result):
    pending=[]
    for key,label in (('upload','сохранить исходный счёт в карточке'),
                      ('economics','пересчитать и сохранить экономику'),
                      ('procurement_register','обновить реестр закупок в карточке')):
        step=result.get(key) or {}
        if not step.get('ok'):pending.append(label+': '+str(step.get('error') or 'результат не подтверждён'))
        elif step.get('archive_warning'):pending.append('сохранить '+label+' в OneDrive: '+str(step['archive_warning']))
    return pending

def record(spec,result,root=FINANCE):
    if str(root) not in sys.path:sys.path.insert(0,str(root))
    from review_registry import record_processing_followup
    doc=spec.get('invoice') or {}
    identity=[str(spec.get('deal_id')),doc.get('supplier_inn'),doc.get('buyer_inn'),doc.get('number'),doc.get('date')]
    if not doc.get('number'):identity.append(json.dumps(spec,sort_keys=True,ensure_ascii=False))
    key='supplier-followup:'+hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:24]
    pending=pending_steps(result)
    record_processing_followup(key,{'supplier':doc.get('supplier') or 'Счёт поставщика',
        'invoices':doc.get('number',''),'company':doc.get('buyer',''),'inn':doc.get('supplier_inn',''),
        'deal_id':str(spec.get('deal_id')),'spec':spec,'result':result},pending,root=root)
    return pending

def summary(results):
    pending=[f"Сделка №{r.get('deal_id')}: "+'; '.join(r.get('pending_steps',[])) for r in results if r.get('pending_steps')]
    if pending:return 'Распределение записано. Осталось выполнить:\n'+'\n'.join(pending)+'\nПовторно применять закупку не нужно.'
    return 'Экономика и реестр закупок обновлены; исходные счета сохранены в карточках.'
