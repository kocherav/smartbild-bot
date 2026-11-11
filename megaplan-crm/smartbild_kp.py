"""Automation proposals in the SmartBild template (kp-smartbild/, owner decision 11.11).

The deal snapshot of ``deal_proposal`` (live CRM rows, sections, VAT, total) becomes the
template's deal JSON + calculation CSV; ``build.cjs`` renders the PDF and ``build_docx.cjs``
the Word file. Amounts come only from Megaplan: the CSV is checked to reproduce every line
and the deal total to the kopeck before anything is rendered.

Owner decisions: the template is suggested by the deal's contents (automation equipment),
branding is SmartBild with the owner's contacts, modules are suggested and the owner edits
them in the preview.
"""
import csv
import io
import json
import re
import subprocess
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

KP_DIR = Path(__file__).resolve().parent / 'templates' / 'kp-smartbild'
CENT = Decimal('0.01')
MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
          'сентября', 'октября', 'ноября', 'декабря')
MANAGER = {'name': 'Кочержинский Артем Вадимович', 'role': 'Руководитель проектов',
           'phone': '+7 (495) 846-72-71', 'email': 'info@smartbild.pro', 'site': 'smartbild.pro'}

# Order of pages in the template; labels are what the owner sees on the buttons.
MODULES = (('light', 'Свет и шторы'), ('climate', 'Климат'), ('media', 'Медиа и кино'),
           ('telegram', 'Уведомления'), ('scenes', 'Сценарии'))
MODULE_LABELS = dict(MODULES)
MODULE_KEYS = {label: key for key, label in MODULES}

AUTOMATION_RE = re.compile(
    r'(?i)iridi|ириди|умн\w*\s+дом|автоматизац|\bknx\b|zigbee|z-wave|\bdali\b|modbus|\bbacnet\b|'
    r'контроллер|шлюз|gateway|интерфейс\s+knx|\bdcm\b|сервер\s+(?:умного|автомат)|hs\s*server|'
    r'панел\w*\s+управлен|сенсорн\w*\s+панел|wiren\s*board|loxone|zennio|gira|jung|mdt|'
    r'датчик\s+(?:присутств|движен|протечк)|сценар\w+|визуализац')
MODULE_RULES = {
    'light': re.compile(r'(?i)свет|освещ|диммер|dali|led|лент[аы]|светильн|штор|карниз|жалюз|рольстав'),
    'climate': re.compile(r'(?i)кондиц|daikin|mitsubishi|\bdcm\b|vrv|vrf|пву|вентил|отоплен|термостат|'
                          r'тёпл\w*\s+пол|тепл\w*\s+пол|климат|увлажн|breezart|радиатор|фанкойл'),
    'media': re.compile(r'(?i)медиа|кино|аудио|акусти|проектор|ресивер|sonos|мультирум|телевиз|av-'),
}


AC_ONLY_RE = re.compile(r'(?i)кондиц|daikin|mitsubishi|\bdcm\b|vrv|vrf')
VENT_RE = re.compile(r'(?i)пву|вентил|увлажн|breezart|приточн')


def module_overrides(rows, modules, kp_dir=KP_DIR):
    """Air-conditioning-only deals get the КП-906 «Климат» texts (Daikin/DCM) instead of the
    generic page about ventilation units and Breezart humidifiers."""
    text = ' '.join(str(r.get('name') or '') for r in rows)
    if 'climate' not in modules or not AC_ONLY_RE.search(text) or VENT_RE.search(text):
        return {}
    sample = json.loads((Path(kp_dir) / 'deals' / 'КП-906' / 'КП-906.json').read_text(encoding='utf-8'))
    climate = (sample.get('overrides') or {}).get('climate')
    return {'climate': climate} if climate else {}


def is_automation(rows):
    """An automation proposal: the deal contains automation equipment or works."""
    return any(AUTOMATION_RE.search(str(r.get('name') or '')) for r in rows)


def suggest_modules(rows):
    text = ' '.join(str(r.get('name') or '') for r in rows)
    chosen = [key for key in ('light', 'climate', 'media') if MODULE_RULES[key].search(text)]
    # Notifications and scenarios are part of every automation project (КП-906).
    return [key for key, _ in MODULES if key in chosen or key in ('telegram', 'scenes')]


def ordered(modules):
    wanted = set(modules or [])
    return [key for key, _ in MODULES if key in wanted]


def single_vat(rows):
    """The template prints one «В том числе НДС N %» line. Mixed rates cannot be shown
    truthfully, so the classic proposal is used for such deals."""
    rates = {str(r.get('tax_rate')) for r in rows}
    if rates == {'-1'}:
        return None, None
    if len(rates) != 1 or '-1' in rates:
        return None, 'В сделке позиции с разными ставками НДС — шаблон SmartBild показывает одну ставку'
    rate = Decimal(rates.pop())
    return (int(rate) if rate == rate.to_integral() else float(rate)), None


def _dec(value):
    return Decimal(str(value))


def _price_line(row):
    """(qty, price, name) whose qty·price reproduces the CRM line total exactly."""
    qty, total = _dec(row['qty']), _dec(row['total'])
    price = (total / qty).quantize(CENT, rounding=ROUND_HALF_UP) if qty else total
    if qty > 0 and (price * qty).quantize(CENT, rounding=ROUND_HALF_UP) == total:
        return qty, price, str(row['name'])
    # The unit price is not a whole number of kopecks: show the line as one set so the
    # sum stays exactly the CRM amount, and keep the quantity in the name.
    qty_text = format(qty.normalize(), 'f').replace('.', ',')
    return Decimal(1), total, f"{row['name']} ({qty_text} {row.get('unit') or 'шт.'})"


def ru_date(moment):
    return f'{moment.day} {MONTHS[moment.month - 1]} {moment.year}'


def build_inputs(data, modules, recipient, moment, kp_dir=KP_DIR):
    """Return (deal_json, csv_text) for the template. Raises ValueError on any mismatch."""
    vat, problem = single_vat(data['rows'])
    if problem:
        raise ValueError(problem)
    out = io.StringIO()
    writer = csv.writer(out, delimiter=';', lineterminator='\n')
    writer.writerow(['Раздел', 'Наименование', 'Ед.', 'Кол-во', 'Цена'])
    total = Decimal('0')
    for row in data['rows']:
        qty, price, name = _price_line(row)
        total += (qty * price).quantize(CENT, rounding=ROUND_HALF_UP)
        writer.writerow([row.get('section') or 'Оборудование и материалы', name.replace(';', ','),
                         row.get('unit') or 'шт.', format(qty.normalize(), 'f'), format(price, 'f')])
    if total != _dec(data['total']):
        raise ValueError('Суммы позиций КП не совпадают с итогом сделки. КП не сформировано')
    client = str(data['client'])
    recipient = ' '.join(str(recipient or '').split())
    subject = ' '.join(re.sub(r'<[^>]+>', ' ', str(data.get('subject') or '')).split())[:200]
    deal = {'number': f"КП-{data['deal_id']}", 'date': ru_date(moment),
            'client': f'{recipient} · {client}' if recipient and recipient not in client else client,
            'object': subject or 'Система автоматизации', 'modules': ordered(modules),
            'table': 'table.csv', 'warranty': 'по договору', 'out': f"deal-{data['deal_id']}",
            'manager': dict(MANAGER)}
    if vat is not None:
        deal['vat'] = vat
    overrides = module_overrides(data['rows'], deal['modules'], kp_dir)
    if overrides:
        deal['overrides'] = overrides
    return deal, out.getvalue()


def render(data, modules, recipient, moment, folder, runner=subprocess.run, kp_dir=KP_DIR):
    """Render PDF and Word into ``folder``; returns their paths."""
    deal, table = build_inputs(data, modules, recipient, moment, kp_dir)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'table.csv').write_text(table, encoding='utf-8')
    deal_path = folder / 'deal.json'
    deal_path.write_text(json.dumps(deal, ensure_ascii=False, indent=2), encoding='utf-8')
    for script in ('build.cjs', 'build_docx.cjs'):
        result = runner(['node', str(Path(kp_dir) / script), str(deal_path)], cwd=str(kp_dir),
                        capture_output=True, text=True, timeout=240)
        if result.returncode != 0:
            tail = ' / '.join((result.stderr or result.stdout or '').strip().splitlines()[-3:])
            raise ValueError(f'Шаблон SmartBild не собрал КП ({script}): {tail[:300]}')
    pdf, docx = folder / f"КП_{deal['out']}.pdf", folder / f"КП_{deal['out']}.docx"
    if not pdf.is_file() or not docx.is_file():
        raise ValueError('Шаблон SmartBild не создал PDF или Word')
    from pypdf import PdfReader
    text = ' '.join((page.extract_text() or '') for page in PdfReader(str(pdf)).pages)
    text = text.replace('\xa0', ' ').replace('\u202f', ' ')
    expected = f"{_dec(data['total']):,.2f}".replace(',', ' ').replace('.', ',')
    if expected not in text:
        raise ValueError('Не пройдена проверка итоговой суммы в готовом PDF шаблона SmartBild')
    return pdf, docx
