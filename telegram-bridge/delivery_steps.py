"""Per-channel durable receipts; retry must not resend already delivered files."""
from effect_runner import execute


def deliver(store, bundle_id, fingerprint, steps):
    with store.connect(transaction=True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS delivery_bundles(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL)')
        db.execute('INSERT OR IGNORE INTO delivery_bundles VALUES(?,?)',(str(bundle_id),fingerprint))
        old=db.execute('SELECT fingerprint FROM delivery_bundles WHERE id=?',(str(bundle_id),)).fetchone()[0]
        if old!=fingerprint:
            return {'ok':False,'error':'Версия комплекта изменилась после начала доставки. Нельзя смешивать старый договор с новым счётом; нужна проверка и явная отправка нового комплекта.'}
    results = []
    for name, action in steps:
        def invoke(action=action):
            value = action()
            if value is False:
                return {'ok': False, 'error': 'Канал не подтвердил доставку'}
            return {'ok': True}
        result = execute(store, 'document-delivery', name, bundle_id,
                         {'bundle': bundle_id}, {'fingerprint': fingerprint}, invoke)
        results.append({'step': name, **result})
    failed = [r for r in results if not r.get('ok')]
    if failed:
        return {'ok': False, 'steps': results,
                'error': '; '.join(f'Этап {r["step"]}: {r.get("error")}' for r in failed) +
                         '. Уже доставленные части повторно не отправляются.'}
    return {'ok': True, 'steps': results}
