"""Read CRM comments and recover a known attachment's local publication receipt.

Never creates/deletes/updates a remote object. Missing or ambiguous evidence never
clears an uncertainty marker. Only the exact saved file ID is accepted.
"""
import argparse
import json
import os
import tempfile
from registry_transaction import locked
from megaplan_api import MegaplanAPI

def find_comment(api,deal_id,file_id):
    if not file_id: raise ValueError('Не сохранён ID загруженного файла; нужна ручная сверка')
    comments=api._call('GET',f'/deal/{deal_id}/comments').get('data') or []
    matches={str(c['id']) for c in comments if c.get('id') and any(str(x.get('id'))==str(file_id) for x in c.get('attaches') or [])}
    if len(matches)!=1: raise ValueError('Однозначное подтверждение публикации не найдено; запись не изменена')
    return matches.pop()

def installation(deal_id,api):
    import installation_workflow as iw
    with locked(iw.DB+'.publication'):
        db=iw.connect()
        try:
            row=db.execute('SELECT * FROM installations WHERE deal_id=?',(str(deal_id),)).fetchone()
            if not row or row['publication_create_state']!='uncertain': raise ValueError('Неопределённая публикация не найдена')
            comment=find_comment(api,deal_id,row['megaplan_file_id'])
            db.execute("UPDATE installations SET megaplan_comment_id=?,publication_create_state='confirmed' WHERE deal_id=?",(comment,str(deal_id)))
            iw.enqueue_publication(db,deal_id)
            iw.audit(db,deal_id,'publication',comment,'reconciled','operator',{'file_id':row['megaplan_file_id']})
            db.commit(); return {'ok':True,'comment_id':comment,'file_id':row['megaplan_file_id']}
        finally:db.close()

def economics(deal_id,api):
    import deal_browser as browser
    with locked(browser.ECONOMICS_ATTACHMENTS_PATH):
        with open(browser.ECONOMICS_ATTACHMENTS_PATH,encoding='utf-8') as file: registry=json.load(file)
        row=registry.get(str(deal_id)) or {}
        if not row.get('pending_comment_create'):raise ValueError('Неопределённая публикация не найдена')
        file_id=row.get('pending_file_id'); comment=find_comment(api,deal_id,file_id)
        registry[str(deal_id)]={'comment_id':comment,'file_id':file_id,'reconciled':True}
        fd,tmp=tempfile.mkstemp(prefix='.reconcile-',dir=os.path.dirname(browser.ECONOMICS_ATTACHMENTS_PATH))
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as file:
                json.dump(registry,file,ensure_ascii=False,allow_nan=False); file.flush(); os.fsync(file.fileno())
            os.replace(tmp,browser.ECONOMICS_ATTACHMENTS_PATH)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return {'ok':True,'comment_id':comment,'file_id':file_id}

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('kind',choices=('installation','economics')); parser.add_argument('deal_id'); args=parser.parse_args()
    try:print(json.dumps(globals()[args.kind](args.deal_id,MegaplanAPI())))
    except Exception as exc:print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False)); raise SystemExit(1)
