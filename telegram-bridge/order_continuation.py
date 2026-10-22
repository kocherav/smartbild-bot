"""Keep the requested documents attached to the deal creation intent."""
import re

def requested(spec):
    text=str(spec.get('user_request') or '').casefold().replace('ё','е')
    return 'договор' in text and 'счет' in text and bool(re.search(r'100\s*(?:%|процент)',text))

LABELS={'дата':'date','дата договора':'date','адрес':'address','адрес поставки':'address','плательщик':'payer',
        'подписант':'name','фио подписанта':'name','должность':'position','основание':'authority','предмет':'subject'}
def parse(text):
    result={}
    for line in text.splitlines():
        key,sep,value=line.partition(':')
        key=re.sub(r'^\s*\d+[.)]?\s*','',key).strip().casefold()
        if sep and key in LABELS and value.strip():result[LABELS[key]]=value.strip()
    return result

def question(result):
    missing=result.get('missing') or []
    labels={'ФИО подписанта':'Подписант','должность подписанта':'Должность','основание полномочий подписанта':'Основание'}
    lines=[labels.get(m,m) for m in missing]
    candidates='; '.join(p['name']+' (ID '+str(p['id'])+')' for p in result.get('payers',[]))
    return ('Для договора и счёта по сделке №'+str(result['deal_id'])+' нужны только следующие данные. Ответьте одним сообщением, каждое поле с новой строки:\n\n'+
            '\n'.join(x+': …' for x in lines)+
            ('\n\nПлательщики клиента в базе: '+candidates if candidates else '')+
            '\n\nПосле заполнения подготовлю и пришлю договор и счёт на 100%. Сделка повторно не создаётся. Для продолжения сохранённого задания: «Продолжить комплект».')


def recovery_hint(outcome):
    if outcome.get('requires_reconciliation') or outcome.get('uncertain'):
        return ('\nЗадание сохранено. Нужна техническая сверка результата предыдущей операции; '
                'команда «Продолжить комплект» до сверки её не восстановит. Успешные этапы сохранены.')
    return '\nЗадание сохранено. Напишите «Продолжить комплект»: успешные этапы не повторяются.'
