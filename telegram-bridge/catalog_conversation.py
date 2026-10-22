"""A catalog conversation owns its followups; pending documents cannot capture them."""
import re,time,json
import invoice_tasks
PRODUCT=re.compile(r'(?i)кондиционер|сплит|инвертор|модел[ьи]|haier|хайер|хаер|хэйер|хогарт|hogart|casarte')
INTENT=re.compile(r'(?i)найди|поищи|посмотр|покажи|подбер|проверь|дешев|стоимост|розниц|закупк|налич|сколько\s+стоит')
FOLLOWUP=re.compile(r'(?i)^(?:а\s+|и\s+|тогда\s+|ещ[её]\s+)?(?:посмотр|покажи|найди|поищи|подбер|дешев|дороже|другие|не\s*инвертор|инвертор|только|без\s+|с\s+достав|какой\s+остаток)')
INVOICE=re.compile(r'(?i)сч[её]т|накладн|разнес|разнос|оплат[аиуы]|сделк')
PROPOSAL=re.compile(r'(?i)\bкп\b|коммерческ\w*\s+предложени\w*')
def proposal_requested(state):
 return bool(PROPOSAL.search(state.get('catalog_request',''))) or any(item.get('role')=='user' and PROPOSAL.search(item.get('text','')) for item in state.get('catalog_history',[]))
def explicit(text):
 text=str(text or '')
 return bool(PRODUCT.search(text) and INTENT.search(text) and not INVOICE.search(text))
def is_turn(text,state):
 if explicit(text):return True
 # Short answers belong to the foreground task, even without product keywords.
 # Never send an ambiguous continuation into the unrelated persistent model session.
 return bool(str(text or '').strip() and state.get('foreground')=='catalog' and time.time()-state.get('catalog_at',0)<86400 and not INVOICE.search(text) and not text.strip().startswith('/'))
def begin(chat,text):
 def start(s):
  if s.get('foreground')!='catalog' or time.time()-s.get('catalog_at',0)>=86400:
   s['catalog_history']=[];s.pop('catalog_request',None);s.pop('catalog_inputs',None)
  if 'catalog_inputs' not in s:
   s['catalog_inputs']=[item['text'] for item in s.get('catalog_history',[]) if item.get('role')=='user']
  s['catalog_inputs'].append(text)
  s['catalog_inputs']=s['catalog_inputs'][-32:]
  if not s.get('catalog_request'):
   s['catalog_request']=next((item['text'] for item in s.get('catalog_history',[]) if item.get('role')=='user'),text)
  if explicit(text) and PROPOSAL.search(text):s['catalog_request']=text
  s.update(foreground='catalog',paused=True,catalog_at=time.time())
  s.setdefault('catalog_history',[]).append({'role':'user','text':text});s['catalog_history']=s['catalog_history'][-8:]
 return invoice_tasks.change(chat,start)[0]
def finish(chat,text):
 def done(s):
  s.setdefault('catalog_history',[]).append({'role':'assistant','text':text[:16000]});s['catalog_history']=s['catalog_history'][-8:]
 return invoice_tasks.change(chat,done)[0]
def prompt(state):
 return ('[ТЕКУЩАЯ ЗАДАЧА: ПОДБОР ТОВАРОВ]\nОбрабатывай только запрос каталога и его уточнения ниже. '
 'Запрашивай свежие цены и наличие через доступные поисковые команды. Уточнение меняет только названные пользователем условия; сохраняй адресата, количества, монтаж и трассы. Не переноси клиента или комплектацию из других задач. '
 'Бренд, выбранный тобой, не является ограничением пользователя. Для самых дешёвых без указанного бренда сравни доступные бренды Hogart и Daichi, оба типа инвертора, если тип не задан. Сравни полную стоимость комплекта нужных количеств одного бренда. Не утверждай глобальный минимум по неполному поиску. '
 'Ошибка или тайм-аут поиска не означают отсутствие товара. Не предлагай менять требования из-за технического сбоя. '
 'Не возвращайся к счетам и не выполняй финансовые действия: это отдельная приостановленная задача. '
 'Данные цены/остатка из истории требуют новой проверки.\n'+
 ('Пользователь запросил КП: после свежего поиска сформируй BUILD_KP_BEGIN/BUILD_KP_END по общим правилам КП. '
  'Это разрешённая подготовка PDF и Excel экономики. Сохрани адресата, бренд, мощности, количества, монтаж и суммарные метры дополнительной трассы по каждой позиции. '
  'Запрет финансовых действий относится к счетам и записям в CRM, а не к подготовке КП.\n' if proposal_requested(state) else '')+
 '[ИСХОДНЫЙ ЗАПРОС; ПОСЛЕДУЮЩИЕ УТОЧНЕНИЯ ИМЕЮТ ПРИОРИТЕТ]\n'+state.get('catalog_request','')+'\n'+
 '[УСЛОВИЯ ПОЛЬЗОВАТЕЛЯ ПО ПОРЯДКУ; ВЫБОР БОТА НЕ МЕНЯЕТ УСЛОВИЯ]\n'+json.dumps(state.get('catalog_inputs',[]),ensure_ascii=False)+'\n'+
 json.dumps(state.get('catalog_history',[]),ensure_ascii=False))

def search_failure(supplier,results):
 if any(not isinstance(r,dict) or r.get('error') or r.get('ok') is False for r in results):
  return f'Не удалось проверить каталог {supplier}: поиск завершился технической ошибкой или превысил время ожидания. Наличие и цены не подтверждены; это не означает, что товара нет. Условия подбора сохранены.'
 return None

def guard(reply,state=None):
 if not isinstance(reply,str):return reply
 allowed={'HOGART_SEARCH','DAICHI_SEARCH'}
 if proposal_requested(state or {}):allowed.update({'BUILD_KP','BUILD_KP_BEGIN','BUILD_KP_END'})
 markers=re.findall(r'(?m)^\s*([A-Z][A-Z_]+)(?::|\s|$)',reply)
 if any(m not in allowed for m in markers):
  return 'Для ответа по подбору нужна свежая проверка каталога.'
 return reply
