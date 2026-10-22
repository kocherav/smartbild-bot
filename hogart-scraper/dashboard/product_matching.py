"""Deterministic equivalence and vetoes. Never use fuzzy string similarity."""
import re
import unicodedata
VERSION='rules-2'

def canonical(value):
 s=unicodedata.normalize('NFKC',str(value or '')).casefold().replace('ё','е')
 s=re.sub(r'\bавв\b','abb',s)
 # PDF line wrapping can split this literal protocol suffix inside an SKU.
 s=re.sub(r'(?<=-)da\s+li(?=2(?:-|\b))','dali',s)
 s=re.sub(r'(?<=\d),(?=\d)', '.', s)
 s=re.sub(r'(?<=\d)\s*[хx×]\s*(?=\d)','x',s)
 s=re.sub(r'(?<=\d)\s+(?=(?:мм|см|м|шт|ма|ma|ка|ka|а|a|в|v|w|вт)\b)','',s)
 s=re.sub(r'(?<!\d)[.,;:]|[.,;:](?!\d)',' ',s)
 s=re.sub(r'\b[сc]\s*(\d+(?:\.\d+)?)\b',r'c\1',s)
 s=re.sub(r'\b([bcdс]\d+(?:\.\d+)?)\s*[аa]\b',r'\1',s)
 s=re.sub(r'\bс(?=\d)', 'c', s)
 return re.sub(r'\s+',' ',s).strip()

def attributes(value):
 s=canonical(value)
 attrs={}
 def put(key,pattern):
  found=set(re.findall(pattern,s))
  if found:attrs[key]=found
 put('модель автомата',r'\b(?:ds|s)\d{3}[a-z]*\b')
 put('характеристика и ток',r'\b[bcd]\d+(?:\.\d+)?\b')
 put('полюса',r'\b(\d+)\s*(?:-?полюс\w*|p)\b')
 put('диаметр',r'\bд\s*\.?\s*(\d+(?:\.\d+)?)\s*мм')
 put('номинальный диаметр',r'(?:ø|⌀|дн|ду)\s*(\d+(?:\.\d+)?)')
 put('давление',r'\b(?:pn|ру)\s*(\d+)')
 put('угол отвода',r'\b(?:отвод|угольник)[^\n]*?(45|90)(?:°|гр)')
 put('размер наконечника',r'\b(?:тмл|ншп)\s*(\d+)')
 put('экранирование',r'\b[fu]/utp\b')
 put('размеры',r'\b\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)+(?![\d.x])')
 put('класс защиты',r'\bip\d+\b')
 put('тип и ток утечки',r'\b(?:ac|a)\d+(?=\b)')
 put('цвет',r'\b(?:черный|белый|серый|black|white|silver)\b')
 if 'цвет' in attrs:attrs['цвет']={dict(black='черный',white='белый',silver='серебристый').get(v,v) for v in attrs['цвет']}
 put('производитель',r'\b(?:abb|dkc|schneider|legrand|arlight|diora)\b')
 put('маркировка изделия',r'\b(?:hdr|icl|knx|dm|fs-bt|frm|sct|arpv|sl-arc)[a-z0-9]*(?:-[a-z0-9]+)+\b')
 put('артикул ABB',r'\b(?:2csr|1sda)[a-z0-9]+\b')
 put('номинальный ток',r'(?<![\w.])(\d+(?:\.\d+)?)\s*[аa]\b')
 for unit in ('мм','см','м','вт','w','v','в','ma','ма','ka','ка'):
  put('значение '+unit,r'(?<![\w.])(\d+(?:\.\d+)?)\s*'+unit+r'\b')
 return attrs

def compare(left,right):
 a,b=canonical(left),canonical(right)
 x,y=attributes(left),attributes(right)
 conflicts=[f'{k}: {", ".join(sorted(x[k]))} / {", ".join(sorted(y[k]))}' for k in x.keys()&y.keys() if x[k]!=y[k]]
 # F/UTP vs U/UTP and decimal values remain material even without units.
 da=set(re.findall(r'\b\d+\.\d+\b',a));db=set(re.findall(r'\b\d+\.\d+\b',b))
 if da and db and da!=db:conflicts.append('Различаются дробные числовые характеристики')
 if conflicts:return {'same':False,'basis':'Различаются характеристики','conflicts':sorted(conflicts)}
 if a and a==b:return {'same':True,'basis':'Совпадает после нормализации записи','conflicts':[]}
 # A deliberately narrow family rule: same ABB model, curve/current and leakage code.
 models=x.get('модель автомата',set())
 if 'abb' in a.split() and 'abb' in b.split() and len(models)==1 and models==y.get('модель автомата') and x.get('характеристика и ток') and x.get('характеристика и ток')==y.get('характеристика и ток'):
  model=next(iter(models)); poles={'s201':'1','s203':'3','ds201':'2'}.get(model)
  if poles and any(v and v!={poles} for v in (x.get('полюса'),y.get('полюса'))):return {'same':False,'basis':'Число полюсов противоречит модели','conflicts':['Число полюсов противоречит модели']}
  leakage=x.get('тип и ток утечки')
  if poles and (not model.startswith('ds') or leakage and leakage==y.get('тип и ток утечки')):
   return {'same':True,'basis':'Совпадают ABB, модель, характеристика и ток'+(' и защита от утечки' if model.startswith('ds') else ''),'conflicts':[]}
 return {'same':False,'basis':'Нужно проверить соответствие названий','conflicts':[]}
