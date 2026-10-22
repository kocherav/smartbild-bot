"""Explicit creation instructions survive separate attachment/model turns."""
import json,re
import human_intents

def explicit(text):
    intent=human_intents.classify(text)
    return bool(intent and intent.name==human_intents.CREATE_DEAL)

def initial_state(text):
    spec={'user_request':text,'allow_new_client':False}
    intent=human_intents.classify(text)
    if intent and intent.name==human_intents.CREATE_DEAL and intent.target:
        spec['client_name']=intent.target
    return {'deal_creation_active':True,'deal_creation_request':text,
            'deal_create_spec':spec,'deal_creation_items':None,'deal_creation_result':None,
            'deal_creation_economics_path':None,'deal_create_clients':None,
            'current_deal_id':None,'contract_deal_id':None,'pending':'deal_create_items'}

def awaiting_file(text):
    return bool(re.search(r'(?:сч[её]т[а-я]*|файл[а-я]*|спецификаци[а-я]*)',text,re.I))

def is_current(state, request, path):
    return bool(
        state.get('deal_creation_active')
        and state.get('deal_creation_request') == request
        and state.get('deal_creation_source_path') == path
    )

def prompt(state,path,extracted):
    request=state.get('deal_creation_request') or (state.get('deal_create_spec') or {}).get('user_request') or ''
    return ('\n\n[ЗАДАНИЕ ВЛАДЕЛЬЦА ДЛЯ ЭТОГО ВЛОЖЕНИЯ]\n'+request+
        '\n[ТЕКУЩИЙ ФАЙЛ]\n'+str(path)+'\n[ТЕКСТ ТЕКУЩЕГО ФАЙЛА]\n'+
        (extracted or 'Текст автоматически не извлечён. Прочитай именно текущий файл средствами чтения документов; старые файлы не использовать.')+
        '\n[ПРАВИЛА СОЗДАНИЯ]\nЭто создание новой сделки, не разнесение закупки. '
        'Клиент и цена продажи из задания имеют приоритет. Плательщик и заказчик в счёте поставщика '
        'не являются клиентом новой сделки и не определяют нашу организацию-продавца. '
        'Бери только заказанные пользователем категории позиций; не добавляй остальные строки счёта молча. '
        'Сохрани количество, единицу, артикул, закупочную цену после скидки отдельно от цены продажи. '
        'Сохрани требования о договоре и размере оплаты. Не спрашивай повторно уже указанные данные. '
        'Не утверждай, что CRM или документы созданы: сейчас готовится черновик. '
        'Верни CREATE_MEGAPLAN_DEAL_BEGIN/END для штатной проверки. '
        'Если неизвестны существенные условия, задай только вопрос об этих условиях.\n'+
        '[СОХРАНЁННЫЕ ПОЛЯ]\n'+json.dumps(state.get('deal_create_spec') or {},ensure_ascii=False))
