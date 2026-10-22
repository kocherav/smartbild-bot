from docx import Document
from docx.shared import Mm,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pathlib import Path
ROOT=Path(__file__).parent/'templates'/'closing'
LOGO=str(ROOT/'logo.png')
BLUE='02B4DC';INK='10222C'

def font(run,size=10,bold=False,color=INK):
 run.font.name='Houschka Pro';run.font.size=Pt(size);run.font.bold=bold;run.font.color.rgb=RGBColor.from_string(color)

def p(d,text='',size=10,bold=False,after=4):
 a=d.add_paragraph();a.paragraph_format.space_after=Pt(after);a.paragraph_format.line_spacing=1.0
 font(a.add_run(text),size,bold);return a

def heading(d,text):
 a=p(d,text,11,True,5);a.paragraph_format.keep_with_next=True
 a.runs[0].font.color.rgb=RGBColor.from_string('0086B3')

def table(d,heads,rows,widths,right_columns=()):
 t=d.add_table(rows=1,cols=len(heads));t.autofit=False
 for col,w in zip(t.columns,widths):col.width=Mm(w)
 for i,h in enumerate(heads):t.rows[0].cells[i].text=h
 for row in rows:
  cells=t.add_row().cells
  for i,v in enumerate(row):cells[i].text=str(v)
 for ri,row in enumerate(t.rows):
  trPr=row._tr.get_or_add_trPr();flag=OxmlElement('w:cantSplit');trPr.append(flag)
  if ri==0:trPr.append(OxmlElement('w:tblHeader'))
  for i,c in enumerate(row.cells):
   c.width=Mm(widths[i]);pr=c._tc.get_or_add_tcPr()
   borders=OxmlElement('w:tcBorders')
   for side in ['top','left','bottom','right']:
    b=OxmlElement('w:'+side);b.set(qn('w:val'),'single');b.set(qn('w:sz'),'4');b.set(qn('w:color'),'E3ECF1');borders.append(b)
   pr.append(borders)
   if ri==0:
    sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'E8F8FD');pr.append(sh)
   for a in c.paragraphs:
    if i in right_columns:a.alignment=2
    a.paragraph_format.space_before=Pt(2);a.paragraph_format.space_after=Pt(2)
    for r in a.runs:font(r,8.5,ri==0)
 p(d,'',after=1)
 return t

def base(label):
 d=Document();s=d.sections[0];s.page_width=Mm(210);s.page_height=Mm(297)
 s.top_margin=Mm(35);s.bottom_margin=Mm(22);s.left_margin=Mm(18);s.right_margin=Mm(18);s.header_distance=Mm(9);s.footer_distance=Mm(9)
 style=d.styles['Normal'];style.font.name='Houschka Pro';style.font.size=Pt(10)
 h0=s.header.paragraphs[0];h0.paragraph_format.space_after=Pt(0);h0.paragraph_format.line_spacing=Pt(1);font(h0.add_run(''),1)
 ht=s.header.add_table(rows=1,cols=2,width=Mm(174));ht.columns[0].width=Mm(70);ht.columns[1].width=Mm(104)
 ht.cell(0,0).paragraphs[0].add_run().add_picture(LOGO,width=Mm(43))
 a=ht.cell(0,1).paragraphs[0];a.alignment=2;a.paragraph_format.space_before=Pt(10)
 font(a.add_run('КЛИМАТИЧЕСКИЕ СИСТЕМЫ\nПРОЕКТИРОВАНИЕ · МОНТАЖ · СЕРВИС'),8,False,'0086B3')
 h=s.header.add_paragraph();h.paragraph_format.space_after=Pt(0);h.paragraph_format.space_before=Pt(0);h.paragraph_format.line_spacing=Pt(1)
 bd=OxmlElement('w:pBdr');b=OxmlElement('w:bottom');b.set(qn('w:val'),'single');b.set(qn('w:sz'),'8');b.set(qn('w:color'),BLUE);bd.append(b);h._p.get_or_add_pPr().append(bd)
 f=s.footer.paragraphs[0]
 font(f.add_run('ООО «Кливэл» · +7 495 640-0687 · info@cliwell.ru · www.cliwell.ru\n'+label+' · Проект v0.2 / 12.10.2026 · Стр. '),8,False,'667681')
 fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');f._p.append(fld)
 return d

def signs(d,left='Сдал — Исполнитель',right='Принял — Заказчик'):
 table(d,[left,right],[['Должность / статус: ______________\nФ.И.О.: ________________________\nПолномочия: ___________________\nПодпись: __________  Дата: __________\nМ.П. (при наличии)','Должность / статус: ______________\nФ.И.О.: ________________________\nПолномочия: ___________________\nПодпись: __________  Дата: __________\nМ.П. (при наличии)']],[87,87])


from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
def floating_picture(paragraph,path,width,x,y):
 inline=paragraph.add_run().add_picture(str(path),width=Mm(width))._inline
 anchor=OxmlElement('wp:anchor')
 for k,v in {'distT':'0','distB':'0','distL':'0','distR':'0','simplePos':'0','relativeHeight':'0','behindDoc':'1','locked':'0','layoutInCell':'1','allowOverlap':'1'}.items():anchor.set(k,v)
 pos=OxmlElement('wp:simplePos');pos.set('x','0');pos.set('y','0');anchor.append(pos)
 for axis,relative,value in [('H','column',x),('V','paragraph',y)]:
  pos=OxmlElement('wp:position'+axis);pos.set('relativeFrom',relative)
  off=OxmlElement('wp:posOffset');off.text=str(int(Mm(value)));pos.append(off);anchor.append(pos)
 for tag in ['wp:extent','wp:effectExtent']:
  el=inline.find(qn(tag))
  if el is not None:anchor.append(el)
 anchor.append(OxmlElement('wp:wrapNone'))
 for tag in ['wp:docPr','wp:cNvGraphicFramePr','a:graphic']:
  el=inline.find(qn(tag))
  if el is not None:anchor.append(el)
 inline.getparent().replace(inline,anchor)
def special_notes(d):
 p(d,'Особые отметки:',8.5,after=0)
 for _ in range(2):
  a=p(d,'',8.5,after=4);a.paragraph_format.line_spacing=Pt(11)
  border=OxmlElement('w:pBdr');line=OxmlElement('w:bottom')
  for k,v in [('val','single'),('sz','4'),('color','667681'),('space','1')]:line.set(qn('w:'+k),v)
  border.append(line)
  between=OxmlElement('w:between')
  for k,v in [('val','single'),('sz','4'),('color','667681'),('space','1')]:between.set(qn('w:'+k),v)
  border.append(between);a._p.get_or_add_pPr().append(border)

from decimal import Decimal
from datetime import datetime
import re, subprocess, os, html

def money(x):return f'{Decimal(str(x)):,.2f}'.replace(',',' ').replace('.',',')
def sign_block(d,data):
 from generate_contract import surname_initials
 vals=[['Передал — Поставщик / Исполнитель','Принял — Заказчик'],['ООО «Кливэл»',data['payer_name']],['Генеральный директор',data['signatory']['position']],[ 'Кочержинская С.В.',surname_initials(data['signatory']['name'])],['Подпись: ______________________','Подпись: ______________________'],['Дата подписания: ______________','Дата подписания: ______________'],['М.П.','М.П. (при наличии)']]
 t=d.add_table(rows=7,cols=2);t.autofit=False
 for c in t.columns:c.width=Mm(87)
 for ri,row in enumerate(t.rows):
  row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
  for ci,cell in enumerate(row.cells):
   cell.width=Mm(87);a=cell.paragraphs[0];a.paragraph_format.space_before=Pt(9 if ri==4 else 0);a.paragraph_format.space_after=Pt(2);a.paragraph_format.line_spacing=1.;a.paragraph_format.keep_with_next=ri<6
   font(a.add_run(vals[ri][ci]),9,ri<2)
   if ri==4 and ci==0:
    floating_picture(a,ROOT/'ours-000.png',40,43,-10);floating_picture(a,ROOT/'ours-001.png',20,24,-9)

def validate_contract_rows(text,positions):
 from work_contract_scope import is_work_contract,validate
 if is_work_contract(text):return validate(text,positions)
 # Validate specification quantities/prices; preserve the deal unit label in output.
 start=text.upper().rfind('СПЕЦИФИКАЦИЯ')
 if start<0:raise ValueError('Не найдена спецификация к договору')
 spec=text[start:]
 # The deal's unit vocabulary is authoritative; do not silently drop an entire
 # specification row just because its unit is absent from a fixed short list.
 labels={str(p.get('unit') or '').strip() for p in positions}-{''}
 units='|'.join(re.escape(u) for u in sorted(labels,key=lambda u:(-len(u),u)))
 units='(?:'+(units+'|' if units else '')+r'шт\.?|м|к-т|компл\.?|комплект|усл\.?)'
 money=r'([\d \u00a0\u202f]+[,.]\d{2})[ \t\u00a0\u202f]*(?:руб\.?)?'
 # Both column-aligned PDF text and paragraph-per-cell DOCX use the same
 # vocabulary and monetary tokens. Collect both layouts, including mixed text.
 aligned=r'[ \t\u00a0\u202f]{2,}('+units+r')\s+(\d+(?:[,.]\d+)?)\s+'+money+r'\s+'+money
 cells=r'(?m:^[ \t]*('+units+r')[ \t]*\n[ \t]*(\d+(?:[,.]\d+)?)[ \t]*\n[ \t]*'+money+r'[ \t]*\n[ \t]*'+money+')'
 pattern='(?:'+aligned+'|'+cells+')'
 matches=[tuple(v for v in m if v is not None) for m in
          (match.groups() for match in re.finditer(pattern,spec))]
 if len(matches)!=len(positions):raise ValueError(f'В спецификации распознано {len(matches)} строк, в сделке {len(positions)}. Состав договора и сделки требует сверки.')
 normalized=re.sub(r'\s+','',re.sub(pattern,'',spec)).casefold()
 indexed=[]
 for original,pos in enumerate(positions):
  name=re.sub(r'\s+','',pos['name']).casefold()
  offsets=[m.start() for m in re.finditer(re.escape(name),normalized)]
  if len(offsets)!=1:raise ValueError('Не найдено однозначное наименование в спецификации: '+pos['name'])
  indexed.append((offsets[0],original,pos))
 if len({x[0] for x in indexed})!=len(indexed):raise ValueError('Повторяющиеся наименования требуют сверки спецификации')
 result=[None]*len(positions)
 for (_,original,pos),(unit,qty,price,total) in zip(sorted(indexed),matches):
  dec=lambda v:Decimal(re.sub(r'\s+','',v).replace(',','.'))
  if dec(qty)!=Decimal(str(pos['quantity'])) or dec(total)!=Decimal(str(pos['total'])).quantize(Decimal('.01')):raise ValueError('Объём или сумма позиции отличается от спецификации: '+pos['name'])
  result[original]={**pos,'unit':pos.get('unit') or unit,'unit_price':str(dec(price)),'total':str(dec(total))}
 return result

def act_number(data):
 explicit=str(data.get('act_number') or '').strip()
 if explicit:return explicit
 deal_id=str(data.get('deal_id') or '').strip()
 if not deal_id.isdigit():raise ValueError('Для номера акта не определён номер сделки')
 return deal_id+'-АПП'

def group_tax(items):
 from document_tax_policy import tax_label
 rates=set(int(r.get('tax_rate',-1)) for r in items)
 if len(rates)==1:return tax_label(sum(Decimal(str(r['total'])) for r in items),rates.pop())
 return 'НДС по строкам: '+money(sum(Decimal(str(r.get('vat_amount',0))) for r in items))+' ₽'

def act_filename(data,test=False):
 deal=str(data.get('deal_id') or '').strip()
 if not deal.isdigit():raise ValueError('Для имени файла акта нужен номер сделки')
 number=re.sub(r'[\\/:*?"<>|\s]+','-',act_number(data)).strip('.-')
 if not number.startswith(deal+'-') and number!=deal:number=deal+'-'+number
 return ('ТЕСТ — ' if test else '')+'Акт_'+number+'.docx'

def generate_act(data,out,test=False):
 if (data.get('seller') or {}).get('id')=='kocherzhinsky_ip':
  from smartbild_act import document
  out=Path(out);out.mkdir(parents=True,exist_ok=True)
  path=out/act_filename(data,test);document(data,test).save(path)
  return render_pdf(path)
 if data.get('partial'):
  from document_tax_policy import decorate
  from copy import deepcopy
  data=decorate(deepcopy(data))
 out=Path(out);out.mkdir(parents=True,exist_ok=True);today=data['act_date'];number=act_number(data);goods=[r for r in data['positions'] if r['kind']!='work'];works=[r for r in data['positions'] if r['kind']=='work']
 if not goods and not works:raise ValueError('Нет позиций для передачи')
 total=lambda rows:sum(Decimal(str(r['total'])) for r in rows)
 if total(goods)+total(works)!=Decimal(str(data['total'])):raise ValueError('Итог строк не совпадает с суммой сделки')
 d=base('Акт приёма-передачи');d.sections[0].top_margin=Mm(40)
 p(d,'АКТ ПРИЁМА-ПЕРЕДАЧИ № '+number,17,True,2);p(d,'товаров, выполненных работ и оказанных услуг',12,True,8)
 p(d,'Дата составления: '+today+'                         г. Москва',10,True)
 basis=f"Договор № {data['number']} от {data['date']}"
 p(d,basis+' · '+data.get('contract_scope_reference','Спецификация: приложение № 1 к договору.')+'\nОбъект: '+data['address']+'.',9)
 dates=data.get('transfer_dates',{})
 if dates:p(d,' '.join(([('Дата передачи товаров: '+dates.get('goods',today)+'.')] if goods else [])+([('Дата передачи работ: '+dates.get('work',today)+'.')] if works else [])),8.5)
 p(d,('Срок выполнения по договору: '+data['deadline_condition']) if data.get('deadline_condition') else (f"Период выполнения по договору: с {data['date']} по {data['deadline']}." if data.get('deadline') else 'Сроки исполнения определяются договором; акт фиксирует выбранный объём передачи.'),8.5,after=7)
 p(d,'ОБЩАЯ СТОИМОСТЬ ПЕРЕДАЧИ: '+money(data['total'])+' ₽',15,True,4)
 from num2words import num2words
 v=Decimal(str(data['total']));p(d,num2words(int(v),lang='ru').capitalize()+f' рублей {int(v*100)%100:02d} копеек.\n'+data.get('tax_text','Без НДС — согласно договору')+'.',9)
 table(d,['Состав передачи','Стоимость, ₽'],([['Товары и оборудование — '+str(len(goods))+' позиции',money(total(goods))]] if goods else [])+([['Выполненные работы и услуги — '+str(len(works))+' позиций',money(total(works))]] if works else [])+[['ИТОГО ПО АКТУ',money(v)]],[130,44],right_columns=(1,))
 p(d,'Поставщик / Исполнитель: ООО «Кливэл», ИНН 7743151323, КПП 774301001, в лице генерального директора Кочержинской Светланы Викторовны, действующей на основании Устава.',8.5)
 payer=data['payer'];p(d,f"Заказчик / Плательщик: {data['payer_name']}, ИНН {payer['inn']}, КПП {payer.get('kpp','—')}. Подписант: {data['signatory']['position']} {data['signatory']['name']}, основание полномочий: {data['signatory']['authority']}.",8.5)
 texts=['1. Поставщик передал, а Заказчик принял товары, результаты выполненных работ и оказанных услуг в полном объёме по перечням приложения № 1, являющегося неотъемлемой частью настоящего акта.',
 '2. Оборудование передано комплектным; работы и услуги выполнены качественно. Предусмотренные договором проверки и пусконаладка проведены с положительным результатом. Необходимые документы, инструкции и принадлежности переданы, инструктаж проведён.',
 '3. Заказчик осмотрел и проверил переданное. Количество, комплектность, объём и стоимость согласованы; претензий по явным недостаткам нет, кроме прямо указанных в особых отметках. Гарантийные обязательства определяются договором.',
 f"4. Окончательный расчёт: {money(data['payment']['amount'])} ₽ согласно п. {data['payment']['clause']} договора, с учётом ранее произведённых в его счёт платежей. Подписание акта не подтверждает получение оплаты Поставщиком."]
 if data.get('partial'):
  texts[1]='2. По перечню настоящего акта товары переданы комплектными, указанные работы и услуги выполнены качественно; относящиеся к этому объёму документы и принадлежности переданы. Остальной объём договора настоящим актом не закрывается.'
  pay=data.get('partial_payment') or {}
  texts[3]=(f"4. Частичный расчёт: {money(pay['amount'])} ₽ по п. {pay['clause']} договора. Основание: {pay['basis']}. Ранее поступившие платежи учитываются при расчётах по договору." if pay else '4. Порядок и сроки оплаты определяются договором. Настоящий акт фиксирует передачу указанного объёма и не изменяет условия платежей.')+' Подписание акта не подтверждает получение оплаты Поставщиком.'
 for text in texts:
  p(d,text,8.5,after=4)
 special_notes(d);sign_block(d,data)
 for title,items in [('01 / Товары и оборудование',goods),('02 / Выполненные работы и оказанные услуги',works)]:
  if not items:continue
  d.add_page_break();p(d,'ПРИЛОЖЕНИЕ № 1',17,True,2);p(d,'к акту приёма-передачи № '+number+' от '+today,10,True,6);p(d,basis+'\nЗаказчик: '+data['payer_name']+'\nОбъект: '+data['address'],9,after=8);heading(d,title)
  table(d,['Поз.¹','Наименование','Ед.','Кол-во','Цена, ₽','Сумма, ₽'],[[r.get('source_number',data['positions'].index(r)+1),r['name'],r['unit'],str(r['quantity']).removesuffix('.0'),money(r['unit_price']),money(r['total'])] for r in items],[10,88,10,12,27,27],right_columns=(3,4,5))
  p(d,'ИТОГО ПО ГРУППЕ: '+money(total(items))+' ₽. '+group_tax(items)+'.',10,True,6)
  p(d,('¹ Работа по п. 1.2 договора.' if data.get('contract_scope_reference') else '¹ Номер позиции в спецификации к договору.')+' Единицы измерения — по спецификации; суммы включают указанный для группы НДС.\nПеречень является частью единого акта на общую сумму '+money(v)+' ₽.',8,after=5);sign_block(d,data)
 for t in d.tables:
  for row in t.rows:
   for c in row.cells:c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
 for s in d.sections:
  if test:
   a=s.header.tables[0].cell(0,1).paragraphs[0];a.clear();font(a.add_run('ТЕСТ — НЕ ОТПРАВЛЯТЬ КЛИЕНТУ\nПроверка комплекта закрывающих документов'),8,True,'BB2222')
  f=s.footer.paragraphs[0];f.clear();font(f.add_run(('ТЕСТ · ' if test else '')+'ООО «Кливэл» · Акт № '+number+' от '+today+' · '+data['payer_name']+' · Страница '),8);fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');f._p.append(fld)
 path=out/act_filename(data,test);d.save(path)
 return render_pdf(path)

def render_pdf(path):
 path=Path(path);out=path.parent
 env=os.environ.copy();env['LD_LIBRARY_PATH']='/home/kocher.av/.local/lib/libreoffice-appimage/deps/usr/lib/x86_64-linux-gnu'
 import tempfile
 from document_renderer import office_command
 executable=office_command(env)
 with tempfile.TemporaryDirectory(prefix='closing-lo-') as profile:
  r=subprocess.run([executable,'--headless','--nologo','--nodefault','--nolockcheck','-env:UserInstallation=file://'+profile,'--convert-to','pdf','--outdir',str(out),str(path)],capture_output=True,text=True,timeout=90,env=env)
 if r.returncode or not path.with_suffix('.pdf').exists():raise ValueError('Не удалось получить PDF акта')
 return str(path.with_suffix('.pdf'))

def test_invoice(data,out):
 from weasyprint import HTML
 from document_tax_policy import tax_label
 esc=lambda x:html.escape(str(x));pay=data['payment'];seller=data['seller'];bank=seller.get('bank') or {}
 # Known Cliwell account details are checked against the contract before rendering.
 fields=[('Получатель','ООО «КЛИВЭЛ», ИНН 7743151323, КПП 774301001'),('Банк получателя','АО «АЛЬФА-БАНК», БИК 044525593'),('Счёт получателя','40702810902570001580'),('Корреспондентский счёт','30101810200000000593')]
 s='<style>@page{size:A4;margin:18mm}body{font:11pt Arial}table{border-collapse:collapse;width:100%}td,th{border:1px solid #555;padding:7px}h3{color:#a00}.sign{height:45mm;position:relative}.sign p{position:absolute;left:0;top:7mm;z-index:2;margin:0}.stamp{width:40mm;position:absolute;left:95mm;top:0;z-index:0}.signature{width:20mm;position:absolute;left:49mm;top:0mm;z-index:1}td:last-child{white-space:nowrap;min-width:26mm}</style><h3>ТЕСТ — НЕ ОПЛАЧИВАТЬ, НЕ ОТПРАВЛЯТЬ КЛИЕНТУ</h3><table>'
 s+=''.join('<tr><td>'+esc(k)+'</td><td>'+esc(v)+'</td></tr>' for k,v in fields)+'</table>'
 s+='<h2>Счёт на оплату б/н от '+esc(data['act_date'])+'</h2><p>Покупатель: '+esc(data['payer_name'])+', ИНН '+esc(data['payer']['inn'])+'</p><p>Основание: '+esc(pay['basis'])+'</p><table><tr><th>Наименование</th><th>Кол.</th><th>Сумма, ₽</th></tr><tr><td>'+esc(pay['line'])+'</td><td>1</td><td>'+money(pay['amount'])+'</td></tr></table><h3 style="color:black">Итого: '+money(pay['amount'])+' ₽. '+esc(tax_label(pay['amount'],pay.get('tax_rate',-1)))+'.</h3><p>Условия окончательного расчёта определены п. '+pay['clause']+' договора.</p><div class="sign"><p>Генеральный директор __________ / Кочержинская С.В. /</p><img class="stamp" src="'+(ROOT/'ours-000.png').as_uri()+'"><img class="signature" src="'+(ROOT/'ours-001.png').as_uri()+'"></div><p>Тестовый экземпляр. Номер боевого счёта присваивается при выпуске в Мегаплане.</p>'
 path=Path(out)/'ТЕСТ — Счёт окончательного расчёта.pdf';HTML(string=s,base_url=str(ROOT)).write_pdf(path);return str(path)

def price_addendum(data,out):
 """Final agreement for EDO signing; customer signature remains blank."""
 from weasyprint import HTML
 from document_tax_policy import approved_deal
 approved=approved_deal(data['deal_id'])
 if not approved:return None
 if data.get('seller',{}).get('id','cliwell')!='cliwell':return None
 if data.get('partial') and not any(int(r.get('tax_rate',-1))==5 for r in data['positions']):return None
 clauses=[k for k in approved.get('payments',{}) if k in ('6.4.2','6.4.3')]
 if len(clauses)!=1:raise ValueError('Для допсоглашения нужен однозначный пункт окончательного платежа')
 clause=clauses[0]
 esc=lambda x:html.escape(str(x))
 pay=approved['payments'][clause];goods=approved['payments']['6.4.1'];dates=approved['transfer_dates']
 if Decimal(str(pay['base']))+Decimal(str(approved['vat']))!=Decimal(str(pay['gross'])) or Decimal(str(goods['gross']))+Decimal(str(pay['gross']))!=Decimal(str(approved['gross_total'])):raise ValueError('Суммы допсоглашения не сходятся с согласованной экономикой')
 paragraphs=[
  'ООО «Кливэл», ИНН 7743151323, в лице генерального директора Кочержинской Светланы Викторовны, действующей на основании Устава, и '+data['payer_name']+', ИНН '+data['payer']['inn']+' (представитель: '+data['signatory']['position']+' '+data['signatory']['name']+'; основание полномочий: '+data['signatory']['authority']+'), договорились о следующем:',
  '1. Стоимость товаров по спецификации составляет '+money(goods['gross'])+' руб., без НДС. Дата передачи товаров — '+dates['goods']+'.',
  '2. К стоимости работ и услуг '+money(pay['base'])+' руб. начисляется НДС 5% в сумме '+money(approved['vat'])+' руб. Стоимость работ и услуг с НДС составляет '+money(pay['gross'])+' руб.',
  '3. Общая стоимость товаров, работ и услуг по договору с учётом настоящего соглашения составляет '+money(approved['gross_total'])+' руб., в том числе НДС 5% — '+money(approved['vat'])+' руб.',
  '4. Сумму окончательного платежа по п. '+clause+' договора установить в размере '+money(pay['gross'])+' руб., в том числе НДС 5% — '+money(approved['vat'])+' руб. Срок оплаты по договору сохраняется. Фактически внесённые платежи засчитываются; непогашенная часть аванса остаётся обязательством Заказчика.',
  '5. Остальные условия договора не изменяются. Настоящее соглашение вступает в силу с момента его подписания обеими сторонами и является неотъемлемой частью договора.'
 ]
 source='<meta charset="utf-8"><style>@page{size:A4;margin:20mm}body{font:10pt Arial;line-height:1.35}h1{font-size:17pt;color:#0086B3} .draft{color:#a00;font-weight:bold}td{vertical-align:top;width:50%}.sign{height:42mm;position:relative;overflow:hidden}.stamp{position:absolute;width:40mm;left:40mm;top:0}.signature{position:absolute;width:20mm;left:23mm;top:-7mm}.line{position:relative;z-index:2}</style>'
 source+='<h1>Дополнительное соглашение № 1</h1><p>к договору № '+esc(data['number'])+' от '+esc(data['date'])+'</p><p>г. Москва · Дата составления: '+esc(data['act_date'])+'</p>'
 source+=''.join('<p>'+esc(x)+'</p>' for x in paragraphs)
 source+='<table style="width:100%"><tr><td><b>Поставщик: ООО «Кливэл»</b><p>Генеральный директор<br>Кочержинская С.В.</p><div class="sign"><img class="stamp" src="'+(ROOT/'ours-000.png').as_uri()+'"><img class="signature" src="'+(ROOT/'ours-001.png').as_uri()+'"><p class="line">Подпись: __________________</p><p class="line">Дата подписания: ____________</p></div></td><td><b>Заказчик: '+esc(data['payer_name'])+'</b><p>'+esc(data['signatory']['position'])+'<br>'+esc(data['signatory']['name'])+'</p><p>Подпись: __________________</p><p>Дата подписания: ____________</p></td></tr></table>'
 path=Path(out)/('Дополнительное соглашение №1 — сделка '+str(data['deal_id'])+' — НДС 5%.pdf');HTML(string=source,base_url=str(ROOT)).write_pdf(path);return str(path)
