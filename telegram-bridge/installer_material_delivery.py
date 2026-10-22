"""Price-free material files, authorized against current installer assignment."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile


def authorize(installation_db, account_db, chat, deal_id, test_chat=''):
    if not str(deal_id).isdigit():
        raise PermissionError('Объект не выбран')
    with sqlite3.connect(Path(account_db).resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT profile FROM accounts WHERE chat=?', (str(chat),)).fetchone()
    profile = str(row[0]) if row else None
    if not profile and test_chat and str(chat) == str(test_chat):
        profile = '1000142'  # existing, explicitly configured test account
    with sqlite3.connect(Path(installation_db).resolve().as_uri() + '?mode=ro', uri=True) as db:
        target = db.execute('SELECT installer_ref,status FROM installations WHERE deal_id=?', (str(deal_id),)).fetchone()
    if not profile or not target or str(target[0]) != profile or target[1] not in ('transferred', 'in_progress', 'review'):
        raise PermissionError('Материалы доступны только по переданным вам действующим объектам')


def build(chat, deal_id, test_chat=''):
    base = Path(__file__).resolve().parent
    crm = base.parent / 'megaplan-crm'
    authorize(crm/'installations.sqlite3', base/'installer_accounts.sqlite3', chat, deal_id, test_chat)
    sys.path.insert(0, str(crm))
    from installation_materials import export
    folder = Path(tempfile.mkdtemp(prefix='installer-materials-'))
    try:
        xlsx = folder/f'Материалы сделки {deal_id}.xlsx'
        pdf = folder/f'Материалы сделки {deal_id}.pdf'
        result = export(deal_id, xlsx, pdf_output=pdf)
        authorize(crm/'installations.sqlite3', base/'installer_accounts.sqlite3', chat, deal_id, test_chat)
        return {'ok': True, 'xlsx': str(xlsx), 'pdf': str(pdf), 'positions': result['positions'],
                'confirmed_positions': result['confirmed_positions']}
    except Exception:
        import shutil
        shutil.rmtree(folder)
        raise


if __name__ == '__main__':
    try:
        req = json.load(sys.stdin)
        print(json.dumps(build(req['chat'], req['deal_id'], req.get('test_chat', '')), ensure_ascii=False))
    except PermissionError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
    except Exception:
        print(json.dumps({'ok': False, 'error': 'Не удалось сформировать материалы. Сообщите руководителю; данные учёта не изменены.'}, ensure_ascii=False))
