"""Configure only the owner's Mini App menu and deliver the requested dashboard."""
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import credentials

def call(method, payload):
    token,_=credentials()
    req=urllib.request.Request('https://api.telegram.org/bot'+token+'/'+method,
        data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:
        result=json.load(r)
    if not result.get('ok'):raise RuntimeError('Telegram request failed: '+method)
    return result['result']

if __name__=='__main__':
    _,allowed=credentials();owner=next(iter(allowed));url='https://claude.smartbild.su/deal-dashboard/'
    backup=ROOT/'data/bot-menu-before.json'
    if not backup.exists():
        backup.write_text(json.dumps(call('getChatMenuButton',{'chat_id':owner}),ensure_ascii=False));backup.chmod(0o600)
    button={'type':'web_app','text':'Пульт сделок','web_app':{'url':url}}
    call('setChatMenuButton',{'chat_id':owner,'menu_button':button})
    if call('getChatMenuButton',{'chat_id':owner})!=button:raise RuntimeError('Menu verification failed')
    result=call('sendMessage',{'chat_id':owner,
        'text':'Пульт сделок запущен. Нажмите кнопку ниже или постоянную кнопку «Пульт сделок» рядом с полем ввода.\n\nВнутри — реальные данные Мегаплана, графики денег и закупок, фильтры, карточки сделок и сохраняемые чеклисты.\n\nДля текущего года выберите «Созданы в 2026». В CRM также есть старые сделки в активных статусах.\n\nДля входа на компьютере откройте дашборд здесь и нажмите «Вход на компьютере».',
        'reply_markup':{'inline_keyboard':[[{'text':'📊 Открыть пульт сделок','web_app':{'url':url}}]]}})
    report={'menu_verified':True,'message_id':result['message_id'],'url':url}
    (ROOT/'evidence/bot-delivery.json').write_text(json.dumps(report,ensure_ascii=False))
    print(json.dumps(report,ensure_ascii=False))
