"""Persist manually reviewed mail evidence; all originals/version hashes retained."""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parent
D=json.loads((root/'evidence/kav/documents.json').read_text())
spec=[
('7743949955','1794','0ba0f88b',65028000),
('7736192449','22427744/SA','40f4a5d7',6037475),
('7703675923','DAER-014914','f3529bc9',3036400),
('7717632694','45547','bff63ef9',1875249),
('7717632694','52475','aac8e1f5',4636320),
('7728336506','208096','6b4591cf',1540991),
('4004022080','1952','bbe5f185',22404000),
('775114176346','1695','3f03a60f',4236000),
('7717632694','60665','9b99a366',8826840),
('7719228261','УТ-12795','bed520c8',4892264),
('7728336506','208164','4da9702d',426450),
('9717003403','5399/МА15421','3e678530',40688000),
('7719618222','6856','547e430e',1638300),
('6623097295','793','a99a4476',175500),
('615518680653','42','d5a1306f',3500000),
('7743250099','У65 835','296660fd',4460000),
('7811504932','83280','c6bb1bdb',4182552)]
result=[]
for inn,num,prefix,cents in spec:
 hits=[d for d in D if Path(d['path']).name.startswith(prefix)];assert len(hits)==1;d=hits[0]
 buyer='7743151323' if inn in ['775114176346','615518680653'] else '7743926877'
 assert inn in d['text'] and buyer in d['text']
 refs=[]
 for p in (root/'evidence/kav').glob('*_*.json'):
  msg=json.loads(p.read_text())
  if any(x['path']==d['path'] for x in msg.get('files',[])):refs.append({'folder':msg['folder'],'uid':msg['uid'],'subject':msg['Subject'],'date':msg['Date']})
 note=f'Найден в kav@innsis.ru: счёт {num}, {cents/100:.2f} руб.; ИНН продавца и покупателя сверены. Источник '+Path(d['path']).name[:12]+'.'
 if num=='52475':note+=' Вместе с присланным пользователем №52550 на 17475,36 = 63838,56. Почтовая версия №52550 на 18723,60 к этому платежу не подходит.'
 if num=='1695':note+=' Исправленная версия на 42360; перенос позиций подтверждён письмом 66481. Ранняя версия 31791 не использована.'
 if num=='УТ-12795':note+=' Выбрана версия 48922,64, а не ранняя 20090,87.'
 if num=='1794':note+=' Письмо INBOX UID66512: Ленинградский проспект, вл.8, ЖК Слава. Объект установлен; соответствие конкретной сделке ещё не подтверждено.'
 if num=='22427744/SA':note+=' Выбрана версия 60374,75 по точной сумме платежа; другие версии 46946,57 и 60648,88 сохранены отдельно.'
 if num=='42':note+=' В документе указан объект: Подвойского 5/19. Конкретная сделка/раздел работ ещё не установлены.'
 result.append({'supplier_inn':inn,'buyer_inn':buyer,'number':num,'amount_cents':cents,'source':d['path'],'messages':refs,'note':note})
(root/'evidence/kav/reviewed.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('reviewed',len(result))
