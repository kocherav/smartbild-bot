"""Run interactively on the server; never echo credentials or pass them as arguments."""
import getpass,imaplib,json,os,tempfile,socket,ssl
from pathlib import Path
host=input('IMAP-сервер [imap.yandex.ru]: ').strip() or 'imap.yandex.ru'
password=getpass.getpass('Пароль приложения для kav@innsis.ru (ввод скрыт): ').strip()
if not password:
 print('Пароль не введён. Повторите запуск и вставьте пароль приложения.');raise SystemExit(1)
stage='соединение с сервером'
try:
 with imaplib.IMAP4_SSL(host,993,timeout=30) as c:
  stage='вход в ящик kav@innsis.ru'
  c.login('kav@innsis.ru',password)
  stage='открытие папки Входящие'
  status,_=c.select('INBOX',readonly=True)
  if status!='OK':raise RuntimeError('Вход выполнен, но папка INBOX недоступна')
except Exception as exc:
 print('Этап: '+stage+'. Пароль не сохранён.')
 if isinstance(exc,imaplib.IMAP4.error):
  detail=str(exc).replace(password,'[скрыто]')
  detail=''.join(ch for ch in detail if ch.isprintable())[:600]
  print('Ответ IMAP: '+detail)
  print('Проверьте: пароль приложения создан именно для kav@innsis.ru; включены IMAP и «Пароли приложений и OAuth-токены».')
 elif isinstance(exc,(TimeoutError,socket.timeout)):
  print('Сервер не ответил вовремя. Это ошибка соединения, пароль не проверен.')
 elif isinstance(exc,ssl.SSLError):
  print('Не удалось установить защищённое TLS-соединение. Пароль не проверен.')
 elif isinstance(exc,OSError):
  print('Ошибка сети/DNS. Пароль не проверен. Тип: '+type(exc).__name__)
 else:
  print('Ошибка проверки ящика: '+type(exc).__name__)
 raise SystemExit(1)
folder=Path('/home/kocher.av/.config/innsis-finance');folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o700)
fd,tmp=tempfile.mkstemp(dir=folder,prefix='.kav-')
with os.fdopen(fd,'w') as f:json.dump({'host':host,'port':993,'username':'kav@innsis.ru','password':password},f)
os.chmod(tmp,0o600);os.replace(tmp,folder/'kav-mail.json')
print('Доступ проверен и сохранён. Можно сообщить ассистенту: почта kav подключена.')
