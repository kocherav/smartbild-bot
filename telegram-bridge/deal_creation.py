"""Deterministic final review; extraction must never itself authorize a CRM write."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def number(value, label, positive=False):
    try:
        result = Decimal(str(value).replace('\u00a0', '').replace(' ', '').replace(',', '.'))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f'{label}: требуется число') from None
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(f'{label}: недопустимое значение')
    return result


def review(spec):
    from document_tax_policy import creation_rate
    expected=creation_rate(spec)
    if expected!=spec.get("tax_mode"):raise ValueError("Налоговый режим не соответствует текущей политике продавца. Обновите предварительный просмотр.")
    if not spec.get('client_id') and not spec.get('allow_new_client'):
        raise ValueError('Сначала выберите карточку клиента либо подтвердите создание нового клиента.')
    if not spec.get('client_name') or not spec.get('description'):
        raise ValueError('Не заполнены клиент или название сделки.')
    if spec.get('tax_mode') not in ('none', '22', '5'):
        raise ValueError('Выберите режим НДС.')
    rows = spec.get('items') or []
    if not rows:
        raise ValueError('Пришлите спецификацию с позициями.')
    total = Decimal('0')
    lines = []
    document_discount = number(spec.get('discount_pct', 0), 'Скидка документа')
    if document_discount > 100:
        raise ValueError('Скидка не может превышать 100%.')
    for index, row in enumerate(rows, 1):
        if not row.get('name'):
            raise ValueError(f'Строка {index}: отсутствует название.')
        qty = number(row.get('qty'), f'Строка {index}, количество', positive=True)
        price = number(row.get('unit_price'), f'Строка {index}, цена за единицу')
        discount = number(row.get('discount_pct', document_discount), f'Строка {index}, скидка')
        if discount > 100:
            raise ValueError(f'Строка {index}: скидка больше 100%.')
        if discount and row.get('price_basis', spec.get('price_basis')) != 'net':
            raise ValueError(f'Строка {index}: указана скидка, но не подтверждена итоговая цена за единицу после скидки. Укажите net-цену; повторно скидка не применяется.')
        # Imported unit_price is the approved net sale price. Never silently
        # apply an additional discount or add installation during the commit.
        if row.get('include_install') or row.get('line_length_m') or row.get('install') or row.get('freon_line'):
            raise ValueError('Дополнительные работы нужно включить отдельными строками до подтверждения.')
        for key in ('cost_material', 'cost_work'):
            if row.get(key) is not None:
                number(row[key], f'Строка {index}, {key}')
        amount = (qty * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        source_total = row.get('line_total', row.get('total'))
        if source_total is not None and abs(number(source_total, f'Строка {index}, итог') - amount) > Decimal('0.01'):
            raise ValueError(f'Строка {index}: количество × итоговая цена не совпадает с суммой строки. Проверьте скидку и цену за единицу.')
        total += amount
        lines.append(f'{index}. {row["name"]} — {qty:g} × {price:,.2f} = {amount:,.2f} ₽')
    client = f'ID {spec["client_id"]}' if spec.get('client_id') else 'НОВАЯ карточка'
    tax = {'none': 'без НДС', '22': 'НДС 22%', '5': 'НДС 5%'}[spec['tax_mode']]
    if spec['tax_mode'] != 'none':
        from document_tax_policy import tax_label
        tax = tax_label(total, int(spec['tax_mode'])) + '; НДС включён в цены позиций'
    return (f'Проверьте новую сделку: {spec["description"]}\n'
            f'Клиент: {spec["client_name"]} ({client})\nРежим: {tax}\n\n' +
            '\n'.join(lines) + f'\n\nИтого по позициям: {total:,.2f} ₽.\n'
            'Данные ещё не записаны. Создание — только кнопкой подтверждения.')
