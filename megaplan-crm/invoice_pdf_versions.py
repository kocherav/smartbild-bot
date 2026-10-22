"""Approved PDF corrections for immutable issued CRM invoices.

Never alter invoice money or create another invoice. Refuse stale corrections.
"""
import hashlib,json,os,shutil,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent/'invoice_pdf_versions'

def fingerprint(invoice):
 money=lambda v:{k:(v or {}).get(k) for k in ('value','currency')}
 data={k:invoice.get(k) for k in ('id','number','invoiceDate')}
 data.update(sum=money(invoice.get('sum')),payer=(invoice.get('payer') or {}).get('id'),recipient=(invoice.get('recipient') or {}).get('id'),rows=[{'id':r.get('id'),'name':r.get('name'),'quantity':str(r.get('quantity')),'price':money(r.get('price')),'sum':money(r.get('sum')),'tax':(r.get('tax') or {}).get('id')} for r in invoice.get('rows') or []])
 return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def approved_pdf(invoice):
 ident=str(invoice['id'])
 if not ident.isdigit():raise ValueError('Некорректный идентификатор счёта')
 meta=ROOT/(ident+'.json')
 if not meta.exists():return None
 info=json.loads(meta.read_text())
 if info['invoice_fingerprint']!=fingerprint(invoice):raise ValueError('Счёт изменён после утверждения исправленного PDF. Требуется обновить исправленную версию.')
 name=info['filename']
 if Path(name).name!=name:raise ValueError('Некорректный путь исправленного счёта')
 path=ROOT/name
 if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Исправленный PDF счёта отсутствует или изменён')
 fd,temporary=tempfile.mkstemp(prefix="approved-invoice-",suffix=".pdf");os.close(fd)
 shutil.copyfile(path,temporary)
 return temporary
