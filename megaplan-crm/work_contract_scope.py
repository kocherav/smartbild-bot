"""Explicit reviewed mapping for a work contract without a specification table."""
import json,re,hashlib,copy
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).parent/'contracts'
def clause(text,number):
 m=re.search(r'(?m)^\s*'+re.escape(number)+r'\.\s*(.+?)(?=\n\s*\d+\.|\Z)',text,re.S)
 if not m:raise ValueError('Не найден пункт '+number+' договора подряда')
 return ' '.join(m[1].split())
def is_work_contract(text):return bool(re.search(r'ДОГОВОР\s+ПОДРЯДА\s*№',text,re.I))
def apply(data,text):
 if not is_work_contract(text):return data
 source=ROOT/(str(data['deal_id'])+'-source.json');approved=json.loads(source.read_text()).get('work_scope') if source.exists() else None
 if not approved or approved['text_sha256']!=hashlib.sha256(text.encode()).hexdigest():raise ValueError('Для договора подряда нужна подтверждённая привязка предмета к позиции сделки')
 rows=data['positions']
 if len(rows)!=1 or str(rows[0]['id'])!=approved['row_id'] or rows[0]['name'] not in (approved['original_name'],approved['document_name']):raise ValueError('Позиция договора подряда изменилась')
 result=copy.deepcopy(data);result['positions'][0]['name']=approved['document_name'];result['contract_scope_reference']='Предмет работ — п. 1.2 договора.'
 result['deadline_condition']=clause(text,'1.4')
 return result

def validate(text,positions):
 if len(positions)!=1:raise ValueError('Без спецификации подтверждается только одна договорная работа')
 row=positions[0];subject=clause(text,'1.2');price=clause(text,'3.1')
 amount=re.search(r'составляет\s+([\d\s]+[,.]\d{2})',price,re.I)
 norm=lambda v:' '.join(str(v).casefold().split())
 if not amount or row.get('kind')!='work' or Decimal(str(row['quantity']))!=1 or norm(row['name']) not in norm(subject):raise ValueError('Предмет или объём работы не совпадает с договором подряда')
 expected=Decimal(re.sub(r'\s+','',amount[1]).replace(',','.'))
 if expected!=Decimal(str(row['total'])):raise ValueError('Стоимость работы не совпадает с договором подряда')
 return positions
