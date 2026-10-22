"""Conservative extraction of actual installer report text; no pilot data lookup."""
import re
import subprocess
import tempfile
import time
import zipfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree

MONEY = r'(?:\d{1,3}(?:[. \u00a0]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)'
AMOUNT = re.compile(r'(?:[-–—=:]\s*|по\s+таблице\s+|^итого\s*:?[ ]*)('+MONEY+r')(?![\d.,])(?:\s*(?:₽|руб\.?|р\.?))?(?=\s*(?:$|\())',re.I)
START = re.compile(r'^(?:сделка\s*№?\s*\d|доп\s*работ|монтаж|демонтаж|перекладка|материал|итого|зп\b|страховка|минус|аванс|премия|по таблице)',re.I)
WORK_START = re.compile(r'^(?:монтаж|демонтаж|переклад|передел|такелаж|работ|доп\b|ремонт|замен|запуск|диагност|достав|штроб|отверст|кабел|труб|воздуховод|фасон|теплоизоляц)',re.I)
DEAL = re.compile(r'^сделка\s*№?\s*(\d+)\b',re.I)


def money(value):
    value=value.replace('\xa0','').replace(' ','')
    if re.fullmatch(r'\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?',value):
        value=value.replace('.','')
    return float(Decimal(value.replace(',','.')))


def amount_of(text):
    hits=list(AMOUNT.finditer(re.sub(r'(?<=\d)[ \u00a0]+(?=\d)', '', text)))
    return money(hits[-1][1]) if hits else None


def logical_lines(text):
    """Join PDF visual wraps, keeping new work rows and unknown text visible."""
    result=[]; pending=''
    for raw in text.replace('\r','').splitlines():
        line=re.sub(r'\s+',' ',raw).strip()
        if not line:continue
        if pending:
            # Open parenthetical descriptions can wrap in the middle of a word.
            open_paren=pending.count('(')>pending.count(')')
            continuation=open_paren or (amount_of(pending) is None and not START.match(line) and not WORK_START.match(line)
                and (bool(START.match(pending)) or line[:1].islower()))
            if continuation:
                pending+=' '+line
            else:
                result.append(pending);pending=line
        else:pending=line
        if amount_of(pending) is not None and pending.count('(')<=pending.count(')'):
            result.append(pending);pending=''
    if pending:result.append(pending)
    return result


def parse_rows(text):
    rows=[];current='Объект не указан';totals=[]
    for source in logical_lines(text):
        lower=source.casefold().replace('ё','е')
        amount=amount_of(source);qty=rate=unit=None;sign=1
        explicit=DEAL.match(source)
        if explicit:current='Сделка №'+explicit[1]
        obj=current
        if lower.startswith('итого'):
            kind='Итог из PDF';sign=0;obj='Контроль отчёта';totals.append(len(rows))
        elif re.match(r'^(?:зп\b|зарплата|страховка|минус|удержан|аванс|получено)',lower):
            kind='Аванс' if re.match(r'^(?:аванс|получено)',lower) else 'Удержание'
            sign=-1;obj='Взаиморасчёты'
        elif 'премия' in lower:
            kind='Премия';obj='Взаиморасчёты'
        elif re.search(r'по\s+таблице',lower):kind='Работа по таблице'
        elif re.match(r'^материал',lower):kind='Материал'
        elif (amount is None and not START.match(source) and not WORK_START.match(source) and len(source.split())<=3
              and not re.search(r'[\d?=]',source)) or (explicit and source[explicit.end():].strip()==''):
            current='Сделка №'+explicit[1] if explicit else source
            obj=current;kind='Заголовок';sign=0
        else:
            kind='Работа'
            # An explicit site name ends inheritance from the previous numbered deal.
            site=re.search(r'\s(?:в|на)\s+([^\d()]+?)(?:\s*[-–—]\s*\d)',source,re.I)
            if site and not re.match(r'^(?:потолке|санузле|стене|полу|объекте)\b',site[1],re.I):
                current=site[1].strip();obj=current
            formula=re.search(r'(\d+(?:[.,]\d+)?)\s*(м|шт\.?)?\s*[xх×]\s*('+MONEY+r')\s*(?:р\.?|руб\.?|₽)?\s*=',source,re.I)
            if formula:
                qty=money(formula[1]);unit=formula[2];rate=money(formula[3])
            else:
                quantity=re.search(r'(\d+(?:[.,]\d+)?)\s*(шт|м)\b',source,re.I)
                if quantity:qty=money(quantity[1]);unit=quantity[2]
        rows.append([obj,source,kind,qty,unit,rate,amount,sign])
    for index in totals[:-1]:rows[index][2]='Итог начислений из PDF'
    if not any(r[7] for r in rows):
        raise ValueError('в документе не найдены строки работ или расчётов; исходный файл сохранён')
    return rows


def docx_text(path):
    with zipfile.ZipFile(path) as archive:
        info=archive.getinfo('word/document.xml')
        if info.file_size>8_000_000:raise ValueError('слишком большой текст Word')
        root=ElementTree.fromstring(archive.read(info))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    text='\n'.join(''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in root.findall('.//w:p',ns))
    if not text.strip():raise ValueError('в Word нет текстовых строк; исходный файл сохранён')
    return text


def ocr_page(path,page):
    with tempfile.TemporaryDirectory(prefix='installer-ocr-') as directory:
        prefix=str(Path(directory)/'page')
        raster=subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-scale-to','2400','-png',str(path),prefix],capture_output=True,timeout=20)
        if raster.returncode:raise ValueError(f'не удалось прочитать страницу {page} PDF')
        result=subprocess.run(['tesseract',prefix+'.png','stdout','-l','rus+eng','--psm','6'],capture_output=True,text=True,timeout=20)
        if result.returncode:raise ValueError(f'не удалось распознать страницу {page} PDF')
        return result.stdout


def extract_pdf(path):
    # Per-page extraction prevents losing a scan attached to a text PDF.
    from pypdf import PdfReader
    reader=PdfReader(path)
    if len(reader.pages)>12:raise ValueError('в сборном отчёте больше 12 страниц; нужен отдельный разбор')
    parts=[];scanned=[]
    deadline=time.monotonic()+120
    native=subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,text=True,timeout=25)
    native_pages=native.stdout.split('\f') if not native.returncode else []
    for index,page in enumerate(reader.pages,1):
        if '/Contents' not in page:
            continue
        if time.monotonic()>deadline:raise ValueError('распознавание PDF не завершилось вовремя; исходный файл сохранён')
        text=native_pages[index-1] if index<=len(native_pages) else (page.extract_text() or '')
        if not text.strip():
            text=ocr_page(path,index);scanned.append(index)
        parts.append(text)
    if not any(x.strip() for x in parts):raise ValueError('в PDF не удалось прочитать строки; исходный файл сохранён')
    return '\n'.join(parts),scanned
