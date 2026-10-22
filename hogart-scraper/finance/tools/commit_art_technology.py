import sys,json,hashlib
sys.path[:0]=['/home/kocher.av/.report-venv/lib/python3.14/site-packages','/home/kocher.av/hogart-scraper/finance','/home/kocher.av/telegram-bridge']
from post_confirmed import *
import statement_document_context as context
A=MegaplanAPI();D=ROOT/'evidence/art_technology';mp=ROOT/'evidence/payment_correction/supplier_mapping.json';mapping=json.loads(mp.read_text());inn='7709895139'
if not mapping.get(inn,{}).get('contractor_id'):
 assert not json.loads((D/'search_7709895139.json').read_text())['data'] and not json.loads((D/'search_АРТ ТЕХНОЛОГИЯ.json').read_text())['data']
 assert mapping.get(inn,{}).get('state')!='creating'
 payload={'contentType':'ContractorCompany','name':'ООО «АРТ ТЕХНОЛОГИЯ»','type':{'contentType':'ContractorType','id':'5'},'description':'ИНН7709895139; КПП774301001. Реквизиты сверены по счетам11-197 от24.06.2026 и11-293 от03.09.2026, загруженным владельцем07.10.2026.','contactInfo':[{'contentType':'Address','type':{'contentType':'AddressType','id':'1'},'value':'125212, Москва, ул. Адмирала Макарова, д.6Б, к.1, офис АПАРТ №8'}]}
 mapping[inn]={'state':'creating','payload':payload};atomic(mp,mapping);result=wait_budget(A._call,'POST','/contractorCompany',json_body=payload);atomic(D/'supplier_created.json',result);mapping[inn].update(state='created',contractor_id=result['data']['id']);atomic(mp,mapping)
current=wait_budget(A._call,'GET','/contractorCompany/'+mapping[inn]['contractor_id']);assert current['data']['id']==mapping[inn]['contractor_id'];atomic(D/'supplier_verified.json',current)
rows=json.loads((ROOT/'reports/ledger.json').read_text());q=json.loads((ROOT/'evidence/finish_all/owner_questions.json').read_text());allocpath=ROOT/'evidence/deep_review/reviewed_allocations.json';alloc=json.loads(allocpath.read_text());new={}
for number,amount,filename,oldnum in [('11-197',39803720,'1791363095-Счет_на_оплату___11_197_от_24_июня_2026_г.pdf',30),('11-293',2119750,'1791363025-Счет_на_оплату___11_293_от_3_сентября_2026_г.pdf',31)]:
 source=ROOT.parent/'incoming'/filename
 import subprocess
 txt=subprocess.check_output(['pdftotext','-layout',str(source),'-'],text=True)
 intake=context.match_document(str(source),txt,'289622514');assert intake and intake['invoice']==number and intake['amount_cents']==amount
 r=next(x for x in rows if x['inn']==inn and x['amount_cents']==amount and number in x.get('references',''))
 assert r['company']=='КЛИВЭЛ'
 basis=('Счёт11-197:13радиаторовRoyalThermoPianoForte500/VDR/10секций и4Tower200/18секций с крепежом, клапанами и автоматикой. Уникальное совпадение состава и количеств с актуальной спецификацией отопления1этажаJetCar857. Цвет и фактическая марка части арматуры заменены относительноКП (SilverSatin вместоNoir); это фактическая закупка, а не основание менять клиентскоеКП. ' if number=='11-197' else 'Счёт11-293:дозакупка одногоRoyalThermoPianoForte500/SilverSatin/VDR/10секций, крепёж, нижнее подключение и доставка. Точная модель и цвет совпадают с предыдущим11-197 для отопления1этажаJetCar857; по совокупности состава и поставщика оплата отнесена на857. Дополнительная закупка не изменяет количество13в клиентскомКП автоматически. ')
 basis+='В обоих документах покупательКЛИВЭЛ ИНН7743151323, поставщик7709895139; сумма и номер совпали с банком. Только оплата; SecondarySum=0. Отгрузка/приёмка отдельно.'
 x={'confirmed':True,'reviewed_by':'assistant','inn':inn,'number':number,'amount_cents':amount,'source':basis,'invoice_source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'allocations':[{'deal_id':'857','project':'JetCar — отопление 1 этажа','amount_cents':amount}],'cleared_flags':[],'old_question_number':oldnum};alloc[r['id']]=x;new[r['id']]=x
atomic(allocpath,alloc);atomic(D/'reviewed_allocations.json',new);print('prepared',len(new),'supplier',mapping[inn]['contractor_id'],flush=True)
