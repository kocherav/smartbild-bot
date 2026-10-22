import sys,json,copy,html
from pathlib import Path
sys.path[:0]=['/home/kocher.av/telegram-bridge','/home/kocher.av/megaplan-crm']
import closing_runtime as c
from closing_documents import generate_act
from pypdf import PdfReader
from weasyprint import HTML
P=Path('/home/kocher.av/telegram-bridge/docs/architecture/act861-date-20260930');P.mkdir(exist_ok=True)
old=Path('/home/kocher.av/telegram-bridge/docs/architecture/act861-correction-20261014')
j=c.registry().get('4825945d11e728c8');(P/'job-before.json').write_text(json.dumps(j,ensure_ascii=False))
p=json.loads((old/'prepared.json').read_text()); data=copy.deepcopy(p['data']);assert data['act_date']=='13.10.2026';data['act_date']='30.09.2026'
assert all(r['kind']!='work' for r in data['positions'])
path=Path(generate_act(data,P,test=False));dest=P/'Акт 861-АПП-01 от 30.09.2026.pdf';path.rename(dest)
text='\n'.join(page.extract_text() for page in PdfReader(dest).pages)
assert '13.10.2026' not in text and 'Дата составления: 30.09.2026' in text
assert '861-АПП/01 от 30.09.2026' in text and '4 799 480,20' in text
assert '02 / Выполненные работы и оказанные услуги' not in text
note='ИСПРАВЛЕННАЯ ДАТА АКТА №861-АПП/01: 30.09.2026.\nПо указанию руководителя дата акта исправлена на 30.09.2026 на первом листе и в приложении. Заменяет ранее отправленные версии акта и подсказки. Состав, сумма 4 799 480,20 ₽, дата передачи и финансовая операция №3248 не меняются. Повторную реализацию не создавать. Если прежний акт уже направлен в ЭДО, сообщите руководителю для согласования исправления.\n\n'+p['note'].split('\n\n',1)[1]
assert '13.10.2026' not in note
hint=P/'Подсказка бухгалтеру — акт от 30.09.2026.pdf'
HTML(string='<meta charset="utf-8"><style>@page{size:A4;margin:16mm}body{font:10pt Arial}p{white-space:pre-wrap;overflow-wrap:anywhere}</style><p>'+html.escape(note)+'</p>').write_pdf(hint)
(P/'prepared.json').write_text(json.dumps({'documents':[str(dest),str(hint)],'data':data,'note':note},ensure_ascii=False,indent=2))
(P/'verification.json').write_text(json.dumps({'act_date':data['act_date'],'pages':len(PdfReader(dest).pages),'old_date_absent':True,'total':data['total'],'positions_unchanged':data['positions']==p['data']['positions']},ensure_ascii=False))
s=(old/'deliver.py').read_text().replace('Исправленная группировка акта 861-АПП/01:','Исправленная дата акта 861-АПП/01 — 30.09.2026:').replace('goods/service classification correction','act date correction to 30.09.2026').replace("documents=prepared['documents'],note=prepared['note'],document_revision=", "documents=prepared['documents'],note=prepared['note'],data=prepared['data'],document_revision=").replace('ИСПРАВЛЕННЫЙ АКТ №861-АПП/01 — только товары, сумма без изменений','ИСПРАВЛЕННЫЙ АКТ №861-АПП/01 ОТ 30.09.2026').replace('act861-classification-correction-20261014','act861-date-correction-20260930-v1').replace('Пять позиций на 56 970 ₽ перенесены из работ в товары.','Дата акта и ссылка на акт в приложении исправлены на 30.09.2026. Все позиции — товары.')
(P/'deliver.py').write_text(s)
print((P/'verification.json').read_text())
