"""Owner decisions via the existing bot polling process, never a second poller.

CLI: decision_channel.py ask CODE STAGE TEXT | list
Replies in Telegram are consumed by bridge before all business handlers.
"""
import argparse
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

from workflow_runtime import Store

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / 'workflow_runtime.sqlite3'
CODE = re.compile(r'^\s*(Q-[A-Z0-9-]+)\s*[:\s]\s*(.+)$', re.I | re.S)


def consume(message, owner_chat_id, store):
    if str((message.get('chat') or {}).get('id')) != str(owner_chat_id):
        return None
    if str((message.get('from') or {}).get('id')) != str(owner_chat_id):
        return None
    text = str(message.get('text') or '').strip()
    if not text:
        return None
    reply = message.get('reply_to_message') or {}
    explicit = CODE.match(text)
    return store.answer(str(owner_chat_id), reply.get('message_id'),
                        explicit.group(2) if explicit else text, message.get('message_id'),
                        code=explicit.group(1).upper() if explicit else None)


def ask(store, owner, code, stage, text, sender):
    if not re.fullmatch(r'Q-[A-Z0-9-]+', code):
        raise ValueError('Use a stable question code Q-...')
    question = store.question(str(owner), code, text, stage)
    if question.get('telegram_message_id'):
        return question
    response = sender({'chat_id': str(owner),
        'text': f'Вопрос по плану SmartBild [{code}], этап {stage}\n\n{text}\n\nОтветьте на это сообщение через «Ответить» либо напишите «{code}: ваш ответ». Ответ сохранится к этому вопросу; выбранная сделка не изменится.',
        'reply_markup': json.dumps({'force_reply': True, 'selective': True})})
    if not response.get('ok') or not (response.get('result') or {}).get('message_id'):
        raise RuntimeError('Telegram did not confirm question delivery')
    store.question_sent(question['id'], response['result']['message_id'])
    return next(q for q in store.questions(str(owner)) if q['id'] == question['id'])


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('ask')
    p.add_argument('code'); p.add_argument('stage'); p.add_argument('text')
    sub.add_parser('list')
    args = parser.parse_args()
    env = {}
    for line in (BASE / '.env').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1); env[key.strip()] = value.strip()
    owner = env['TELEGRAM_CHAT_ID']
    store = Store(DB_PATH)
    if args.action == 'list':
        print(json.dumps(store.questions(owner), ensure_ascii=False, indent=2))
        return
    def sender(params):
        url = 'https://api.telegram.org/bot' + env['TELEGRAM_BOT_TOKEN'] + '/sendMessage'
        try:
            with urllib.request.urlopen(url, data=urllib.parse.urlencode(params).encode(), timeout=15) as response:
                return json.load(response)
        except Exception as exc:
            # Never expose URL containing the bot token.
            raise RuntimeError('Telegram question delivery failed: ' + type(exc).__name__) from None
    result = ask(store, owner, args.code, args.stage, args.text, sender)
    print(json.dumps({'id': result['id'], 'code': result['code'], 'status': result['status'],
                      'telegram_message_id': result['telegram_message_id']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
