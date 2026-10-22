"""Owner-approved additional Telegram accounts for the existing installer.

Registration callbacks deliberately do not use workflow views: a request must
never expire the manager's invoice/report confirmation.
"""
import os
import secrets
import sqlite3
import time
import json

DB=os.path.join(os.path.dirname(__file__),'installer_accounts.sqlite3')
PROFILE='1000142'
GUIDE='''Добро пожаловать, Сергей! Кабинет связан с вашим профилем. Объекты, принятые отчёты и история взаиморасчётов уже доступны.

1. «🛠 Мои монтажи» → выберите объект. Здесь адрес, назначенный контакт, проект и актуальная монтажная ведомость. «📦 Материалы по счетам» выдаёт PDF для телефона и Excel для компьютера без цен. Количества по подтверждённым привязкам не означают доставку; возможные совпадения и свободные остатки отмечены отдельно. Если данных нет, запросите их у руководителя.

2. Отчёт по одному объекту: «🧰 Новый отчёт». Напишите, что выполнено: название работы, количество и единицы, например «Проложено 20 м трассы». Прикрепите фото, видео или документы (каждый файл до 20 МБ). Затем «✅ Все материалы отправлены». Отправляйте выполнение за этот период, а не накопительный итог повторно.

3. Отчёт по нескольким объектам: в главном меню «📤 Сборный отчёт» → основной PDF. Если есть строки «По таблице», дождитесь запроса Excel .xlsx, отправьте таблицы и нажмите «✅ Все файлы загружены». Проверьте объекты, исправьте ошибочные привязки, разберите вопросы и нажмите «📤 Передать руководителю». Основной Excel сейчас относится к одной выбранной сделке.

4. Материалы, доставка, такелаж и дополнительные расходы указываются отдельными строками: объект, назначение, сумма. Не придумывайте доли другой работы. Руководитель решит, куда отнести расход. Если ответ неизвестен, оставьте вопрос руководителю.

5. Отправка отчёта — не приёмка и не выплата. Руководитель проверит его; после принятия обновятся ведомость, накопительное выполнение и начисления. При возврате прочитайте причину. Не отправляйте уже принятый отчёт повторно ради исправления — обратитесь к руководителю.

6. «📊 Мои взаиморасчёты» — отчёты, начисления и учтённые выплаты. Для новых безналичных выплат зачёт составляет 94%, для наличных — 100%; исторические выплаты не пересчитываются. Выплаты регистрирует руководитель.

7. «📚 Утверждённые отчёты» — ранее принятые отчёты. «📜 История монтажей» — архивные объекты. Кнопка «❓ Помощь» повторно открывает эту инструкцию.

Меню находится внизу, подтверждения — под соответствующим сообщением. Если бот сообщил об ошибке, сохраните сообщение и обратитесь к руководителю; не подтверждайте одну операцию много раз. Тестовый аккаунт руководителя остаётся подключённым; история общая, диалоги раздельные.'''

def connect():
    db=sqlite3.connect(DB,timeout=15);db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,chat TEXT UNIQUE,name TEXT,username TEXT,status TEXT,notified INTEGER DEFAULT 0,created REAL,approved_by TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS accounts(chat TEXT PRIMARY KEY,profile TEXT,approved_by TEXT,created REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS invites(token TEXT PRIMARY KEY,expires REAL,used_by TEXT)')
    db.commit();os.chmod(DB,0o600);return db

def members():
    if not os.path.exists(DB):return set()
    with connect() as db:return {r['chat'] for r in db.execute('SELECT chat FROM accounts WHERE profile=?',(PROFILE,))}

def invitation():
    token=secrets.token_urlsafe(24)
    with connect() as db:db.execute('INSERT INTO invites VALUES(?,?,NULL)',(token,time.time()+7*86400))
    return 'join_'+token

def request(user,payload=''):
    chat=str(user['id'])
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if payload:
            row=db.execute('SELECT * FROM invites WHERE token=?',(payload.removeprefix('join_'),)).fetchone()
            if not row or row['expires']<time.time() or row['used_by'] not in (None,chat):raise ValueError('Приглашение недействительно. Попросите руководителя прислать новое.')
            db.execute('UPDATE invites SET used_by=? WHERE token=?',(chat,payload.removeprefix('join_')))
        name=' '.join(str(user.get(k) or '') for k in ('first_name','last_name')).strip()
        db.execute("INSERT OR IGNORE INTO requests(id,chat,name,username,status,created) VALUES(?,?,?,?,'pending',?)",(secrets.token_hex(12),chat,name,str(user.get('username') or ''),time.time()))
        return dict(db.execute('SELECT * FROM requests WHERE chat=?',(chat,)).fetchone())

def decide(request_id,actor,owner,approve):
    if str(actor)!=str(owner):raise ValueError('Подтверждение доступно только руководителю')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone()
        if not row:raise ValueError('Запрос не найден')
        if row['status']!='pending':return dict(row),False
        status='approved' if approve else 'rejected'
        db.execute('UPDATE requests SET status=?,approved_by=? WHERE id=?',(status,str(actor),request_id))
        if approve:db.execute('INSERT OR IGNORE INTO accounts VALUES(?,?,?,?)',(row['chat'],PROFILE,str(actor),time.time()))
        return {**dict(row),'status':status},True

def handle(update,owner,known,api,menu):
    callback=update.get('callback_query') or {};data=str(callback.get('data') or '')
    def send(chat,text,markup=None):
        args={'chat_id':chat,'text':text}
        if markup:args['reply_markup']=json.dumps(markup,ensure_ascii=False)
        return api('sendMessage',args).get('ok',False)
    if data.startswith('join:'):
        actor=str((callback.get('from') or {}).get('id'))
        private=str(((callback.get('message') or {}).get('chat') or {}).get('id'))
        if actor!=str(owner) or private!=str(owner):
            api('answerCallbackQuery',{'callback_query_id':callback['id'],'text':'Только руководитель может подтвердить доступ.'});return True
        parts=data.split(':')
        if len(parts)!=3 or parts[1] not in ('yes','no'):return True
        row,changed=decide(parts[2],actor,owner,parts[1]=='yes')
        api('answerCallbackQuery',{'callback_query_id':callback['id'],'text':'Решение сохранено' if changed else 'Решение уже сохранено'})
        if row['status']=='approved':
            delivered=send(row['chat'],GUIDE,menu)
            send(owner,'Аккаунт '+row['name']+' (Telegram ID '+row['chat']+') подключён к профилю Сергея Деревянко. Тестовый доступ сохранён. '+('Инструкция отправлена.' if delivered else 'Доставка инструкции не подтверждена; она доступна через «Помощь».'))
        elif changed:send(row['chat'],'Руководитель не подтвердил подключение. Доступ к объектам не выдан.')
        return True
    msg=update.get('message') or {};user=msg.get('from') or {};chat=str((msg.get('chat') or {}).get('id') or '')
    if chat!=str(user.get('id')):return False
    text=str(msg.get('text') or '').strip()
    if chat in known:
        if text.startswith('/start join_'):
            send(chat,GUIDE,menu);return True
        return False
    if text!='/start' and not text.startswith('/start join_'):return False
    try:row=request(user,text.split(' ',1)[1] if ' ' in text else '')
    except ValueError as exc:send(chat,str(exc));return True
    send(chat,'Здравствуйте! Запрос на подключение направлен руководителю. После подтверждения здесь появятся кабинет и инструкция. Пока доступ к объектам закрыт.' if row['status']=='pending' else 'Запрос уже рассмотрен. Свяжитесь с руководителем.')
    if row['status']=='pending' and not row['notified']:
        markup={'inline_keyboard':[[{'text':'✅ Подключить к Сергею','callback_data':'join:yes:'+row['id']}],[{'text':'❌ Отклонить','callback_data':'join:no:'+row['id']}]]}
        if send(owner,'Запрос доступа к кабинету Сергея Деревянко.\nИмя Telegram: '+row['name']+'\nUsername: '+('@'+row['username'] if row['username'] else 'нет')+'\nTelegram ID: '+chat+'\n\nУбедитесь, что это Сергей. Имя аккаунта само по себе не подтверждает личность. Подключить дополнительно, сохранив тестовый аккаунт?',markup):
            with connect() as db:db.execute('UPDATE requests SET notified=1 WHERE id=?',(row['id'],))
    return True
