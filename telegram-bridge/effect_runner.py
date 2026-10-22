"""Exactly-once local dispatch with honest handling of uncertain remote effects."""
import hashlib
from workflow_runtime import Conflict, dump


def execute(store, actor, scenario, intent, target, payload, action, fresh=lambda: True):
    if not fresh():
        return {'ok': False, 'stale': True, 'error': 'Действие устарело: открыт другой запрос. Запись не начиналась.'}
    # Same confirmed intent and same action data have one receipt, including
    # retries after a timeout. A deliberately new preview supplies a new intent.
    key = str(intent) + ':' + hashlib.sha256(dump({'target': target, 'payload': payload}).encode()).hexdigest()
    try:
        operation = store.create(str(actor), scenario, key, target, payload)
    except Conflict as exc:
        return {'ok':False,'no_effect':True,'error':str(exc)}
    if operation['status'] == 'succeeded':
        return {**operation['receipt'], '_operation_id': operation['id'], '_reused': True}
    if operation['status'] not in ('draft', 'confirmed'):
        return {'ok': False, 'uncertain': operation['status'] in ('running', 'uncertain'),
                '_operation_id': operation['id'],
                'error': 'Повторная запись остановлена. Предыдущая операция уже запущена или требует сверки результата; повторно создавать её нельзя.'}
    try:
        store.confirm(operation['id'], operation['revision'])
    except Conflict:
        return {'ok': False, '_operation_id': operation['id'], 'error': 'Операция уже принята другим обработчиком.'}
    if not store.claim(operation['id']):
        return {'ok': False, '_operation_id': operation['id'], 'error': 'Операция уже выполняется.'}
    if not fresh():
        result = {'ok': False, 'stale': True, 'error': 'Контекст изменён до отправки запроса. Запись не начиналась.'}
        store.finish(operation['id'], result, status='failed')
        return result
    try:
        result = action()
        if not isinstance(result, dict):
            raise ValueError('Operation handler returned no structured receipt')
    except Exception as exc:
        # Error message may contain a request URL/token; persist only its type.
        result = {'ok': False, 'uncertain': True, '_operation_id': operation['id'],
                  'error': 'Не получено подтверждение результата. Нужна сверка; автоматический повтор записи запрещён.'}
        store.finish(operation['id'], result, status='uncertain', error=type(exc).__name__)
        return result
    if result.get('ok'):
        store.finish(operation['id'], result)
    else:
        # Legacy wrappers collapse validation, timeout and remote errors into
        # ok=False. Until they expose an explicit no-effect flag, be conservative.
        status = 'failed' if result.get('no_effect') else 'uncertain'
        store.finish(operation['id'], result, status=status)
        if status == 'uncertain':
            result = {**result, 'uncertain': True,
                      'error': str(result.get('error') or 'Нет подтверждения') + ' Повтор записи заблокирован до сверки результата.'}
    return {**result, '_operation_id': operation['id']}
