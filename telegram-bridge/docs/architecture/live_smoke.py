"""Explicit read-only connector smoke check. No sends, orders or CRM writes."""
import datetime,json,sys,time
from pathlib import Path
BASE=Path('/home/kocher.av')

def main():
    import imaplib,urllib.request,subprocess,tempfile
    for directory in ('telegram-bridge','megaplan-crm','hogart-scraper','daichi-scraper'):sys.path.insert(0,str(BASE/directory))
    import bridge
    env=bridge.load_env();results=[]
    def probe(name,action):
        started=time.monotonic()
        try:
            action();results.append({'module':name,'ok':True,'seconds':round(time.monotonic()-started,2)})
        except Exception as exc:
            results.append({'module':name,'ok':False,'error_type':type(exc).__name__,
                            'http_status':getattr(exc,'status',getattr(exc,'code',None)),
                            'seconds':round(time.monotonic()-started,2)})
    def telegram():
        with urllib.request.urlopen('https://api.telegram.org/bot'+env['TELEGRAM_BOT_TOKEN']+'/getMe',timeout=20) as response:
            assert json.load(response).get('ok')
    def crm():
        from megaplan_api import MegaplanAPI
        api=MegaplanAPI();deal=api._call('GET','/deal/899')['data'];assert str(deal['id'])=='899'
        assert isinstance(api._call('GET','/deal/899/allFiles',params={'limit':100})['data'],list)
    def mail():
        with imaplib.IMAP4_SSL(env.get('IMAP_HOST') or 'imap.yandex.ru',int(env.get('IMAP_PORT') or 993),timeout=20) as client:
            client.login(env.get('IMAP_USERNAME') or env['SMTP_USERNAME'],env.get('IMAP_PASSWORD') or env['SMTP_PASSWORD'])
            assert client.select('INBOX',readonly=True)[0]=='OK'
    def smtp():
        import smtplib
        host=env.get('SMTP_HOST') or 'smtp.yandex.ru';port=int(env.get('SMTP_PORT') or 465)
        cls=smtplib.SMTP_SSL if port==465 else smtplib.SMTP
        with cls(host,port,timeout=20) as client:
            if port!=465:client.starttls()
            client.login(env['SMTP_USERNAME'],env['SMTP_PASSWORD'])
            assert client.noop()[0]==250
    def drive():
        run=subprocess.run(['rclone','lsjson','onedrive:SmartBild/Сделки','--stat','--retries','1','--timeout','15s','--contimeout','5s'],capture_output=True,text=True,timeout=40)
        if run.returncode:raise RuntimeError('remote listing failed')
        assert json.loads(run.stdout).get('IsDir')
    def hogart():
        from hogart_api import HogartAPI
        assert HogartAPI().search_products(keyword='Daikin',limit=1) is not None
    def daichi():
        from daichi_api import DaichiAPI
        assert DaichiAPI().get_stores() is not None
    def queue_access():
        root=BASE/'hogart-scraper/finance/data'
        json.loads((root/'review_registry.json').read_text())
        with tempfile.TemporaryFile(dir=root) as file:file.write(b'permission probe')
        with (root/'review_registry.lock').open('a'):pass
    for name,action in [('Telegram API',telegram),('Megaplan read',crm),('IMAP info read-only',mail),('SMTP login without sending',smtp),('OneDrive listing',drive),('Hogart catalog read',hogart),('Daichi catalog read',daichi),('Shared queue permissions',queue_access)]:probe(name,action)
    print(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':results,'business_writes':0},ensure_ascii=False))
    return 0 if all(r['ok'] for r in results) else 1
if __name__=='__main__':raise SystemExit(main())
