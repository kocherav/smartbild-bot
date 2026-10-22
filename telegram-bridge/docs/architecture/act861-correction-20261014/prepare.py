import sys,json,copy,html
from pathlib import Path
from decimal import Decimal
sys.path[:0]=['/home/kocher.av/telegram-bridge','/home/kocher.av/megaplan-crm','/home/kocher.av/hogart-scraper/dashboard']
import closing_runtime as c
from position_types import classify_position
from closing_documents import generate_act
from weasyprint import HTML
from pypdf import PdfReader
P=Path(__file__).parent;j=c.registry().get('4825945d11e728c8');(P/'job-before.json').write_text(json.dumps(j,ensure_ascii=False))
data=copy.deepcopy(j['data']);crm=c.api();deal=crm._call('GET','/deal/861')['data'];kinds={str(r['id']):classify_position(r) for r in deal['positions']}
changes=[]
for r in data['positions']:
 kind=kinds[str(r.get('source_id') or r['id'])]
 if r['kind']!=kind:changes.append(r['id'])
 r['kind']=kind
assert len(changes)==5 and all(r['kind']!='work' for r in data['positions'])
assert sum(Decimal(str(r['total'])) for r in data['positions'])==Decimal('4799480.20')
path=Path(generate_act(data,P,test=False));dest=P/'Акт 861-АПП-01 — исправленная группировка.pdf';path.rename(dest)
text='\n'.join(x.extract_text() for x in PdfReader(dest).pages);assert '02 / Выполненные работы и оказанные услуги' not in text and 'ТЕСТ' not in text
note=j['note'];old='Товары: 4 742 510,20 ₽. Работы: 56 970,00 ₽.';assert old in note
note=note.replace(old,'Товары: 4 799 480,20 ₽. Работы: 0,00 ₽.')
preface='ИСПРАВЛЕННАЯ ГРУППИРОВКА ПОЗИЦИЙ АКТА №861-АПП/01 от 13.10.2026.\nЗаменяет ранее отправленный PDF этого акта и подсказку бухгалтеру. Пять товарных позиций на 56 970,00 ₽ перенесены из работ в товары. Состав, количества, цены, сумма 4 799 480,20 ₽ и дата передачи 30.09.2026 не изменены. Это не новая отгрузка: операцию №3248 и реализацию повторно не создавать. Если прежний акт уже отправлен в ЭДО, сообщите руководителю для согласования исправления.\n\n'
note=preface+note;(P/'Подсказка бухгалтеру.txt').write_text(note)
hint=P/'Подсказка бухгалтеру — исправленная.pdf';HTML(string='<meta charset="utf-8"><style>@page{size:A4;margin:16mm}body{font:10pt Arial}p{white-space:pre-wrap;overflow-wrap:anywhere}</style><p>'+html.escape(note)+'</p>').write_pdf(hint)
(P/'prepared.json').write_text(json.dumps({'documents':[str(dest),str(hint)],'note':note,'data':data,'changed_rows':changes},ensure_ascii=False,indent=2));print({'prepared':True,'changed':changes,'total':data['total']})
