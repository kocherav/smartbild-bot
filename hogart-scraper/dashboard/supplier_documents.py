import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'megaplan-crm'))
from procurement_projection import effective_registry
"""Authenticated read-only invoice rendering. Paths are resolved solely from the registry."""
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOTS = (Path('/home/kocher.av/hogart-scraper/incoming'), Path('/home/kocher.av/megaplan-crm'),Path('/home/kocher.av/hogart-scraper/finance'))


def resolve(registry, deal, invoice_id, row):
    if any(not isinstance(value, str) or not value.strip() for value in (deal, invoice_id, row)):
        raise ValueError('Не указана сделка, счёт или позиция')
    registry=effective_registry(registry)
    matches = [i for i in registry.get('invoices', []) if str(i.get('id')) == str(invoice_id)]
    if len(matches) != 1: raise ValueError('Счёт не найден')
    invoice = matches[0]
    lines = [line for a in invoice.get('allocations', []) if str(a.get('deal_id')) == str(deal)
             for line in (a.get('source_lines') or a.get('updates') or []) if str(line.get('offer_row_id')) == str(row)]
    if deal=='_document' and row=='_document':lines=[{'source_name':l['name'],'source_sku':l.get('sku','')} for l in invoice.get('lines',[])] or [{'source_name':'Счёт целиком'}]
    if deal=='_document' and row.startswith('stock:'):
        stock=next((s for s in registry.get('unallocated_stock',[]) if s['id']==row[6:] and s['document_key']==invoice['document_key']),None)
        if stock:lines=[{'source_name':stock['name'],'source_sku':stock.get('sku','')}]
    if not lines: raise ValueError('Счёт не связан с этой позицией сделки')
    path = Path(invoice.get('source_path') or '').resolve()
    if not any(path.is_relative_to(root.resolve()) for root in ROOTS): raise ValueError('Файл счёта недоступен')
    if not path.is_file(): raise ValueError('Файл счёта не найден в архиве')
    if path.suffix.lower() not in ('.pdf','.xls','.xlsx','.docx'): raise ValueError('Формат файла не поддерживается')
    if path.stat().st_size > 40*1024*1024: raise ValueError('Файл слишком велик для встроенного просмотра')
    with path.open('rb') as stream:
        if path.suffix.lower()=='.pdf' and not stream.read(5).startswith(b'%PDF-'): raise ValueError('Файл не является PDF')
    return invoice, path, lines


def parse_bbox(xml):
    root = ET.fromstring(xml)
    pages = []
    for page in root.iter():
        if page.tag.split('}')[-1] != 'page': continue
        words = []
        for word in page.iter():
            if word.tag.split('}')[-1] == 'word':
                a = word.attrib
                words.append({'text':word.text or '', 'x':float(a['xMin']), 'y':float(a['yMin']),
                              'w':float(a['xMax'])-float(a['xMin']), 'h':float(a['yMax'])-float(a['yMin'])})
        pages.append({'width':float(page.attrib['width']), 'height':float(page.attrib['height']), 'words':words})
    if not pages or len(pages) > 100: raise ValueError('Число страниц не поддерживается')
    return pages


def compact(text):
    return ''.join(c for c in str(text).casefold().replace('ё','е') if c.isalnum())


def locate(pages, lines):
    """Highlight only unique complete name/SKU matches; never guess a similar model."""
    result = {}
    for line in lines:
        for term in [line.get('source_name'), line.get('source_sku')]:
            needle = compact(term or '')
            if len(needle) < 5: continue
            hits = []
            for page_no, page in enumerate(pages):
                pieces = [compact(w['text']) for w in page['words']]
                text = ''.join(pieces);start = 0;spans=[]
                for i,piece in enumerate(pieces):
                    spans.append((start,start+len(piece),i));start+=len(piece)
                for match in re.finditer(re.escape(needle), text):
                    selected=[i for a,b,i in spans if a < match.end() and b > match.start()]
                    # Do not match C10 inside C100 or a partial article number.
                    if selected and spans[selected[0]][0]==match.start() and spans[selected[-1]][1]==match.end():
                        hits.append((page_no,[page['words'][i] for i in selected]))
            if len(hits) == 1:
                page_no, boxes = hits[0];result.setdefault(page_no,[]).extend(boxes);break
    return result


def describe(path, lines):
    output = subprocess.run(['/usr/bin/pdftotext','-bbox-layout',str(path),'-'],capture_output=True,check=True,timeout=20)
    pages = parse_bbox(output.stdout);hits=locate(pages,lines)
    return {'pages':[{'width':p['width'],'height':p['height'],'highlights':hits.get(i,[])} for i,p in enumerate(pages)],
            'first_page':min(hits)+1 if hits else 1,'highlighted':bool(hits),
            'targets':list(dict.fromkeys(str(x.get('source_name') or '') for x in lines))}


def render(path, page):
    if page < 1 or page > 100: raise ValueError('Некорректная страница')
    with tempfile.TemporaryDirectory(prefix='invoice-view-') as directory:
        output=Path(directory)/'page'
        subprocess.run(['/usr/bin/pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-scale-to','1800','-png',str(path),str(output)],capture_output=True,check=True,timeout=25)
        return output.with_suffix('.png').read_bytes()
