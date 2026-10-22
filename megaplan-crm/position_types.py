"""Single product/service boundary. Explicit CRM document type is authoritative.

The native type/category of cloned offers is immutable; the explicit custom field
is shared by CRM, proposals, contracts and shipments. Costs never define type. Name rules
are only defaults for new/legacy untyped rows, not overrides of stored CRM types.
"""
import re

FIELD = 'Category1000045CustomFieldTipPozitsiiDlyaDokumentov'
GOODS = 'Товар / материал / оборудование'
WORK = 'Работа / услуга'

MATERIAL_WORDS = ('труб','кабел','изоляц','креп','кронштейн','расходн','хладагент',
                  'фреон','дренаж','короб','канал','материал','лоток','провод',
                  'наконечник','гильз','стяжк','перемычк','плата','рама')
# Match actions, not adjective substrings (монтажная, под опрессовку).
ACTION = re.compile(r'^(?:(?:дополнительные|дополнительная|комплексные|комплексная|алмазное|стандартный|комплекс|услуги по)\s+)?'
                    r'(?:монтаж|демонтаж|установка|прокладка|бурение|сборка|огнезаделка|заземление|'
                    r'электроизмерения|доставка|погрузка|разгрузка|пусконаладка|пусконаладочные работы|'
                    r'монтажные работы|монтажные и пусконаладочные работы|демонтажные работы|проектные работы|альпработы|высотные работы|работа|работы|услуги|вакуумирование|опрессовка|'
                    r'подключение|оконцевание|перевальцовка|восстановление|заправка|испытания|'
                    r'настройка|ремонт|техническое обслуживание|обслуживание|устройство|разработка|адаптация|испытание|инженерное сопровождение|защита зон производства работ|внутренняя коммутация|организация высотных работ|погрузочно-разгрузочные работы)\b')


def name_kind(name):
    low = re.sub(r'\s+', ' ', str(name or '').casefold().replace('ё','е')).strip()
    # A compound supplied item is not silently converted into a service.
    if re.match(r'^установка (?:приточно-вытяжная|приточная|вытяжная|вентиляционная|канальная)\b', low):
        return 'equipment'
    if ACTION.search(low):
        return 'work'
    if any(word in low for word in MATERIAL_WORDS):
        return 'material'
    return 'equipment'


def crm_type(row):
    offer = row.get('offer') or {}
    explicit = offer.get(FIELD) or row.get(FIELD)
    if explicit:
        normalized=re.sub(r'\s*/\s*','/',str(explicit).strip().casefold())
        if normalized in ('работа/услуга','работы/услуги','работа','работы','услуга','услуги','work','service'): return 'service'
        if normalized in ('товар/материал/оборудование','товар','товары','материал','материалы','оборудование','product','goods','material','equipment'): return 'product'
        raise ValueError(f"Позиция {row.get('id','')}: в поле «Тип позиции для документов» выберите «{GOODS}» или «{WORK}» в карточке номенклатуры Мегаплана и обновите сделку.")
    value = offer.get('type') or row.get('type')
    if value is not None and value not in ('product','service'):
        raise ValueError(f"Позиция {row.get('id','')}: неизвестный тип {value!r}. Укажите в карточке товара Мегаплана тип «Товар» или «Услуга» и обновите сделку.")
    return value


def classify_position(row):
    name = row.get('name') or (row.get('offer') or {}).get('name') or ''
    stored = crm_type(row)
    if stored == 'service':
        return 'work'
    if stored == 'product':
        if not ((row.get('offer') or {}).get(FIELD) or row.get(FIELD)) and name_kind(name) == 'work':
            raise ValueError(f"Позиция {row.get('id','')} «{name}»: старый тип «Товар» противоречит названию работы. Заполните поле «Тип позиции для документов» в карточке номенклатуры Мегаплана и обновите сделку.")
        return 'material' if any(w in name.casefold() for w in MATERIAL_WORDS) else 'equipment'
    return name_kind(name)


def new_offer_type(name, kind=None):
    if kind is not None and kind not in ('equipment','material','goods','work','product','service'):
        raise ValueError('Неизвестный тип новой позиции: '+str(kind))
    return 'service' if (kind or name_kind(name)) in ('work','service') else 'product'


def resolve(row, override=None):
    kind = classify_position(row)
    if override is None:
        return kind
    if override not in ('equipment','material','work'):
        raise ValueError('Неизвестный тип позиции: '+str(override))
    stored = crm_type(row)
    if stored and (override == 'work') != (stored == 'service'):
        raise ValueError(f"Тип позиции {row.get('id','')} в документе противоречит Мегаплану. Исправьте тип в карточке товара и обновите сделку.")
    return override


def category_for(api, offer_type):
    cache=getattr(api,'_position_categories',None)
    if cache is None:
        rows=api._call('GET','/offerCategory')['data']
        cache={}
        for item in rows:
            if item.get('type') not in cache: cache[item.get('type')]=str(item['id'])
        api._position_categories=cache
    if offer_type not in cache:
        raise ValueError('В Мегаплане не настроена категория номенклатуры '+offer_type)
    return {'contentType':'OfferCategory','id':cache[offer_type]}


def prepare_offer(api, offer_id, kind=None):
    """Persist type once when adding an existing catalog item to a new deal."""
    offer=api._call('GET','/offer/'+str(offer_id))['data']
    existing=offer.get(FIELD)
    if existing:
        chosen=crm_type({'offer':offer})
        if kind is not None and chosen!=new_offer_type(offer.get('name'),kind):
            raise ValueError('Подтверждённый тип номенклатуры противоречит новой позиции: '+str(offer_id))
        return chosen
    chosen=new_offer_type(offer.get('name'),kind) if kind is not None or offer.get('type')!='service' else 'service'
    label=WORK if chosen=='service' else GOODS
    api._call('POST','/offer/'+str(offer_id),json_body={'contentType':'Offer',FIELD:label})
    checked=api._call('GET','/offer/'+str(offer_id))['data']
    if checked.get(FIELD)!=label:
        raise ValueError('Тип позиции не сохранён; проверьте карточку номенклатуры '+str(offer_id))
    return chosen
